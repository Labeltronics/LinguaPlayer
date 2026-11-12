"""Internet television UI; network/import work never blocks the Qt event loop."""
import datetime,json,time
from pathlib import Path
from PySide6.QtCore import Qt,QThread,Signal,QTimer
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLineEdit,QPushButton,QLabel,QComboBox,QTableWidget,QTableWidgetItem,QFileDialog,QInputDialog,QCheckBox,QAbstractItemView)
from internet_tv import API,catalog,parse_m3u,parse_xmltv,filter_rows,adult
from web_transfer import read_document,open_http
from parental_control import ParentalLock

class TVLoad(QThread):
    loaded=Signal(object);failed=Signal(str)
    def __init__(self,kind,source=''):super().__init__();self.kind=kind;self.source=source
    def run(self):
        try:
            if self.kind=='catalog':
                channels=json.loads(read_document(API+'channels.json',limit=32*1024*1024)[0])
                if self.isInterruptionRequested():return
                streams=json.loads(read_document(API+'streams.json',limit=32*1024*1024)[0]);rows=catalog(channels,streams)
            elif self.kind=='playlist':
                if self.source.startswith(('http://','https://')):text,base=read_document(self.source,limit=32*1024*1024)
                else:
                    p=Path(self.source)
                    if p.stat().st_size>32*1024*1024:raise ValueError('Playlist terlalu besar.')
                    text=p.read_text(encoding='utf-8-sig');base=''
                rows=parse_m3u(text,base)
            elif self.kind=='epg':
                if self.source.startswith(('http://','https://')):
                    with open_http(self.source) as response:data=response.read(32*1024*1024+1)
                else:
                    p=Path(self.source)
                    if p.stat().st_size>32*1024*1024:raise ValueError('EPG terlalu besar.')
                    data=p.read_bytes()
                rows=parse_xmltv(data)
            else:raise ValueError('Jenis impor tidak dikenal.')
            if not self.isInterruptionRequested():self.loaded.emit(rows)
        except Exception:self.failed.emit('Katalog/impor gagal. Periksa koneksi, URL atau format file; alamat privat tidak dicatat.')

