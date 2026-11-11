import os, sys, tempfile, subprocess, wave, json
from pathlib import Path
# Load bundled VLC before importing python-vlc.
ROOT=Path(getattr(sys,'_MEIPASS',Path(__file__).parent))
vlcdir=ROOT/'vlc'
if vlcdir.is_dir():
    os.environ['PYTHON_VLC_LIB_PATH']=str(vlcdir/'libvlc.dll')
    os.environ['PYTHON_VLC_MODULE_PATH']=str(vlcdir/'plugins')
    os.environ['VLC_PLUGIN_PATH']=str(vlcdir/'plugins')
    os.environ['PATH']=str(vlcdir)+os.pathsep+os.environ.get('PATH','')
    if hasattr(os,'add_dll_directory'): DLL_HANDLE=os.add_dll_directory(str(vlcdir))
import vlc, imageio_ffmpeg
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtWidgets import (QApplication,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QPushButton,
    QFileDialog,QLabel,QLineEdit,QComboBox,QSlider,QTableWidget,QTableWidgetItem,QMessageBox,QSpinBox)
from core import Cue, transcribe, srt
from credentials import save_key, load_key, delete_key

class Job(QThread):
    progress=Signal(str)
    result=Signal(object)
    failed=Signal(str)
    def __init__(self, path, key, model, language, google, glossary):
        super().__init__(); self.args=(path,key,model,language,google,glossary)
    def run(self):
        path,key,model,lang,google,glossary=self.args
        cues=[]
        try:
            ff=imageio_ffmpeg.get_ffmpeg_exe()
            flags={'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {}
            with tempfile.TemporaryDirectory(prefix='linguaplayer-') as tmp:
                offset=0
                while not self.isInterruptionRequested():
                    self.progress.emit(f'Mengekstrak audio {offset//60:02}:{offset%60:02} …')
                    out=str(Path(tmp)/'chunk.wav')
                    p=subprocess.Popen([ff,'-v','error','-y','-ss',str(offset),'-i',path,'-t','45','-vn','-ac','1','-ar','16000',out],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,**flags)
                    while True:
                        try: _,err=p.communicate(timeout=.2); break
                        except subprocess.TimeoutExpired:
                            if self.isInterruptionRequested():
                                p.kill(); p.communicate(); raise InterruptedError('Dibatalkan')
                    if p.returncode: raise RuntimeError('FFmpeg tidak dapat membaca audio. Video mungkin tanpa audio, rusak, atau format tidak didukung.')
                    with wave.open(out,'rb') as w: duration=w.getnframes()/w.getframerate()
                    if duration < .1: break
                    self.progress.emit(f'Mentranskrip / menerjemahkan {offset//60:02}:{offset%60:02} …')
                    cues.extend(transcribe(Path(out).read_bytes(),key,model,lang,duration,offset,google,self.isInterruptionRequested,glossary))
                    if duration < 44.95: break
                    offset+=45
            if self.isInterruptionRequested(): raise InterruptedError('Dibatalkan')
            self.result.emit(cues)
        except Exception as e: self.failed.emit(str(e))

class Window(QMainWindow):
    def __init__(self):
        super().__init__(); self.setWindowTitle('LinguaPlayer • Video & AI Subtitle'); self.resize(1200,850)
        self.path=''; self.job=None; self.cues=[]
        self.engine=vlc.Instance('--no-video-title-show'); self.player=self.engine.media_player_new()
        root=QWidget(); self.setCentralWidget(root); layout=QVBoxLayout(root)
        title=QLabel('LinguaPlayer  |  Video • Speech to Text • Terjemahan'); title.setStyleSheet('font-size:22px;font-weight:bold'); layout.addWidget(title)
        self.video=QWidget(); self.video.setMinimumHeight(280); self.video.setStyleSheet('background:black'); layout.addWidget(self.video,1)
        if sys.platform=='win32': self.player.set_hwnd(int(self.video.winId()))
        elif sys.platform=='darwin': self.player.set_nsobject(int(self.video.winId()))
        else: self.player.set_xwindow(int(self.video.winId()))
        self.subtitle=QLabel('Buka video untuk mulai'); self.subtitle.setWordWrap(True); self.subtitle.setAlignment(Qt.AlignCenter); self.subtitle.setTextFormat(Qt.PlainText)
        self.subtitle.setStyleSheet('font-size:20px;color:#ffe18a;background:#131b2c;padding:10px'); layout.addWidget(self.subtitle)
        row=QHBoxLayout(); layout.addLayout(row)
        self.open=self.button(row,'Buka video',self.open_video); self.button(row,'▶ / Pause',self.play)
        self.button(row,'Stop',self.player.stop)
        self.seek=QSlider(Qt.Horizontal); self.seek.setRange(0,1000); self.seek.sliderReleased.connect(lambda:self.player.set_position(self.seek.value()/1000)); row.addWidget(self.seek,1)
        volume=QSlider(Qt.Horizontal); volume.setRange(0,100); volume.setValue(80); volume.setMaximumWidth(100); volume.valueChanged.connect(self.player.audio_set_volume); row.addWidget(QLabel('Volume'));row.addWidget(volume);self.player.audio_set_volume(80)
        row=QHBoxLayout();layout.addLayout(row)
        self.key=QLineEdit(os.getenv('GEMINI_API_KEY',''));self.key.setEchoMode(QLineEdit.Password);self.key.setPlaceholderText('Gemini API key');row.addWidget(self.key)
        self.model=QLineEdit('gemini-2.5-flash');self.model.setMaximumWidth(170);row.addWidget(self.model)
        self.lang=QComboBox();self.lang.setEditable(True)
        for name,code in [('Indonesia','id'),('English','en'),('Mandarin','zh-CN'),('Jepang','ja'),('Korea','ko'),('Arab','ar'),('Spanyol','es'),('Prancis','fr'),('Jerman','de'),('Hindi','hi'),('Portugis','pt'),('Rusia','ru'),('Thai','th'),('Vietnam','vi')]: self.lang.addItem(name,code)
        row.addWidget(self.lang)
        self.google=QLineEdit(os.getenv('GOOGLE_TRANSLATE_API_KEY',''));self.google.setEchoMode(QLineEdit.Password);self.google.setPlaceholderText('Google Translate key (opsional)');row.addWidget(self.google)
        row=QHBoxLayout();layout.addLayout(row)
        self.button(row,'Simpan API key di Windows',self.save_keys);self.button(row,'Hapus key tersimpan',self.delete_keys)
        self.glossary=QLineEdit();self.glossary.setPlaceholderText('Kamus ejaan: nama orang, merek, istilah khusus (untuk transkripsi/Gemini)');layout.addWidget(self.glossary)
        self.generate=self.button(row,'Buat subtitle online',self.process);self.cancel=self.button(row,'Batalkan',self.cancel_job);self.cancel.setEnabled(False)
        self.button(row,'Buka SRT offline',self.import_srt);self.button(row,'Ekspor SRT',self.export);self.button(row,'Simpan proyek',self.save);self.load=self.button(row,'Buka proyek',self.load_project)
        row.addWidget(QLabel('Offset subtitle (ms)'));self.offset=QSpinBox();self.offset.setRange(-600000,600000);self.offset.setSingleStep(100);row.addWidget(self.offset)
        self.mode=QComboBox();self.mode.addItems(['Bilingual','Terjemahan','Asli']);row.addWidget(self.mode)
        self.table=QTableWidget(0,4);self.table.setHorizontalHeaderLabels(['Mulai (detik)','Akhir (detik)','Ucapan asli','Terjemahan']);self.table.horizontalHeader().setStretchLastSection(True);self.table.setColumnWidth(2,360);self.table.setColumnWidth(3,360);layout.addWidget(self.table)
        self.table.itemChanged.connect(self.edited);self.table.cellDoubleClicked.connect(self.jump)
        self.status=QLabel('Audio dikirim ke Google saat Anda menekan Buat subtitle online. Akurasi perlu ditinjau.');self.status.setWordWrap(True);layout.addWidget(self.status)
        try:
            self.key.setText(load_key('Gemini') or self.key.text());self.google.setText(load_key('GoogleTranslate') or self.google.text())
        except Exception:pass
        self.timer=QTimer(self);self.timer.timeout.connect(self.tick);self.timer.start(100)
        self.setStyleSheet('QMainWindow,QWidget{background:#111827;color:#e5e7eb} QPushButton,QLineEdit,QComboBox,QSpinBox{padding:7px;background:#25334b;border:1px solid #41516c;border-radius:5px} QTableWidget{background:#172237} QPushButton:disabled{color:#6b7280}')
    def button(self,row,label,fn):
        b=QPushButton(label);b.clicked.connect(fn);row.addWidget(b);return b
    def save_keys(self):
        try:
            if not self.key.text().strip():raise ValueError('Isi Gemini API key terlebih dahulu.')
            save_key('Gemini',self.key.text().strip())
            if self.google.text().strip():save_key('GoogleTranslate',self.google.text().strip())
            else:delete_key('GoogleTranslate')
            self.status.setText('API key disimpan di Windows Credential Manager dan akan terisi otomatis saat aplikasi dibuka lagi.')
        except Exception as e:self.error(str(e))
    def delete_keys(self):
        try:
            delete_key('Gemini');delete_key('GoogleTranslate');self.key.clear();self.google.clear()
            self.status.setText('API key tersimpan telah dihapus.')
        except Exception as e:self.error(str(e))
    def error(self,message): QMessageBox.warning(self,'LinguaPlayer',message)
    def open_video(self):
        p,_=QFileDialog.getOpenFileName(self,'Pilih video','','Semua file (*.*)')
        if p:
            self.path=p;self.player.set_media(self.engine.media_new_path(p));self.player.play();self.fill([]);self.status.setText(Path(p).name)
    def play(self):
        if self.path: self.player.pause() if self.player.is_playing() else self.player.play()
    def process(self):
        if not self.path or not self.key.text().strip(): return self.error('Buka video dan isi Gemini API key.')
        if QMessageBox.question(self,'Proses online','Audio video akan dikirim ke Google. Pemakaian API dapat dikenakan biaya. Lanjutkan?')!=QMessageBox.Yes: return
        lang=self.lang.currentData() if self.lang.currentText()==self.lang.itemText(self.lang.currentIndex()) else self.lang.currentText().strip()
        self.job=Job(self.path,self.key.text().strip(),self.model.text().strip(),lang,self.google.text().strip(),self.glossary.text().strip())
        self.job.progress.connect(self.status.setText);self.job.result.connect(self.done);self.job.failed.connect(self.error);self.job.finished.connect(self.finished)
        self.open.setEnabled(False);self.load.setEnabled(False);self.generate.setEnabled(False);self.cancel.setEnabled(True);self.job.start()
    def cancel_job(self):
        if self.job: self.job.requestInterruption();self.status.setText('Membatalkan; menunggu permintaan API aktif selesai (maks. 120 detik).')
    def finished(self):
        self.open.setEnabled(True);self.load.setEnabled(True);self.generate.setEnabled(True);self.cancel.setEnabled(False);self.job.deleteLater();self.job=None
    def done(self,cues): self.fill(cues);self.status.setText(f'{len(cues)} subtitle selesai. Koreksi teks/timing pada tabel; klik dua kali untuk menuju adegan.')
    def fill(self,cues):
        self.cues=cues;self.table.blockSignals(True);self.table.setRowCount(len(cues))
        for i,c in enumerate(cues):
            for j,v in enumerate((c.start,c.end,c.source,c.target)):self.table.setItem(i,j,QTableWidgetItem(str(v)))
        self.table.blockSignals(False)
    def edited(self,item):
        r=item.row();c=self.cues[r]
        try:
            a=float(self.table.item(r,0).text());b=float(self.table.item(r,1).text())
            import math
            if not math.isfinite(a+b) or a<0 or b<=a: raise ValueError()
            c.start=a;c.end=b;c.source=self.table.item(r,2).text();c.target=self.table.item(r,3).text()
        except ValueError:
            self.error('Waktu harus angka positif dan akhir lebih besar dari mulai.');self.fill(self.cues)
    def jump(self,row,col): self.player.set_time(int(self.cues[row].start*1000))
    def tick(self):
        if not self.seek.isSliderDown():self.seek.setValue(max(0,int(self.player.get_position()*1000)))
        t=(self.player.get_time()-self.offset.value())/1000
        cue=next((c for c in self.cues if c.start<=t<c.end),None)
        self.subtitle.setText(('\n'.join(filter(None,[cue.source,cue.target])) if self.mode.currentIndex()==0 else (cue.target or cue.source) if self.mode.currentIndex()==1 else cue.source) if cue else '')
        if self.player.get_state()==vlc.State.Error:self.status.setText('VLC gagal memutar video. Periksa codec, DRM, atau kerusakan file.')
    def import_srt(self):
        p,_=QFileDialog.getOpenFileName(self,'Buka SRT offline','','SRT (*.srt)')
        if p:
            try:
                from core import parse_srt
                self.fill(parse_srt(Path(p).read_text(encoding='utf-8-sig')))
                self.status.setText('SRT dibuka offline. Pilih video dengan membuka video lebih dahulu.')
            except Exception as e:self.error(str(e))
    def export(self):
        if not self.cues:return self.error('Belum ada subtitle.')
        p,_=QFileDialog.getSaveFileName(self,'Simpan SRT','subtitle.srt','SRT (*.srt)')
        if p:
            try:
                shift=self.offset.value()/1000
                cues=[Cue(max(0,c.start+shift),max(.001,c.end+shift),c.source,c.target) for c in self.cues if c.end+shift>0]
                Path(p).write_text(srt(sorted(cues,key=lambda c:c.start),self.mode.currentIndex()!=2),encoding='utf-8-sig')
            except OSError as e:self.error(str(e))
    def save(self):
        p,_=QFileDialog.getSaveFileName(self,'Simpan proyek','subtitle.lingua.json','JSON (*.json)')
        if p:
            try:Path(p).write_text(json.dumps({'video':self.path,'offset_ms':self.offset.value(),'cues':[vars(c) for c in self.cues]},ensure_ascii=False,indent=2),encoding='utf-8')
            except OSError as e:self.error(str(e))
    def load_project(self):
        p,_=QFileDialog.getOpenFileName(self,'Buka proyek','','JSON (*.json)')
        if p:
            try:
                from core import validate
                data=json.loads(Path(p).read_text(encoding='utf-8'));cues=validate(data['cues'],1e12)
                if not Path(data['video']).is_file():raise ValueError('Video asli tidak ditemukan. Lokasi video harus tetap sama.')
                self.path=data['video'];self.player.set_media(self.engine.media_new_path(self.path));self.fill(cues);self.offset.setValue(int(data.get('offset_ms',0)));self.player.play()
            except Exception as e:self.error(str(e))
    def closeEvent(self,event):
        if self.job and self.job.isRunning():self.cancel_job();self.error('Tunggu pembatalan selesai sebelum menutup aplikasi.');event.ignore();return
        self.player.stop();self.player.release();self.engine.release();event.accept()

if __name__=='__main__':
    app=QApplication(sys.argv)
    try:
        w=Window();w.show()
        if '--self-test' in sys.argv:
            output=Path(sys.argv[sys.argv.index('--self-test')+1])
            def self_test():
                try:
                    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-version'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
                    import uuid
                    test_name='SelfTest-'+str(uuid.uuid4())
                    try:
                        save_key(test_name,'temporary-test-value');assert load_key(test_name)=='temporary-test-value'
                    finally:delete_key(test_name)
                    assert load_key(test_name)==''
                    output.write_text(json.dumps({'credential_manager':'PASS','qt_window':'PASS','vlc_version':vlc.libvlc_get_version().decode(),'ffmpeg':'PASS'}),encoding='utf-8')
                    w.close();app.exit(0)
                except Exception as e:
                    output.write_text(json.dumps({'error':str(e)}),encoding='utf-8');app.exit(1)
            QTimer.singleShot(500,self_test)
        sys.exit(app.exec())
    except Exception as e:QMessageBox.critical(None,'Gagal mulai',f'{e}\nPastikan VLC 64-bit terpasang atau folder vlc dibundel.');sys.exit(1)
