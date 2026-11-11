"""CPU anaglyph rendering. Stereo sources retain stereo; 2D only gains a plane shift."""
import ctypes, threading
import numpy as np
import vlc
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage,QPainter,QColor
from PySide6.QtWidgets import QFrame

def shifted(image,pixels):
    pixels=int(pixels);out=np.zeros_like(image);width=image.shape[1]
    if pixels==0:return image
    if abs(pixels)>=width:return out
    if pixels>0:out[:,pixels:]=image[:,:width-pixels]
    else:out[:,:width+pixels]=image[:,-pixels:]
    return out

def compose_anaglyph(frame,red=0,blue=0,layout='2d',scheme='red-cyan',swap=False):
    if frame.ndim!=3 or frame.shape[2]!=4:raise ValueError('Frame harus BGRA/RV32')
    h,w,_=frame.shape
    if layout.startswith('sbs'):
        mid=w//2
        if mid<1:raise ValueError('Frame SBS terlalu kecil')
        left,right=frame[:,:mid],frame[:,w-mid:]
        if layout=='sbs-half':
            indices=(np.arange(w)*mid//w).astype(int);left=left[:,indices];right=right[:,indices]
    elif layout.startswith('tb'):
        mid=h//2
        if mid<1:raise ValueError('Frame TB terlalu kecil')
        left,right=frame[:mid],frame[h-mid:]
        if layout=='tb-half':
            indices=(np.arange(h)*mid//h).astype(int);left=left[indices];right=right[indices]
    else:left=right=frame
    if swap:left,right=right,left
    left=shifted(left,red);right=shifted(right,blue)
    out=np.zeros_like(left)
    out[:,:,2]=left[:,:,2];out[:,:,0]=right[:,:,0]
    if scheme=='red-cyan':out[:,:,1]=right[:,:,1]
    out[:,:,3]=255
    return np.ascontiguousarray(out)

class VideoSurface(QFrame):
    def __init__(self):
        super().__init__();self.image=None;self.setFocusPolicy(Qt.StrongFocus)
    def paintEvent(self,event):
        if self.image is None:return super().paintEvent(event)
        painter=QPainter(self);painter.fillRect(self.rect(),QColor('black'))
        size=self.image.size().scaled(self.size(),Qt.KeepAspectRatio)
        x=(self.width()-size.width())//2;y=(self.height()-size.height())//2
        painter.drawImage(x,y,self.image.scaled(size,Qt.KeepAspectRatio,Qt.FastTransformation))
    def show_frame(self,array):
        h,w,_=array.shape
        self.image=QImage(array.data,w,h,w*4,QImage.Format_RGB32).copy();self.update()
    def clear_frame(self):self.image=None;self.update()

class MemoryVideo:
    """Keep callbacks and frame storage alive for the lifetime of the VLC player."""
    def __init__(self,player):
        self.lock=threading.Lock();self.width=0;self.height=0;self.buffer=None;self.latest=None;self.frame_count=0;self.revision=0
        # char* must stay a writable pointer; c_char_p would turn it into Python bytes.
        FormatCallback=ctypes.CFUNCTYPE(ctypes.c_uint,ctypes.POINTER(ctypes.c_void_p),ctypes.POINTER(ctypes.c_char),ctypes.POINTER(ctypes.c_uint),ctypes.POINTER(ctypes.c_uint),ctypes.POINTER(ctypes.c_uint),ctypes.POINTER(ctypes.c_uint))
        @FormatCallback
        def setup(opaque,chroma,width,height,pitches,lines):
            try:
                scale=min(1.,960/max(1,width[0]),540/max(1,height[0]))
                w=max(16,int(width[0]*scale)//16*16);h=max(2,int(height[0]*scale))
                with self.lock:
                    self.width=w;self.height=h;size=w*h*4
                    self.storage=(ctypes.c_ubyte*(size+32))()
                    address=(ctypes.addressof(self.storage)+31)&~31
                    self.buffer=(ctypes.c_ubyte*size).from_address(address)
                ctypes.memmove(chroma,b'RV32',4);width[0]=w;height[0]=h;pitches[0]=w*4;lines[0]=h
                return 1
            except Exception:return 0
        @vlc.CallbackDecorators.VideoLockCb
        def lock(opaque,planes):
            self.lock.acquire();planes[0]=ctypes.addressof(self.buffer);return None
        @vlc.CallbackDecorators.VideoUnlockCb
        def unlock(opaque,picture,planes):self.lock.release()
        @vlc.CallbackDecorators.VideoDisplayCb
        def display(opaque,picture):
            try:
                with self.lock:
                    self.latest=np.ctypeslib.as_array(self.buffer).reshape(self.height,self.width,4).copy()
                    self.frame_count+=1;self.revision+=1
            except Exception:pass
        @vlc.CallbackDecorators.VideoCleanupCb
        def cleanup(opaque):pass
        self.callbacks=(lock,unlock,display,setup,cleanup)
        player.video_set_callbacks(lock,unlock,display,None)
        player.video_set_format_callbacks(setup,cleanup)
    def snapshot(self):
        with self.lock:return self.latest,self.revision
