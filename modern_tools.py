"""Modern UI and playback controls kept separate from playback/AI workers."""
import json,time,sys
from pathlib import Path
import vlc
from PySide6.QtCore import Qt,QSettings,QPoint
from PySide6.QtGui import QColor,QCursor
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,QComboBox,QSpinBox,QCheckBox,QPushButton,QDialog,QFileDialog,QInputDialog,QMessageBox,QGraphicsDropShadowEffect,QTableWidget,QTableWidgetItem,QAbstractItemView,QSystemTrayIcon,QScrollArea)
from themes import THEMES,validate_theme,stylesheet
from subtitle_tools import parse_vtt,vtt,synchronize,quality_report

from advanced_addons import AdvancedAddons

class ModernTools(AdvancedAddons):
    def setup_modern_tools(self):
        self.persistence_available=self.storage_enabled;self.theme_data=dict(THEMES['Cyber Neon']);self.settings=QSettings('Cyber80','Players')
        self.last_attachment_subtitle=None;self.last_hardsub=None;self.background_job=None;self.tray=None;self.background_notice=None;self.audio_dsp='off';self.rotation='off';self.utility_job=None;self.sync_other=False;self.sync_offset=0.;self.private_session=False;self._last_cursor=None;self._cursor_time=time.monotonic()
        self.appearance_menu=self.menuBar().addMenu('Personalisasi')
        for name in THEMES:self.appearance_menu.addAction(name,lambda checked=False,n=name:self.select_theme(n))
        self.appearance_menu.addAction('Warna aksen…',self.choose_accent)
        self.appearance_menu.addAction('Impor skin JSON',self.import_skin);self.appearance_menu.addAction('Ekspor skin JSON',self.export_skin)
        self.appearance_menu.addAction('Simpan layout',self.save_layout);self.appearance_menu.addAction('Pulihkan layout tersimpan',self.restore_layout)
        simple=self.appearance_menu.addAction('Mode sederhana');simple.setCheckable(True);simple.toggled.connect(self.set_simple_mode);self.simple_action=simple
        self.private_action=self.appearance_menu.addAction('Sesi privat (tanpa riwayat/cache baru)');self.private_action.setCheckable(True);self.private_action.toggled.connect(self.set_private)
        row=QHBoxLayout();self.ai_panel.layout().insertLayout(1,row)
        row.addWidget(QLabel('Cara menonton'));self.ai_policy=QComboBox()
        for label,value in [('Siapkan subtitle dahulu','prepare'),('Tonton — tunggu subtitle','wait'),('Tonton terus tanpa menunggu','continue')]:self.ai_policy.addItem(label,value)
        self.ai_policy.setCurrentIndex(1);row.addWidget(self.ai_policy)
        row.addWidget(QLabel('Potongan audio'));self.ai_chunk=QSpinBox();self.ai_chunk.setRange(10,60);self.ai_chunk.setSingleStep(10);self.ai_chunk.setValue(30);self.ai_chunk.setSuffix(' detik');row.addWidget(self.ai_chunk)
        row.addWidget(QLabel('Track sumber AI (0 = pertama)'));self.ai_stream=QSpinBox();self.ai_stream.setRange(0,31);self.ai_stream.setToolTip('Nomor urut audio FFmpeg, bukan ID track VLC. Gunakan Info track AI untuk memeriksa.');row.addWidget(self.ai_stream)
        b=QPushButton('Info track AI');b.clicked.connect(self.show_ai_tracks);row.addWidget(b)
        label=QLabel('30 detik mengurangi jumlah permintaan; bukan jaminan real-time. Mode siapkan dahulu tetap pause sampai Anda menekan Play. Track AI dipilih terpisah dari track pemutaran.');label.setWordWrap(True);self.ai_panel.layout().insertWidget(2,label)
        self.overlay=QLabel(self,Qt.Tool|Qt.FramelessWindowHint|Qt.WindowDoesNotAcceptFocus|Qt.WindowStaysOnTopHint)
        self.overlay.setAttribute(Qt.WA_TransparentForMouseEvents);self.overlay.setAttribute(Qt.WA_ShowWithoutActivating);self.overlay.setAttribute(Qt.WA_TranslucentBackground)
        self.overlay.setWordWrap(True);self.overlay.setAlignment(Qt.AlignCenter);self.overlay.setTextFormat(Qt.PlainText)
        shadow=QGraphicsDropShadowEffect();shadow.setBlurRadius(5);shadow.setOffset(1,2);shadow.setColor(QColor('black'));self.overlay.setGraphicsEffect(shadow)
        self.overlay_enabled=True;self.overlay_margin=8
        menu=self.menuBar().addMenu('Playback Pro')
        menu.addAction('Lompat ke waktu…',self.goto_time);menu.addAction('Frame berikutnya',self.player_next_frame)
        menu.addAction('Chapter…',self.choose_chapter)
        aspect=menu.addMenu('Aspect ratio')
        for label,value in [('Asli',None),('16:9','16:9'),('4:3','4:3'),('21:9','21:9'),('1:1','1:1')]:aspect.addAction(label,lambda checked=False,v=value:self.player.video_set_aspect_ratio(v))
        crop=menu.addMenu('Crop')
        for label,value in [('Tanpa crop',None),('16:9','16:9'),('4:3','4:3'),('2.35:1','235:100')]:crop.addAction(label,lambda checked=False,v=value:self.player.video_set_crop_geometry(v))
        rotation=menu.addMenu('Rotasi / cermin')
        for label,value in [('Asli','off'),('90°','90'),('180°','180'),('270°','270'),('Cermin horizontal','hflip'),('Cermin vertikal','vflip')]:rotation.addAction(label,lambda checked=False,v=value:self.select_rotation(v))
        dynamics=menu.addMenu('Dinamika audio native')
        for label,value in [('Nonaktif','off'),('Ratakan volume','normalize'),('Dialog / malam (kompresor)','night')]:dynamics.addAction(label,lambda checked=False,v=value:self.select_dsp(v))
        deint=menu.addMenu('Deinterlace')
        for label,value in [('Nonaktif',None),('Blend','blend'),('Bob','bob'),('Yadif','yadif')]:deint.addAction(label,lambda checked=False,v=value:self.player.video_set_deinterlace(v))
        self.native_sub_menu=menu.addMenu('Track subtitle tertanam');self.native_sub_menu.aboutToShow.connect(self.refresh_native_subtitles)
        menu.addAction('Buka subtitle native ASS/SSA/VTT/SRT',self.load_native_subtitle)
        menu.addAction('Buka VTT untuk editor AI',self.import_vtt);menu.addAction('Ekspor VTT editor AI',self.export_vtt)
        menu.addAction('Sinkronisasi subtitle dua titik',self.sync_subtitles);menu.addAction('Periksa keterbacaan subtitle',self.check_subtitles)
        overlay=menu.addAction('Subtitle AI di atas video');overlay.setCheckable(True);overlay.setChecked(True);overlay.toggled.connect(self.toggle_overlay)
        menu.addAction('Jarak subtitle dari bawah…',self.subtitle_margin)
        menu.addAction('Perangkat output audio…',self.choose_audio_device)
        menu.addAction('Koleksi & favorit',self.show_collection)
        menu.addAction('Ekspor diagnosis tanpa key',self.export_diagnostics)
        menu.addAction('Sinkronkan pemutar kedua (toggle)',self.toggle_dual_sync);menu.addAction('Offset pemutar kedua…',self.set_sync_offset)
        tools=self.menuBar().addMenu('Alat media offline')
        for kind in ('Potong klip MP4','Ekstrak audio WAV','Ekstrak audio MP3','Normalisasi audio WAV','Remux MKV','Bakar subtitle MP4'):tools.addAction(kind,lambda checked=False,k=kind:self.start_utility(k))
        tools.addAction('Batalkan pekerjaan',self.cancel_utility)
        menu.addAction('Ukuran cache subtitle',self.show_cache_size);menu.addAction('Hapus semua cache subtitle',self.clear_all_cache)
        if self.storage_enabled:
            try:
                raw=self.settings.value('theme','')
                if raw:self.theme_data=validate_theme(json.loads(raw))
            except (ValueError,TypeError):pass
        self.setup_background_controls()
        self.setup_addons()
        for dock in (self.subtitle_dock,self.studio_dock,self.sound_dock,self.stereo_dock):
            panel=dock.widget();scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(panel);scroll.setMinimumSize(240,120);dock.setWidget(scroll)
        self.apply_theme()
    def set_ai_controls_enabled(self,value):
        for control in (self.ai_policy,self.ai_chunk,self.ai_stream):control.setEnabled(value)
    def apply_theme(self):
        if not hasattr(self,'theme_data'):return
        self.setStyleSheet(stylesheet(self.theme_data))
        if self.pip:self.pip.setStyleSheet(stylesheet(self.theme_data))
    def select_theme(self,name):
        self.theme_data=dict(THEMES[name]);self.apply_theme();self.persist_theme()
    def persist_theme(self):
        if self.storage_enabled:self.settings.setValue('theme',json.dumps(self.theme_data))
    def choose_accent(self):
        from PySide6.QtWidgets import QColorDialog
        color=QColorDialog.getColor(QColor(self.theme_data['accent']),self,'Warna aksen')
        if color.isValid():self.theme_data['accent']=color.name();self.apply_theme();self.persist_theme()
    def import_skin(self):
        path,_=QFileDialog.getOpenFileName(self,'Impor skin warna','','JSON (*.json)')
        if path:
            try:
                if Path(path).stat().st_size>8192:raise ValueError('Skin terlalu besar.')
                self.theme_data=validate_theme(json.loads(Path(path).read_text(encoding='utf-8-sig')));self.apply_theme();self.persist_theme()
            except (OSError,ValueError) as exc:self.error(str(exc))
    def export_skin(self):
        path,_=QFileDialog.getSaveFileName(self,'Simpan skin','Cyber80_Skin.json','JSON (*.json)')
        if path:
            try:Path(path).write_text(json.dumps(self.theme_data,indent=2),encoding='utf-8')
            except OSError as exc:self.error(str(exc))
    def save_layout(self):
        if self.storage_enabled:
            self.settings.setValue('layout',self.saveState());self.settings.setValue('geometry',self.saveGeometry());self.status.setText('Layout disimpan.')
    def restore_layout(self):
        if self.storage_enabled and self.settings.contains('layout'):
            self.restoreState(self.settings.value('layout'));self.restoreGeometry(self.settings.value('geometry'))
    def set_simple_mode(self,value):
        self.advanced_toolbar.setVisible(not value)
        for dock in (self.playlist_dock,self.subtitle_dock,self.stereo_dock,self.sound_dock,self.studio_dock):dock.hide()
        if not value:self.playlist_dock.show()
    def set_private(self,value):
        if self.processing or self.export_job is not None or self.utility_job is not None or self.background_job is not None:
            self.private_action.blockSignals(True);self.private_action.setChecked(self.private_session);self.private_action.blockSignals(False);self.status.setText('Selesaikan pekerjaan aktif sebelum mengganti mode privat.');return
        self.private_session=value;self.storage_enabled=self.persistence_available and not value
        # Shared store must stay persistent for the other window; private window gets an isolated memory store.
        from storage import MediaStore
        self.media_store=MediaStore.shared(self.log_path.parent/'media-library.json',self.storage_enabled)
        self.audio_panel.persist=self.storage_enabled;self.change_renderer(self.renderer.currentIndex())
        self.status.setText('Sesi privat: riwayat/cache baru tidak disimpan. File ekspor tetap tersimpan jika diminta.' if value else 'Penyimpanan riwayat aktif kembali.')
    def select_dsp(self,value):
        self.audio_dsp=value;self.change_renderer(self.renderer.currentIndex());self.status.setText('DSP audio: '+value+'. Bukan pemisahan dialog AI; sesuaikan volume speaker.')
    def select_rotation(self,value):
        self.rotation=value;self.change_renderer(self.renderer.currentIndex())
    def player_next_frame(self):self.want_play=False;self.player.next_frame()
    def goto_time(self):
        seconds,ok=QInputDialog.getDouble(self,'Lompat ke waktu','Detik dari awal:',max(0,self.player.get_time())/1000,0,max(1,self.player.get_length()/1000),3)
        if ok:self.player.set_time(round(seconds*1000))
    def choose_chapter(self):
        count=self.player.get_chapter_count()
        if not isinstance(count,int) or count<=0:self.status.setText('Media ini tidak mempunyai chapter yang dapat dibaca VLC.');return
        n,ok=QInputDialog.getInt(self,'Chapter','Nomor chapter:',max(1,self.player.get_chapter()+1),1,count)
        if ok:self.player.set_chapter(n-1)
    def refresh_native_subtitles(self):
        self.native_sub_menu.clear();current=self.player.video_get_spu()
        for track_id,label in self.player.video_get_spu_description() or []:
            if isinstance(label,bytes):label=label.decode('utf-8',errors='replace')
            action=self.native_sub_menu.addAction(str(label));action.setCheckable(True);action.setChecked(track_id==current);action.triggered.connect(lambda checked=False,i=track_id:self.player.video_set_spu(i))
    def load_native_subtitle(self):
        path,_=QFileDialog.getOpenFileName(self,'Subtitle native','','Subtitle (*.ass *.ssa *.vtt *.srt *.sub)')
        if path and self.player.add_slave(vlc.MediaSlaveType.subtitle,Path(path).resolve().as_uri(),True)!=0:self.error('VLC tidak dapat memuat subtitle.')
    def import_vtt(self):
        if self.processing:return
        path,_=QFileDialog.getOpenFileName(self,'Buka VTT','','WebVTT (*.vtt)')
        if path:
            try:self.fill(parse_vtt(Path(path).read_text(encoding='utf-8-sig')));self.cache_context=None
            except (OSError,ValueError) as exc:self.error(str(exc))
    def export_vtt(self):
        if not self.cues:return
        path,_=QFileDialog.getSaveFileName(self,'Simpan VTT','subtitle.vtt','WebVTT (*.vtt)')
        if path:
            try:Path(path).write_text(vtt(self.cues),encoding='utf-8')
            except OSError as exc:self.error(str(exc))
    def sync_subtitles(self):
        if self.processing or not self.cues:return
        values=[]
        for label in ('Waktu subtitle titik A (detik)','Waktu suara titik A (detik)','Waktu subtitle titik B (detik)','Waktu suara titik B (detik)'):
            n,ok=QInputDialog.getDouble(self,'Sinkronisasi dua titik',label,0,0,1e8,3)
            if not ok:return
            values.append(n)
        try:self.fill(synchronize(self.cues,*values));self.status.setText('Sinkronisasi diterapkan di editor. Ekspor SRT/VTT untuk menyimpan hasil.')
        except ValueError as exc:self.error(str(exc))
    def check_subtitles(self):
        issues=quality_report(self.cues)
        box=QMessageBox(self);box.setWindowTitle('Pemeriksaan keterbacaan');box.setTextFormat(Qt.PlainText);box.setText(f'{len(issues)} dari {len(self.cues)} cue perlu ditinjau. Ini pemeriksaan heuristik, bukan penilaian akurasi terjemahan.');box.setDetailedText(json.dumps(issues,ensure_ascii=False,indent=2));box.exec()
    def toggle_overlay(self,value):self.overlay_enabled=value;self.overlay.hide()
    def subtitle_margin(self):
        value,ok=QInputDialog.getInt(self,'Posisi subtitle','Jarak dari bawah (%):',self.overlay_margin,0,40)
        if ok:self.overlay_margin=value
    def update_overlay(self):
        if not hasattr(self,'overlay'):return
        text=self.subtitle.text();host=self.pip or self
        visible=self.overlay_enabled and bool(text) and host.isVisible() and not host.isMinimized() and host.isActiveWindow() and not self.video.audio_title
        self.subtitle.setVisible(not self.overlay_enabled)
        if self.pip:self.pip.caption.setVisible(not self.overlay_enabled)
        if not visible:self.overlay.hide();return
        width=max(100,self.video.width()-40);height=min(self.video.height(),self.subtitle_font.value()*5+20)
        pos=self.video.mapToGlobal(QPoint((self.video.width()-width)//2,max(0,self.video.height()-height-self.video.height()*self.overlay_margin//100)))
        self.overlay.setStyleSheet(f'background:transparent;color:{self.subtitle_color.currentData()};font-size:{self.subtitle_font.value()}px;font-weight:600;padding:6px;')
        self.overlay.setText(text);self.overlay.setGeometry(pos.x(),pos.y(),width,height);self.overlay.show();self.overlay.raise_()
    def modern_tick(self):
        if not hasattr(self,'overlay'):return
        self.addons_tick();self.update_dual_sync()
        cursor=QCursor.pos()
        if self._last_cursor!=cursor:self._last_cursor=cursor;self._cursor_time=time.monotonic()
        if self.pip:
            hide=self.pip.isFullScreen() and time.monotonic()-self._cursor_time>3
            for button in self.pip.findChildren(QPushButton):button.setVisible(not hide)
    def choose_audio_device(self):
        devices=[('Default sistem',None)];head=None
        try:
            head=self.player.audio_output_device_enum();node=head
            while node:
                item=node.contents;devices.append((item.description.decode(errors='replace'),item.device.decode(errors='replace')));node=item.next
        except Exception:self.status.setText('Daftar perangkat tidak tersedia dari output audio VLC saat ini.')
        finally:
            if head:vlc.libvlc_audio_output_device_list_release(head)
        labels=[f'{i}: {name}' for i,(name,_) in enumerate(devices)];choice,ok=QInputDialog.getItem(self,'Output audio','Perangkat:',labels,0,False)
        if ok:self.player.audio_output_device_set(None,devices[labels.index(choice)][1])
    def show_ai_tracks(self):
        if not self.path:return
        media=self.player.get_media();lines=[];ordinal=0
        if media:
            for track in media.tracks_get() or []:
                if track.type==vlc.TrackType.audio:
                    lines.append(f'Audio #{ordinal}: VLC ID {track.id}, codec {int(track.codec).to_bytes(4,"little").decode(errors="replace")}');ordinal+=1
        QMessageBox.information(self,'Track sumber AI','\n'.join(lines) or 'Track belum tersedia; mulai pemutaran lalu coba kembali.')
    def show_collection(self):
        dialog=QDialog(self);dialog.setWindowTitle('Koleksi lokal • Favorit & status menonton');layout=QVBoxLayout(dialog)
        table=QTableWidget(0,4);table.setHorizontalHeaderLabels(['Judul','Favorit','Selesai ditonton','Lokasi']);table.setSelectionBehavior(QAbstractItemView.SelectRows);table.setEditTriggers(QAbstractItemView.NoEditTriggers);layout.addWidget(table)
        records=self.media_store.entries();table.setRowCount(len(records))
        for i,record in enumerate(records):
            for j,value in enumerate((record.get('title',Path(record['path']).stem),'Ya' if record.get('favorite') else '', 'Ya' if record.get('watched') else '',record['path'])):table.setItem(i,j,QTableWidgetItem(str(value)))
        row=QHBoxLayout();layout.addLayout(row)
        def selected():
            i=table.currentRow();return records[i] if 0<=i<len(records) else None
        def toggle(field,col):
            record=selected()
            if record:
                record[field]=not record.get(field,False);self.media_store.update(record['path'],**{field:record[field]});table.item(table.currentRow(),col).setText('Ya' if record[field] else '')
        def play():
            record=selected()
            if record:
                try:self.open_path(record['path']);dialog.accept()
                except Exception as exc:self.error(str(exc))
        def relink():
            record=selected()
            if not record:return
            path,_=QFileDialog.getOpenFileName(dialog,'Cari file pengganti (riwayat dipindahkan secara manual)')
            if path:
                self.media_store.relink(record['path'],path);record['path']=path;table.item(table.currentRow(),3).setText(path)
        for name,fn in [('Putar',play),('Favorit',lambda:toggle('favorite',1)),('Sudah ditonton',lambda:toggle('watched',2)),('Hubungkan ulang file',relink)]:
            b=QPushButton(name);b.clicked.connect(fn);row.addWidget(b)
        table.horizontalHeader().setStretchLastSection(True);dialog.resize(900,450);dialog.exec()
    def export_diagnostics(self):
        info=self.media_info();info.pop('file',None);info.update(requested_renderer=self.renderer.currentText(),hardware_acceleration_verified=False,python=sys.version.split()[0],vlc=vlc.libvlc_get_version().decode(errors='replace'),subtitle_engine=self.ai_engine.currentData(),subtitle_count=len(self.cues),ai_chunk_seconds=self.ai_chunk.value())
        path,_=QFileDialog.getSaveFileName(self,'Simpan diagnosis tanpa API key/lokasi file','Cyber80_Diagnosis.json','JSON (*.json)')
        if path:
            try:Path(path).write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding='utf-8')
            except OSError as exc:self.error(str(exc))
    def show_cache_size(self):
        files=list(self.subtitle_cache.root.glob('*.json'));size=sum(p.stat().st_size for p in files)
        QMessageBox.information(self,'Cache subtitle',f'{len(files)} file, {size/1024/1024:.2f} MiB. Audio dan API key tidak disimpan di cache subtitle.')
    def clear_all_cache(self):
        if self.processing:self.status.setText('Tunggu pekerjaan AI selesai sebelum menghapus cache.');return
        if QMessageBox.question(self,'Hapus cache','Hapus semua hasil AI tersimpan? SRT/VTT yang diekspor tidak ikut dihapus.')==QMessageBox.Yes:
            try:
                for path in self.subtitle_cache.root.glob('*.json'):path.unlink()
                self.status.setText('Semua cache subtitle dihapus.')
            except OSError as exc:self.error(str(exc))
    def start_utility(self,kind):
        if not self.path:
            self.online_dock.show();self.online_status.setText('Alat cutting/ekspor membutuhkan media lokal. Rekam atau unduh media online dahulu.');return
        if self.utility_job is not None or self.background_job is not None:return
        start=end=0
        if kind=='Potong klip MP4':
            start,ok=QInputDialog.getDouble(self,'Potong klip','Awal (detik):',0,0,1e8,3)
            if not ok:return
            end,ok=QInputDialog.getDouble(self,'Potong klip','Akhir (detik):',start+10,0,1e8,3)
            if not ok:return
            if end<=start:self.error('Akhir harus lebih besar dari awal.');return
        extension='mkv' if kind=='Remux MKV' else 'mp3' if kind=='Ekstrak audio MP3' else 'wav' if kind in ('Ekstrak audio WAV','Normalisasi audio WAV') else 'mp4'
        path,_=QFileDialog.getSaveFileName(self,kind,Path(self.path).stem+'_Cyber80.'+extension,f'{extension.upper()} (*.{extension})')
        if not path:return
        from media_jobs import UtilityJob
        from core import srt
        self.utility_job=UtilityJob(self.path,path,kind,start,end,srt(self.cues) if self.cues else '')
        self.utility_job.status.connect(self.status.setText);self.utility_job.success.connect(lambda value:self.status.setText('Selesai: '+value));self.utility_job.failure.connect(self.error);self.utility_job.finished.connect(self.utility_finished);self.utility_job.start()
    def cancel_utility(self):
        if self.utility_job:self.utility_job.cancel()
    def utility_finished(self):self.utility_job.deleteLater();self.utility_job=None
    def toggle_dual_sync(self):
        from player_extras import PlayerExtras
        other=next((w for w in PlayerExtras.windows if w is not self and not w.closing),None)
        if other is None:self.status.setText('Buka pemutar kedua dan media terlebih dahulu.');return
        self.sync_other=not self.sync_other
        if self.sync_other:other.sync_other=False
        self.status.setText('Sinkronisasi pemutar kedua aktif; pemutar ini menjadi pengendali. Jangan gunakan untuk sinkronisasi frame presisi.' if self.sync_other else 'Sinkronisasi dimatikan.')
    def set_sync_offset(self):
        value,ok=QInputDialog.getDouble(self,'Offset pemutar kedua','Selisih (detik, negatif/positif):',self.sync_offset,-3600,3600,3)
        if ok:self.sync_offset=value
    def update_dual_sync(self):
        if not self.sync_other:return
        from player_extras import PlayerExtras
        other=next((w for w in PlayerExtras.windows if w is not self and not w.closing),None)
        if other is None:self.sync_other=False;return
        if not self.path or not other.path or self.processing or other.processing:return
        state=self.player.get_state();other_state=other.player.get_state()
        if state not in (vlc.State.Playing,vlc.State.Paused):return
        target=max(0,self.player.get_time()+round(self.sync_offset*1000))
        if abs(other.player.get_time()-target)>400:other.player.set_time(target)
        if state==vlc.State.Playing and other_state!=vlc.State.Playing:other.player.play()
        elif state==vlc.State.Paused and other_state==vlc.State.Playing:other.player.set_pause(1)
        if abs(other.speed_box.value()-self.speed_box.value())>.001:other.speed_box.setValue(self.speed_box.value())
    def modern_cleanup(self):
        self.addons_cleanup()
        self.overlay.hide();self.overlay.close()
        if self.tray:self.tray.hide()
        if self.utility_job:self.utility_job.cancel();self.utility_job.wait(5000)


    def setup_background_controls(self):
        row=QHBoxLayout();self.ai_panel.layout().addLayout(row)
        self.attachment_fallback=QCheckBox('Fallback audio jika video sibuk/timeout (kuota tambahan, model sama)');self.attachment_fallback.setChecked(True);self.ai_panel.layout().addWidget(self.attachment_fallback)
        self.attachment_proxy=QCheckBox('Proxy MP4 720p (file besar/format lain/track pilihan)');row.addWidget(self.attachment_proxy)
        self.attachment_start=QPushButton('Attachment video → subtitle di latar belakang');self.attachment_start.clicked.connect(self.start_background_subtitles);row.addWidget(self.attachment_start)
        self.attachment_cancel=QPushButton('Batalkan attachment');self.attachment_cancel.clicked.connect(self.cancel_background);self.attachment_cancel.setEnabled(False);row.addWidget(self.attachment_cancel)
        self.attachment_status=QLabel('Attachment mengirim video ke Google; hasil SRT tersimpan otomatis. Anda boleh menonton media lain/minimalkan aplikasi. Jangan tutup aplikasi sampai selesai.');self.attachment_status.setWordWrap(True);self.ai_panel.layout().addWidget(self.attachment_status)
        row=QHBoxLayout();self.ai_panel.layout().addLayout(row)
        self.hardsub_button=QPushButton('Gabungkan subtitle film aktif → Simpan video baru');self.hardsub_button.clicked.connect(self.burn_current_subtitle);row.addWidget(self.hardsub_button)
        b=QPushButton('Gabungkan subtitle attachment terakhir');b.clicked.connect(self.burn_attachment_subtitle);row.addWidget(b)
        b=QPushButton('Buka folder hasil subtitle/video');b.clicked.connect(self.open_hardsub_folder);row.addWidget(b)
        menu=self.menuBar().addMenu('Studio Bahasa');menu.addAction('Subtitle / Dubbing / Lirik terpadu…',self.open_language_studio);menu.addAction('Buat dari attachment video…',self.start_background_subtitles);menu.addAction('Batalkan pekerjaan',self.cancel_background)
    def start_background_subtitles(self):
        if self.background_job is not None:self.status.setText('Satu pekerjaan attachment masih berjalan.');return
        key=self.key.text().strip()
        if not key:self.subtitle_dock.show();self.key.setFocus();self.status.setText('Isi Gemini API key untuk attachment video.');return
        source,_=QFileDialog.getOpenFileName(self,'Pilih video yang akan dikirim sebagai attachment ke Google',self.path,'Video (*.*)')
        if not source:return
        lang=self.lang.currentData() if self.lang.currentText()==self.lang.itemText(self.lang.currentIndex()) else self.lang.currentText().strip()
        from background_subtitles import MIMES,MAX_UPLOAD,BackgroundSubtitleJob
        proxy=self.attachment_proxy.isChecked()
        if not proxy and (Path(source).suffix.lower() not in MIMES or Path(source).stat().st_size>MAX_UPLOAD):
            self.error('Format/ukuran attachment memerlukan proxy. Centang Proxy MP4 720p lalu pilih video lagi.');return
        target,_=QFileDialog.getSaveFileName(self,'Simpan subtitle hasil attachment',str(Path(source).with_suffix(''))+'.Cyber80.srt','SRT (*.srt)')
        if not target:return
        if Path(target).resolve()==Path(source).resolve():self.error('Hasil subtitle tidak boleh menimpa video.');return
        self.background_job=BackgroundSubtitleJob(source,target,key,self.model.text().strip(),lang,self.glossary.text().strip(),proxy,self.ai_stream.value(),self.storage_enabled,self.attachment_fallback.isChecked())
        self.background_job.progress.connect(self.attachment_status.setText);self.background_job.completed.connect(self.background_complete);self.background_job.failed.connect(self.background_failed);self.background_job.finished.connect(self.background_finished)
        self.attachment_start.setEnabled(False);self.attachment_cancel.setEnabled(True)
        if self.tray is None and QSystemTrayIcon.isSystemTrayAvailable():
            self.tray=QSystemTrayIcon(self.windowIcon(),self);self.tray.setToolTip('Cyber80 Players • Subtitle');self.tray.show()
        self.attachment_status.setText('Pekerjaan attachment dimulai …');self.background_job.start()
    def cancel_background(self):
        if self.background_job:self.background_job.cancel();self.attachment_status.setText('Membatalkan attachment; permintaan aktif dapat menunggu timeout hingga 180 detik.')
    def background_complete(self,path,cues):
        if self.background_job:self.last_attachment_subtitle={'source':self.background_job.source,'cues':list(cues),'path':path}
        message=f'Subtitle selesai dibuat: {len(cues)} cue.\n{path}'
        self.attachment_status.setText(message);self.status.setText(message)
        if self.background_job and self.path==self.background_job.source and not self.processing:
            self.fill(cues);self.cache_context=None
        if self.tray and QSystemTrayIcon.supportsMessages():self.tray.showMessage('Cyber80 • Subtitle selesai',message,QSystemTrayIcon.Information,10000)
        else:
            self.background_notice=QMessageBox(self);self.background_notice.setWindowTitle('Subtitle selesai dibuat');self.background_notice.setTextFormat(Qt.PlainText);self.background_notice.setText(message);self.background_notice.setStandardButtons(QMessageBox.Close)
            burn=self.background_notice.addButton('Gabungkan → Video baru',QMessageBox.ActionRole);burn.clicked.connect(self.burn_attachment_subtitle)
            self.background_notice.open()
    def background_failed(self,message):
        self.attachment_status.setText('Attachment gagal/dibatalkan: '+message);self.status.setText('Subtitle attachment belum selesai. Lihat panel Subtitle / AI.')
        if self.tray and QSystemTrayIcon.supportsMessages():self.tray.showMessage('Cyber80 • Subtitle belum selesai',message,QSystemTrayIcon.Warning,10000)
    def background_finished(self):
        self.background_job.deleteLater();self.background_job=None;self.attachment_start.setEnabled(True);self.attachment_cancel.setEnabled(False)

    def burn_current_subtitle(self):
        if not self.path or not self.cues:self.status.setText('Buka media dan buat/impor subtitle terlebih dahulu.');return
        from core import Cue
        shift=self.offset.value()/1000
        cues=[Cue(max(0,c.start+shift),c.end+shift,c.source,c.target,c.language) for c in self.cues if c.end+shift>0]
        self.start_hardsub(self.path,cues)
    def burn_attachment_subtitle(self):
        if not self.last_attachment_subtitle:self.status.setText('Belum ada subtitle attachment yang selesai.');return
        self.start_hardsub(self.last_attachment_subtitle['source'],self.last_attachment_subtitle['cues'])
    def start_hardsub(self,source,cues):
        if self.utility_job is not None:self.status.setText('Tunggu pekerjaan alat media aktif selesai.');return
        if not cues:self.status.setText('Tidak ada teks subtitle untuk digabungkan.');return
        from player_extras import AUDIO_SUFFIXES
        music=Path(source).suffix.lower() in AUDIO_SUFFIXES
        target,_=QFileDialog.getSaveFileName(self,'Simpan video lirik baru' if music else 'Simpan video baru dengan hard subtitle',str(Path(source).with_suffix(''))+('_lyrics.mp4' if music else '_hardsub.mp4'),'MP4 (*.mp4)')
        if not target:return
        from media_jobs import UtilityJob
        from core import srt
        self.utility_job=UtilityJob(source,target,'Video lirik MP4' if music else 'Bakar subtitle MP4',subtitle_text=srt(cues))
        self.utility_job.status.connect(self.status.setText);self.utility_job.failure.connect(self.error);self.utility_job.success.connect(self.hardsub_completed);self.utility_job.finished.connect(self.utility_finished);self.utility_job.start()
    def hardsub_completed(self,path):
        self.last_hardsub=path;self.status.setText('Video baru dengan subtitle selesai: '+path)
        if self.tray:self.tray.showMessage('Cyber80 • Video subtitle selesai',Path(path).name,QSystemTrayIcon.Information,10000)
        else:
            self.background_notice=QMessageBox(self);self.background_notice.setWindowTitle('Video baru selesai');self.background_notice.setText('Video baru tersimpan: '+path);self.background_notice.setStandardButtons(QMessageBox.Close);button=self.background_notice.addButton('Buka folder',QMessageBox.ActionRole);button.clicked.connect(self.open_hardsub_folder);self.background_notice.open()
    def open_hardsub_folder(self):
        path=self.last_hardsub or (self.last_attachment_subtitle['path'] if self.last_attachment_subtitle else None)
        if path:
            from PySide6.QtGui import QDesktopServices
            from PySide6.QtCore import QUrl
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(path).parent)))
