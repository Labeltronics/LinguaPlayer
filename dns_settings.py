"""Explicit Windows adapter DNS control; no automatic elevation or global filtering changes."""
import os,sys,json,subprocess
from pathlib import Path
from PySide6.QtCore import QProcess
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLabel,QComboBox,QPushButton,QMessageBox
SERVERS=('1.1.1.1','1.0.0.1','2606:4700:4700::1111','2606:4700:4700::1001')
def powershell_path():return str(Path(os.environ.get('SystemRoot',r'C:\Windows'))/'System32'/'WindowsPowerShell'/'v1.0'/'powershell.exe')
def script_path():return Path(getattr(sys,'_MEIPASS',Path(__file__).parent))/'cloudflare_dns.ps1'
def command(mode,index=None):
    if mode not in ('List','Plan','Apply','Dhcp'):raise ValueError('Mode DNS tidak sah.')
    args=['-NoProfile','-ExecutionPolicy','Bypass','-File',str(script_path()),'-Mode',mode]
    if mode in ('Apply','Dhcp'):
        if not isinstance(index,int) or isinstance(index,bool) or not 0<index<2**31:raise ValueError('Pilih adaptor jaringan yang sah.')
        args+=['-InterfaceIndex',str(index)]
    return args
class DnsDialog(QDialog):
    def __init__(self,parent):
        super().__init__(parent);self.setWindowTitle('Cloudflare DNS 1.1.1.1 • Windows');self.resize(760,330);self.rows=[];self.process=None
        box=QVBoxLayout(self);note=QLabel('Pilih adaptor yang Anda gunakan. DNS Cloudflare biasa (bukan Families/filter): 1.1.1.1 dan 1.0.0.1, serta padanan IPv6. Perubahan berlaku untuk Windows pada adaptor terpilih, bukan hanya Cyber80. Memerlukan UAC Administrator. Tidak menonaktifkan HTTPS, sandbox, Defender atau firewall.');note.setWordWrap(True);box.addWidget(note)
        self.adapters=QComboBox();box.addWidget(self.adapters);self.status=QLabel();self.status.setWordWrap(True);box.addWidget(self.status);row=QHBoxLayout();box.addLayout(row)
        for label,fn in [('Periksa DNS',self.refresh),('Terapkan 1.1.1.1',lambda:self.apply('Apply')),('DNS otomatis / DHCP',lambda:self.apply('Dhcp'))]:
            button=QPushButton(label);button.clicked.connect(fn);row.addWidget(button)
        text=QLabel('Catat DNS lama sebelum mengubah. Tombol DHCP bukan pemulihan DNS khusus sebelumnya. DNS-over-HTTPS belum dikonfigurasi di sini. VPN/proxy dan kebijakan jaringan dapat memakai resolver lain. Tidak menjamin blokir situs terbuka.');text.setWordWrap(True);box.addWidget(text);self.refresh()
    def refresh(self):
        if sys.platform!='win32':self.status.setText('Pengaturan ini hanya tersedia di Windows.');return
        if self.process and self.process.state()!=QProcess.NotRunning:return
        self.status.setText('Membaca adaptor dan DNS Windows…');self.process=QProcess(self);self.process.finished.connect(self.loaded);self.process.errorOccurred.connect(lambda *args:self.status.setText('Tidak dapat membaca pengaturan jaringan.'));self.process.start(powershell_path(),command('List'))
    def loaded(self,code,*args):
        if code:self.status.setText('Pembacaan DNS gagal. Periksa izin atau pengaturan jaringan Windows.');return
        try:
            rows=json.loads(bytes(self.process.readAllStandardOutput()).decode('utf-8-sig'));rows=[rows] if isinstance(rows,dict) else rows
            selected=self.adapters.currentData();self.adapters.clear();self.rows=rows
            for item in rows:
                self.adapters.addItem(f"{item['name']} — {', '.join(item.get('servers',[])) or 'DNS belum tersedia'}",int(item['index']))
            i=self.adapters.findData(selected)
            if i>=0:self.adapters.setCurrentIndex(i)
            self.status.setText('Daftar menampilkan DNS yang benar-benar terpasang. Pilih adaptor, lalu terapkan atau periksa ulang setelah UAC selesai.')
        except (ValueError,TypeError,KeyError):self.status.setText('Respons pengaturan DNS tidak dapat dibaca.')
    def apply(self,mode):
        index=self.adapters.currentData()
        if index is None:self.status.setText('Tidak ada adaptor yang dipilih.');return
        text=('Ganti DNS adaptor ini dengan Cloudflare untuk seluruh Windows? Catat DNS lama yang terlihat di atas.' if mode=='Apply' else 'Kembalikan adaptor ini ke DNS otomatis/DHCP? Ini tidak memulihkan DNS khusus lama.')
        if QMessageBox.question(self,'Ubah DNS Windows',text)!=QMessageBox.Yes:return
        try:
            import ctypes
            from ctypes import wintypes
            execute=ctypes.windll.shell32.ShellExecuteW;execute.argtypes=[wintypes.HWND,wintypes.LPCWSTR,wintypes.LPCWSTR,wintypes.LPCWSTR,wintypes.LPCWSTR,ctypes.c_int];execute.restype=ctypes.c_void_p
            result=execute(None,'runas',powershell_path(),subprocess.list2cmdline(command(mode,int(index))),None,1) or 0
            self.status.setText('Permintaan Administrator dikirim. Setelah selesai, tekan Periksa DNS untuk melihat hasilnya.' if result>32 else 'Permintaan dibatalkan atau tidak dapat dijalankan; DNS belum dikonfirmasi berubah.')
        except (OSError,ValueError):self.status.setText('Tidak dapat membuka pengaturan DNS Administrator.')
    def closeEvent(self,event):
        if self.process and self.process.state()!=QProcess.NotRunning:self.process.kill();self.process.waitForFinished(1000)
        event.accept()
