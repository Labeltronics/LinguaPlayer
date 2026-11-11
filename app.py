import os, sys, tempfile, subprocess, wave, json, time
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
from PySide6.QtCore import Qt, QThread, Signal, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QApplication,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QPushButton,
    QFileDialog,QLabel,QLineEdit,QComboBox,QSlider,QTableWidget,QTableWidgetItem,QMessageBox,QSpinBox,QFrame,QDialog,QDockWidget)
from core import Cue, transcribe, srt
from credentials import save_key, load_key, delete_key
from stereo import VideoSurface
from player_extras import PlayerExtras

class Job(QThread):
    progress=Signal(str)
    result=Signal(object)
    chunk_ready=Signal(object,float)
    failed=Signal(str)
    def __init__(self, path, key, model, language, google, glossary, resume_from=0, initial_cues=None):
        super().__init__(); self.args=(path,key,model,language,google,glossary)
        self.resume_from=resume_from;self.start_offset=resume_from;self.initial_cues=list(initial_cues or [])
    def run(self):
        path,key,model,lang,google,glossary=self.args
        cues=list(self.initial_cues)
        try:
            ff=imageio_ffmpeg.get_ffmpeg_exe()
            flags={'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {}
            with tempfile.TemporaryDirectory(prefix='linguaplayer-') as tmp:
                offset=self.start_offset
                while not self.isInterruptionRequested():
                    self.progress.emit(f'Mengekstrak audio {offset//60:02}:{offset%60:02} …')
                    out=str(Path(tmp)/'chunk.wav')
                    p=subprocess.Popen([ff,'-v','error','-y','-ss',str(offset),'-i',path,'-t','10','-vn','-ac','1','-ar','16000',out],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,**flags)
                    while True:
                        try: _,err=p.communicate(timeout=.2); break
                        except subprocess.TimeoutExpired:
                            if self.isInterruptionRequested():
                                p.kill(); p.communicate(); raise InterruptedError('Dibatalkan')
                    if p.returncode: raise RuntimeError('FFmpeg tidak dapat membaca audio. Video mungkin tanpa audio, rusak, atau format tidak didukung.')
                    with wave.open(out,'rb') as w: duration=w.getnframes()/w.getframerate()
                    if duration < .1: break
                    self.progress.emit(f'Mentranskrip / menerjemahkan {offset//60:02}:{offset%60:02} …')
                    chunk=transcribe(Path(out).read_bytes(),key,model,lang,duration,offset,google,self.isInterruptionRequested,glossary,progress=self.progress.emit,timeout=180)
                    cues.extend(chunk);self.resume_from=offset+10;self.chunk_ready.emit(chunk,offset+duration)
                    if duration < 9.95: break
                    offset+=10
            if self.isInterruptionRequested(): raise InterruptedError('Dibatalkan')
            self.result.emit(cues)
        except Exception as e: self.failed.emit(str(e))

class PictureWindow(QDialog):
    returning=Signal()
    def __init__(self,owner):
        super().__init__(None,Qt.Window|Qt.WindowStaysOnTopHint)
        self.setWindowTitle('LinguaPlayer • Picture in Picture');self.resize(520,380)
        self.setMinimumSize(300,230)
        self.box=QVBoxLayout(self);self.box.setContentsMargins(4,4,4,4)
        self.caption=QLabel();self.caption.setWordWrap(True);self.caption.setAlignment(Qt.AlignCenter);self.caption.setTextFormat(Qt.PlainText)
        self.caption.setStyleSheet('color:#ffe18a;font-size:16px;padding:5px;background:#111827')
        controls=QHBoxLayout();self.box.addWidget(self.caption);self.box.addLayout(controls)
        owner.button(controls,'▶ / Pause',owner.play)
        owner.button(controls,'Kembali ke pemutar',owner.leave_pip)
        self.setStyleSheet('QDialog{background:black} QPushButton{padding:7px}')
    def closeEvent(self,event):
        event.ignore();self.returning.emit()

class Window(PlayerExtras,QMainWindow):
    def __init__(self):
        super().__init__(); self.setWindowTitle('LinguaPlayer • Video & AI Subtitle'); self.resize(1200,850)
        self.retry_context=None;self.resume_offset=0
        self.path=''; self.job=None; self.cues=[];self.coverage=0.;self.processing=False;self.buffering=False;self.want_play=False
        self.pip=None;self.pending_seek=None;self.pending_pause=False;self.closing=False;self.playback_error_reported=False
        self.log_path=Path(os.getenv('LOCALAPPDATA',tempfile.gettempdir()))/'LinguaPlayer'/'playback.log'
        self.log_path.parent.mkdir(parents=True,exist_ok=True)
        self.engine=self.make_engine(0);self.player=self.engine.media_player_new()
        root=QWidget(); self.setCentralWidget(root); layout=QVBoxLayout(root)
        title=QLabel('LinguaPlayer  |  Video • Speech to Text • Terjemahan'); title.setWordWrap(True);title.setStyleSheet('font-size:18px;font-weight:bold'); layout.addWidget(title)
        self.video_host=QWidget();self.host_layout=QVBoxLayout(self.video_host);self.host_layout.setContentsMargins(0,0,0,0)
        self.video=VideoSurface();self.video.setMinimumSize(160,160)
        self.video.setAttribute(Qt.WA_NativeWindow,True)
        self.video.setAttribute(Qt.WA_DontCreateNativeAncestors,True)
        self.video.setAttribute(Qt.WA_NoSystemBackground,True)
        self.video.setAutoFillBackground(False)
        self.host_layout.addWidget(self.video);layout.addWidget(self.video_host,1)
        self.bind_video()
        self.subtitle=QLabel('Buka video untuk mulai'); self.subtitle.setWordWrap(True); self.subtitle.setAlignment(Qt.AlignCenter); self.subtitle.setTextFormat(Qt.PlainText)
        self.subtitle.setStyleSheet('font-size:20px;color:#ffe18a;background:#131b2c;padding:10px'); layout.addWidget(self.subtitle)
        row=QHBoxLayout(); layout.addLayout(row)
        self.open=self.button(row,'Buka video',self.open_video); self.button(row,'▶ / Pause',self.play)
        self.button(row,'Stop',self.stop);self.pip_button=self.button(row,'PiP',self.toggle_pip)
        self.renderer=QComboBox();self.renderer.addItems(['Kompatibel (CPU / GDI)','Otomatis (GPU)','Direct3D11'])
        if sys.platform!='win32':self.renderer.setCurrentIndex(1)
        self.renderer.currentIndexChanged.connect(self.change_renderer)
        render_row=QHBoxLayout();layout.addLayout(render_row);render_row.addWidget(self.renderer);render_row.addStretch()
        self.button(render_row,'Log video',lambda:QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.log_path))))
        self.seek=QSlider(Qt.Horizontal); self.seek.setRange(0,1000); self.seek.sliderReleased.connect(lambda:self.player.set_position(self.seek.value()/1000)); row.addWidget(self.seek,1)
        volume=QSlider(Qt.Horizontal); volume.setRange(0,100); volume.setValue(80); volume.setMaximumWidth(100); volume.valueChanged.connect(lambda value:self.player.audio_set_volume(value)); row.addWidget(QLabel('Volume'));row.addWidget(volume);self.player.audio_set_volume(80);self.volume=volume
        self.ai_panel=QWidget();ai_layout=QVBoxLayout(self.ai_panel)
        row=QHBoxLayout();ai_layout.addLayout(row)
        self.key=QLineEdit(os.getenv('GEMINI_API_KEY',''));self.key.setEchoMode(QLineEdit.Password);self.key.setPlaceholderText('Gemini API key');row.addWidget(self.key)
        self.model=QLineEdit('gemini-3.5-flash-lite');self.model.setMaximumWidth(170);row.addWidget(self.model)
        self.lang=QComboBox();self.lang.setEditable(True);self.lang.setToolTip('Pilih bahasa atau ketik bahasa/kode lain. Untuk Google Translate gunakan kode bahasa yang didukung API.')
        for name,code in [('Indonesia','id'),('English','en'),('Mandarin','zh-CN'),('Jepang','ja'),('Korea','ko'),('Arab','ar'),('Spanyol','es'),('Prancis','fr'),('Jerman','de'),('Hindi','hi'),('Portugis','pt'),('Rusia','ru'),('Melayu','ms'),('Italia','it'),('Belanda','nl'),('Turki','tr'),('Thai','th'),('Vietnam','vi')]: self.lang.addItem(name,code)
        self.lang.setCurrentIndex(self.lang.findData('id'))
        row.addWidget(self.lang)
        self.google=QLineEdit(os.getenv('GOOGLE_TRANSLATE_API_KEY',''));self.google.setEchoMode(QLineEdit.Password);self.google.setPlaceholderText('Google Translate nonaktif (Gemini Free Tier)');self.google.setEnabled(False);self.google.hide()
        row=QHBoxLayout();ai_layout.addLayout(row)
        self.button(row,'Simpan API key di Windows',self.save_keys);self.button(row,'Hapus key tersimpan',self.delete_keys)
        row=QHBoxLayout();ai_layout.addLayout(row)
        self.glossary=QLineEdit();self.glossary.setPlaceholderText('Kamus ejaan: nama orang, merek, istilah khusus (untuk transkripsi/Gemini)');ai_layout.addWidget(self.glossary)
        self.generate=self.button(row,'Buat / Lanjutkan subtitle',self.process);self.cancel=self.button(row,'Batalkan',self.cancel_job);self.cancel.setEnabled(False)
        row=QHBoxLayout();ai_layout.addLayout(row)
        self.import_button=self.button(row,'Buka SRT offline',self.import_srt);self.button(row,'Ekspor SRT',self.export);self.button(row,'Simpan proyek',self.save);self.load=self.button(row,'Buka proyek',self.load_project)
        row=QHBoxLayout();ai_layout.addLayout(row)
        row.addWidget(QLabel('Offset subtitle (ms)'));self.offset=QSpinBox();self.offset.setRange(-600000,600000);self.offset.setSingleStep(100);row.addWidget(self.offset)
        self.mode=QComboBox();self.mode.addItems(['Bilingual','Terjemahan','Asli']);self.mode.setCurrentIndex(1);row.addWidget(self.mode)
        self.table=QTableWidget(0,4);self.table.setMinimumHeight(100);self.table.setHorizontalHeaderLabels(['Mulai (detik)','Akhir (detik)','Ucapan asli','Terjemahan']);self.table.horizontalHeader().setStretchLastSection(True);self.table.setColumnWidth(2,360);self.table.setColumnWidth(3,360);ai_layout.addWidget(self.table)
        self.table.itemChanged.connect(self.edited);self.table.cellDoubleClicked.connect(self.jump)
        self.detected=QLabel('Bahasa sumber: deteksi otomatis dari suara → Indonesia (default)');ai_layout.addWidget(self.detected)
        self.api_status=QLabel('AI: siap. Gunakan proyek Free Tier tanpa billing.');self.api_status.setWordWrap(True);ai_layout.addWidget(self.api_status)
        self.status=QLabel('Audio dikirim ke Google saat Anda menekan Buat subtitle online. Akurasi perlu ditinjau.');self.status.setWordWrap(True);layout.addWidget(self.status)
        self.subtitle_dock=QDockWidget('Subtitle & Gemini',self);self.subtitle_dock.setObjectName('subtitle');self.subtitle_dock.setWidget(self.ai_panel);self.addDockWidget(Qt.BottomDockWidgetArea,self.subtitle_dock);self.subtitle_dock.hide()
        try:
            self.key.setText(load_key('Gemini') or self.key.text());self.google.clear()
        except Exception:pass
        self.google.clear()
        self.setup_extras()
        self.timer=QTimer(self);self.timer.timeout.connect(self.tick);self.timer.start(100)
        QTimer.singleShot(0,self.bind_video)
        self.setStyleSheet('QMainWindow,QWidget{background:#111827;color:#e5e7eb} QPushButton,QLineEdit,QComboBox,QSpinBox{padding:7px;background:#25334b;border:1px solid #41516c;border-radius:5px} QTableWidget{background:#172237} QPushButton:disabled{color:#6b7280}')
    def make_engine(self,mode):
        options=['--ignore-config','--no-video-title-show','--no-osd','--video','--audio',
                 '--audio-time-stretch','--no-plugins-cache','--file-logging','--logfile='+str(self.log_path),'--verbose=2']
        if '--self-test' in sys.argv:options+=['--aout=dummy']
        if sys.platform=='win32':
            if vlcdir.is_dir():
                import ctypes
                # Keep VLC decoder dependencies ahead of unrelated Qt/PyInstaller DLLs.
                ctypes.windll.kernel32.SetDllDirectoryW(str(vlcdir))
            if getattr(self,'stereo_on',False):options+=['--avcodec-hw=none','--vout=vmem']
            elif mode==0:options+=['--avcodec-hw=none','--vout=wingdi']
            elif mode==2:options+=['--avcodec-hw=none','--vout=direct3d11']
        engine=vlc.Instance(*options)
        if engine is None:raise RuntimeError('VLC tidak dapat memuat plugin codec yang dibundel.')
        return engine
    def bind_video(self):
        if getattr(self,'stereo_on',False):return
        handle=int(self.video.winId())
        if sys.platform=='win32':self.player.set_hwnd(handle)
        elif sys.platform=='darwin':self.player.set_nsobject(handle)
        else:self.player.set_xwindow(handle)
    def change_renderer(self,index):
        position=max(0,self.player.get_time());state=self.player.get_state()
        active=state in (vlc.State.Playing,vlc.State.Paused,vlc.State.Buffering)
        paused=state==vlc.State.Paused
        self.player.stop();self.player.release();self.engine.release()
        self.engine=self.make_engine(index);self.player=self.engine.media_player_new();self.configure_video_output()
        self.player.audio_set_volume(self.volume.value());self.apply_speed()
        if self.path:
            self.player.set_media(self.engine.media_new_path(self.path))
            if active:self.pending_seek=position;self.pending_pause=paused;self.player.play();self.apply_speed()
        self.status.setText('Mode tampilan: '+self.renderer.currentText())
    def restart_surface(self,position,active,paused):
        if self.closing:return
        self.bind_video()
        if active:
            self.pending_seek=position;self.pending_pause=paused;self.player.play();self.apply_speed()
    def toggle_pip(self):
        if self.pip:return self.leave_pip()
        position=max(0,self.player.get_time());state=self.player.get_state()
        active=state in (vlc.State.Playing,vlc.State.Paused,vlc.State.Buffering);paused=state==vlc.State.Paused
        if active:self.player.stop()
        popup=PictureWindow(self);self.pip=popup;popup.returning.connect(self.leave_pip)
        self.host_layout.removeWidget(self.video);self.video.setMinimumSize(160,90)
        popup.box.insertWidget(0,self.video,1);popup.caption.setText(self.subtitle.text());popup.show();self.video.show()
        self.pip_button.setText('Kembali dari PiP')
        QTimer.singleShot(0,lambda:self.restart_surface(position,active,paused))
    def leave_pip(self):
        if self.pip is None:return
        position=max(0,self.player.get_time());state=self.player.get_state()
        active=not self.closing and state in (vlc.State.Playing,vlc.State.Paused,vlc.State.Buffering)
        paused=state==vlc.State.Paused
        self.player.stop()
        popup=self.pip;self.pip=None;popup.box.removeWidget(self.video)
        self.video.setMinimumSize(160,160);self.host_layout.addWidget(self.video);self.video.show()
        popup.hide();popup.deleteLater();self.pip_button.setText('PiP')
        if not self.closing:QTimer.singleShot(0,lambda:self.restart_surface(position,active,paused))
    def open_path(self,path):
        path=Path(path).resolve()
        if not path.is_file():raise ValueError('File video tidak ditemukan.')
        self.player.stop();self.path=str(path);self.pending_seek=None;self.pending_pause=False;self.playback_error_reported=False
        self.bind_video();self.player.set_media(self.engine.media_new_path(self.path))
        if self.player.play()==-1:raise RuntimeError('VLC gagal memulai video. Coba mode Kompatibel (CPU / GDI).')
        self.fill([]);self.status.setText(path.name)
        self.retry_context=None;self.resume_offset=0
        self.playlist_opened(self.path)
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
        p,_=QFileDialog.getOpenFileName(self,'Pilih video','','Video (*.mp4 *.mkv *.avi *.flv *.ts *.mts *.m2ts *.3gp *.3g2 *.mov *.webm *.wmv *.mpg *.mpeg *.vob *.ogv *.m4v);;Semua file (*.*)')
        if p:
            try:self.open_path(p)
            except Exception as e:self.error(str(e))
    def stop(self):
        self.want_play=False;self.player.stop()
    def play(self):
        if self.processing:
            self.want_play=not self.want_play
            if not self.want_play:self.player.set_pause(1)
            elif not self.buffering:self.player.play()
        elif self.path:self.player.pause() if self.player.is_playing() else self.player.play()
    def process(self):
        if self.job is not None and self.job.isRunning():return
        if not self.path:return self.error('Buka video terlebih dahulu.')
        if not self.key.text().strip():
            self.subtitle_dock.show();self.subtitle_dock.raise_();self.key.setFocus();self.status.setText('Isi Gemini API key, lalu simpan di Windows.');return
        if QMessageBox.question(self,'Proses online','Audio video akan dikirim ke Google. Pemakaian API dapat dikenakan biaya. Lanjutkan?')!=QMessageBox.Yes: return
        lang=self.lang.currentData() if self.lang.currentText()==self.lang.itemText(self.lang.currentIndex()) else self.lang.currentText().strip()
        context=(self.path,self.model.text().strip(),lang,self.glossary.text().strip())
        resume=self.retry_context==context and self.resume_offset>0 and bool(self.cues)
        position=self.resume_offset if resume else 0
        if not resume:self.fill([]);self.coverage=0.
        self.retry_context=context
        self.player.set_pause(1);self.player.set_time(position*1000)
        self.processing=True;self.buffering=True;self.want_play=True
        self.offset.setValue(0);self.lang.setEnabled(False);self.seek.setEnabled(False);self.table.setEnabled(False);self.import_button.setEnabled(False)
        self.job=Job(self.path,self.key.text().strip(),self.model.text().strip(),lang,'',self.glossary.text().strip(),resume_from=position,initial_cues=self.cues)
        self.job.chunk_ready.connect(self.receive_chunk);self.job.progress.connect(self.api_status.setText);self.job.result.connect(self.done);self.job.failed.connect(self.job_error);self.job.finished.connect(self.finished)
        self.open.setEnabled(False);self.load.setEnabled(False);self.generate.setEnabled(False);self.cancel.setEnabled(True);self.job.start()
    def job_error(self,message):
        if self.job is not None:self.resume_offset=self.job.resume_from
        self.want_play=False;self.player.set_pause(1);self.api_status.setText(message)
        if message!='Dibatalkan':self.error(message+'\nHasil parsial dipertahankan. Anda dapat menyimpan SRT atau melanjutkan bagian yang gagal.')
    def cancel_job(self):
        if self.job: self.job.requestInterruption();self.status.setText('Membatalkan; menunggu permintaan API aktif selesai (maks. 180 detik).')
    def receive_chunk(self,cues,coverage):
        self.coverage=coverage;self.fill(self.cues+list(cues))
        langs=sorted({c.language for c in self.cues if c.language})
        if langs:self.detected.setText('Bahasa sumber terdeteksi: '+', '.join(langs)+' → '+self.lang.currentText())
        if self.buffering and self.player.get_time()/1000 < self.coverage-.15:
            self.buffering=False
            if self.want_play:self.player.play()
    def finished(self):
        self.processing=False;self.buffering=False;self.lang.setEnabled(True);self.seek.setEnabled(True);self.table.setEnabled(True);self.import_button.setEnabled(True)
        self.open.setEnabled(True);self.load.setEnabled(True);self.generate.setEnabled(True);self.cancel.setEnabled(False);self.job.deleteLater();self.job=None
    def done(self,cues):
        self.processing=False;self.buffering=False;self.retry_context=None;self.resume_offset=0
        self.api_status.setText('AI: proses selesai.')
        if self.want_play:self.player.play()
        self.fill(cues);self.status.setText(f'{len(cues)} subtitle selesai. Koreksi teks/timing pada tabel; klik dua kali untuk menuju adegan.')
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
        self.extra_tick()
        if self.pending_seek is not None and self.player.get_state()==vlc.State.Playing:
            self.player.set_time(self.pending_seek);self.pending_seek=None;self.apply_speed()
            if self.pending_pause:self.player.set_pause(1)
            self.pending_pause=False
        if not self.seek.isSliderDown():self.seek.setValue(max(0,int(self.player.get_position()*1000)))
        if self.processing and self.want_play and self.player.get_time()/1000 >= self.coverage-.15:
            self.player.set_pause(1);self.buffering=True
            self.status.setText('Buffering: menunggu subtitle berikutnya agar suara dan teks tetap sinkron …')
        t=(self.player.get_time()-self.offset.value())/1000
        cue=next((c for c in self.cues if c.start<=t<c.end),None)
        self.subtitle.setText(('\n'.join(filter(None,[cue.source,cue.target])) if self.mode.currentIndex()==0 else (cue.target or cue.source) if self.mode.currentIndex()==1 else cue.source) if cue else '')
        if self.pip is not None:self.pip.caption.setText(self.subtitle.text())
        if self.player.get_state()==vlc.State.Error and not self.playback_error_reported:
            self.playback_error_reported=True
            self.status.setText('VLC gagal memutar video. Pilih mode Kompatibel (CPU / GDI) atau lihat Log video. File rusak/DRM mungkin tidak didukung.')
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
                self.open_path(data['video']);self.fill(cues);self.offset.setValue(int(data.get('offset_ms',0)))
            except Exception as e:self.error(str(e))
    def closeEvent(self,event):
        if self.job and self.job.isRunning():self.cancel_job();self.error('Tunggu pembatalan selesai sebelum menutup aplikasi.');event.ignore();return
        self.closing=True;self.leave_pip();self.timer.stop();self.extras_cleanup()
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
                    from playback_checks import run_playback_checks
                    playback=run_playback_checks(w)
                    output.write_text(json.dumps({'playback':playback,'credential_manager':'PASS','qt_window':'PASS','vlc_version':vlc.libvlc_get_version().decode(),'ffmpeg':'PASS'}),encoding='utf-8')
                    w.close();app.exit(0)
                except Exception as e:
                    output.write_text(json.dumps({'error':str(e)}),encoding='utf-8');app.exit(1)
            QTimer.singleShot(500,self_test)
        sys.exit(app.exec())
    except Exception as e:QMessageBox.critical(None,'Gagal mulai',f'{e}\nPastikan VLC 64-bit terpasang atau folder vlc dibundel.');sys.exit(1)
