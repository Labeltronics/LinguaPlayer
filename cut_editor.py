"""Visual trim editor with its own VLC preview and sequential export queue."""
import sys,time
from pathlib import Path
import vlc
from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import (QDialog,QWidget,QVBoxLayout,QHBoxLayout,QPushButton,QLabel,QSlider,QDoubleSpinBox,QCheckBox,QFileDialog,QListWidget,QListWidgetItem,QMessageBox)
from media_jobs import UtilityJob

def trim_range(a,b,duration):
    import math
    if not all(math.isfinite(v) for v in (a,b,duration)) or not 0<=a<b<=duration+.05:raise ValueError('Pilih rentang awal/akhir yang berada dalam durasi media.')
    return a,b
class PreviewPlayer(QDialog):
    def __init__(self,owner,source,title='Preview media'):
        super().__init__(owner,Qt.Window);self.owner=owner;self.source=str(source);self.job=None;self.exports=[];self.setWindowTitle('Cyber80 • '+title);self.resize(1000,700)
        options=['--ignore-config','--no-video-title-show','--no-osd','--quiet','--no-plugins-cache']
        if sys.platform=='win32':options+=['--vout=wingdi','--avcodec-hw=none']
        if '--self-test' in sys.argv:options+=['--aout=dummy']
        self.engine=vlc.Instance(*options);self.player=self.engine.media_player_new();self.released=False
        box=QVBoxLayout(self);self.surface=QWidget();self.surface.setAttribute(Qt.WA_NativeWindow);self.surface.setMinimumSize(320,180);self.surface.setStyleSheet('background:black');box.addWidget(self.surface,1)
        handle=int(self.surface.winId())
        if sys.platform=='win32':self.player.set_hwnd(handle)
        elif sys.platform=='darwin':self.player.set_nsobject(handle)
        else:self.player.set_xwindow(handle)
        media=self.engine.media_new(self.source) if self.source.startswith(('http://','https://')) else self.engine.media_new_path(self.source)
        self.player.set_media(media);self.player.video_set_key_input(False);self.player.video_set_mouse_input(False)
        row=QHBoxLayout();box.addLayout(row)
        for label,fn in [('Play/Pause',lambda:self.player.pause() if self.player.is_playing() else self.player.play()),('−5 s',lambda:self.seek_relative(-5)),('+5 s',lambda:self.seek_relative(5)),('Frame +',self.player.next_frame)]:
            b=QPushButton(label);b.clicked.connect(fn);row.addWidget(b)
        self.seek=QSlider(Qt.Horizontal);self.seek.setRange(0,10000);self.seek.sliderReleased.connect(lambda:self.player.set_position(self.seek.value()/10000));row.addWidget(self.seek,1)
        self.mute=QCheckBox('Mute');self.mute.toggled.connect(self.player.audio_set_mute);row.addWidget(self.mute)
        self.info=QLabel('Memuat media …');box.addWidget(self.info);self.timer=QTimer(self);self.timer.timeout.connect(self.tick);self.timer.start(100);self.player.play()
    def seek_relative(self,n):self.player.set_time(max(0,self.player.get_time()+n*1000))
    def tick(self):
        if not self.seek.isSliderDown():self.seek.setValue(max(0,int(self.player.get_position()*10000)))
        if self.job is None:self.info.setText(f'{max(0,self.player.get_time())/1000:.3f} / {max(0,self.player.get_length())/1000:.3f} detik')
        if self.player.get_state()==vlc.State.Error:self.info.setText('Media tidak dapat diputar langsung. Untuk media bersesi login, gunakan Download lalu putar hasilnya.')
    def closeEvent(self,event):
        if self.job is not None:
            self.job.cancel();self.info.setText('Membatalkan ekspor; tutup lagi setelah selesai.');event.ignore();return
        if not self.released:self.timer.stop();self.player.stop();self.player.release();self.engine.release();self.released=True
        event.accept()
