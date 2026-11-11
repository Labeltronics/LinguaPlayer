"""Download queue UI. Session secrets stay in memory; source URLs use Windows vault."""
import os,json,time,uuid,shutil
from pathlib import Path
from PySide6.QtCore import Qt,QTimer,QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QTableWidget,QTableWidgetItem,QSpinBox,QDoubleSpinBox,QFileDialog,QInputDialog,QMessageBox,QAbstractItemView,QApplication,QSystemTrayIcon)
from download_engine import DownloadJob,RateLimiter,target_stamp
from web_transfer import checked_url,safe_filename,atomic_json
from credentials import save_key,load_key,delete_key

def human(n):return f'{n/1024/1024:.1f} MiB' if n else 'belum diketahui'
class DownloadManager(QDialog):
    def __init__(self,owner):
        super().__init__(owner,Qt.Window);self.owner=owner;self.setWindowTitle('Cyber80 • Download Manager');self.resize(1100,520)
        self.records=[];self.urls={};self.headers={};self.providers={};self.jobs={};self.native={};self.pending_done={};self.limiter=RateLimiter();self.header_provider=None;self.tray=None
        self.persist=owner.storage_enabled;self.index=owner.log_path.parent/f'downloads-{owner.window_number}.json';self.last_save=0
        layout=QVBoxLayout(self);row=QHBoxLayout();layout.addLayout(row)
        for label,fn in [('Tambah URL',self.manual),('Jeda',self.pause),('Lanjutkan / Coba lagi',self.resume),('Batal',self.cancel),('Prioritas +',self.priority),('Perbarui URL',self.replace_url),('Hubungkan sesi',self.attach_session),('Putar',self.play_selected),('Playlist',self.playlist_selected),('Buka folder',self.folder),('SHA256',self.checksum),('Bersihkan daftar selesai',self.clear_finished)]:
            button=QPushButton(label);button.clicked.connect(fn);row.addWidget(button)
        row=QHBoxLayout();layout.addLayout(row);row.addWidget(QLabel('Unduhan bersamaan'));self.concurrent=QSpinBox();self.concurrent.setRange(1,4);self.concurrent.setValue(2);row.addWidget(self.concurrent)
        row.addWidget(QLabel('Koneksi per file'));self.connections=QSpinBox();self.connections.setRange(1,4);self.connections.setValue(1);row.addWidget(self.connections)
        row.addWidget(QLabel('Batas total'));self.speed=QDoubleSpinBox();self.speed.setRange(0,1000);self.speed.setSuffix(' MiB/s (0 = bebas)');self.speed.valueChanged.connect(lambda v:setattr(self.limiter,'rate',int(v*1024*1024)));row.addWidget(self.speed)
        self.table=QTableWidget(0,6);self.table.setHorizontalHeaderLabels(['Nama','Status','Progres','Kecepatan','Perkiraan sisa','Info']);self.table.setSelectionBehavior(QAbstractItemView.SelectRows);self.table.setEditTriggers(QAbstractItemView.NoEditTriggers);self.table.horizontalHeader().setStretchLastSection(True);layout.addWidget(self.table)
        self.status=QLabel('Satu koneksi default. Paralel hanya jika Range dan ETag kuat tervalidasi. URL/sesi tidak ditulis ke log.');self.status.setWordWrap(True);layout.addWidget(self.status)
        self.timer=QTimer(self);self.timer.timeout.connect(self.pump);self.timer.start(250);self.load();self.refresh()
    def record(self):
        i=self.table.currentRow();return self.records[i] if 0<=i<len(self.records) else None
    def add(self,url,name='media.bin',kind='file',headers=None,quality=999,target=None,private=False):
        url=checked_url(url)
        if target is None:
            suffix='.mp4' if kind in ('hls','dash') else ''
            suggested=Path.home()/'Downloads'/(safe_filename(Path(name).stem)+suffix if suffix else safe_filename(name))
            target,_=QFileDialog.getSaveFileName(self,'Simpan unduhan',str(suggested))
        if not target:return None
        target=str(Path(target).resolve())
        if any(r['target']==target and r['status'] in ('Queued','Running','Paused') for r in self.records):raise ValueError('Tujuan ini masih dipakai unduhan lain.')
        rid=uuid.uuid4().hex;record={'id':rid,'target':target,'name':Path(target).name,'status':'Queued','kind':kind,'quality':quality,'connections':self.connections.value(),'priority':0,'private':bool(private or self.owner.private_session),'received':0,'total':0,'validator':'','target_stamp':target_stamp(target)}
        self.records.append(record);self.urls[rid]=url;self.headers[rid]=dict(headers or {});
        if not record['private']:self.save_url(rid,url)
        self.save();self.refresh();self.show();self.pump();return record
    def save_url(self,rid,url):
        if self.persist and os.name=='nt':
            try:save_key('Download-'+rid,url)
            except Exception:self.status.setText('URL terlalu panjang/tidak dapat disimpan aman. Setelah restart, URL perlu diisi ulang.')
    def save(self):
        if not self.persist or not self.owner.storage_enabled:return
        try:atomic_json(self.index,[r for r in self.records if not r.get('private')])
        except OSError:self.status.setText('Antrean berjalan, tetapi tidak dapat disimpan.')
    def load(self):
        if not self.persist:return
        try:
            rows=json.loads(self.index.read_text(encoding='utf-8'))
            for record in rows[:1000]:
                if not isinstance(record,dict) or not all(k in record for k in ('id','target','name','status')):continue
                import re
                if not re.fullmatch('[0-9a-f]{32}',str(record['id'])) or not Path(record['target']).is_absolute():continue
                if record['status'] not in ('Completed','Cancelled'):record['status']='Paused'
                try:url=load_key('Download-'+record['id']) if os.name=='nt' else ''
                except Exception:url=''
                if url:
                    try:self.urls[record['id']]=checked_url(url)
                    except ValueError:pass
                self.records.append(record)
        except (OSError,ValueError,TypeError):pass
    def refresh(self):
        selected=self.table.currentRow();self.table.setRowCount(len(self.records))
        for i,r in enumerate(self.records):
            received=r.get('received',0);total=r.get('total',0);progress=f'{received/total*100:.1f}%' if total else human(received);eta=r.get('eta')
            values=(r['name'],r['status'],progress,f'{human(r.get("speed",0))}/s' if r.get('speed') else '—',f'{eta:.0f} detik' if eta is not None else '—',r.get('message',''))
            for j,value in enumerate(values):self.table.setItem(i,j,QTableWidgetItem(str(value)))
        if 0<=selected<len(self.records):self.table.selectRow(selected)
    def pump(self):
        if len(self.jobs)+sum(not req.isFinished() for req in self.native.values())<self.concurrent.value():
            queued=sorted((r for r in self.records if r['status']=='Queued' and r['id'] not in self.jobs),key=lambda r:-r.get('priority',0))
            if queued:self.start(queued[0])
        if time.monotonic()-self.last_save>2:self.save();self.last_save=time.monotonic()
    def start(self,record):
        rid=record['id'];url=self.urls.get(rid)
        if not url:record['status']='Needs URL';record['message']='Isi URL baru; sesi login tidak disimpan di antrean.';self.refresh();return
        headers=self.headers.get(rid,{})
        provider=self.providers.get(rid)
        if provider:
            headers={k:v for k,v in headers.items() if k.lower()!='cookie'}
            headers.update(provider(url))
        job=DownloadJob(record,url,headers,self.limiter);self.jobs[rid]=job;record['status']='Running'
        job.update.connect(lambda data,r=record:self.update_record(r,data));job.done.connect(lambda state,message,r=record:self.result(r,state,message));job.finished.connect(lambda i=rid:self.release(i));job.start();self.refresh()
    def update_record(self,record,data):record.update(data);self.refresh()
    def result(self,record,state,message):
        record['status']=state;record['message']=message;record['speed']=0;record['eta']=None
        if state=='Completed':
            record['received']=Path(record['target']).stat().st_size;record['total']=record['received']
            if record.get('auto_playlist'):self.owner.add_paths([record['target']])
            if self.persist and os.name=='nt':
                try:delete_key('Download-'+record['id'])
                except Exception:pass
            self.notify(record)
        self.save();self.refresh()
    def release(self,rid):
        job=self.jobs.pop(rid,None)
        if job:job.deleteLater()
    def notify(self,record):
        self.status.setText('Selesai: '+record['name']+' — pilih Putar, Playlist, atau Buka folder.')
        if QSystemTrayIcon.isSystemTrayAvailable():
            if self.tray is None:self.tray=QSystemTrayIcon(self.owner.windowIcon(),self);self.tray.show()
            self.tray.showMessage('Cyber80 • Unduhan selesai',record['name'],QSystemTrayIcon.Information,8000)
        QApplication.alert(self,3000)
    def manual(self):
        url,ok=QInputDialog.getText(self,'Tambah unduhan','URL HTTP/HTTPS (file, HLS VOD atau DASH statis):')
        if ok:
            try:
                from urllib.parse import urlsplit
                path=urlsplit(checked_url(url)).path;kind='hls' if path.lower().endswith('.m3u8') else 'dash' if path.lower().endswith('.mpd') else 'file';self.add(url,Path(path).name or 'media.bin',kind)
            except Exception as exc:QMessageBox.warning(self,'Unduhan',str(exc))
    def pause(self):
        r=self.record()
        if not r:return
        if r['id'] in self.jobs:self.jobs[r['id']].stop()
        elif r['id'] in self.native:self.native[r['id']].pause();r['status']='Paused'
        elif r['status']=='Queued':r['status']='Paused'
        self.refresh();self.save()
    def resume(self):
        r=self.record()
        if r and r['id'] not in self.jobs:
            if r['id'] in self.native:self.native[r['id']].resume();r['status']='Running'
            elif r['status']!='Completed':r['status']='Queued'
            self.refresh();self.save()
    def cancel(self):
        r=self.record()
        if not r:return
        if r['id'] in self.jobs:self.jobs[r['id']].stop(True)
        elif r['id'] in self.native:self.native[r['id']].cancel();r['status']='Cancelled'
        else:
            r['status']='Cancelled';Path(r['target']+'.'+r['id']+'.part').unlink(missing_ok=True);shutil.rmtree(r['target']+'.'+r['id']+'.segments',ignore_errors=True)
        self.refresh();self.save()
    def priority(self):
        r=self.record()
        if r:r['priority']=r.get('priority',0)+1;self.status.setText('Prioritas dinaikkan. Berlaku saat slot tersedia.');self.save()
    def replace_url(self):
        r=self.record()
        if not r or r['id'] in self.jobs or r['status']=='Completed':return
        url,ok=QInputDialog.getText(self,'Perbarui URL','URL baru untuk sumber yang sama:')
        if ok:
            try:
                self.urls[r['id']]=checked_url(url);self.headers[r['id']]={}
                if not r.get('private'):self.save_url(r['id'],url)
                r['status']='Paused';self.save();self.refresh()
            except ValueError as exc:QMessageBox.warning(self,'URL',str(exc))
    def attach_session(self):
        r=self.record()
        if not r or r['id'] in self.jobs:return
        browsers=self.owner.browsers
        if not browsers:self.status.setText('Buka browser dan login pada situs sumber terlebih dahulu.');return
        labels=[f'{i+1}: '+('Privat' if b.private else 'Normal') for i,b in enumerate(browsers)];choice,ok=QInputDialog.getItem(self,'Sesi browser','Gunakan cookie profil ini hanya untuk domain sumber:',labels,0,False)
        if ok:
            browser=browsers[labels.index(choice)];self.providers[r['id']]=browser.headers_for;self.status.setText('Sesi profil dihubungkan. Tekan Lanjutkan; token Authorization yang tidak tersedia perlu dideteksi ulang dari halaman.')
    def checksum(self):
        r=self.record()
        if not r:return
        if r['id'] in self.jobs:self.status.setText('Jeda tugas dan tunggu berhenti sebelum mengatur checksum SHA256.');return
        value,ok=QInputDialog.getText(self,'SHA256','Checksum SHA256 yang diharapkan (kosong = tidak memeriksa):')
        if ok:
            import re
            if value and not re.fullmatch('[0-9a-fA-F]{64}',value):QMessageBox.warning(self,'SHA256','Harus 64 karakter heksadesimal.');return
            r['sha256']=value.lower();self.save()
    def clear_finished(self):
        ids={r['id'] for r in self.records if r['status'] in ('Completed','Cancelled') and r['id'] not in self.jobs}
        for rid in ids:
            self.urls.pop(rid,None);self.headers.pop(rid,None);self.providers.pop(rid,None)
            if self.persist and os.name=='nt':
                try:delete_key('Download-'+rid)
                except Exception:pass
        self.records=[r for r in self.records if r['id'] not in ids];self.refresh();self.save();self.status.setText('Daftar dibersihkan. File hasil unduhan tidak dihapus.')
    def completed_path(self):
        r=self.record();return r['target'] if r and r['status']=='Completed' and Path(r['target']).is_file() else None
    def play_selected(self):
        path=self.completed_path()
        if path:
            try:self.owner.open_path(path);self.owner.showNormal();self.owner.activateWindow()
            except Exception as exc:QMessageBox.warning(self,'Putar',str(exc))
    def playlist_selected(self):
        path=self.completed_path()
        if path:self.owner.add_paths([path]);self.status.setText('Ditambahkan ke playlist. Untuk subtitle, buka media lalu gunakan Subtitle / AI.')
    def folder(self):
        r=self.record()
        if r:QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(r['target']).parent)))
    def accept_native(self,request,private=False):
        target,_=QFileDialog.getSaveFileName(self,'Simpan unduhan browser',str(Path.home()/'Downloads'/safe_filename(request.suggestedFileName())))
        if not target:request.cancel();return
        rid=uuid.uuid4().hex;target=str(Path(target).resolve());temp=Path(target).parent/('.cyber80-native-'+rid);temp.mkdir();stamp=target_stamp(target)
        r={'id':rid,'target':target,'name':Path(target).name,'kind':'native','private':bool(private or self.owner.private_session),'status':'Running','received':0,'total':0,'message':'Sesi browser; resume lintas restart perlu dimulai lagi dari halaman.'};self.records.append(r);self.native[rid]=request
        request.setDownloadDirectory(str(temp));request.setDownloadFileName(Path(target).name)
        def update():
            if r['status']=='Completed':return
            r['received']=request.receivedBytes();r['total']=max(0,request.totalBytes())
            if request.isFinished():
                name=request.state().name
                if name=='DownloadCompleted':
                    if target_stamp(target)!=stamp:self.result(r,'Failed','Tujuan berubah; file browser tetap di folder sementara.');return
                    os.replace(temp/Path(target).name,target);shutil.rmtree(temp,ignore_errors=True);self.result(r,'Completed','Selesai')
                elif name=='DownloadCancelled':self.result(r,'Cancelled','Dibatalkan');shutil.rmtree(temp,ignore_errors=True)
                else:self.result(r,'Failed','Unduhan browser terputus; ulangi dari halaman sumber.')
            else:self.refresh()
        request.receivedBytesChanged.connect(update);request.totalBytesChanged.connect(update);request.stateChanged.connect(update);request.accept();self.show();self.refresh()
    def active(self):return bool(self.jobs) or any(not req.isFinished() for req in self.native.values())
    def shutdown(self):
        self.timer.stop();self.save()
        if self.tray:self.tray.hide()
        for req in self.native.values():
            if not req.isFinished():req.cancel()
        self.hide()
    def closeEvent(self,event):self.hide();event.ignore()
