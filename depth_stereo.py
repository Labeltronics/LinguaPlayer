"""Depth-based synthetic stereo and native stereo packing, without anaglyph."""
import sys,time,threading,os,uuid
from pathlib import Path
import numpy as np
from PySide6.QtCore import QThread,Signal,Qt
from PySide6.QtGui import QImage
ROOT=Path(getattr(sys,'_MEIPASS',Path(__file__).parent))
DEFAULT_MODEL=ROOT/'models'/'midas-small.onnx'
def resize_frame(frame,width,height):
    frame=np.ascontiguousarray(frame,dtype=np.uint8);h,w,_=frame.shape;image=QImage(frame.data,w,h,w*4,QImage.Format_RGB32).copy().scaled(width,height,Qt.IgnoreAspectRatio,Qt.SmoothTransformation)
    return np.frombuffer(image.bits(),dtype=np.uint8,count=image.sizeInBytes()).reshape(height,image.bytesPerLine())[:,:width*4].reshape(height,width,4).copy()
def resize_depth(depth,width,height):
    depth=np.asarray(depth,np.float32);h,w=depth.shape;y=np.linspace(0,h-1,height);x=np.linspace(0,w-1,width);a=y.astype(int);b=x.astype(int);c=np.minimum(a+1,h-1);d=np.minimum(b+1,w-1);fy=(y-a)[:,None];fx=(x-b)[None,:]
    return ((1-fy)*((1-fx)*depth[a[:,None],b]+fx*depth[a[:,None],d])+fy*((1-fx)*depth[c[:,None],b]+fx*depth[c[:,None],d])).astype(np.float32)
class DepthModel:
    def __init__(self,path=DEFAULT_MODEL,provider='CPU'):
        import onnxruntime as ort
        if not Path(path).is_file():raise ValueError('Model kedalaman MiDaS tidak ditemukan. Pilih model-small.onnx melalui menu 3D.')
        options=ort.SessionOptions();options.intra_op_num_threads=2;options.enable_mem_pattern=False;options.execution_mode=ort.ExecutionMode.ORT_SEQUENTIAL
        if provider=='DirectML' and 'DmlExecutionProvider' not in ort.get_available_providers():raise ValueError('DirectML tidak tersedia pada runtime/perangkat ini. Pilih CPU secara eksplisit.')
        providers=['DmlExecutionProvider','CPUExecutionProvider'] if provider=='DirectML' else ['CPUExecutionProvider']
        self.session=ort.InferenceSession(str(path),sess_options=options,providers=providers);self.provider=self.session.get_providers()
        if provider=='DirectML' and 'DmlExecutionProvider' not in self.provider:raise ValueError('DirectML gagal diinisialisasi. Pilih CPU; tidak ada klaim GPU aktif.')
        shape=self.session.get_inputs()[0].shape
        if shape!=[1,3,256,256]:raise ValueError('Gunakan model MiDaS v2.1 small ONNX 1×3×256×256 yang kompatibel.')
        self.input=self.session.get_inputs()[0].name
    def infer(self,frame):
        # Official ONNX export embeds normalization; input is RGB float 0..1.
        image=resize_frame(frame,256,256)[:,:,[2,1,0]].astype(np.float32)/255
        prediction=self.session.run(None,{self.input:np.ascontiguousarray(image.transpose(2,0,1)[None])})[0]
        depth=np.asarray(prediction,np.float32).squeeze()
        if depth.ndim!=2 or not np.isfinite(depth).all():raise ValueError('Model menghasilkan depth tidak valid.')
        low,high=np.percentile(depth,[2,98]);return np.clip((depth-low)/max(1e-6,high-low),0,1).astype(np.float32)
def stereo_pair(frame,depth,strength=2.,convergence=.5):
    if frame.ndim!=3 or frame.shape[2]!=4:raise ValueError('Frame harus BGRA.')
    h,w,_=frame.shape;depth=resize_depth(depth,w,h)
    if not np.isfinite(depth).all() or not np.isfinite(strength+convergence):raise ValueError('Pengaturan kedalaman tidak valid.')
    disparity=(np.clip(depth,0,1)-np.clip(convergence,0,1))*w*np.clip(strength,0,6)/200
    x=np.arange(w)[None,:];y=np.arange(h)[:,None];left=np.clip(np.rint(x-disparity),0,w-1).astype(int);right=np.clip(np.rint(x+disparity),0,w-1).astype(int)
    return frame[y,left].copy(),frame[y,right].copy()
def unpack_stereo(frame,layout):
    h,w,_=frame.shape
    if layout.startswith('sbs'):
        m=w//2;left,right=frame[:,:m],frame[:,w-m:]
        if layout=='sbs-half':left=resize_frame(left,w,h);right=resize_frame(right,w,h)
    elif layout.startswith('tb'):
        m=h//2;left,right=frame[:m],frame[h-m:]
        if layout=='tb-half':left=resize_frame(left,w,h);right=resize_frame(right,w,h)
    else:return frame,frame
    return left.copy(),right.copy()
