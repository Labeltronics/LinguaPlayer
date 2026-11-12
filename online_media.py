"""Shared full-feature player for browser media and Internet TV.
Online identity stays separate from local paths, so it never enters file caches.
"""
import os,time,uuid
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QDockWidget,QFileDialog,QInputDialog)
import imageio_ffmpeg
from dubbing import DubbingJob
from web_transfer import checked_url

class StreamRecording(DubbingJob):
    def __init__(self,source,target,seconds,start=0,headers=None):super().__init__(source,target,[]);self.seconds=seconds;self.start=start;self.headers=headers
    def execute(self):
        source=checked_url(self.source);target=Path(self.target).resolve()
        if target.exists():raise ValueError('Nama hasil sudah ada. Pilih nama baru.')
        if not 1<=self.seconds<=7200 or not 0<=self.start<=864000:raise ValueError('Rentang rekaman tidak valid.')
        if target.suffix.lower()!='.mp4':raise ValueError('Rekaman disimpan sebagai MP4 H.264/AAC.')
        partial=target.with_name(target.stem+'.'+uuid.uuid4().hex+'.partial.mp4')
        try:
            args=[imageio_ffmpeg.get_ffmpeg_exe(),'-v','error','-y','-rw_timeout','15000000']
            if self.start:args+=['-ss',str(self.start)]
            from tv_tuning import ffmpeg_headers
            args+=ffmpeg_headers(self.headers)
            args+=['-re','-i',source,'-t',str(self.seconds),'-map','0:v:0?','-map','0:a:0?','-c:v','libx264','-preset','veryfast','-crf','22','-pix_fmt','yuv420p','-c:a','aac','-movflags','+faststart',str(partial)]
            self.progress.emit('Merekam cuplikan media online ke MP4 …');self.run_command(args)
            from video_render import probe
            if probe(imageio_ffmpeg.get_ffmpeg_exe(),partial)['duration']<=0:raise ValueError('Rekaman kosong; posisi di luar durasi atau siaran tidak tersedia.')
            if self.cancelled():raise InterruptedError('Dibatalkan')
            # Windows rename cannot overwrite; exclusive copy is portable to FAT/exFAT.
            created=False
            try:
                with target.open('xb') as out,partial.open('rb') as inp:
                    created=True
                    while True:
                        if self.cancelled():raise InterruptedError('Dibatalkan')
                        data=inp.read(4*1024*1024)
                        if not data:break
                        out.write(data)
            except Exception:
                if created:target.unlink(missing_ok=True)
                raise
            return str(target)
        finally:partial.unlink(missing_ok=True)

class OnlinePreview:
    """Compatibility handle for browser/TV callers; rendering uses the main Window."""
    def __init__(self,owner,source):self.owner=owner;self.source=source
    @property
    def released(self):return self.owner.closing or self.owner.stream_url!=self.source
    @property
    def player(self):return self.owner.player
    def show(self):self.owner.showNormal();self.owner.raise_();self.owner.activateWindow()
    def close(self):
        if not self.released:
            self.owner.stop_online_subtitles();self.owner.player.stop();self.owner.stream_url='';self.owner.online_caption=None;self.owner.video.clear_frame();self.owner.fill([]);self.owner.subtitle.clear()