class CutEditor(PreviewPlayer):
    def __init__(self,owner,source):
        super().__init__(owner,source,'Cutting visual • '+Path(source).name);self.initialized=False;self.duration=0;self.batch=[];self.export_source=str(source);self.export_error=False
        from player_extras import AUDIO_SUFFIXES
        self.audio_only=Path(source).suffix.lower() in AUDIO_SUFFIXES
        if self.audio_only:
            self.audio_label=QLabel('Audio • '+Path(source).name+'\nGunakan timeline dan tanda awal/akhir untuk memotong musik.',self.surface);self.audio_label.setAlignment(Qt.AlignCenter);self.audio_label.setStyleSheet('color:white;background:black');cover=QVBoxLayout(self.surface);cover.addWidget(self.audio_label)
        self.player.audio_set_mute(True);self.mute.setChecked(True)
        row=QHBoxLayout();self.layout().insertLayout(2,row);self.start=QDoubleSpinBox();self.end=QDoubleSpinBox()
        for label,spin in [('Awal',self.start),('Akhir',self.end)]:spin.setRange(0,864000);spin.setDecimals(3);spin.setSuffix(' detik');row.addWidget(QLabel(label));row.addWidget(spin)
        for label,fn in [('Tandai awal',lambda:self.start.setValue(max(0,self.player.get_time())/1000)),('Tandai akhir',lambda:self.end.setValue(max(0,self.player.get_time())/1000)),('Ke awal',lambda:self.player.set_time(round(self.start.value()*1000))),('Preview pilihan',self.preview_selection),('Tambah potongan',self.add_clip)]:
            button=QPushButton(label);button.clicked.connect(fn);row.addWidget(button)
        self.loop=QCheckBox('Ulangi pilihan A–B');row.addWidget(self.loop)
        self.clips=QListWidget();self.clips.setMaximumHeight(100);self.layout().addWidget(self.clips);row=QHBoxLayout();self.layout().addLayout(row)
        for label,fn in [('Ekspor pilihan MP4',self.export_selection),('Ekspor semua potongan',self.export_all),('Hapus potongan',lambda:self.clips.takeItem(self.clips.currentRow())),('Batalkan ekspor',self.cancel_export)]:
            b=QPushButton(label);b.clicked.connect(fn);row.addWidget(b)
        note=QLabel('Preview memakai suara mute awal agar tidak bercampur dengan pemutar utama. Rentang ditampilkan dalam detik/milidetik. Ekspor re-encode H.264/AAC; sumber tidak diubah.');note.setWordWrap(True);self.layout().addWidget(note)
    def tick(self):
        super().tick()
        if not hasattr(self,'initialized'):return
        length=self.player.get_length()/1000
        if length>0 and not self.initialized:
            self.duration=length;self.start.setMaximum(length);self.end.setMaximum(length);self.end.setValue(length);self.initialized=True
        if self.loop.isChecked() and self.player.is_playing() and self.end.value()>self.start.value() and self.player.get_time()>=self.end.value()*1000:self.player.set_time(round(self.start.value()*1000))
    def selection(self):return trim_range(self.start.value(),self.end.value(),self.duration)
    def preview_selection(self):
        try:a,b=self.selection();self.player.set_time(round(a*1000));self.loop.setChecked(True);self.player.play()
        except ValueError as exc:QMessageBox.warning(self,'Cutting',str(exc))
    def add_clip(self):
        try:
            a,b=self.selection();item=QListWidgetItem(f'{a:.3f} → {b:.3f} s ({b-a:.3f} detik)');item.setData(Qt.UserRole,(a,b));self.clips.addItem(item)
        except ValueError as exc:QMessageBox.warning(self,'Cutting',str(exc))
    def export_selection(self):
        if self.job is not None:return
        try:a,b=self.selection()
        except ValueError as exc:QMessageBox.warning(self,'Cutting',str(exc));return
        extension='m4a' if self.audio_only else 'mp4'
        path,_=QFileDialog.getSaveFileName(self,'Ekspor potongan',Path(self.source).stem+'_clip.'+extension,f'{extension.upper()} (*.{extension})')
        if path:self.export_error=False;self.batch=[(path,a,b)];self.next_export()
    def export_all(self):
        if self.job is not None or not self.clips.count():return
        folder=QFileDialog.getExistingDirectory(self,'Folder hasil semua potongan')
        if not folder:return
        import uuid
        self.export_error=False;prefix=Path(self.source).stem+'_'+uuid.uuid4().hex[:6];extension='m4a' if self.audio_only else 'mp4'
        self.batch=[(str(Path(folder)/f'{prefix}_{i+1:03}.{extension}'),*self.clips.item(i).data(Qt.UserRole)) for i in range(self.clips.count())];self.next_export()
    def next_export(self):
        if not self.batch:
            if not self.export_error:self.info.setText('Seluruh potongan selesai diekspor.')
            return
        path,a,b=self.batch.pop(0);self.job=UtilityJob(self.export_source,path,'Potong klip audio M4A' if self.audio_only else 'Potong klip MP4',a,b)
        self.job.status.connect(self.info.setText);self.job.success.connect(lambda p:self.owner.status.setText('Potongan selesai: '+p));self.job.failure.connect(self.export_failed);self.job.finished.connect(self.export_finished);self.job.start()
    def export_failed(self,message):self.batch=[];self.export_error=True;self.info.setText(message)
    def export_finished(self):self.job.deleteLater();self.job=None;QTimer.singleShot(0,self.next_export)
    def cancel_export(self):
        self.batch=[]
        if self.job:self.job.cancel()
