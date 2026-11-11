import os,subprocess,tempfile,time,functools,uuid
from pathlib import Path
from PySide6.QtCore import QThread,Signal
import imageio_ffmpeg

RESOLUTIONS={'HD 720p':(1280,720),'Full HD 1080p':(1920,1080),'4K 2160p':(3840,2160)}

def export_command(ff,source,target,width,height,mode='CPU',sharpness=0,source_size=None):
    size=f'{width}:{height}'
    sw,sh=source_size or (width,height);factor=min(width/max(1,sw),height/max(1,sh))
    rw=max(2,int(sw*factor)//2*2);rh=max(2,int(sh*factor)//2*2)
    # CPU path is always available. GPU filters/encoders require a supported FFmpeg build and driver.
    if mode=='NVIDIA CUDA':
        start=['-hwaccel','cuda','-hwaccel_output_format','cuda'];filters=f'scale_cuda={rw}:{rh}:format=nv12,hwdownload,format=nv12,pad={size}:(ow-iw)/2:(oh-ih)/2,setsar=1';encoder=['-c:v','h264_nvenc','-cq','20']
        # CUDA path keeps scaling on GPU; native playback sharpening is a separate control.
    elif mode=='Intel QSV':
        start=['-init_hw_device','qsv=hw','-filter_hw_device','hw'];filters=f'format=nv12,hwupload=extra_hw_frames=64,vpp_qsv=w={rw}:h={rh},hwdownload,format=nv12,pad={size}:(ow-iw)/2:(oh-ih)/2,setsar=1';encoder=['-c:v','h264_qsv','-global_quality','20']
    elif mode=='AMD AMF':
        start=[];filters=f'scale={size}:force_original_aspect_ratio=decrease,pad={size}:(ow-iw)/2:(oh-ih)/2,setsar=1';encoder=['-c:v','h264_amf','-quality','quality','-qp_i','20','-qp_p','22']
    else:
        start=[];filters=f'scale={size}:force_original_aspect_ratio=decrease:flags=lanczos,pad={size}:(ow-iw)/2:(oh-ih)/2,setsar=1'
        if sharpness>0:filters+=f',unsharp=5:5:{min(1.5,float(sharpness))}:5:5:0'
        encoder=['-c:v','libx264','-preset','medium','-crf','20']
    return [ff,'-v','error','-y',*start,'-i',str(source),'-map','0:v:0','-map','0:a?', '-vf',filters,*encoder,*([] if mode in ('NVIDIA CUDA','Intel QSV') else ['-pix_fmt','yuv420p']),'-c:a','aac','-b:a','192k','-sn','-movflags','+faststart','-progress','pipe:1','-nostats',str(target)]

@functools.lru_cache(maxsize=2)
def export_capabilities(ff):
    flags={'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {}
    enc=subprocess.run([ff,'-hide_banner','-encoders'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=15,**flags).stdout
    filters=subprocess.run([ff,'-hide_banner','-filters'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=15,**flags).stdout
    return {'CPU':{'encoder':'libx264','encoder_present':'libx264' in enc,'filter_present':'scale ' in filters},
            'NVIDIA CUDA':{'encoder':'h264_nvenc','encoder_present':'h264_nvenc' in enc,'filter_present':'scale_cuda' in filters},
            'Intel QSV':{'encoder':'h264_qsv','encoder_present':'h264_qsv' in enc,'filter_present':'vpp_qsv' in filters},
            'AMD AMF':{'encoder':'h264_amf','encoder_present':'h264_amf' in enc,'filter_present':'scale ' in filters}}

class ExportJob(QThread):
    status=Signal(str);success=Signal(str);failure=Signal(str)
    def __init__(self,source,target,resolution,mode,sharpness,duration=0):
        super().__init__();self.args=(source,target,resolution,mode,sharpness,duration);self.proc=None
    def cancel(self):
        self.requestInterruption()
        if self.proc is not None:
            try:self.proc.kill()
            except OSError:pass
    def run(self):
        source,target,resolution,mode,sharpness,duration=self.args
        target=Path(target);temporary=target.with_name(target.stem+'.'+uuid.uuid4().hex+'.cyber80-partial'+target.suffix)
        try:
            if Path(source).resolve()==target.resolve():raise ValueError('Hasil ekspor tidak boleh menimpa video sumber.')
            capabilities=export_capabilities(imageio_ffmpeg.get_ffmpeg_exe())[mode]
            if not capabilities['encoder_present'] or not capabilities['filter_present']:raise RuntimeError('Encoder/filter '+mode+' tidak tersedia dalam FFmpeg ini. Pilih CPU. Ketersediaan encoder tidak menjamin driver/GPU cocok.')
            width,height=RESOLUTIONS[resolution]
            source_size=None
            try:
                reader=imageio_ffmpeg.read_frames(str(source));source_size=next(reader).get('size');reader.close()
            except Exception:pass
            flags={'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {}
            with tempfile.TemporaryFile() as errors:
                self.proc=subprocess.Popen(export_command(imageio_ffmpeg.get_ffmpeg_exe(),source,temporary,width,height,mode,sharpness,source_size),stdout=subprocess.PIPE,stderr=errors,text=True,**flags)
                for line in self.proc.stdout:
                    if self.isInterruptionRequested():self.proc.kill();break
                    if line.startswith('out_time_ms='):
                        try:
                            seconds=int(line.strip().split('=')[1])/1e6
                            self.status.emit(f'Ekspor {resolution} / {mode}: '+(f'{min(100,seconds/duration*100):.1f}%' if duration>0 else f'{seconds:.1f} detik'))
                        except ValueError:pass
                self.proc.wait()
                if self.isInterruptionRequested():raise InterruptedError('Ekspor dibatalkan')
                if self.proc.returncode:
                    errors.seek(0);detail=errors.read().decode(errors='replace')[-1500:]
                    raise RuntimeError('Ekspor gagal. Encoder/filter GPU mungkin tidak tersedia atau driver tidak cocok; pilih CPU bila perlu.\n'+detail)
            os.replace(temporary,target);self.success.emit(str(target))
        except Exception as exc:
            temporary.unlink(missing_ok=True);self.failure.emit(str(exc))
        finally:
            if self.proc is not None and self.proc.stdout is not None:self.proc.stdout.close()
            self.proc=None