class OnlineMedia:
    def setup_online(self,menu):
        self.stream_audio_available=None;self.stream_headers={};self.online_job=None;self.online_record_job=None;self.last_online_recording='';self.last_online_source='';self.online_caption=None;self.online_cues=[];self.online_clock=0.;self.stream_live=False;self.stream_title='';self.online_browser=None
        self.online_dock=QDockWidget('Media online • kontrol Cyber80 bersama',self);self.online_dock.setObjectName('online_media');panel=QWidget();box=QVBoxLayout(panel)
        self.online_status=QLabel('Media browser/TV memakai mesin pemutar yang sama: volume/EQ, fullscreen/PiP, zoom, capture, 3D preview dan Cast. Seek/speed bergantung stream. Editing/ekspor membutuhkan rekaman/unduhan lokal.');self.online_status.setTextFormat(Qt.PlainText);self.online_status.setWordWrap(True);box.addWidget(self.online_status)
        row=QHBoxLayout();box.addLayout(row)
        for text,fn in [('Subtitle online',self.start_online_subtitles),('Hentikan subtitle',self.stop_online_subtitles),('Rekam cuplikan MP4',self.record_online),('Batalkan rekaman',self.cancel_online_record),('Edit rekaman',self.edit_online_record),('Unduh lewat browser',self.show_online_browser)]:
            b=QPushButton(text);b.clicked.connect(fn);row.addWidget(b)
        self.online_dock.setWidget(panel);self.addDockWidget(Qt.BottomDockWidgetArea,self.online_dock);self.tabifyDockWidget(self.subtitle_dock,self.online_dock);self.online_dock.hide();menu.addAction('Kontrol media online',lambda:(self.online_dock.show(),self.online_dock.raise_()))
    def open_stream(self,url,title='Media online',live=False,browser=None,headers=None):
        if self.online_job is not None:self.stop_online_subtitles();self.status.setText('Tunggu subtitle online berhenti, lalu pilih media lagi.');return None
        if self.job is not None and self.job.isRunning():self.status.setText('Batalkan subtitle file sebelum mengganti media.');return None
        from tv_tuning import media_headers
        approved_headers=media_headers(headers)
        source=checked_url(url);self.stream_audio_available=None;self.stream_headers=approved_headers;was_online=bool(self.stream_url);self.record_position();self.surface_generation+=1;self.player.stop();self.path='';self.stream_url=source;self.stream_title=title;self.stream_live=live;self.online_browser=browser;self.online_caption=None;self.online_cues=[];self.pending_seek=None;self.pending_pause=False;self.playback_error_reported=False;self.cache_context=None;self.retry_context=None;self.resume_offset=0;self.ab_a=None;self.ab_b=None
        self.tv_generation+=1;self.tv_last_revision=-1;self.cues_4d=[]
        if not was_online:self.change_renderer(self.renderer.currentIndex())
        self.bind_video();media=self.make_stream_media();self.player.set_media(media);self.video.audio_title='';self.video.clear_frame();self.fill([])
        if self.player.play()==-1:raise RuntimeError('Sumber online tidak dapat diputar. Coba unduh media yang Anda berhak akses lalu buka file lokal.')
        self.apply_speed();self.player.audio_set_mute(self.mute_action.isChecked());self.request_audio_sync();self.online_dock.show();self.online_dock.raise_();self.online_status.setText(title+' • kontrol pemutar lengkap aktif. Subtitle online memiliki jeda analisis. Rekam/unduh sebelum cutting, editing dan ekspor.');self.setWindowTitle('Cyber80 Players • '+title);self.showNormal();self.raise_();self.activateWindow();return OnlinePreview(self,source)
    def make_stream_media(self):
        media=self.engine.media_new(self.stream_url);media.add_option(':network-caching=2500')
        if self.stream_headers.get('User-Agent'):media.add_option(':http-user-agent='+self.stream_headers['User-Agent'])
        if self.stream_headers.get('Referer'):media.add_option(':http-referrer='+self.stream_headers['Referer'])
        return media
    def start_online_subtitles(self,language=None):
        if not self.stream_url:self.status.setText('Putar media online terlebih dahulu.');return
        if self.online_job:return
        if self.stream_audio_available is False:self.online_status.setText('Subtitle membutuhkan audio; sumber TV ini hanya mengirim video.');return
        # QPushButton.clicked may supply a boolean argument.
        if not isinstance(language,str):language=self.lang.currentData() if self.lang.currentIndex()>=0 and self.lang.currentText()==self.lang.itemText(self.lang.currentIndex()) else self.lang.currentText().strip()
        if not self.key.text().strip():self.online_status.setText('Isi Gemini API key pada Subtitle / AI.');return
        from live_tv_subtitles import LiveTVSubtitles
        self.online_job=LiveTVSubtitles(self.stream_url,self.key.text().strip(),self.model.text().strip(),language or 'id',headers=self.stream_headers);self.online_caption='';self.online_job.progress.connect(self.online_status.setText);self.online_job.failed.connect(self.online_status.setText);self.online_job.captions.connect(self.receive_online_captions);self.online_job.finished.connect(self.online_finished);self.online_job.start()
    def receive_online_captions(self,cues,delay):
        self.online_cues=cues;self.online_clock=time.monotonic();
        languages=sorted({c.language for c in cues if c.language})
        if languages:self.detected.setText('Bahasa sumber terdeteksi (perkiraan): '+', '.join(languages))
        self.online_status.setText(f'Subtitle online tertunda sekitar {delay:.0f} detik. API yang tertinggal dapat melewati potongan lama.')
    def online_tick(self):
        if self.online_job and self.stream_url:
            t=time.monotonic()-self.online_clock;self.online_caption='\n'.join(c.target or c.source for c in self.online_cues if c.start<=t<c.end)
    def stop_online_subtitles(self):
        if self.online_job:self.online_job.cancel();self.online_status.setText('Membatalkan subtitle online; tunggu permintaan API aktif berhenti.')
        self.online_cues=[];self.online_caption=None
    def online_finished(self):self.online_job.deleteLater();self.online_job=None;self.online_cues=[];self.online_caption=None
    def record_online(self):
        if not self.stream_url or self.online_record_job:return
        seconds,ok=QInputDialog.getInt(self,'Rekam cuplikan','Durasi rekaman dalam detik (maksimum 2 jam):',60,1,7200)
        if not ok:return
        target,_=QFileDialog.getSaveFileName(self,'Simpan cuplikan online dengan nama baru','Cyber80_Online.mp4','MP4 (*.mp4)')
        if not target:return
        self.online_record_job=StreamRecording(self.stream_url,target,seconds,0 if self.stream_live else max(0,self.player.get_time())/1000,headers=self.stream_headers);self.online_record_job.progress.connect(self.online_status.setText);self.online_record_job.completed.connect(self.record_ready);self.online_record_job.failed.connect(self.online_status.setText);self.online_record_job.finished.connect(self.record_finished);self.online_record_job.start()
    def record_ready(self,path):self.last_online_recording=path;self.last_online_source=self.online_record_job.source;self.online_status.setText('Rekaman selesai: '+path+' — pilih Edit rekaman atau buka file untuk memakai semua alat offline.')
    def record_finished(self):self.online_record_job.deleteLater();self.online_record_job=None
    def cancel_online_record(self):
        if self.online_record_job:self.online_record_job.cancel()
    def edit_online_record(self):
        if not self.last_online_recording:self.online_status.setText('Rekam cuplikan atau unduh media terlebih dahulu.');return
        studio=self.open_video_studio(False);studio.import_paths([self.last_online_recording])
    def show_online_browser(self):
        if self.online_browser:self.online_browser.showNormal();self.online_browser.raise_();self.online_browser.activateWindow()
        else:self.online_status.setText('Untuk siaran TV gunakan Rekam cuplikan; untuk VOD browser gunakan Download Manager pada browser.')