def pack_stereo(left,right,output='SBS half',swap=False,shift=0):
    if left.shape!=right.shape:raise ValueError('Ukuran mata kiri/kanan berbeda.')
    if swap:left,right=right,left
    h,w,_=left.shape
    if shift:
        x=np.arange(w);left=left[:,np.clip(x-int(shift),0,w-1)];right=right[:,np.clip(x+int(shift),0,w-1)]
    if output=='SBS full':return np.ascontiguousarray(np.concatenate((left,right),axis=1))
    if output=='TB full':return np.ascontiguousarray(np.concatenate((left,right),axis=0))
    if output=='SBS half':return np.ascontiguousarray(np.concatenate((resize_frame(left,w//2,h),resize_frame(right,w//2,h)),axis=1))
    if output=='TB half':return np.ascontiguousarray(np.concatenate((resize_frame(left,w,h//2),resize_frame(right,w,h//2)),axis=0))
    if output=='Mata kiri':return np.ascontiguousarray(left)
    if output=='Mata kanan':return np.ascontiguousarray(right)
    yy,xx=np.indices((h,w));mask=(yy%2==0) if output=='Interlaced baris' else (xx%2==0) if output=='Interlaced kolom' else ((xx+yy)%2==0)
    return np.ascontiguousarray(np.where(mask[:,:,None],left,right))
def render(frame,settings,model=None,previous=None):
    if settings['input']=='2d-ai':
        if model is None:raise ValueError('Model kedalaman diperlukan.')
        depth=model.infer(frame)
        # Smooth depth only when scene appearance remains similar; hard cuts reset it.
        if previous is not None and previous.shape==depth.shape:depth=depth*(1-settings.get('smooth',.3))+previous*settings.get('smooth',.3)
        left,right=stereo_pair(frame,depth,settings['strength'],settings['convergence'])
    else:left,right=unpack_stereo(frame,settings['input']);depth=None
    return pack_stereo(left,right,settings['output'],settings['swap'],settings['shift']),depth
class StereoWorker(QThread):
    rendered=Signal(object,int,float);failure=Signal(str);ready=Signal(str)
    def __init__(self,settings):super().__init__();self.settings=dict(settings);self.condition=threading.Condition();self.pending=None;self.ending=False
    def submit(self,frame,generation,settings):
        with self.condition:self.pending=(frame.copy(),generation,dict(settings));self.condition.notify()
    def close(self):
        with self.condition:self.ending=True;self.condition.notify()
    def run(self):
        model=None;model_key=None;previous=None;last_gray=None;last_generation=None
        try:
            while True:
                with self.condition:
                    while self.pending is None and not self.ending:self.condition.wait(.2)
                    if self.ending:return
                    frame,generation,settings=self.pending;self.pending=None
                started=time.monotonic();key=(settings['model'],settings['provider'])
                if settings['input']=='2d-ai' and key!=model_key:
                    model=DepthModel(*key);model_key=key;previous=None;self.ready.emit('Provider model: '+', '.join(model.provider)+'; warp/packing berjalan di CPU.')
                gray=frame[::16,::16,:3].mean(axis=2)
                if generation!=last_generation or last_gray is None or gray.shape!=last_gray.shape or np.abs(gray-last_gray).mean()>30:previous=None
                output,previous=render(frame,settings,model,previous);last_gray=gray;last_generation=generation
                if not self.ending:self.rendered.emit(output,generation,(time.monotonic()-started)*1000)
        except Exception as exc:self.failure.emit(str(exc))
class StereoExport(QThread):
    progress=Signal(str);done=Signal(str);failure=Signal(str)
    def __init__(self,source,target,settings):super().__init__();self.source=source;self.target=target;self.settings=dict(settings)
    def run(self):
        import imageio_ffmpeg
        target=Path(self.target);partial=target.with_name(target.stem+'.'+uuid.uuid4().hex+'.partial.mp4');reader=writer=None
        try:
            if Path(self.source).resolve()==target.resolve():raise ValueError('Hasil 3D tidak boleh menimpa sumber.')
            model=DepthModel(self.settings['model'],self.settings['provider']) if self.settings['input']=='2d-ai' else None
            reader=imageio_ffmpeg.read_frames(self.source,pix_fmt='rgb24');meta=next(reader);w,h=meta['size'];fps=float(meta['fps']);previous=None
            for i,raw in enumerate(reader):
                if self.isInterruptionRequested():raise InterruptedError('Ekspor 3D dibatalkan')
                rgb=np.frombuffer(raw,np.uint8).reshape(h,w,3);frame=np.empty((h,w,4),np.uint8);frame[:,:,:3]=rgb[:,:,::-1];frame[:,:,3]=255
                output,previous=render(frame,self.settings,model,previous);oh,ow,_=output.shape
                if writer is None:
                    writer=imageio_ffmpeg.write_frames(str(partial),(ow,oh),fps=fps,codec='libx264',quality=8,macro_block_size=2,audio_path=self.source if meta.get('audio_codec') else None,audio_codec='aac' if meta.get('audio_codec') else None,ffmpeg_log_level='error',ffmpeg_timeout=20);writer.send(None)
                writer.send(np.ascontiguousarray(output[:,:,[2,1,0]]).tobytes())
                if i%10==0:self.progress.emit(f'Ekspor 3D: frame {i}, {i/fps:.1f} detik. Ukuran {ow}×{oh}.')
            if writer:writer.close();writer=None
            if self.isInterruptionRequested():raise InterruptedError('Ekspor 3D dibatalkan')
            if not partial.is_file() or partial.stat().st_size==0:raise ValueError('Hasil ekspor 3D kosong.')
            os.replace(partial,target);self.done.emit(str(target))
        except Exception as exc:
            if writer:
                try:writer.close()
                except Exception:pass
                writer=None
            partial.unlink(missing_ok=True);self.failure.emit(str(exc))
        finally:
            if reader:reader.close()
            if writer:writer.close()
