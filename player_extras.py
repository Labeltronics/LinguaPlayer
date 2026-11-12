import os,json,random,sys,time
from pathlib import Path
from PySide6.QtCore import Qt,QTimer,QEvent
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (QApplication,QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,
    QDockWidget,QListWidget,QListWidgetItem,QAbstractItemView,QCheckBox,QComboBox,QSpinBox,
    QDoubleSpinBox,QFileDialog,QLineEdit,QAbstractSpinBox,QTableWidget,QToolBar)
import vlc
from playlist import read_playlist,write_playlist
from stereo import MemoryVideo,compose_anaglyph
from cinema_tools import CinemaTools

AUDIO_SUFFIXES={'.mp3','.aac','.m4a','.flac','.wav','.ogg','.oga','.opus','.wma','.aif','.aiff','.ape','.ac3','.eac3','.dts','.mka','.amr','.wv','.tta','.caf','.au'}
VIDEO_SUFFIXES={'.mp4','.mkv','.avi','.flv','.ts','.mts','.m2ts','.3gp','.3g2','.mov','.webm','.wmv','.mpg','.mpeg','.vob','.ogv','.m4v'}

class PlayerExtras(CinemaTools):
    windows=[]
    def setup_extras(self):
        self.memory_video=None;self.stereo_on=False;self._last_frame_revision=-1;self._last_frame=None
        self._end_handled=False;self._fullscreen_was_pip=False
        self.window_number=next(i for i in (1,2,3) if all(getattr(w,'window_number',None)!=i for w in PlayerExtras.windows))
        PlayerExtras.windows.append(self)
        self.setWindowTitle(f'Cyber80 Players • Pemutar {self.window_number}')
        self.setAcceptDrops(True)
        self.playlist_widget=QListWidget();self.playlist_widget.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.playlist_widget.setDragDropMode(QAbstractItemView.InternalMove)
        self.playlist_widget.itemDoubleClicked.connect(lambda item:self.play_item(item))
        self.playlist_dock=QDockWidget('Playlist',self);self.playlist_dock.setObjectName('playlist')
        panel=QWidget();box=QVBoxLayout(panel);box.addWidget(self.playlist_widget)
        row=QHBoxLayout();box.addLayout(row)
        self.button(row,'+ Film',self.add_films);self.button(row,'↑',lambda:self.move_playlist(-1));self.button(row,'↓',lambda:self.move_playlist(1));self.button(row,'Hapus',self.remove_playlist)
        row=QHBoxLayout();box.addLayout(row)
        self.button(row,'Buka daftar',self.load_playlist);self.button(row,'Simpan daftar',self.save_playlist)
        self.auto_next_box=QCheckBox('Putar film berikutnya otomatis');self.auto_next_box.setChecked(True);box.addWidget(self.auto_next_box)
        row=QHBoxLayout();box.addLayout(row)
        self.shuffle_box=QCheckBox('Acak');row.addWidget(self.shuffle_box)
        self.repeat_box=QComboBox();self.repeat_box.addItems(['Tanpa ulang','Ulang semua','Ulang satu']);row.addWidget(self.repeat_box)
        self.playlist_dock.setWidget(panel);self.addDockWidget(Qt.RightDockWidgetArea,self.playlist_dock)
        toolbar=QToolBar('Kontrol lanjutan',self);self.advanced_toolbar=toolbar;toolbar.setObjectName('advanced');toolbar.setMovable(False);self.addToolBar(toolbar)
        def action(label,fn,checkable=False):
            a=QAction(label,self);a.setCheckable(checkable);a.triggered.connect(fn);toolbar.addAction(a);return a
        action('Tambah film',self.add_films);action('Sebelumnya',lambda:self.next_film(-1));action('Berikutnya',lambda:self.next_film(1))
        action('Pemutar kedua',self.open_second_player);action('Fullscreen',self.toggle_fullscreen)
        self.mute_action=action('Mute',self.set_muted,True)
        toolbar.addWidget(QLabel('  Kecepatan '));self.speed_box=QDoubleSpinBox();self.speed_box.setRange(.1,10);self.speed_box.setSingleStep(.25);self.speed_box.setDecimals(2);self.speed_box.setValue(1);self.speed_box.setSuffix(' ×');self.speed_box.valueChanged.connect(self.apply_speed);toolbar.addWidget(self.speed_box)
        self.stereo_dock=QDockWidget('3D anaglyph — kacamata merah / cyan atau biru',self);self.stereo_dock.setObjectName('stereo')
        controls=QWidget();form=QVBoxLayout(controls)
        row=QHBoxLayout();form.addLayout(row)
        self.stereo_check=QCheckBox('Aktifkan 3D');self.stereo_check.toggled.connect(self.toggle_stereo);row.addWidget(self.stereo_check)
        self.stereo_layout=QComboBox()
        for name,value in [('2D (efek kedalaman buatan)','2d'),('SBS half (kiri–kanan)','sbs-half'),('SBS full (kiri–kanan)','sbs-full'),('TB half (atas–bawah)','tb-half'),('TB full (atas–bawah)','tb-full')]:self.stereo_layout.addItem(name,value)
        row.addWidget(self.stereo_layout)
        self.stereo_scheme=QComboBox();self.stereo_scheme.addItem('Merah–cyan','red-cyan');self.stereo_scheme.addItem('Merah–biru','red-blue');row.addWidget(self.stereo_scheme)
        row=QHBoxLayout();form.addLayout(row)
        row.addWidget(QLabel('Merah / mata kiri (−/+ px)'));self.red_shift=QSpinBox();self.red_shift.setRange(-200,200);self.red_shift.setValue(-3);row.addWidget(self.red_shift)
        row.addWidget(QLabel('Cyan/biru / mata kanan (−/+ px)'));self.blue_shift=QSpinBox();self.blue_shift.setRange(-200,200);self.blue_shift.setValue(3);row.addWidget(self.blue_shift)
        row=QHBoxLayout();form.addLayout(row)
        self.swap_eyes=QCheckBox('Tukar mata');row.addWidget(self.swap_eyes)
        self.button(row,'Reset geser',lambda:(self.red_shift.setValue(0),self.blue_shift.setValue(0)))
        help_label=QLabel('Video 2D hanya mendapat pergeseran bidang; pasangan stereo asli memerlukan sumber SBS/TB. Mode 3D memakai CPU dan pratinjau maksimal 960×540.');help_label.setWordWrap(True);form.addWidget(help_label)
        for control in (self.red_shift,self.blue_shift):control.valueChanged.connect(lambda value:self.render_stereo(True))
        self.stereo_layout.currentIndexChanged.connect(lambda value:self.render_stereo(True));self.stereo_scheme.currentIndexChanged.connect(lambda value:self.render_stereo(True));self.swap_eyes.toggled.connect(lambda value:self.render_stereo(True))
        self.stereo_dock.setWidget(controls);self.addDockWidget(Qt.BottomDockWidgetArea,self.stereo_dock);self.stereo_dock.hide()
        self.tabifyDockWidget(self.subtitle_dock,self.stereo_dock)
        action('Subtitle / AI',lambda:(self.subtitle_dock.show(),self.subtitle_dock.raise_()))
        action('Setelan 3D',lambda:(self.stereo_dock.show(),self.stereo_dock.raise_()))
        file_menu=self.menuBar().addMenu('File')
        for name,fn in [('Buka video/audio (Ctrl+O)',self.open_video),('Tambah banyak media',self.add_films),('Tambah folder',self.add_folder),('Buka playlist',self.load_playlist),('Simpan playlist',self.save_playlist),('Kosongkan playlist',self.playlist_widget.clear),('Buka pemutar kedua',self.open_second_player)]:file_menu.addAction(name,fn)
        play_menu=self.menuBar().addMenu('Pemutaran')
        for name,fn in [('Play / Pause (Space)',self.play),('Stop',self.stop),('Mundur 5 detik (←)',lambda:self.seek_relative(-5)),('Maju 5 detik (→)',lambda:self.seek_relative(5)),('Maju 1 menit (↑)',lambda:self.seek_relative(60)),('Mundur 1 menit (↓)',lambda:self.seek_relative(-60)),('Film sebelumnya (PageUp)',lambda:self.next_film(-1)),('Film berikutnya (PageDown)',lambda:self.next_film(1))]:play_menu.addAction(name,fn)
        view=self.menuBar().addMenu('Tampilan');view.addAction('Fullscreen (F / F11)',self.toggle_fullscreen);view.addAction('PiP',self.toggle_pip);view.addAction(self.playlist_dock.toggleViewAction());view.addAction(self.subtitle_dock.toggleViewAction());view.addAction(self.stereo_dock.toggleViewAction())
        subtitles=self.menuBar().addMenu('Subtitle');subtitles.addAction('Buat / lanjutkan subtitle online',self.process);subtitles.addAction('Buka SRT offline',self.import_srt);subtitles.addAction('Ekspor SRT',self.export)
        self.stereo_timer=QTimer(self);self.stereo_timer.timeout.connect(self.render_stereo);self.stereo_timer.start(33)
        QApplication.instance().installEventFilter(self)
        self.playlist_cache=self.log_path.parent/f'playlist-{self.window_number}.json'
        if '--self-test' not in __import__('sys').argv and os.getenv('QT_QPA_PLATFORM')!='offscreen':
            try:
                source=self.playlist_cache if self.playlist_cache.exists() else self.log_path.parent.parent/'LinguaPlayer'/f'playlist-{self.window_number}.json'
                self.add_paths(read_playlist(source))
            except Exception:pass
        self.setup_cinema_tools(action)
        self.configure_video_output();self.setup_modern_tools()
    def add_paths(self,paths):
        known={self.playlist_widget.item(i).data(Qt.UserRole) for i in range(self.playlist_widget.count())}
        for p in paths:
            path=str(Path(p).resolve())
            if path in known:continue
            item=QListWidgetItem(Path(path).name);item.setData(Qt.UserRole,path);item.setToolTip(path);self.playlist_widget.addItem(item);known.add(path)
    def add_films(self):
        paths,_=QFileDialog.getOpenFileNames(self,'Tambahkan beberapa video/audio (Ctrl/Shift untuk memilih)','','Video / Audio (*.*)')
        self.add_paths(paths)
        if paths and not self.path:self.play_item(self.playlist_widget.item(0))
    def add_folder(self):
        folder=QFileDialog.getExistingDirectory(self,'Pilih folder film')
        if folder:self.add_paths(str(p) for p in sorted(Path(folder).iterdir()) if p.is_file() and p.suffix.lower() in VIDEO_SUFFIXES|AUDIO_SUFFIXES)
    def play_item(self,item):
        if item is None:return
        if self.job is not None and self.job.isRunning():self.status.setText('Batalkan proses subtitle sebelum mengganti film.');return
        try:self.open_path(item.data(Qt.UserRole))
        except Exception as e:self.error(str(e))
    def playlist_opened(self,path):
        self._end_handled=False;self.add_paths([path])
        for i in range(self.playlist_widget.count()):
            if self.playlist_widget.item(i).data(Qt.UserRole)==path:self.playlist_widget.setCurrentRow(i);break
        self.setWindowTitle(f'Cyber80 Players {self.window_number} • '+Path(path).name)
        self.apply_speed();self.player.audio_set_mute(self.mute_action.isChecked());self.request_audio_sync();self.cinema_opened()
        subtitle=Path(path).with_suffix('.srt')
        if subtitle.is_file():
            try:
                from core import parse_srt
                self.fill(parse_srt(subtitle.read_text(encoding='utf-8-sig')))
            except Exception:self.status.setText('Video dibuka; SRT di folder yang sama tidak dapat dibaca.')
    def move_playlist(self,direction):
        row=self.playlist_widget.currentRow();target=row+direction
        if 0<=row<self.playlist_widget.count() and 0<=target<self.playlist_widget.count():
            item=self.playlist_widget.takeItem(row);self.playlist_widget.insertItem(target,item);self.playlist_widget.setCurrentRow(target)
    def remove_playlist(self):
        for item in list(self.playlist_widget.selectedItems()):self.playlist_widget.takeItem(self.playlist_widget.row(item))
    def save_playlist(self):
        path,_=QFileDialog.getSaveFileName(self,'Simpan playlist','playlist.m3u8','M3U8 (*.m3u8);;JSON (*.json)')
        if path:
            try:write_playlist(path,[self.playlist_widget.item(i).data(Qt.UserRole) for i in range(self.playlist_widget.count())])
            except Exception as e:self.error(str(e))
    def load_playlist(self):
        path,_=QFileDialog.getOpenFileName(self,'Buka playlist','','Playlist (*.m3u *.m3u8 *.json)')
        if path:
            try:self.add_paths(read_playlist(path))
            except Exception as e:self.error(str(e))
    def next_film(self,direction=1,automatic=False):
        n=self.playlist_widget.count()
        if not n:return
        row=next((i for i in range(n) if self.playlist_widget.item(i).data(Qt.UserRole)==self.path),-1)
        if automatic and self.repeat_box.currentIndex()==2 and self.path:
            self.player.stop();self.player.play();self.apply_speed();self._end_handled=False;return
        if self.shuffle_box.isChecked() and n>1:target=random.choice([i for i in range(n) if i!=row])
        else:target=row+direction
        if not 0<=target<n:
            if self.repeat_box.currentIndex()==1:target%=n
            else:return
        self.play_item(self.playlist_widget.item(target))
    def extra_tick(self):
        self.sync_master_audio();self.cinema_tick();self.modern_tick()
        if not self._end_handled and self.path and self.player.get_state()==vlc.State.Ended and not self.processing and self.job is None:
            self._end_handled=True
            if self.auto_next_box.isChecked():QTimer.singleShot(0,lambda:self.next_film(1,True))
    def seek_fraction(self,value):
        if self.stream_url and not self.player.is_seekable():self.status.setText('Siaran ini tidak menyediakan seek/timeshift.');return
        self.player.set_position(value)
    def seek_relative(self,seconds):
        if not (self.path or self.stream_url):return
        if self.stream_url and not self.player.is_seekable():self.status.setText('Siaran ini tidak menyediakan seek/timeshift.');return
        current=max(0,self.player.get_time());length=self.player.get_length()
        target=max(0,current+int(seconds*1000))
        if isinstance(length,int) and length>0:target=min(target,max(0,length-100))
        self.player.set_time(target)
    def apply_speed(self,value=None):
        if hasattr(self,'speed_box'):
            rate=self.speed_box.value()
            if self.player.set_rate(rate)==-1:self.status.setText('Kecepatan ini tidak didukung oleh media/perangkat saat ini.')
    def set_muted(self,value):
        self.player.audio_set_mute(bool(value));self.request_audio_sync()
    def request_audio_sync(self):self.audio_sync_deadline=time.monotonic()+10
    def sync_master_audio(self):
        if not getattr(self,'audio_sync_deadline',0) or time.monotonic()>self.audio_sync_deadline:return
        wanted=self.volume.value();muted=self.mute_action.isChecked()
        try:
            result=self.player.audio_set_volume(wanted);self.player.audio_set_mute(muted);self.last_audio_sync_result=result
            # A successful setter is authoritative; some backends have stale/no readback.
            if result==0:self.audio_sync_deadline=0
        except Exception:pass
    def volume_changed(self,value):
        self.player.audio_set_volume(value);self.request_audio_sync()
    def toggle_fullscreen(self):
        if self.pip is not None and self.pip.isFullScreen():
            if self._fullscreen_was_pip:self.pip.showNormal();self.pip.full_button.setText('Fullscreen (F11)')
            else:self.leave_pip()
        else:
            self._fullscreen_was_pip=self.pip is not None
            if self.pip is None:self.toggle_pip()
            if self.pip:self.pip.full_button.setText('Keluar fullscreen (Esc)');self.pip.showFullScreen()
    def toggle_stereo(self,enabled):
        if enabled and getattr(self,'tv_active',False):self.tv_enable.setChecked(False)
        self.stereo_on=bool(enabled);self._last_frame_revision=-1;self._last_frame=None
        self.video.clear_frame();self.change_renderer(self.renderer.currentIndex())
    def configure_native_audio(self):
        from native_audio import configure
        panel=getattr(self,'audio_panel',None);state=panel.state() if panel else {'enabled':False,'boost':0}
        configure(self.player,state,getattr(self,'audio_dsp','off'))
    def configure_video_output(self):
        probe=getattr(self,'_selftest_audio_probe',None)
        if '--self-test' in sys.argv and probe is not None:probe.attach(self.player)
        self.configure_native_audio()
        if getattr(self,'stereo_on',False) or self.canvas_active():
            size=(960,540) if self.stereo_on or getattr(self,'tv_active',False) else (3840,2160)
            self.memory_video=MemoryVideo(self.player,*size);self.video.setAttribute(Qt.WA_NoSystemBackground,False)
        else:
            self.memory_video=None;self.video.clear_frame();self.bind_video()
        try:self.player.video_set_key_input(False);self.player.video_set_mouse_input(False)
        except Exception:pass
    def render_stereo(self,force=False):
        if not self.stereo_on or self.memory_video is None or self.video.audio_title:return
        frame,revision=self.memory_video.snapshot()
        if frame is None or (not force and revision==self._last_frame_revision):return
        self._last_frame_revision=revision
        try:
            result=compose_anaglyph(frame,self.red_shift.value(),self.blue_shift.value(),self.stereo_layout.currentData(),self.stereo_scheme.currentData(),self.swap_eyes.isChecked())
            self.video.show_frame(result)
        except Exception as e:self.status.setText('Render 3D gagal: '+str(e))
    def open_second_player(self):
        other=next((w for w in PlayerExtras.windows if w is not self and not w.closing),None)
        if other:other.showNormal();other.raise_();other.activateWindow();return other
        other=type(self)();other.key.setText(self.key.text());other.model.setText(self.model.text())
        other.mute_action.setChecked(True);other.set_muted(True);other.show()
        screen=QApplication.primaryScreen().availableGeometry();half=screen.width()//2
        self.setGeometry(screen.x(),screen.y(),half,screen.height());other.setGeometry(screen.x()+half,screen.y(),screen.width()-half,screen.height())
        other.status.setText('Pemutar kedua siap. Suara awal mute; klik Mute untuk mengaktifkan suara.')
        return other
    def eventFilter(self,obj,event):
        if event.type()==QEvent.Wheel and obj is self.video and hasattr(self,'wheel_seconds') and (self.path or self.stream_url):
            self.handle_video_wheel(event.angleDelta().y());return True
        if event.type()==QEvent.KeyPress and QApplication.activeWindow() is not None and QApplication.activeWindow() in (self,getattr(self,'pip',None)):
            if event.key()==Qt.Key_O and event.modifiers() & Qt.ControlModifier:self.open_video();return True
            focused=QApplication.focusWidget()
            if not isinstance(focused,(QLineEdit,QAbstractSpinBox,QComboBox,QAbstractItemView)):
                key=event.key()
                actions={Qt.Key_Left:lambda:self.seek_relative(-5),Qt.Key_Right:lambda:self.seek_relative(5),Qt.Key_Up:lambda:self.seek_relative(60),Qt.Key_Down:lambda:self.seek_relative(-60),Qt.Key_Space:self.play,Qt.Key_M:lambda:self.mute_action.trigger(),Qt.Key_F:self.toggle_fullscreen,Qt.Key_F11:self.toggle_fullscreen,Qt.Key_PageDown:lambda:self.next_film(1),Qt.Key_PageUp:lambda:self.next_film(-1)}
                if key==Qt.Key_Escape and self.pip:
                    self.toggle_fullscreen() if self.pip.isFullScreen() else self.leave_pip();return True
                if key in actions:actions[key]();return True
        return super().eventFilter(obj,event)
    def dragEnterEvent(self,event):
        if event.mimeData().hasUrls():event.acceptProposedAction()
    def dropEvent(self,event):
        paths=[url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        self.add_paths(p for p in paths if Path(p).is_file());event.acceptProposedAction()
    def extras_cleanup(self):
        QApplication.instance().removeEventFilter(self);self.stereo_timer.stop()
        if self.storage_enabled:
            try:write_playlist(self.playlist_cache,[self.playlist_widget.item(i).data(Qt.UserRole) for i in range(self.playlist_widget.count())])
            except Exception:pass
        self.modern_cleanup();self.cinema_cleanup()
        if self in PlayerExtras.windows:PlayerExtras.windows.remove(self)
