"""Browser/download, visual cutting, stereo TV and mouse/zoom controls."""
import sys,time,json
from pathlib import Path
from PySide6.QtCore import Qt,QEvent,QTimer
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QComboBox,QDoubleSpinBox,QSpinBox,QCheckBox,QDockWidget,QFileDialog,QInputDialog,QMessageBox,QScrollArea)
from depth_stereo import StereoWorker,StereoExport,DEFAULT_MODEL
class AdvancedAddons:
    def setup_addons(self):
        self.language_studio=None;self.download_manager=None;self.browsers=[];self.cut_editor=None;self.video_studio=None;self.tv_active=False;self.tv_worker=None;self.tv_export=None;self.tv_generation=0;self.tv_last_revision=-1;self.wheel_remainder=0;self.wheel_hook=None
        self.wheel_seconds=5
        if self.storage_enabled:
            try:self.wheel_seconds=max(1,min(300,int(self.settings.value('wheel_seconds',5))))
            except (ValueError,TypeError):pass
        menu=self.menuBar().addMenu('Cyber80 Hub')
        for title,fn in [('Studio Bahasa • Subtitle / Dubbing / Lirik',self.open_language_studio),('Browser multimedia • Privat',lambda:self.open_browser(True)),('Browser normal (opsional)',lambda:self.open_browser(False)),('Download Manager',lambda:self.get_download_manager().show()),('Video Studio • Editor multilayer',lambda:self.open_video_studio()),('Koleksi media',self.show_collection),('Cutting visual',self.open_cut_editor),('3D / 4D Cinema',self.show_tv),('Atur scroll seek',self.set_wheel_seconds)]:menu.addAction(title,fn)
        self.tv_dock=QDockWidget('3D TV / Depth AI / 4D cue preview',self);self.tv_dock.setObjectName('tv3d');panel=QWidget();box=QVBoxLayout(panel)
        row=QHBoxLayout();box.addLayout(row);self.tv_enable=QCheckBox('Aktifkan stereo TV (bukan anaglyph)');row.addWidget(self.tv_enable)
        self.tv_input=QComboBox()
        for label,value in [('2D → stereo AI','2d-ai'),('SBS half asli','sbs-half'),('SBS full asli','sbs-full'),('TB half asli','tb-half'),('TB full asli','tb-full')]:self.tv_input.addItem(label,value)
        row.addWidget(self.tv_input);self.tv_output=QComboBox();self.tv_output.addItems(['SBS half','SBS full','TB half','TB full','Interlaced baris','Interlaced kolom','Checkerboard','Mata kiri','Mata kanan']);row.addWidget(self.tv_output)
        row=QHBoxLayout();box.addLayout(row);self.tv_strength=QDoubleSpinBox();self.tv_strength.setRange(0,6);self.tv_strength.setSingleStep(.1);self.tv_strength.setValue(2);self.tv_strength.setSuffix(' % lebar');row.addWidget(QLabel('Kedalaman AI'));row.addWidget(self.tv_strength)
        self.tv_convergence=QDoubleSpinBox();self.tv_convergence.setRange(0,1);self.tv_convergence.setSingleStep(.05);self.tv_convergence.setValue(.5);row.addWidget(QLabel('Bidang layar / pop-out AI'));row.addWidget(self.tv_convergence)
        self.tv_shift=QSpinBox();self.tv_shift.setRange(-100,100);row.addWidget(QLabel('Konvergensi mata ±px'));row.addWidget(self.tv_shift)
        self.tv_swap=QCheckBox('Tukar kiri/kanan');row.addWidget(self.tv_swap)
        row=QHBoxLayout();box.addLayout(row);self.tv_smooth=QDoubleSpinBox();self.tv_smooth.setRange(0,.9);self.tv_smooth.setValue(.3);self.tv_smooth.setSingleStep(.1);row.addWidget(QLabel('Stabilisasi depth'));row.addWidget(self.tv_smooth)
        self.tv_provider=QComboBox();self.tv_provider.addItems(['CPU','DirectML']);row.addWidget(QLabel('Inference'));row.addWidget(self.tv_provider)
        self.tv_model=str(DEFAULT_MODEL);b=QPushButton('Pilih model MiDaS ONNX');b.clicked.connect(self.choose_depth_model);row.addWidget(b)
        b=QPushButton('Reset 3D');b.clicked.connect(self.reset_tv);row.addWidget(b)
        row=QHBoxLayout();box.addLayout(row)
        for title,fn in [('Ekspor stereo TV MP4',self.export_tv),('Batal ekspor 3D',self.cancel_tv_export),('Tambahkan cue 4D',self.add_4d_cue),('Simpan cue 4D',self.save_4d_cues),('Buka cue 4D',self.load_4d_cues)]:
            b=QPushButton(title);b.clicked.connect(fn);row.addWidget(b)
        self.tv_status=QLabel('Mode SBS/TB membutuhkan TV/headset 3D dan mode input yang cocok. AI memperkirakan kedalaman, bukan mengembalikan geometri asli. Warp/packing berjalan di CPU; preview dibatasi 960×540. 4D di sini hanya pratinjau cue, tidak mengendalikan kursi/perangkat fisik.');self.tv_status.setWordWrap(True);box.addWidget(self.tv_status)
        self.cues_4d=[];self.cue_4d_label=QLabel('4D: tidak ada cue aktif (preview saja)');box.addWidget(self.cue_4d_label)
        self.tv_dock.setWidget(panel);self.addDockWidget(Qt.BottomDockWidgetArea,self.tv_dock);self.tabifyDockWidget(self.subtitle_dock,self.tv_dock);self.tv_dock.hide();self.tv_enable.toggled.connect(self.toggle_tv)
        for control in (self.tv_input,self.tv_output,self.tv_provider):control.currentIndexChanged.connect(self.tv_config_changed)
        for control in (self.tv_strength,self.tv_convergence,self.tv_smooth,self.tv_shift):control.valueChanged.connect(self.tv_config_changed)
        self.tv_swap.toggled.connect(self.tv_config_changed)
        self.zoom_dock=QDockWidget('Zoom / Speed / Capture',self);self.zoom_dock.setObjectName('zoom');panel=QWidget();row=QHBoxLayout(panel)
        self.zoom_box=QDoubleSpinBox();self.zoom_box.setRange(.1,1000);self.zoom_box.setDecimals(2);self.zoom_box.setValue(100);self.zoom_box.setSingleStep(10);self.zoom_box.setSuffix(' %');row.addWidget(QLabel('Zoom'));row.addWidget(self.zoom_box)
        self.zoom_quality=QComboBox();self.zoom_quality.addItems(['Sumber asli','Full HD 1080p','4K 2160p']);row.addWidget(self.zoom_quality)
        for text,fn in [('Zoom −',lambda:self.zoom_box.setValue(self.zoom_box.value()/1.25)),('Zoom +',lambda:self.zoom_box.setValue(self.zoom_box.value()*1.25)),('Reset zoom',lambda:(self.zoom_box.setValue(100),self.zoom_quality.setCurrentIndex(0))),('Capture tampilan',self.capture_view),('Capture frame sumber',self.capture_dialog)]:
            b=QPushButton(text);b.clicked.connect(fn);row.addWidget(b)
        self.zoom_dock.setWidget(panel);self.addDockWidget(Qt.BottomDockWidgetArea,self.zoom_dock);self.zoom_dock.hide();self.zoom_box.valueChanged.connect(self.zoom_changed);self.zoom_quality.currentIndexChanged.connect(self.zoom_changed)
        menu.addAction('Zoom / Speed / Capture',lambda:(self.zoom_dock.show(),self.zoom_dock.raise_()))
        for dock in (self.tv_dock,self.zoom_dock):
            content=dock.widget();scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(content);scroll.setMinimumSize(240,90);dock.setWidget(scroll)
        self.canvas_timer=QTimer(self);self.canvas_timer.timeout.connect(self.render_canvas);self.canvas_timer.start(33)
        if sys.platform=='win32' and '--self-test' not in sys.argv:
            try:
                from wheel_input import NativeWheelHook
                self.wheel_hook=NativeWheelHook(self)
            except Exception:self.status.setText('Scroll memakai event Qt; hook mouse Windows tidak tersedia.')
    def set_wheel_seconds(self):
        value,ok=QInputDialog.getInt(self,'Scroll video','Detik per satu langkah scroll (atas maju, bawah mundur):',self.wheel_seconds,1,300)
        if ok:
            self.wheel_seconds=value
            if self.storage_enabled:self.settings.setValue('wheel_seconds',value)
    def handle_video_wheel(self,delta):
        self.wheel_remainder+=delta;steps=int(self.wheel_remainder/120)
        if steps:self.wheel_remainder-=steps*120;self.seek_relative(steps*self.wheel_seconds)
    def get_download_manager(self):
        if self.download_manager is None:
            from download_manager import DownloadManager
            self.download_manager=DownloadManager(self)
        return self.download_manager
    def open_browser(self,private=True):
        private=bool(private or self.private_session)
        if sys.platform=='win32':
            import ctypes,os,PySide6
            qt=Path(PySide6.__file__).parent
            candidates=[qt,qt/'Qt'/'bin']
            os.environ['PATH']=os.pathsep.join(str(p) for p in candidates if p.is_dir())+os.pathsep+os.environ.get('PATH','')
            # VLC's legacy DLL directory must not be inherited by Chromium helpers.
            ctypes.windll.kernel32.SetDllDirectoryW(str(qt))
        from web_browser import BrowserWindow
        browser=next((b for b in self.browsers if b.private==private),None)
        if browser is None:browser=BrowserWindow(self,private or self.private_session);self.browsers.append(browser)
        browser.showNormal();browser.raise_();browser.activateWindow();return browser
    def open_language_studio(self):
        if self.language_studio is None:
            from language_studio import LanguageStudio
            self.language_studio=LanguageStudio(self)
        self.language_studio.showNormal();self.language_studio.raise_();self.language_studio.activateWindow();return self.language_studio
    def open_video_studio(self,import_current=True):
        if self.video_studio is None or self.video_studio.released:
            from video_editor import VideoStudio
            self.video_studio=VideoStudio(self)
            if import_current and self.path:self.video_studio.import_paths([self.path])
        self.video_studio.showNormal();self.video_studio.raise_();self.video_studio.activateWindow();return self.video_studio
    def open_cut_editor(self):
        if not self.path:self.status.setText('Buka video/audio lokal terlebih dahulu.');return
        if self.cut_editor and not self.cut_editor.released:self.cut_editor.showNormal();self.cut_editor.raise_();return self.cut_editor
        from cut_editor import CutEditor
        self.cut_editor=CutEditor(self,self.path);self.cut_editor.show();return self.cut_editor
    def show_tv(self):self.tv_dock.show();self.tv_dock.raise_()
    def choose_depth_model(self):
        path,_=QFileDialog.getOpenFileName(self,'MiDaS v2.1 small ONNX 256×256',self.tv_model,'ONNX (*.onnx)')
        if path:self.tv_model=path;self.tv_config_changed()
    def tv_settings(self):return {'input':self.tv_input.currentData(),'output':self.tv_output.currentText(),'strength':self.tv_strength.value(),'convergence':self.tv_convergence.value(),'shift':self.tv_shift.value(),'swap':self.tv_swap.isChecked(),'smooth':self.tv_smooth.value(),'model':self.tv_model,'provider':self.tv_provider.currentText()}
    def reset_tv(self):self.tv_strength.setValue(2);self.tv_convergence.setValue(.5);self.tv_shift.setValue(0);self.tv_swap.setChecked(False);self.tv_smooth.setValue(.3)
    def tv_config_changed(self,*args):self.tv_generation+=1;self.tv_last_revision=-1
    def canvas_active(self):return getattr(self,'tv_active',False) or (hasattr(self,'zoom_box') and (abs(self.zoom_box.value()-100)>.001 or self.zoom_quality.currentIndex()!=0))
    def toggle_tv(self,value):
        if value and self.stereo_on:self.stereo_check.setChecked(False)
        self.tv_active=value;self.tv_generation+=1;self.tv_last_revision=-1
        if value:
            if self.tv_worker and self.tv_worker.isRunning():self.tv_enable.blockSignals(True);self.tv_enable.setChecked(False);self.tv_enable.blockSignals(False);self.tv_active=False;self.tv_status.setText('Worker 3D sebelumnya sedang berhenti; coba lagi sesaat.');return
            self.tv_worker=StereoWorker(self.tv_settings());self.tv_worker.rendered.connect(self.tv_rendered);self.tv_worker.failure.connect(self.tv_failed);self.tv_worker.ready.connect(self.tv_status.setText);self.tv_worker.start()
        elif self.tv_worker:self.tv_worker.close()
        self.change_renderer(self.renderer.currentIndex())
    def tv_failed(self,message):
        self.tv_status.setText('3D: '+message);self.tv_enable.setChecked(False)
    def tv_rendered(self,frame,generation,elapsed):
        if self.tv_active and generation==self.tv_generation:
            self.video.show_frame(frame);self.tv_status.setText(f'Stereo TV aktif — pemrosesan {elapsed:.0f} ms/frame. Preview maksimum 960×540; gunakan ekspor untuk resolusi sumber. Provider diminta: {self.tv_provider.currentText()}, warp CPU. Interlaced perlu pemetaan piksel TV yang cocok.')
    def zoom_changed(self,*args):
        self.video.zoom_factor=self.zoom_box.value()/100;self.video.upscale_size=(1920,1080) if self.zoom_quality.currentIndex()==1 else (3840,2160) if self.zoom_quality.currentIndex()==2 else None
        self.tv_generation+=1;self.tv_last_revision=-1;self.change_renderer(self.renderer.currentIndex());self.status.setText('Zoom memakai interpolasi halus; peningkatan resolusi tidak mengembalikan detail sumber yang hilang.')
    def render_canvas(self):
        if self.stereo_on or not self.canvas_active() or self.memory_video is None or self.video.audio_title:return
        frame,revision=self.memory_video.snapshot()
        if frame is None or revision==self.tv_last_revision:return
        self.tv_last_revision=revision
        if self.tv_active and self.tv_worker and self.tv_worker.isRunning():self.tv_worker.submit(frame,self.tv_generation,self.tv_settings())
        elif not self.tv_active:self.video.show_frame(frame)
    def capture_view(self):
        if self.video.image is None:self.capture_dialog();return
        path,_=QFileDialog.getSaveFileName(self,'Capture tampilan zoom/3D','Cyber80_View.png','PNG (*.png)')
        if path and not self.video.grab().save(path):self.error('Capture tidak dapat disimpan.')
    def export_tv(self):
        if not self.path or self.tv_export is not None:return
        path,_=QFileDialog.getSaveFileName(self,'Ekspor stereo TV MP4',Path(self.path).stem+'_stereo.mp4','MP4 (*.mp4)')
        if not path:return
        self.tv_export=StereoExport(self.path,path,self.tv_settings());self.tv_export.progress.connect(self.tv_status.setText);self.tv_export.done.connect(lambda p:self.tv_status.setText('Ekspor stereo selesai: '+p));self.tv_export.failure.connect(self.tv_status.setText);self.tv_export.finished.connect(self.tv_export_finished);self.tv_export.start()
    def cancel_tv_export(self):
        if self.tv_export:self.tv_export.requestInterruption()
    def tv_export_finished(self):self.tv_export.deleteLater();self.tv_export=None
    def add_4d_cue(self):
        effect,ok=QInputDialog.getItem(self,'Cue 4D (preview saja)','Jenis efek:',['Getaran','Angin','Gerak','Cahaya'],0,False)
        if not ok:return
        intensity,ok=QInputDialog.getInt(self,'Cue 4D','Intensitas profil 0–100:',30,0,100)
        if ok:
            duration,ok=QInputDialog.getDouble(self,'Cue 4D','Durasi efek pratinjau (detik):',2,.1,60,2)
            if ok:self.cues_4d.append({'start':max(0,self.player.get_time())/1000,'duration':duration,'effect':effect,'intensity':intensity})
    def save_4d_cues(self):
        path,_=QFileDialog.getSaveFileName(self,'Simpan profil cue 4D (tanpa hardware)','Cyber80_4D.json','JSON (*.json)')
        if path:
            from web_transfer import atomic_json
            atomic_json(path,{'version':1,'preview_only':True,'cues':self.cues_4d})
    def load_4d_cues(self):
        path,_=QFileDialog.getOpenFileName(self,'Buka profil cue 4D','','JSON (*.json)')
        if path:
            try:
                data=json.loads(Path(path).read_text());cues=data['cues']
                if len(cues)>10000:raise ValueError('Terlalu banyak cue.')
                import math
                for c in cues:
                    if not all(math.isfinite(float(c[k])) for k in ('start','duration','intensity')) or c['start']<0 or not 0<c['duration']<=60 or not 0<=c['intensity']<=100 or c['effect'] not in ('Getaran','Angin','Gerak','Cahaya'):raise ValueError('Cue tidak valid.')
                self.cues_4d=cues
            except (OSError,ValueError,TypeError,KeyError) as exc:self.error('Profil cue tidak valid: '+str(exc))
    def addons_tick(self):
        if not hasattr(self,'cues_4d'):return
        t=max(0,self.player.get_time())/1000;active=[c for c in self.cues_4d if c['start']<=t<c['start']+c['duration']]
        self.cue_4d_label.setText('4D preview: '+', '.join(f'{c["effect"]} {c["intensity"]}%' for c in active) if active else '4D: tidak ada cue aktif (preview saja)')
    def addons_can_close(self):
        language=getattr(self,'language_studio',None)
        if language and language.job is not None:
            self.status.setText('Studio Bahasa masih bekerja. Sembunyikan aplikasi, atau batalkan dan tunggu pekerjaan selesai.');return False
        if language and language.preview and not language.preview.released:language.preview.close()
        studio=getattr(self,'video_studio',None)
        if studio and not studio.released:
            if studio.import_job:studio.import_job.requestInterruption();self.status.setText('Menunggu impor Video Studio selesai.');return False
            if studio.job:studio.cancel();self.status.setText('Menunggu render Video Studio selesai.');return False
            studio.close()
            if not studio.released:return False

        if self.snapshot_job is not None and self.snapshot_job.isRunning():self.snapshot_job.cancel();self.status.setText('Menunggu capture frame selesai.');return False
        if self.download_manager and self.download_manager.active():self.status.setText('Jeda/batalkan unduhan dan tunggu koneksi berhenti sebelum menutup. Browser boleh disembunyikan.');return False
        if self.cut_editor and self.cut_editor.job is not None:self.cut_editor.cancel_export();self.status.setText('Menunggu pembatalan cutting selesai.');return False
        if self.tv_export is not None:self.cancel_tv_export();self.status.setText('Menunggu ekspor 3D berhenti.');return False
        if self.tv_worker and self.tv_worker.isRunning():
            self.tv_worker.close()
            if not self.tv_worker.wait(1000):self.status.setText('Menunggu inference 3D selesai sebelum menutup.');return False
        return True
    def addons_cleanup(self):
        self.canvas_timer.stop()
        if self.wheel_hook:self.wheel_hook.close()
        if self.cut_editor and not self.cut_editor.released:self.cut_editor.close()
        for browser in self.browsers:browser.shutdown()
        if self.download_manager:self.download_manager.shutdown()
