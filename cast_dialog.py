"""LAN Cast controls and Windows Miracast handoff; no automatic firewall changes."""
import os,ipaddress
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtNetwork import QNetworkInterface,QAbstractSocket
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QComboBox,QLineEdit,QApplication
from lan_cast import ShareSession
from cast_devices import DiscoverCast,CastAction

def lan_addresses():
    values=[]
    for a in QNetworkInterface.allAddresses():
        if a.protocol()==QAbstractSocket.IPv4Protocol:
            value=a.toString();ip=ipaddress.ip_address(value)
            if ip.is_private and not ip.is_loopback and not ip.is_link_local:values.append(value)
    return sorted(set(values)) or ['127.0.0.1']

def windows_mirror():
    if os.name!='nt':raise ValueError('Miracast Win+K tersedia melalui Windows.')
    import ctypes
    user=ctypes.windll.user32
    user.keybd_event(0x5B,0,0,0);user.keybd_event(0x4B,0,0,0);user.keybd_event(0x4B,0,2,0);user.keybd_event(0x5B,0,2,0)

class CastDialog(QDialog):
    def __init__(self,owner,source,title='',cues=(),position=0.,live=False):
        super().__init__(owner,Qt.Window);self.owner=owner;self.source=str(source);self.title=title or Path(source).name;self.cues=list(cues);self.position=position;self.live=live;self.share=None;self.job=None;self.discovery=None;self.browser=None;self.devices=[];self.device=None;self.pending_stop=False;self.closing=False
        self.setWindowTitle('Cyber80 • Cast / Mirroring LAN');self.resize(740,460);box=QVBoxLayout(self);label=QLabel(self.title);label.setTextFormat(Qt.PlainText);box.addWidget(label)
        row=QHBoxLayout();box.addLayout(row);row.addWidget(QLabel('Alamat LAN komputer'));self.ip=QComboBox();self.ip.addItems(lan_addresses());row.addWidget(self.ip)
        b=QPushButton('Buat tautan HP / browser');b.clicked.connect(self.start_share);row.addWidget(b);b=QPushButton('Salin tautan');b.clicked.connect(lambda:QApplication.clipboard().setText(self.link.text()));row.addWidget(b)
        self.link=QLineEdit();self.link.setReadOnly(True);box.addWidget(self.link)
        row=QHBoxLayout();box.addLayout(row);self.list=QComboBox();row.addWidget(self.list,1);b=QPushButton('Cari Google Cast / DLNA');b.clicked.connect(self.discover);row.addWidget(b)
        row=QHBoxLayout();box.addLayout(row);row.addWidget(QLabel('Jenis media'));self.mime=QComboBox();self.mime.setEditable(True);self.mime.addItems(['Otomatis','video/mp4','application/vnd.apple.mpegurl','video/webm','audio/mpeg','audio/mp4']);row.addWidget(self.mime)
        row=QHBoxLayout();box.addLayout(row)
        for text,fn in [('Cast ke perangkat',self.cast),('Play',lambda:self.command('play')),('Pause',lambda:self.command('pause')),('Hentikan Cast',self.stop),('Mirroring Windows • Win+K',self.mirror)]:
            b=QPushButton(text);b.clicked.connect(fn);row.addWidget(b)
        note=QLabel('Chromecast/Google TV memakai Google Cast; Smart TV harus mendukung DLNA MediaRenderer. HP bisa membuka tautan di browser lalu menekan Play. Android TV/HP tertentu memerlukan aplikasi penerima. Perangkat dan PC harus satu jaringan, Wi-Fi guest/AP isolation dapat menghalangi.\nFile/siaran dikirim sebagai media asli, tanpa transcode otomatis. Codec harus didukung perangkat. Untuk FLV/codec yang ditolak, ekspor MP4 H.264/AAC melalui Video Studio. Subtitle file saat Cast dimulai dikirim sebagai WebVTT ke browser/Google Cast; DLNA dan subtitle TV live bergantung penerima.\nUntuk mencerminkan seluruh tampilan beserta subtitle TV/efek pemain, gunakan Mirroring Windows (Win+K) ke penerima Miracast. Windows/perangkat harus mendukung Miracast; fitur ini membuka panel Windows, bukan memasangkan otomatis. Tidak ada jaminan semua Smart TV/HP mendukung semua protokol.');note.setWordWrap(True);box.addWidget(note)
        self.status=QLabel('Belum ada media dibagikan. Tautan hanya aktif setelah tombol berbagi/Cast ditekan.');self.status.setTextFormat(Qt.PlainText);self.status.setWordWrap(True);box.addWidget(self.status)
    def start_share(self):
        try:
            if self.share:self.share.close()
            self.share=ShareSession(self.source,cues=self.cues);self.link.setText(self.share.url(self.ip.currentText()));self.status.setText('Tautan LAN aktif. Buka di browser HP/perangkat. Izinkan firewall hanya pada jaringan privat jika diminta Windows.')
        except Exception as exc:self.status.setText(str(exc))
    def discover(self):
        if self.discovery or self.job:return
        if self.device:self.stop();self.status.setText('Hentikan Cast aktif sebelum mencari perangkat lagi.');return
        self.release_devices();self.list.clear();self.discovery=DiscoverCast();self.discovery.found.connect(self.found);self.discovery.failed.connect(self.status.setText);self.discovery.finished.connect(self.discovery_finished);self.status.setText('Mencari perangkat pada jaringan lokal …');self.discovery.start()
    def found(self,devices,browser):
        self.devices=devices;self.browser=browser
        for d in devices:self.list.addItem(d['name']+' • '+d['kind'],d)
        self.status.setText(f'{len(devices)} perangkat ditemukan. Jika kosong gunakan tautan browser HP atau Miracast.')
    def discovery_finished(self):
        self.discovery.deleteLater();self.discovery=None
        if self.closing:self.release_devices()
    def cast(self):
        if self.job:return
        device=self.list.currentData()
        if not device:self.status.setText('Cari dan pilih perangkat terlebih dahulu.');return
        if not self.share:self.start_share()
        if not self.share:return
        self.device=device;ip=self.ip.currentText();mime=self.share.mime if self.mime.currentText()=='Otomatis' else self.mime.currentText()
        job=CastAction(device,'load',self.share.media_url(ip),mime,self.title,self.position,self.share.url(ip,'subtitle.vtt') if self.share.subtitle else '',self.live);self.run_job(job)
    def run_job(self,job):
        self.job=job;job.completed.connect(self.status.setText);job.failed.connect(self.status.setText);job.finished.connect(self.action_finished);job.start()
    def action_finished(self):
        action=self.job.action;self.job.deleteLater();self.job=None
        if self.pending_stop and action!='stop' and self.device:self.pending_stop=False;self.command('stop')
        elif action=='stop':
            self.pending_stop=False;self.device=None
            if self.closing:self.release_devices()
    def command(self,action):
        if self.job or not self.device:return
        self.run_job(CastAction(self.device,action))
    def stop(self):
        if self.share:self.share.close();self.share=None;self.link.clear()
        if self.job:
            self.pending_stop=True;self.job.requestInterruption();self.status.setText('Menunggu perintah aktif berhenti, lalu menghentikan penerima …')
        elif self.device:self.command('stop')
        else:self.status.setText('Tautan berbagi dihentikan.')
    def mirror(self):
        try:windows_mirror();self.status.setText('Panel mirroring Windows dibuka. Pilih penerima Miracast yang kompatibel.')
        except ValueError as exc:self.status.setText(str(exc))
    def release_devices(self):
        if self.browser:
            try:self.browser.stop_discovery()
            except Exception:pass
            self.browser=None
        for d in self.devices:
            if d['kind']=='chromecast':
                try:d['cast'].disconnect(timeout=1)
                except Exception:pass
        self.devices=[]
    def shutdown(self):
        self.closing=True;self.stop()
        if self.job or self.discovery:return False
        self.release_devices();self.hide();return True
    def closeEvent(self,event):self.shutdown();self.hide();event.ignore()
