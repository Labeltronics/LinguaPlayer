import os,sys,json,time,subprocess,tempfile
from pathlib import Path
import vlc,imageio_ffmpeg
from PySide6.QtCore import Qt,QTimer,QThread,Signal
from PySide6.QtGui import QPixmap,QIcon
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QComboBox,QCheckBox,QLineEdit,QDoubleSpinBox,QSpinBox,QDockWidget,QDialog,QListWidget,QListWidgetItem,QFileDialog,QInputDialog,QMessageBox)
from audio_tools import AudioPanel
from storage import MediaStore,SubtitleCache
from export_tools import ExportJob,RESOLUTIONS,export_capabilities

class ThumbnailJob(QThread):
    ready=Signal(bytes,float)
    def __init__(self,path,seconds):super().__init__();self.path=path;self.seconds=seconds;self.proc=None
    def run(self):
        try:
            flags={'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {}
            self.proc=subprocess.Popen([imageio_ffmpeg.get_ffmpeg_exe(),'-v','error','-ss',str(self.seconds),'-i',self.path,'-frames:v','1','-vf','scale=240:-2','-f','image2pipe','-vcodec','mjpeg','pipe:1'],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,**flags)
            output,_=self.proc.communicate(timeout=10)
            if self.proc.returncode==0 and not self.isInterruptionRequested():self.ready.emit(output,self.seconds)
        except (OSError,subprocess.TimeoutExpired):
            if self.proc is not None:self.proc.kill();self.proc.communicate()
        finally:self.proc=None
    def cancel(self):
        self.requestInterruption()
        if self.proc is not None:
            try:self.proc.kill()
            except OSError:pass

def stamp(ms):
    s=max(0,int(ms)//1000);return f'{s//3600:02}:{s//60%60:02}:{s%60:02}'

from modern_tools import ModernTools

class SnapshotJob(QThread):
    ready=Signal(str);failure=Signal(str)
    def __init__(self,source,target,seconds):super().__init__();self.source=str(source);self.target=str(target);self.seconds=seconds;self.proc=None
    def cancel(self):
        self.requestInterruption()
        if self.proc:
            try:self.proc.kill()
            except OSError:pass
    def run(self):
        import uuid
        target=Path(self.target);temp=target.with_name(target.stem+'.'+uuid.uuid4().hex+'.partial.png')
        try:
            if Path(self.source).resolve()==target.resolve():raise ValueError('Screenshot tidak boleh menimpa media sumber.')
            if self.isInterruptionRequested():raise InterruptedError('Capture dibatalkan')
            flags={'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {}
            self.proc=subprocess.Popen([imageio_ffmpeg.get_ffmpeg_exe(),'-v','error','-y','-ss',str(max(0,self.seconds)),'-i',self.source,'-frames:v','1','-c:v','png','-f','image2',str(temp)],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,**flags)
            try:_,error=self.proc.communicate(timeout=15)
            except subprocess.TimeoutExpired:self.proc.kill();self.proc.communicate();raise RuntimeError('Capture frame timeout.')
            if self.isInterruptionRequested():raise InterruptedError('Capture dibatalkan')
            if self.proc.returncode or not temp.is_file() or not temp.stat().st_size:raise RuntimeError('Frame belum dapat diambil. Coba posisi video lain.')
            os.replace(temp,target);self.ready.emit(str(target))
        except Exception as exc:temp.unlink(missing_ok=True);self.failure.emit(str(exc))
        finally:self.proc=None

class CinemaTools(ModernTools):
    def setup_cinema_tools(self,action):
        self.storage_enabled='--self-test' not in sys.argv and os.getenv('QT_QPA_PLATFORM')!='offscreen'
        self.media_store=MediaStore.shared(self.log_path.parent/'media-library.json',self.storage_enabled)
        self.subtitle_cache=SubtitleCache(self.log_path.parent/'subtitle-cache');self.cache_context=None
        self.last_position_save=0.;self.ab_a=None;self.ab_b=None;self.export_job=None;self.thumbnail_job=None;self.snapshot_job=None
        self.search_box=QLineEdit();self.search_box.setPlaceholderText('Cari koleksi / nama media …');self.search_box.textChanged.connect(self.filter_library)
        self.playlist_dock.widget().layout().insertWidget(0,self.search_box)
        self.sound_dock=QDockWidget('Audio Studio — Equalizer & preset',self);self.sound_dock.setObjectName('audio')
        self.audio_panel=AudioPanel(self);self.sound_dock.setWidget(self.audio_panel);self.addDockWidget(Qt.BottomDockWidgetArea,self.sound_dock);self.tabifyDockWidget(self.subtitle_dock,self.sound_dock);self.sound_dock.hide()
        action('Equalizer',self.show_sound)
        self.studio_dock=QDockWidget('Cinema / Scene Tools',self);self.studio_dock.setObjectName('cinema')
        panel=QWidget();box=QVBoxLayout(panel);row=QHBoxLayout();box.addLayout(row)
        for name,fn in [('Bookmark',self.add_bookmark),('Daftar bookmark',self.show_bookmarks),('A–B repeat',self.mark_ab),('Screenshot',self.capture_dialog),('Info codec',self.show_media_info)]:
            button=QPushButton(name);button.clicked.connect(fn);row.addWidget(button)
        row=QHBoxLayout();box.addLayout(row)
        self.resume_box=QCheckBox('Lanjutkan posisi menonton');self.resume_box.setChecked(True);row.addWidget(self.resume_box)
        self.auto_profile=QCheckBox('Profil per film otomatis');self.auto_profile.setChecked(True);row.addWidget(self.auto_profile)
        for name,fn in [('Simpan profil film',self.save_film_profile),('GPU Cinema',self.activate_gpu_cinema),('Mode kompatibel',lambda:self.renderer.setCurrentIndex(0))]:
            button=QPushButton(name);button.clicked.connect(fn);row.addWidget(button)
        row=QHBoxLayout();box.addLayout(row)
        self.adjust_enabled=QCheckBox('Warna video');row.addWidget(self.adjust_enabled)
        self.color_controls={}
        for name,option,low,high,default in [('Cerah',vlc.VideoAdjustOption.Brightness,0,2,1),('Kontras',vlc.VideoAdjustOption.Contrast,0,2,1),('Saturasi',vlc.VideoAdjustOption.Saturation,0,3,1),('Gamma',vlc.VideoAdjustOption.Gamma,.1,3,1)]:
            row.addWidget(QLabel(name));spin=QDoubleSpinBox();spin.setRange(low,high);spin.setSingleStep(.1);spin.setValue(default);row.addWidget(spin);self.color_controls[name]=(spin,option);spin.valueChanged.connect(self.apply_video_adjust)
        self.adjust_enabled.toggled.connect(self.apply_video_adjust)
        row=QHBoxLayout();box.addLayout(row)
        row.addWidget(QLabel('Subtitle'));self.subtitle_font=QSpinBox();self.subtitle_font.setRange(12,48);self.subtitle_font.setValue(20);self.subtitle_font.setSuffix(' px');row.addWidget(self.subtitle_font)
        self.subtitle_color=QComboBox();self.subtitle_color.addItem('Emas','#ffe18a');self.subtitle_color.addItem('Putih','#ffffff');self.subtitle_color.addItem('Hijau','#adff8a');row.addWidget(self.subtitle_color)
        self.subtitle_font.valueChanged.connect(self.apply_subtitle_style);self.subtitle_color.currentIndexChanged.connect(self.apply_subtitle_style)
        self.subtitle_search=QLineEdit();self.subtitle_search.setPlaceholderText('Cari teks subtitle / adegan …');self.subtitle_search.textChanged.connect(self.filter_subtitles);row.addWidget(self.subtitle_search,1)
        row=QHBoxLayout();box.addLayout(row)
        row.addWidget(QLabel('Ketajaman VLC'));self.sharpness=QDoubleSpinBox();self.sharpness.setRange(0,1);self.sharpness.setSingleStep(.05);self.sharpness.valueChanged.connect(lambda value:self.change_renderer(self.renderer.currentIndex()));row.addWidget(self.sharpness)
        self.preview_box=QCheckBox('Thumbnail seek');self.preview_box.setChecked(True);row.addWidget(self.preview_box)
        self.export_resolution=QComboBox();self.export_resolution.addItems(list(RESOLUTIONS));row.addWidget(self.export_resolution)
        self.export_encoder=QComboBox();self.export_encoder.addItems(['CPU','NVIDIA CUDA','Intel QSV','AMD AMF']);row.addWidget(self.export_encoder)
        export=QPushButton('Ekspor HD / 4K');export.clicked.connect(self.start_export);row.addWidget(export)
        cancel=QPushButton('Batal ekspor');cancel.clicked.connect(self.cancel_export);row.addWidget(cancel)
        help_text=QLabel('GPU Cinema memakai D3D11 pada Windows. HDR mengikuti kemampuan VLC, OS, layar dan driver; tidak ada kalibrasi HDR khusus. Upscale bukan pemulihan detail AI. NVIDIA/Intel memakai filter GPU; AMD AMF memakai encoder GPU dengan skala CPU. Ekspor tidak membakar subtitle/efek 3D.');help_text.setWordWrap(True);box.addWidget(help_text)
        self.studio_dock.setWidget(panel);self.addDockWidget(Qt.BottomDockWidgetArea,self.studio_dock);self.tabifyDockWidget(self.subtitle_dock,self.studio_dock);self.studio_dock.hide()
        action('Cinema / Tools',lambda:(self.studio_dock.show(),self.studio_dock.raise_()))
        menu=self.menuBar().addMenu('Audio');menu.addAction('Equalizer dan preset',self.show_sound);menu.addAction('Muat track audio',self.audio_panel.refresh_tracks)
        scene=self.menuBar().addMenu('Scene');scene.addAction('Tambah bookmark',self.add_bookmark);scene.addAction('Daftar bookmark',self.show_bookmarks);scene.addAction('Tandai A / B / hapus loop',self.mark_ab);scene.addAction('Screenshot',self.capture_dialog);scene.addAction('Informasi media / codec',self.show_media_info)
        row=QHBoxLayout();self.ai_panel.layout().insertLayout(0,row)
        row.addWidget(QLabel('Mesin AI'));self.ai_engine=QComboBox();self.ai_engine.addItem('Gemini online','gemini');self.ai_engine.addItem('AI lokal — Whisper + Ollama','local');row.addWidget(self.ai_engine)
        self.local_speech=QLineEdit('http://127.0.0.1:8080/inference');self.local_speech.setToolTip('Server Whisper lokal, perlu dipasang terpisah.');row.addWidget(self.local_speech)
        self.local_translate=QLineEdit('http://127.0.0.1:11434/api/generate');self.local_translate.setToolTip('Server Ollama lokal, perlu model terpasang.');row.addWidget(self.local_translate)
        self.local_model=QLineEdit('qwen2.5:3b');self.local_model.setMaximumWidth(140);row.addWidget(self.local_model)
        self.ai_engine.currentIndexChanged.connect(self.update_ai_inputs);self.update_ai_inputs()
        cache_button=QPushButton('Hapus cache subtitle film ini');cache_button.clicked.connect(self.clear_subtitle_cache);self.ai_panel.layout().addWidget(cache_button)
        self.thumbnail_label=QLabel(self,Qt.ToolTip);self.thumbnail_label.setStyleSheet('background:black;color:white;padding:4px');self.thumbnail_label.setAlignment(Qt.AlignCenter)
        self.thumbnail_timer=QTimer(self);self.thumbnail_timer.setSingleShot(True);self.thumbnail_timer.timeout.connect(self.load_thumbnail)
        self.seek.sliderMoved.connect(lambda value:self.thumbnail_timer.start(350));self.seek.sliderReleased.connect(self.thumbnail_label.hide)
    def update_ai_inputs(self,*args):
        local=self.ai_engine.currentData()=='local'
        for control in (self.local_speech,self.local_translate,self.local_model):control.setVisible(local)
        self.key.setEnabled(not local);self.model.setEnabled(not local)
        self.api_status.setText('AI lokal: server/model Whisper dan Ollama diperlukan; audio hanya dikirim ke loopback.' if local else 'Gemini: gunakan proyek Free Tier tanpa billing; kuota dan model mengikuti akun Google.')
    def ai_configuration(self):
        config={'engine':self.ai_engine.currentData(),'chunk_seconds':self.ai_chunk.value(),'audio_stream':self.ai_stream.value()}
        if config['engine']=='local':config.update(speech_url=self.local_speech.text().strip(),translate_url=self.local_translate.text().strip(),model=self.local_model.text().strip())
        return config
    def current_ai_context(self,lang):return [self.model.text().strip() if self.ai_engine.currentData()=='gemini' else 'local',lang,self.glossary.text().strip(),self.ai_configuration()]
    def show_sound(self):self.sound_dock.show();self.sound_dock.raise_();self.audio_panel.refresh_tracks()
    def filter_library(self,text):
        for i in range(self.playlist_widget.count()):
            item=self.playlist_widget.item(i);item.setHidden(text.casefold() not in (item.text()+' '+str(item.data(Qt.UserRole))).casefold())
    def filter_subtitles(self,text):
        for i,cue in enumerate(self.cues):self.table.setRowHidden(i,text.casefold() not in (cue.source+' '+cue.target).casefold())
    def record_position(self):
        if not self.path:return
        position=self.pending_seek if self.pending_seek is not None else self.player.get_time();duration=self.player.get_length()
        if not isinstance(position,int) or position<0:return
        if not isinstance(duration,int):duration=0
        if duration>0 and position>=duration-3000:position=0
        try:self.media_store.update(self.path,position=position,duration=duration,title=Path(self.path).stem)
        except OSError:pass
    def cinema_opened(self):
        self.ab_a=None;self.ab_b=None
        record=self.media_store.get(self.path)
        if self.auto_profile.isChecked() and isinstance(record.get('profile'),dict):self.apply_film_profile(record['profile'])
        saved=record.get('position',0)
        if isinstance(saved,(int,float)) and saved>5000:
            if self.resume_box.isChecked():self.pending_seek=int(saved);self.pending_pause=False;self.status.setText('Dilanjutkan dari '+stamp(self.pending_seek))
        try:self.media_store.update(self.path,title=Path(self.path).stem)
        except OSError:pass
        current=self.playlist_widget.currentItem()
        for poster in (Path(self.path).with_suffix('.jpg'),Path(self.path).with_suffix('.png'),Path(self.path).parent/'poster.jpg'):
            if poster.is_file():
                if current:current.setIcon(QIcon(str(poster)))
                break
        self.audio_panel.reapply();QTimer.singleShot(600,self.audio_panel.refresh_tracks)
    def cinema_tick(self):
        if self.ab_a is not None and self.ab_b is not None and self.player.is_playing() and self.player.get_time()>=self.ab_b:self.player.set_time(self.ab_a)
        if time.monotonic()-self.last_position_save>=5:self.last_position_save=time.monotonic();self.record_position()
    def add_bookmark(self):
        if not self.path:return
        position=max(0,self.player.get_time());name,ok=QInputDialog.getText(self,'Bookmark adegan','Nama bookmark:',text=stamp(position))
        if ok:
            bookmarks=list(self.media_store.get(self.path).get('bookmarks',[]));bookmarks.append({'time':position,'name':name.strip() or stamp(position)})
            self.media_store.update(self.path,bookmarks=bookmarks);self.status.setText('Bookmark disimpan: '+stamp(position))
    def show_bookmarks(self):
        dialog=QDialog(self);dialog.setWindowTitle('Bookmark • '+Path(self.path).name);layout=QVBoxLayout(dialog);listing=QListWidget();layout.addWidget(listing)
        for bookmark in self.media_store.get(self.path).get('bookmarks',[]):
            item=QListWidgetItem(stamp(bookmark['time'])+' — '+bookmark['name']);item.setData(Qt.UserRole,bookmark);listing.addItem(item)
        listing.itemDoubleClicked.connect(lambda item:self.player.set_time(item.data(Qt.UserRole)['time']))
        remove=QPushButton('Hapus bookmark terpilih');layout.addWidget(remove)
        def delete():
            row=listing.currentRow()
            if row>=0:listing.takeItem(row);self.media_store.update(self.path,bookmarks=[listing.item(i).data(Qt.UserRole) for i in range(listing.count())])
        remove.clicked.connect(delete);dialog.resize(500,350);dialog.exec()
    def mark_ab(self):
        if not (self.path or self.stream_url):return
        if self.stream_url and not self.player.is_seekable():self.status.setText('Loop A–B membutuhkan stream yang mendukung seek.');return
        position=max(0,self.player.get_time())
        if self.ab_a is None:self.ab_a=position;self.status.setText('Titik A: '+stamp(position)+'. Tekan A–B lagi untuk titik B.')
        elif self.ab_b is None:
            if position<=self.ab_a+500:self.status.setText('Titik B harus lebih dari 0,5 detik setelah A.');return
            self.ab_b=position;self.status.setText('Loop A–B aktif. Tekan A–B untuk menghapus loop.')
        else:self.ab_a=None;self.ab_b=None;self.status.setText('Loop A–B dimatikan.')
    def capture_frame(self,path):
        if self.path and Path(path).resolve()==Path(self.path).resolve():raise ValueError('Screenshot tidak boleh menimpa media sumber.')
        if self.video.audio_title:
            if not self.video.grab().save(str(path)):raise RuntimeError('Capture audio tidak dapat disimpan.')
            return
        if (self.stereo_on or self.canvas_active()) and self.video.image is not None:
            if not self.video.image.save(str(path)):raise RuntimeError('Gambar tidak dapat disimpan.')
        else:
            source=self.path or self.stream_url;seconds=0 if self.stream_url and self.stream_live else max(0,self.player.get_time())/1000
            def stamp_file():
                try:value=Path(path).stat();return (value.st_size,value.st_mtime_ns)
                except OSError:return None
            original=stamp_file()
            if self.player.video_take_snapshot(0,str(path),0,0)==-1:self.snapshot_fallback(source,path,seconds)
            else:
                def verify():
                    if self.closing:return
                    current=stamp_file()
                    if current is None or not current[0] or current==original:self.snapshot_fallback(source,path,seconds)
                QTimer.singleShot(800,verify)
    def snapshot_fallback(self,source,path,seconds):
        if self.closing:return
        if self.snapshot_job is not None:
            QTimer.singleShot(100,lambda:self.snapshot_fallback(source,path,seconds));return
        self.snapshot_job=SnapshotJob(source,path,seconds);self.snapshot_job.ready.connect(lambda p:self.status.setText('Screenshot tersimpan: '+p));self.snapshot_job.failure.connect(self.status.setText);self.snapshot_job.finished.connect(self.snapshot_finished);self.snapshot_job.start()
    def snapshot_finished(self):self.snapshot_job.deleteLater();self.snapshot_job=None
    def capture_dialog(self):
        if not (self.path or self.stream_url):return
        path,_=QFileDialog.getSaveFileName(self,'Simpan screenshot',f'Cyber80_{Path(self.path).stem if self.path else "Online"}_{stamp(self.player.get_time()).replace(":","-")}.png','PNG (*.png)')
        if path:
            try:self.capture_frame(path);self.status.setText('Permintaan screenshot: '+path)
            except Exception as exc:self.error(str(exc))
    def media_info(self):
        info={'application':'Cyber80 Players','file':self.path,'duration_ms':self.player.get_length(),'position_ms':self.player.get_time(),'rate':self.player.get_rate(),'renderer':self.renderer.currentText(),'3d':self.stereo_on,'tracks':[]}
        media=self.player.get_media()
        if media:
            try:
                for track in media.tracks_get() or []:
                    info['tracks'].append({'id':track.id,'type':str(track.type),'codec_fourcc':int(track.codec).to_bytes(4,'little').decode('ascii',errors='replace'),'bitrate':track.bitrate})
                stats=vlc.MediaStats();media.get_stats(stats);info['statistics']={name:getattr(stats,name) for name in ('decoded_video','decoded_audio','displayed_pictures','lost_pictures','demux_corrupted')}
            except Exception:pass
        return info
    def show_media_info(self):
        details=self.media_info()
        try:details['ffmpeg_compiled_support']=export_capabilities(imageio_ffmpeg.get_ffmpeg_exe());details['gpu_note']='Daftar ini menunjukkan encoder/filter yang dikompilasi, bukan verifikasi GPU fisik.'
        except Exception:pass
        dialog=QMessageBox(self);dialog.setWindowTitle('Cyber80 • Informasi media');dialog.setTextFormat(Qt.PlainText);dialog.setText(json.dumps(details,ensure_ascii=False,indent=2));dialog.exec()
    def apply_video_adjust(self,*args):
        self.player.video_set_adjust_int(vlc.VideoAdjustOption.Enable,int(self.adjust_enabled.isChecked()))
        if self.adjust_enabled.isChecked():
            for spin,option in self.color_controls.values():self.player.video_set_adjust_float(option,spin.value())
    def apply_subtitle_style(self,*args):
        style=f'font-size:{self.subtitle_font.value()}px;color:{self.subtitle_color.currentData()};background:#131b2c;padding:10px'
        self.subtitle.setStyleSheet(style)
        if self.pip:self.pip.caption.setStyleSheet(style)
    def activate_gpu_cinema(self):
        if sys.platform=='win32':self.renderer.setCurrentIndex(3)
        else:self.renderer.setCurrentIndex(1)
        self.audio_panel.preset.setCurrentText('Film — seimbang');self.subtitle_font.setValue(22)
        self.status.setText('GPU Cinema dipilih. Jika driver/GPU tidak mendukung, gunakan Mode kompatibel.')
    def profile_state(self):
        return {'rate':self.speed_box.value(),'renderer':self.renderer.currentIndex(),'stereo':self.stereo_on,'stereo_layout':self.stereo_layout.currentData(),'scheme':self.stereo_scheme.currentData(),'red':self.red_shift.value(),'blue':self.blue_shift.value(),'audio':self.audio_panel.state(),'subtitle_font':self.subtitle_font.value(),'subtitle_offset':self.offset.value(),'subtitle_color':self.subtitle_color.currentData(),'subtitle_mode':self.mode.currentIndex(),'target_language':self.lang.currentText(),'audio_channel':self.audio_panel.channel.currentData(),'audio_delay_ms':self.audio_panel.delay.value(),'colors':{name:spin.value() for name,(spin,option) in self.color_controls.items()},'adjust':self.adjust_enabled.isChecked(),'sharpness':self.sharpness.value()}
    def save_film_profile(self):
        if self.path:self.media_store.update(self.path,profile=self.profile_state());self.status.setText('Profil film disimpan.')
    def apply_film_profile(self,state):
        try:
            renderer=max(0,min(3,int(state.get('renderer',0))));stereo=bool(state.get('stereo',False))
            rebuild=renderer!=self.renderer.currentIndex() or stereo!=self.stereo_on or float(state.get('sharpness',0))!=self.sharpness.value()
            self.renderer.blockSignals(True);self.renderer.setCurrentIndex(renderer);self.renderer.blockSignals(False)
            self.stereo_check.blockSignals(True);self.stereo_check.setChecked(stereo);self.stereo_check.blockSignals(False);self.stereo_on=stereo
            self.sharpness.blockSignals(True);self.sharpness.setValue(float(state.get('sharpness',0)));self.sharpness.blockSignals(False)
            self.stereo_layout.setCurrentIndex(max(0,self.stereo_layout.findData(state.get('stereo_layout','2d'))));self.stereo_scheme.setCurrentIndex(max(0,self.stereo_scheme.findData(state.get('scheme','red-cyan'))))
            self.red_shift.setValue(int(state.get('red',-3)));self.blue_shift.setValue(int(state.get('blue',3)))
            self.speed_box.setValue(float(state.get('rate',1)));self.subtitle_font.setValue(int(state.get('subtitle_font',20)));self.offset.setValue(int(state.get('subtitle_offset',0)));self.mode.setCurrentIndex(max(0,min(2,int(state.get('subtitle_mode',self.mode.currentIndex())))))
            color_index=self.subtitle_color.findData(state.get('subtitle_color',self.subtitle_color.currentData()))
            if color_index>=0:self.subtitle_color.setCurrentIndex(color_index)
            if state.get('target_language'):self.lang.setCurrentText(str(state['target_language']))
            channel_index=self.audio_panel.channel.findData(state.get('audio_channel',1))
            if channel_index>=0:self.audio_panel.channel.setCurrentIndex(channel_index)
            self.audio_panel.delay.setValue(int(state.get('audio_delay_ms',0)))
            if isinstance(state.get('audio'),dict):self.audio_panel.set_state(state['audio'])
            for name,value in state.get('colors',{}).items():
                if name in self.color_controls:self.color_controls[name][0].setValue(float(value))
            self.adjust_enabled.setChecked(bool(state.get('adjust',False)))
            if rebuild:self.change_renderer(renderer)
        except (ValueError,TypeError,KeyError):self.status.setText('Sebagian profil film tidak valid; gunakan pengaturan default.')
    def load_thumbnail(self):
        if not self.path or not self.preview_box.isChecked() or not self.seek.isSliderDown() or self.thumbnail_job is not None:return
        length=self.player.get_length()
        if not isinstance(length,int) or length<=0:return
        self.thumbnail_job=ThumbnailJob(self.path,length*self.seek.value()/1e6);self.thumbnail_job.ready.connect(self.show_thumbnail);self.thumbnail_job.finished.connect(self.thumbnail_finished);self.thumbnail_job.start()
    def show_thumbnail(self,data,seconds):
        if not self.seek.isSliderDown():return
        pix=QPixmap();pix.loadFromData(data)
        if not pix.isNull():self.thumbnail_label.setPixmap(pix);self.thumbnail_label.move(self.seek.mapToGlobal(self.seek.rect().topLeft()));self.thumbnail_label.show()
    def thumbnail_finished(self):self.thumbnail_job.deleteLater();self.thumbnail_job=None
    def start_export(self):
        if not self.path:self.status.setText('Rekam/unduh media online dahulu untuk ekspor peningkatan resolusi.');return
        if self.export_job is not None:return
        path,_=QFileDialog.getSaveFileName(self,'Ekspor video yang ditingkatkan',Path(self.path).stem+'_Cyber80.mp4','MP4 (*.mp4)')
        if not path:return
        self.export_job=ExportJob(self.path,path,self.export_resolution.currentText(),self.export_encoder.currentText(),self.sharpness.value(),max(0,self.player.get_length())/1000)
        self.export_job.status.connect(self.status.setText);self.export_job.success.connect(lambda value:self.status.setText('Ekspor selesai: '+value));self.export_job.failure.connect(self.error);self.export_job.finished.connect(self.export_finished);self.export_job.start()
    def cancel_export(self):
        if self.export_job:self.export_job.cancel()
    def export_finished(self):self.export_job.deleteLater();self.export_job=None
    def clear_subtitle_cache(self):
        if self.path:
            lang=self.lang.currentData() if self.lang.currentText()==self.lang.itemText(self.lang.currentIndex()) else self.lang.currentText()
            context=self.cache_context or self.current_ai_context(lang)
            self.subtitle_cache.clear(self.path,context);self.retry_context=None;self.resume_offset=0;self.status.setText('Cache subtitle untuk konfigurasi ini dihapus.')
    def save_ai_checkpoint(self,data):
        if not self.storage_enabled or not self.cache_context:return
        try:self.subtitle_cache.write(self.path,self.cache_context,{'cues':[vars(c) for c in data['cues']],'coverage':data['coverage'],'next_offset':data['next_offset'],'complete':data['complete']})
        except OSError:self.api_status.setText('Subtitle berjalan, tetapi cache tidak dapat disimpan.')
    def cinema_cleanup(self):
        self.record_position();self.audio_panel.shutdown();self.thumbnail_timer.stop();self.thumbnail_label.hide()
        if self.thumbnail_job:self.thumbnail_job.cancel();self.thumbnail_job.wait(3000)
        if self.export_job:self.export_job.cancel();self.export_job.wait(5000)