class InternetTV(QDialog):
    def __init__(self,owner):
        super().__init__(owner,Qt.Window);self.owner=owner;self.caption_job=None;self.caption_label=None;self.caption_queue=[];self.caption_clock=0.;self.job=None;self.preview=None;self.rows=[];self.visible_rows=[];self.programs=[];self.favorites=set();self.lock=ParentalLock(owner.settings if owner.storage_enabled and not owner.private_session else None)
        if self.lock.settings:
            try:self.favorites=set(json.loads(owner.settings.value('iptv/favorites','[]')))
            except (ValueError,TypeError):pass
        self.setWindowTitle('Cyber80 • Internet TV / IPTV');self.resize(1050,700);box=QVBoxLayout(self);row=QHBoxLayout();box.addLayout(row)
        for text,fn in [('Muat katalog dunia gratis',lambda:self.load('catalog')),('Impor M3U file',self.import_file),('Impor M3U URL',self.import_url),('Impor XMLTV / EPG',self.import_epg),('Batalkan impor',self.cancel)]:
            b=QPushButton(text);b.clicked.connect(fn);row.addWidget(b)
        row=QHBoxLayout();box.addLayout(row);self.search=QLineEdit();self.search.setPlaceholderText('Cari saluran / judul acara dari XMLTV yang diimpor');row.addWidget(self.search,1);self.country=QComboBox();self.country.addItem('Semua negara','');row.addWidget(self.country);self.category=QComboBox();self.category.addItem('Semua kategori','');row.addWidget(self.category);self.fav_only=QCheckBox('Favorit');row.addWidget(self.fav_only)
        self.table=QTableWidget(0,4);self.table.setHorizontalHeaderLabels(['Saluran','Negara','Kategori','Sekarang / berikutnya']);self.table.setEditTriggers(QAbstractItemView.NoEditTriggers);self.table.setSelectionBehavior(QAbstractItemView.SelectRows);self.table.setSelectionMode(QAbstractItemView.SingleSelection);self.table.horizontalHeader().setStretchLastSection(True);self.table.doubleClicked.connect(self.play);box.addWidget(self.table,1)
        row=QHBoxLayout();box.addLayout(row)
        for text,fn in [('Putar saluran',self.play),('Tambah/hapus favorit',self.favorite),('Buka 18+ dengan PIN',self.unlock),('Kunci kembali',self.relock),('Ganti PIN',self.change_pin)]:
            b=QPushButton(text);b.clicked.connect(fn);row.addWidget(b)
        row=QHBoxLayout();box.addLayout(row);self.subtitle_language=QLineEdit('id');self.subtitle_language.setMaximumWidth(70);row.addWidget(QLabel('Bahasa subtitle (ISO)'));row.addWidget(self.subtitle_language)
        b=QPushButton('Aktifkan subtitle online saluran');b.clicked.connect(self.start_subtitles);row.addWidget(b);b=QPushButton('Hentikan subtitle');b.clicked.connect(self.stop_subtitles);row.addWidget(b)
        self.subtitle_status=QLabel('Subtitle TV memakai Gemini dari potongan audio 15 detik. Ada jeda API; bukan siaran tanpa delay.');self.subtitle_status.setWordWrap(True);box.addWidget(self.subtitle_status)
        note=QLabel('Katalog publik IPTV-org berisi tautan siaran publik, tanpa saluran NSFW bawaan. Tidak semua saluran tersedia di setiap wilayah atau selalu online. Tidak membuka premium/DRM. Impor playlist Anda sendiri untuk saluran yang Anda berhak akses. Kategori 18+ pada playlist impor memerlukan PIN; metadata dapat salah sehingga PIN bukan penyaring isi video otomatis.');note.setWordWrap(True);box.addWidget(note)
        self.status=QLabel('Klik Muat katalog untuk mencari saluran melalui internet. Tidak memerlukan antena.');self.status.setWordWrap(True);box.addWidget(self.status)
        self.caption_timer=QTimer(self);self.caption_timer.timeout.connect(self.caption_tick);self.caption_timer.start(100)
        self.debounce=QTimer(self);self.debounce.setSingleShot(True);self.debounce.timeout.connect(self.refresh)
        self.search.textChanged.connect(lambda:self.debounce.start(250));self.country.currentIndexChanged.connect(self.refresh);self.category.currentIndexChanged.connect(self.refresh);self.fav_only.toggled.connect(self.refresh)
    def load(self,kind,source=''):
        if self.job:self.status.setText('Tunggu impor aktif selesai.');return
        self.job=TVLoad(kind,source);self.job.loaded.connect(self.got_epg if kind=='epg' else self.got_rows);self.job.failed.connect(self.status.setText);self.job.finished.connect(self.finished);self.status.setText('Memuat di latar belakang …');self.job.start()
    def finished(self):self.job.deleteLater();self.job=None
    def got_rows(self,rows):
        self.rows=rows
        for combo,field,label in ((self.country,'country','Semua negara'),(self.category,'category','Semua kategori')):
            combo.blockSignals(True);combo.clear();combo.addItem(label,'')
            values=sorted({v for r in rows if not adult(r) or self.lock.unlocked for v in (r[field].split(', ') if field=='category' else [r[field]]) if v})
            for v in values:combo.addItem(v,v)
            combo.blockSignals(False)
        self.refresh()
    def got_epg(self,programs):self.programs=programs;self.refresh();self.status.setText(f'EPG dimuat: {len(programs)} acara. Pencocokan memakai tvg-id saluran.')
    def refresh(self,*args):
        rows=filter_rows(self.rows,self.search.text(),self.country.currentData(),self.category.currentData(),self.favorites,self.fav_only.isChecked(),self.lock.unlocked,self.programs);self.visible_rows=rows[:3000];self.table.setRowCount(len(self.visible_rows));now=time.time();schedule={}
        for p in self.programs:
            if p['end']>now and (p['channel'] not in schedule or p['start']<schedule[p['channel']]['start']):schedule[p['channel']]=p
        for i,r in enumerate(self.visible_rows):
            p=schedule.get(r['id']);program=('Sekarang: ' if p['start']<=now else datetime.datetime.fromtimestamp(p['start']).strftime('%H:%M '))+p['title'] if p else 'EPG belum tersedia'
            for j,value in enumerate([('★ ' if r['key'] in self.favorites else '')+r['name'],r['country'],r['category'],program]):self.table.setItem(i,j,QTableWidgetItem(value))
        self.status.setText(f'{len(rows)} hasil; {len(self.visible_rows)} ditampilkan. Persempit pencarian bila hasil lebih dari 3000. Parental: '+('terbuka' if self.lock.unlocked else 'terkunci'))
    def selected(self):
        i=self.table.currentRow();return self.visible_rows[i] if 0<=i<len(self.visible_rows) else None
    def play(self,*args):
        r=self.selected()
        if not r:return
        if adult(r) and not self.lock.unlocked:self.status.setText('Saluran ini terkunci.');return
        if self.caption_job is not None:self.stop_subtitles();self.status.setText('Tunggu subtitle saluran sebelumnya berhenti sebelum pindah.');return
        from cut_editor import PreviewPlayer
        if self.preview and not self.preview.released:self.preview.close()
        self.playing_row=r;self.preview=PreviewPlayer(self.owner,r['url'],'Internet TV • '+r['name']);self.caption_label=QLabel('');self.caption_label.setWordWrap(True);self.caption_label.setAlignment(Qt.AlignCenter);self.caption_label.setStyleSheet('background:#111;color:white;font-size:20px;padding:10px');self.preview.layout().addWidget(self.caption_label);self.preview.show()
    def start_subtitles(self):
        if self.caption_job:return
        if not self.preview or self.preview.released:self.play()
        if not self.preview or self.preview.released:return
        import re
        language=self.subtitle_language.text().strip()
        if not re.fullmatch(r'[a-zA-Z]{2,3}(?:-[a-zA-Z0-9]{2,8})?',language):self.subtitle_status.setText('Isi kode bahasa seperti id, en, ja.');return
        from live_tv_subtitles import LiveTVSubtitles
        self.caption_job=LiveTVSubtitles(self.playing_row['url'],self.owner.key.text().strip(),self.owner.model.text().strip(),language)
        self.caption_job.progress.connect(self.subtitle_status.setText);self.caption_job.failed.connect(self.subtitle_status.setText);self.caption_job.captions.connect(self.got_captions);self.caption_job.finished.connect(self.caption_finished);self.caption_job.start()
    def got_captions(self,cues,delay):
        self.caption_queue=cues;self.caption_clock=time.monotonic();self.subtitle_status.setText(f'Subtitle tertunda sekitar {delay:.0f} detik karena pengambilan audio dan API. Bila API tertinggal, potongan lama dilewati.')
    def caption_tick(self):
        if self.caption_job and (not self.preview or self.preview.released):self.stop_subtitles()
        if self.caption_label and self.preview and not self.preview.released:
            elapsed=time.monotonic()-self.caption_clock
            self.caption_label.setText('\n'.join((c.target or c.source) for c in self.caption_queue if c.start<=elapsed<c.end))
    def stop_subtitles(self):
        if self.caption_job:self.caption_job.cancel();self.subtitle_status.setText('Membatalkan subtitle TV; tunggu permintaan API aktif selesai.')
        self.caption_queue=[]
    def caption_finished(self):
        self.caption_job.deleteLater();self.caption_job=None;self.caption_queue=[]
    def favorite(self):
        r=self.selected()
        if not r:return
        if r['key'] in self.favorites:self.favorites.remove(r['key'])
        else:self.favorites.add(r['key'])
        if self.lock.settings:self.lock.settings.setValue('iptv/favorites',json.dumps(sorted(self.favorites)))
        self.refresh()
    def import_file(self):
        p,_=QFileDialog.getOpenFileName(self,'Playlist M3U','','Playlist (*.m3u *.m3u8)')
        if p:self.load('playlist',p)
    def import_url(self):
        url,ok=QInputDialog.getText(self,'Playlist internet','URL M3U HTTP/HTTPS yang Anda berhak akses:')
        if ok and url:self.load('playlist',url.strip())
    def import_epg(self):
        p,_=QFileDialog.getOpenFileName(self,'Panduan acara XMLTV lokal','','XMLTV (*.xml *.xmltv *.gz)')
        if p:self.load('epg',p)
    def unlock(self):
        pin,ok=QInputDialog.getText(self,'Parental control','PIN:',QLineEdit.Password)
        if ok:
            if self.lock.unlock(pin):self.got_rows(self.rows)
            else:self.status.setText('PIN salah atau percobaan dibatasi. Setelah lima kegagalan tunggu 30 detik.')
    def relock(self):
        self.stop_subtitles();self.lock.lock()
        if self.preview and not self.preview.released:self.preview.close()
        self.got_rows(self.rows)
    def change_pin(self):
        old,ok=QInputDialog.getText(self,'Ganti PIN','PIN lama:',QLineEdit.Password)
        if not ok:return
        new,ok=QInputDialog.getText(self,'Ganti PIN','PIN baru enam angka:',QLineEdit.Password)
        if ok:
            try:self.lock.change(old,new);self.relock();self.status.setText('PIN diganti.')
            except ValueError as exc:self.status.setText(str(exc))
    def cancel(self):
        if self.job:self.job.requestInterruption();self.status.setText('Membatalkan setelah permintaan aktif berhenti …')
    def closeEvent(self,event):
        self.relock();self.hide();event.ignore()
