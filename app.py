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
from PySide6.QtCore import Qt, QThread, Signal, QTimer, QUrl, QCoreApplication
from PySide6.QtGui import QDesktopServices,QIcon
from PySide6.QtWidgets import (QApplication,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QPushButton,
    QFileDialog,QLabel,QLineEdit,QComboBox,QSlider,QTableWidget,QTableWidgetItem,QMessageBox,QSpinBox,QFrame,QDialog,QDockWidget)
from core import Cue, transcribe, srt, validate
from local_ai import transcribe_local
from credentials import save_key, load_key, delete_key
from stereo import VideoSurface
from player_extras import PlayerExtras
if QCoreApplication.instance() is None:QCoreApplication.setAttribute(Qt.AA_ShareOpenGLContexts)

class Job(QThread):
    progress=Signal(str)
    result=Signal(object)
    chunk_ready=Signal(object,float)
    failed=Signal(str)
    checkpoint_ready=Signal(object)
    def __init__(self, path, key, model, language, google, glossary, resume_from=0, initial_cues=None, local_config=None):
        super().__init__(); self.args=(path,key,model,language,google,glossary)
        self.resume_from=resume_from;self.start_offset=resume_from;self.initial_cues=list(initial_cues or []);self.local_config=local_config or {}
        self.chunk_seconds=int(self.local_config.get('chunk_seconds',10));self.audio_stream=int(self.local_config.get('audio_stream',0))
    def run(self):
        path,key,model,lang,google,glossary=self.args
        cues=list(self.initial_cues)
        try:
            ff=imageio_ffmpeg.get_ffmpeg_exe()
            flags={'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {}
            with tempfile.TemporaryDirectory(prefix='cyber80-') as tmp:
                offset=self.start_offset
                while not self.isInterruptionRequested():
                    self.progress.emit(f'Mengekstrak audio {offset//60:02}:{offset%60:02} …')
                    out=str(Path(tmp)/'chunk.wav')
                    overlap=1 if offset>0 else 0
                    p=subprocess.Popen([ff,'-v','error','-y','-ss',str(max(0,offset-overlap)),'-i',path,'-t',str(self.chunk_seconds+overlap),'-map',f'0:a:{self.audio_stream}','-vn','-ac','1','-ar','16000',out],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,**flags)
                    while True:
                        try: _,err=p.communicate(timeout=.2); break
                        except subprocess.TimeoutExpired:
                            if self.isInterruptionRequested():
                                p.kill(); p.communicate(); raise InterruptedError('Dibatalkan')
                    if p.returncode: raise RuntimeError('FFmpeg tidak dapat membaca audio. Video mungkin tanpa audio, rusak, atau format tidak didukung.')
                    with wave.open(out,'rb') as w: duration=w.getnframes()/w.getframerate()
                    if duration < overlap+.1: break
                    self.progress.emit(f'Mentranskrip / menerjemahkan {offset//60:02}:{offset%60:02} …')
                    if self.local_config.get('engine')=='local':chunk=transcribe_local(Path(out).read_bytes(),self.local_config,lang,duration,offset,self.isInterruptionRequested,self.progress.emit,context_seconds=overlap)
                    else:chunk=transcribe(Path(out).read_bytes(),key,model,lang,duration,offset,google,self.isInterruptionRequested,glossary,progress=self.progress.emit,timeout=180,context_seconds=overlap)
                    cues.extend(chunk);self.resume_from=offset+self.chunk_seconds;coverage=offset+duration-overlap
                    self.chunk_ready.emit(chunk,coverage)
                    final_chunk=duration<self.chunk_seconds-.05+overlap
                    self.checkpoint_ready.emit({'cues':list(cues),'coverage':coverage,'next_offset':self.resume_from,'complete':final_chunk})
                    if final_chunk: break
                    offset+=self.chunk_seconds
            if self.isInterruptionRequested(): raise InterruptedError('Dibatalkan')
            self.result.emit(cues)
        except Exception as e: self.failed.emit(str(e))

class PictureWindow(QDialog):
    returning=Signal()
    def __init__(self,owner):
        super().__init__(None,Qt.Window|Qt.WindowStaysOnTopHint)
        self.setWindowTitle('Cyber80 Players • Picture in Picture');self.setWindowIcon(owner.windowIcon());self.resize(520,380)
        self.setMinimumSize(300,230)
        self.box=QVBoxLayout(self);self.box.setContentsMargins(4,4,4,4)
        self.caption=QLabel();self.caption.setWordWrap(True);self.caption.setAlignment(Qt.AlignCenter);self.caption.setTextFormat(Qt.PlainText)
        self.caption.setStyleSheet('color:#ffe18a;font-size:16px;padding:5px;background:#111827')
        controls=QHBoxLayout();self.box.addWidget(self.caption);self.box.addLayout(controls)
        owner.button(controls,'▶ / Pause',owner.play)
        self.full_button=owner.button(controls,'Fullscreen (F11)',owner.toggle_fullscreen)
        owner.button(controls,'Kembali ke pemutar',owner.leave_pip)
        self.setStyleSheet('QDialog{background:black} QPushButton{padding:7px}')
    def closeEvent(self,event):
        if not self.addons_can_close():event.ignore();return
        if self.background_job is not None and self.background_job.isRunning():self.status.setText('Subtitle attachment masih berjalan. Minimalkan aplikasi, atau batalkan pekerjaan dan tunggu selesai sebelum menutup.');event.ignore();return
        event.ignore();self.returning.emit()

class Window(PlayerExtras,QMainWindow):
    def __init__(self):
        super().__init__(); self.setWindowTitle('Cyber80 Players • Video & AI Subtitle');self.setWindowIcon(QIcon(str(ROOT/'assets'/'cyber80.ico'))); self.resize(1200,850)
        self.retry_context=None;self.resume_offset=0
        self.path=''; self.job=None; self.cues=[];self.coverage=0.;self.processing=False;self.buffering=False;self.want_play=False
        self.pip=None;self.pending_seek=None;self.pending_pause=False;self.closing=False;self.playback_error_reported=False;self.surface_generation=0
        self.log_path=Path(os.getenv('LOCALAPPDATA',tempfile.gettempdir()))/'Cyber80 Players'/'playback.log'
        self.log_path.parent.mkdir(parents=True,exist_ok=True)
        self.engine=self.make_engine(0);self.player=self.engine.media_player_new()
        root=QWidget(); self.setCentralWidget(root); layout=QVBoxLayout(root)
        title=QLabel('Cyber80 Players  |  Video • Audio • AI Cinema'); title.setWordWrap(True);title.setStyleSheet('font-size:18px;font-weight:bold'); layout.addWidget(title)
        self.video_host=QWidget();self.host_layout=QVBoxLayout(self.video_host);self.host_layout.setContentsMargins(0,0,0,0)
        self.video=VideoSurface();self.video.setMinimumSize(160,160)
        self.video.setAttribute(Qt.WA_NativeWindow,True)
        self.video.setAttribute(Qt.WA_DontCreateNativeAncestors,True)
        self.video.setAttribute(Qt.WA_NoSystemBackground,True)
        self.video.setAutoFillBackground(False)
        self.host_layout.addWidget(self.video);layout.addWidget(self.video_host,1)
        self.bind_video()
        self.subtitle=QLabel('Buka media untuk mulai'); self.subtitle.setWordWrap(True); self.subtitle.setAlignment(Qt.AlignCenter); self.subtitle.setTextFormat(Qt.PlainText)
        self.subtitle.setStyleSheet('font-size:20px;color:#ffe18a;background:#131b2c;padding:10px'); layout.addWidget(self.subtitle)
        row=QHBoxLayout(); layout.addLayout(row)
        self.open=self.button(row,'Buka media',self.open_video); self.button(row,'▶ / Pause',self.play)
        self.button(row,'Stop',self.stop);self.pip_button=self.button(row,'PiP',self.toggle_pip);self.fullscreen_button=self.button(row,'Full screen (F11)',self.toggle_fullscreen)
        self.renderer=QComboBox();self.renderer.addItems(['Kompatibel (CPU / GDI)','Otomatis (GPU)','Direct3D11','GPU Cinema (D3D11)'])
        if sys.platform!='win32':self.renderer.setCurrentIndex(1)
        self.renderer.currentIndexChanged.connect(self.change_renderer)
        render_row=QHBoxLayout();layout.addLayout(render_row);render_row.addWidget(self.renderer);render_row.addStretch()
        self.button(render_row,'Log video',lambda:QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.log_path))))
        self.seek=QSlider(Qt.Horizontal); self.seek.setRange(0,1000); self.seek.sliderReleased.connect(lambda:self.player.set_position(self.seek.value()/1000)); row.addWidget(self.seek,1)
        volume=QSlider(Qt.Horizontal); volume.setRange(0,200); volume.setValue(100); volume.setMaximumWidth(120); volume.valueChanged.connect(self.volume_changed); row.addWidget(QLabel('Volume'));row.addWidget(volume);self.player.audio_set_volume(100);self.volume=volume
        self.volume_percent=QSpinBox();self.volume_percent.setRange(0,200);self.volume_percent.setValue(100);self.volume_percent.setSuffix(' %');volume.valueChanged.connect(self.volume_percent.setValue);self.volume_percent.valueChanged.connect(volume.setValue);row.addWidget(self.volume_percent);self.button(row,'BOOST Maks',lambda:self.audio_panel.boost_preset(20));self.button(row,'Normal 100%',lambda:self.audio_panel.boost_preset(0))
        self.ai_panel=QWidget();ai_layout=QVBoxLayout(self.ai_panel)
        row=QHBoxLayout();ai_layout.addLayout(row)
        self.key=QLineEdit(os.getenv('GEMINI_API_KEY',''));self.key.setEchoMode(QLineEdit.Password);self.key.setPlaceholderText('Gemini API key');row.addWidget(self.key)
        self.model=QLineEdit('gemini-3.5-flash-lite');self.model.setMaximumWidth(170);row.addWidget(self.model)
        self.lang=QComboBox();self.lang.setEditable(True);self.lang.setToolTip('Pilih bahasa atau ketik nama/kode bahasa yang didukung mesin AI.')
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
        self.status=QLabel('Pilih media. Mesin AI dan tujuan pemrosesan tersedia pada Subtitle / AI.');self.status.setWordWrap(True);layout.addWidget(self.status)
        self.subtitle_dock=QDockWidget('Subtitle & Gemini',self);self.subtitle_dock.setObjectName('subtitle');self.subtitle_dock.setWidget(self.ai_panel);self.addDockWidget(Qt.BottomDockWidgetArea,self.subtitle_dock);self.subtitle_dock.hide()
        try:
            self.key.setText(load_key('Gemini') or self.key.text());self.google.clear()
        except Exception:pass
        self.google.clear()
        self.setup_extras()
        self.timer=QTimer(self);self.timer.timeout.connect(self.tick);self.timer.start(100)
        QTimer.singleShot(0,self.bind_video)
        self.apply_theme()
    def make_engine(self,mode):
        options=['--ignore-config','--no-video-title-show','--no-osd','--video','--audio',
                 '--audio-time-stretch','--no-plugins-cache','--file-logging','--logfile='+str(self.log_path),'--verbose=2']
        if '--self-test' in sys.argv:options+=['--aout=dummy']
        if sys.platform=='win32':
            if vlcdir.is_dir():
                import ctypes
                # Keep VLC decoder dependencies ahead of unrelated Qt/PyInstaller DLLs.
                ctypes.windll.kernel32.SetDllDirectoryW(str(vlcdir))
            if getattr(self,'stereo_on',False) or self.canvas_active():options+=['--avcodec-hw=none','--vout=vmem']
            elif mode==0:options+=['--avcodec-hw=none','--vout=wingdi']
            elif mode==2:options+=['--avcodec-hw=none','--vout=direct3d11']
            elif mode==3:options+=['--avcodec-hw=d3d11va','--vout=direct3d11']
        sharp=self.sharpness.value() if hasattr(self,'sharpness') else 0
        filters=[]
        if sharp>0:filters.append('sharpen');options+=['--sharpen-sigma='+str(sharp)]
        rotation=getattr(self,'rotation','off')
        if rotation!='off':filters.append('transform');options+=['--transform-type='+rotation]
        if filters:options+=['--video-filter='+':'.join(filters)]
        dsp=getattr(self,'audio_dsp','off')
        from audio_gain import native_audio_options,audio_signature
        panel=getattr(self,'audio_panel',None);audio_state=panel.state() if panel else {'enabled':False,'preamp':0,'bands':[0.]*10,'headroom':False,'boost':0,'peak_guard':True}
        options+=native_audio_options(audio_state,dsp);self.engine_audio_signature=audio_signature(audio_state,dsp)
        engine=vlc.Instance(*options)
        if engine is None:raise RuntimeError('VLC tidak dapat memuat plugin codec yang dibundel.')
        return engine
    def bind_video(self):
        if getattr(self,'stereo_on',False) or self.canvas_active():return
        handle=int(self.video.winId())
        if sys.platform=='win32':self.player.set_hwnd(handle)
        elif sys.platform=='darwin':self.player.set_nsobject(handle)
        else:self.player.set_xwindow(handle)
    def output_state(self):
        state=self.player.get_state()
        position=self.pending_seek if self.pending_seek is not None else max(0,self.player.get_time())
        active=self.pending_seek is not None or state in (vlc.State.Playing,vlc.State.Paused,vlc.State.Buffering,vlc.State.Opening)
        paused=self.pending_pause if self.pending_seek is not None else state==vlc.State.Paused
        return position,active,paused
    def change_renderer(self,index):
        position,active,paused=self.output_state();self.surface_generation+=1
        self.pending_seek=None;self.pending_pause=False
        self.player.stop();self.player.release();self.engine.release()
        self.engine=self.make_engine(index);self.player=self.engine.media_player_new();self.configure_video_output()
        self.player.audio_set_volume(self.volume.value());self.player.audio_set_mute(self.mute_action.isChecked());self.request_audio_sync();self.apply_speed()
        self.audio_panel.reapply();self.apply_video_adjust()
        if self.path:
            self.player.set_media(self.engine.media_new_path(self.path))
            if active:self.pending_seek=position;self.pending_pause=paused;self.player.play();self.apply_speed()
        self.status.setText('Mode tampilan: '+self.renderer.currentText())
    def queue_surface(self,position,active,paused):
        self.surface_generation+=1;generation=self.surface_generation
        self.pending_seek=position if active else None;self.pending_pause=paused if active else False
        QTimer.singleShot(0,lambda:self.restart_surface(position,active,paused,generation))
    def restart_surface(self,position,active,paused,generation=None):
        if self.closing or (generation is not None and generation!=self.surface_generation):return
        self.bind_video()
        if active:
            self.pending_seek=position;self.pending_pause=paused;self.player.play();self.apply_speed()
        else:self.pending_seek=None;self.pending_pause=False
    def toggle_pip(self):
        if self.pip:return self.leave_pip()
        position,active,paused=self.output_state()
        if active:self.player.stop()
        popup=PictureWindow(self);self.pip=popup;popup.returning.connect(self.leave_pip)
        self.host_layout.removeWidget(self.video);self.video.setMinimumSize(160,90)
        popup.box.insertWidget(0,self.video,1);popup.caption.setText(self.subtitle.text());popup.show();self.video.show()
        self.pip_button.setText('Kembali dari PiP');self.queue_surface(position,active,paused)
    def leave_pip(self):
        if self.pip is None:return
        position,active,paused=self.output_state();active=active and not self.closing
        self.player.stop()
        popup=self.pip;self.pip=None;popup.box.removeWidget(self.video)
        self.video.setMinimumSize(160,160);self.host_layout.addWidget(self.video);self.video.show()
        popup.hide();popup.deleteLater();self.pip_button.setText('PiP')
        if not self.closing:self.queue_surface(position,active,paused)
    def open_path(self,path):
        if self.job is not None and self.job.isRunning():raise RuntimeError('Batalkan proses subtitle sebelum mengganti media.')
        self.surface_generation+=1
        path=Path(path).resolve()
        if not path.is_file():raise ValueError('File video/audio tidak ditemukan.')
        self.record_position()
        self.tv_generation+=1;self.tv_last_revision=-1;self.cues_4d=[]
        self.player.stop();self.path=str(path);self.pending_seek=None;self.pending_pause=False;self.playback_error_reported=False
        self.bind_video();self.player.set_media(self.engine.media_new_path(self.path))
        if self.player.play()==-1:raise RuntimeError('VLC gagal memulai video. Coba mode Kompatibel (CPU / GDI).')
        from player_extras import AUDIO_SUFFIXES
        self.video.clear_frame();self.cache_context=None
        self.video.audio_title=('Audio • '+path.name) if path.suffix.lower() in AUDIO_SUFFIXES else '';self.video.update()
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
    def error(self,message): QMessageBox.warning(self,'Cyber80 Players',message)
    def open_video(self):
        p,_=QFileDialog.getOpenFileName(self,'Pilih video atau audio','','Media (*.mp4 *.mkv *.avi *.flv *.ts *.mts *.m2ts *.3gp *.3g2 *.mov *.webm *.wmv *.mpg *.mpeg *.vob *.ogv *.m4v *.mp3 *.aac *.m4a *.flac *.wav *.ogg *.oga *.opus *.wma *.aif *.aiff *.ape *.ac3 *.eac3 *.dts *.mka *.amr *.wv *.tta *.caf *.au);;Semua file (*.*)')
        if p:
            try:self.open_path(p)
            except Exception as e:self.error(str(e))
    def stop(self):
        self.surface_generation+=1;self.pending_seek=None;self.pending_pause=False
        self.want_play=False;self.player.stop()
    def play(self):
        if self.processing:
            self.want_play=not self.want_play
            if not self.want_play:self.player.set_pause(1)
            elif not self.buffering:self.player.play()
        elif self.path:self.player.pause() if self.player.is_playing() else self.player.play()
    def process(self):
        if self.job is not None and self.job.isRunning():return
        if not self.path:return self.error('Buka media terlebih dahulu.')
        lang=self.lang.currentData() if self.lang.currentText()==self.lang.itemText(self.lang.currentIndex()) else self.lang.currentText().strip()
        configuration=self.ai_configuration();self.cache_context=self.current_ai_context(lang)
        context=(self.path,self.model.text().strip(),lang,self.glossary.text().strip(),json.dumps(configuration,sort_keys=True))
        cache=self.subtitle_cache.read(self.path,self.cache_context) if self.storage_enabled else None
        if cache:
            try:
                self.fill(validate(cache['cues'],1e12));self.coverage=float(cache.get('coverage',0))
                if cache.get('complete'):self.api_status.setText('Subtitle dari cache lokal — tanpa panggilan API.');return
                self.retry_context=context;self.resume_offset=max(0,int(cache.get('next_offset',0)))
            except (ValueError,TypeError,KeyError):cache=None
        if configuration['engine']=='gemini' and not self.key.text().strip():
            self.subtitle_dock.show();self.subtitle_dock.raise_();self.key.setFocus();self.status.setText('Isi Gemini API key, lalu simpan di Windows.');return
        message='Audio dikirim ke layanan lokal di komputer ini. Model/server Whisper dan Ollama harus sudah tersedia.' if configuration['engine']=='local' else 'Audio dikirim ke Google. Gunakan proyek Free Tier tanpa billing. Aplikasi tidak mengaktifkan billing atau berpindah ke layanan berbayar.'
        if QMessageBox.question(self,'Proses subtitle',message+' Lanjutkan?')!=QMessageBox.Yes:return
        resume=self.retry_context==context and self.resume_offset>0
        position=self.resume_offset if resume else 0
        if not resume:self.fill([]);self.coverage=0.
        self.retry_context=context
        self.player.set_pause(1);self.player.set_time(position*1000)
        self.processing=True;self.buffering=True;self.want_play=self.ai_policy.currentData()!='prepare'
        self.set_ai_controls_enabled(False);self.offset.setValue(0);self.lang.setEnabled(False);self.ai_engine.setEnabled(False);self.seek.setEnabled(False);self.table.setEnabled(False);self.import_button.setEnabled(False)
        self.job=Job(self.path,self.key.text().strip(),self.model.text().strip(),lang,'',self.glossary.text().strip(),resume_from=position,initial_cues=self.cues,local_config=configuration)
        self.job.chunk_ready.connect(self.receive_chunk);self.job.checkpoint_ready.connect(self.save_ai_checkpoint);self.job.progress.connect(self.api_status.setText);self.job.result.connect(self.done);self.job.failed.connect(self.job_error);self.job.finished.connect(self.finished)
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
        if langs:self.detected.setText('Bahasa sumber terdeteksi (perkiraan): '+', '.join(langs)+' → '+self.lang.currentText())
        if self.buffering and self.player.get_time()/1000 < self.coverage-.15:
            self.buffering=False
            if self.want_play:self.player.play()
    def finished(self):
        self.set_ai_controls_enabled(True);self.processing=False;self.buffering=False;self.lang.setEnabled(True);self.ai_engine.setEnabled(True);self.seek.setEnabled(True);self.table.setEnabled(True);self.import_button.setEnabled(True)
        self.open.setEnabled(True);self.load.setEnabled(True);self.generate.setEnabled(True);self.cancel.setEnabled(False);self.job.deleteLater();self.job=None
    def done(self,cues):
        self.processing=False;self.buffering=False;self.retry_context=None;self.resume_offset=0
        self.api_status.setText('AI: proses selesai.')
        if self.want_play:self.player.play()
        self.fill(cues);self.save_ai_checkpoint({'cues':cues,'coverage':self.coverage,'next_offset':self.job.resume_from if self.job else 0,'complete':True});self.status.setText(f'{len(cues)} subtitle selesai. Koreksi teks/timing pada tabel; klik dua kali untuk menuju adegan.')
    def fill(self,cues):
        languages=sorted({c.language for c in cues if c.language})
        self.detected.setText(('Bahasa sumber terdeteksi (perkiraan): '+', '.join(languages)+' → '+self.lang.currentText()) if languages else ('Subtitle dimuat; metadata bahasa sumber tidak tersedia.' if cues else 'Bahasa sumber: belum dianalisis → '+self.lang.currentText()))
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
            if self.storage_enabled and self.cache_context:
                cached=self.subtitle_cache.read(self.path,self.cache_context)
                if cached:cached['cues']=[vars(cue) for cue in self.cues];self.subtitle_cache.write(self.path,self.cache_context,cached)
        except ValueError:
            self.error('Waktu harus angka positif dan akhir lebih besar dari mulai.');self.fill(self.cues)
    def jump(self,row,col): self.player.set_time(int(self.cues[row].start*1000))
    def tick(self):
        self.extra_tick()
        if self.pending_seek is not None and self.player.get_state()==vlc.State.Playing:
            self.player.set_time(self.pending_seek);self.pending_seek=None;self.apply_speed();self.audio_panel.reapply();self.apply_video_adjust()
            if self.pending_pause:self.player.set_pause(1)
            self.pending_pause=False
        if not self.seek.isSliderDown():self.seek.setValue(max(0,int(self.player.get_position()*1000)))
        if self.processing and self.want_play and self.ai_policy.currentData()=='wait' and self.player.get_time()/1000 >= self.coverage-.15:
            self.player.set_pause(1);self.buffering=True
            self.status.setText('Buffering: menunggu subtitle berikutnya agar suara dan teks tetap sinkron …')
        t=(self.player.get_time()-self.offset.value())/1000
        cue=next((c for c in self.cues if c.start<=t<c.end),None)
        self.subtitle.setText(('\n'.join(filter(None,[cue.source,cue.target])) if self.mode.currentIndex()==0 else (cue.target or cue.source) if self.mode.currentIndex()==1 else cue.source) if cue else '')
        if self.pip is not None:self.pip.caption.setText(self.subtitle.text())
        self.update_overlay()
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
        if not self.addons_can_close():event.ignore();return
        if self.background_job is not None and self.background_job.isRunning():self.status.setText('Subtitle attachment masih berjalan. Minimalkan aplikasi, atau batalkan pekerjaan dan tunggu selesai sebelum menutup.');event.ignore();return
        if self.utility_job is not None and self.utility_job.isRunning():self.cancel_utility();self.status.setText('Membatalkan alat media; tutup lagi setelah selesai.');event.ignore();return
        if self.export_job is not None and self.export_job.isRunning():self.cancel_export();self.status.setText('Membatalkan ekspor; tutup lagi setelah proses selesai.');event.ignore();return
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
                    from studio_checks import run_studio_checks
                    with tempfile.TemporaryDirectory(prefix='cyber80-studio-test-') as studio_root:playback['video_studio']=run_studio_checks(w,Path(studio_root))
                    from audio_checks import run_audio_boost_checks
                    with tempfile.TemporaryDirectory(prefix='cyber80-boost-test-') as boost_root:playback['audio_boost']=run_audio_boost_checks(w,Path(boost_root))
                    from browser_checks import run_browser_checks
                    browser=run_browser_checks(w)
                    output.write_text(json.dumps({'playback':playback,'browser':browser,'credential_manager':'PASS','qt_window':'PASS','vlc_version':vlc.libvlc_get_version().decode(),'ffmpeg':'PASS'}),encoding='utf-8')
                    w.close();app.exit(0)
                except Exception as e:
                    import traceback
                    output.write_text(json.dumps({'error':str(e),'traceback':traceback.format_exc(),'partial_playback':locals().get('playback')}),encoding='utf-8');app.exit(1)
            QTimer.singleShot(500,self_test)
        sys.exit(app.exec())
    except Exception as e:QMessageBox.critical(None,'Gagal mulai',f'{e}\nPastikan VLC 64-bit terpasang atau folder vlc dibundel.');sys.exit(1)
