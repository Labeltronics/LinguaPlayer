"""Continuous bounded audio segment capture -> delayed live TV captions.
Uses a separate stream connection. No live dubbing, no URL/credential logging.
"""
import os,subprocess,tempfile,time,wave
from pathlib import Path
from PySide6.QtCore import Signal
import imageio_ffmpeg
from dubbing import DubbingJob
from core import transcribe
from web_transfer import checked_url
from video_render import flags
class LiveTVSubtitles(DubbingJob):
    captions=Signal(object,float)
    def __init__(self,url,key,model,language='id',headers=None):
        super().__init__(checked_url(url),'',[],key=key,model=model,language=language);self.headers=headers
    def run(self):
        try:
            if not self.key:raise ValueError('Isi Gemini API key di panel Subtitle / AI pemutar.')
            with tempfile.TemporaryDirectory(prefix='cyber80-tv-caption-') as folder:
                root=Path(folder);last=-1
                with tempfile.TemporaryFile() as errors:
                    from tv_tuning import ffmpeg_headers
                    self.proc=subprocess.Popen([imageio_ffmpeg.get_ffmpeg_exe(),'-v','error','-rw_timeout','15000000',*ffmpeg_headers(self.headers),'-re','-i',self.source,'-map','0:a:0','-vn','-ac','1','-ar','16000','-af','aresample=async=1','-c:a','pcm_s16le','-f','segment','-segment_time','15','-reset_timestamps','1',str(root/'part-%08d.wav')],stdout=subprocess.DEVNULL,stderr=errors,**flags())
                    try:
                        while not self.cancelled():
                            files=sorted(root.glob('part-*.wav'));ended=self.proc.poll() is not None
                            closed=files if ended else files[:-1]
                            ready=[p for p in closed if int(p.stem.split('-')[1])>last]
                            if not ready:
                                if ended:raise ValueError('Siaran berhenti atau audio tidak dapat diambil. Coba saluran lain.')
                                self.progress.emit('Menunggu potongan suara TV (sekitar 15 detik) …');time.sleep(.2);continue
                            # Keep the newest complete segment when the API falls behind.
                            current=ready[-1];index=int(current.stem.split('-')[1]);captured=current.stat().st_mtime
                            with wave.open(str(current)) as audio:duration=audio.getnframes()/audio.getframerate()
                            if duration<.2:last=index;continue
                            self.progress.emit('Menerjemahkan suara siaran … subtitle tertunda oleh analisis API.')
                            cues=transcribe(current.read_bytes(),self.key,self.model,self.language,duration,0,cancelled=self.cancelled,progress=self.progress.emit)
                            if self.cancelled():break
                            self.captions.emit(cues,max(0,time.time()-captured)+duration);last=index
                            for path in closed:
                                if int(path.stem.split('-')[1])<=last:path.unlink(missing_ok=True)
                    finally:
                        if self.proc and self.proc.poll() is None:self.proc.kill()
                        if self.proc:self.proc.wait(timeout=10)
                        self.proc=None
        except Exception as exc:
            if not self.cancelled():
                message=str(exc)
                if self.key:message=message.replace(self.key,'[KEY DISEMBUNYIKAN]')
                self.failed.emit('Subtitle TV berhenti: '+message[:1200])
