"""Cancellable offline utility jobs. Sources are read-only; outputs commit atomically."""
import os,subprocess,tempfile,uuid,shutil,math
from pathlib import Path
from PySide6.QtCore import QThread,Signal
import imageio_ffmpeg

def utility_arguments(kind,start=0,end=0):
    if kind=='Remux MKV':return ['-map','0','-c','copy']
    if kind=='Ekstrak audio WAV':return ['-vn','-c:a','pcm_s16le']
    if kind=='Ekstrak audio MP3':return ['-vn','-c:a','libmp3lame','-q:a','2']
    if kind=='Normalisasi audio WAV':return ['-vn','-af','loudnorm=I=-16:TP=-1.5:LRA=11','-c:a','pcm_s16le']
    if kind=='Potong klip audio M4A':
        if not all(math.isfinite(v) for v in (start,end)) or start<0 or end<=start:raise ValueError('Rentang audio tidak valid.')
        return ['-ss',str(start),'-t',str(end-start),'-map','0:a:0','-vn','-c:a','aac','-b:a','192k','-movflags','+faststart']
    if kind=='Potong klip MP4':
        if not all(math.isfinite(v) for v in (start,end)) or start<0 or end<=start:raise ValueError('Waktu akhir klip harus lebih besar dari awal.')
        return ['-ss',str(start),'-t',str(end-start),'-map','0:v:0','-map','0:a?','-c:v','libx264','-preset','fast','-crf','20','-pix_fmt','yuv420p','-c:a','aac','-movflags','+faststart']
    if kind=='Video lirik MP4':return ['-f','lavfi','-i','color=c=0x101827:s=1920x1080:r=25','-map','1:v:0','-map','0:a:0','-vf',"subtitles=subtitle.srt:force_style='Alignment=5,FontSize=22,Outline=2'",'-c:v','libx264','-preset','veryfast','-crf','20','-pix_fmt','yuv420p','-c:a','aac','-shortest','-movflags','+faststart']
    if kind=='Bakar subtitle MP4':return ['-map','0:v:0','-map','0:a?','-vf','subtitles=subtitle.srt','-c:v','libx264','-preset','fast','-crf','20','-pix_fmt','yuv420p','-c:a','aac','-movflags','+faststart']
    raise ValueError('Jenis pekerjaan tidak dikenal.')

class UtilityJob(QThread):
    status=Signal(str);success=Signal(str);failure=Signal(str)
    def __init__(self,source,target,kind,start=0,end=0,subtitle_text=''):
        super().__init__();self.args=(source,target,kind,start,end,subtitle_text);self.proc=None
    def cancel(self):
        self.requestInterruption()
        if self.proc:
            try:self.proc.kill()
            except OSError:pass
    def run(self):
        source,target,kind,start,end,subtitle_text=self.args;target=Path(target).resolve();source=Path(source).resolve()
        partial=target.with_name(target.stem+'.'+uuid.uuid4().hex+'.partial'+target.suffix)
        try:
            if source==target:raise ValueError('Hasil tidak boleh menimpa sumber.')
            arguments=utility_arguments(kind,start,end)
            if self.isInterruptionRequested():raise InterruptedError('Dibatalkan')
            flags={'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {}
            with tempfile.TemporaryDirectory(prefix='cyber80-tools-') as temp,tempfile.TemporaryFile() as errors:
                if kind in ('Bakar subtitle MP4','Video lirik MP4'):
                    if not subtitle_text.strip():raise ValueError('Belum ada subtitle untuk dibakar.')
                    Path(temp,'subtitle.srt').write_text(subtitle_text,encoding='utf-8')
                self.proc=subprocess.Popen([imageio_ffmpeg.get_ffmpeg_exe(),'-v','error','-y','-i',str(source),*arguments,'-progress','pipe:1','-nostats',str(partial)],cwd=temp,stdout=subprocess.PIPE,stderr=errors,text=True,**flags)
                for line in self.proc.stdout:
                    if self.isInterruptionRequested():self.proc.kill();break
                    if line.startswith('out_time='):self.status.emit(kind+': '+line.strip().split('=',1)[1])
                self.proc.wait()
                if self.isInterruptionRequested():raise InterruptedError('Pekerjaan dibatalkan')
                if self.proc.returncode:
                    errors.seek(0);raise RuntimeError('FFmpeg gagal: '+errors.read().decode(errors='replace')[-1500:])
            os.replace(partial,target);self.success.emit(str(target))
        except Exception as exc:partial.unlink(missing_ok=True);self.failure.emit(str(exc))
        finally:
            if self.proc is not None and self.proc.stdout is not None:self.proc.stdout.close()
            self.proc=None
