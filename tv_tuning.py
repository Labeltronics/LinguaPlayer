"""Bounded actual frame decoding before TV playback; no URL/headers in errors."""
import re,subprocess,tempfile,time,threading
import imageio_ffmpeg
from PySide6.QtCore import QThread,Signal
from video_render import flags
from web_transfer import checked_url

def media_headers(values):
    values=values or {};result={}
    for name in ('User-Agent','Referer'):
        value=next((str(v) for k,v in values.items() if str(k).lower()==name.lower()),'')
        if value:
            if len(value)>2048 or any(c in value for c in '\r\n\x00'):raise ValueError('Header siaran tidak valid.')
            if name=='Referer':value=checked_url(value)
            result[name]=value
    return result

def ffmpeg_headers(values):
    h=media_headers(values);args=[]
    if h.get('User-Agent'):args+=['-user_agent',h['User-Agent']]
    if h.get('Referer'):args+=['-referer',h['Referer']]
    return args

def candidates(rows,selected,limit=4):
    others=[r for r in rows if selected.get('id') and r.get('id')==selected['id'] and bool(r.get('adult'))==bool(selected.get('adult'))]
    result=[];seen=set()
    for r in [selected,*others]:
        if r['url'] not in seen:result.append(r);seen.add(r['url'])
        if len(result)>=limit:break
    return result

def decode_frame(row,cancelled=lambda:False,timeout=12):
    url=checked_url(row['url']);args=[imageio_ffmpeg.get_ffmpeg_exe(),'-v','info','-rw_timeout','8000000',*ffmpeg_headers(row.get('headers')),'-analyzeduration','4000000','-probesize','4000000','-i',url,'-map','0:v:0','-map','0:a:0?','-frames:v','1','-t','1','-f','null','-']
    with tempfile.TemporaryFile() as log:
        proc=subprocess.Popen(args,stdout=subprocess.DEVNULL,stderr=log,**flags());deadline=time.monotonic()+timeout;timed=False
        try:
            while proc.poll() is None:
                if cancelled():raise InterruptedError('Dibatalkan')
                if time.monotonic()>deadline:timed=True;break
                time.sleep(.05)
        finally:
            if proc.poll() is None:proc.kill()
            proc.wait()
        log.seek(0);text=log.read(512*1024).decode(errors='replace')
    if cancelled():raise InterruptedError('Dibatalkan')
    if timed:return False,'Timeout / sinyal lambat'
    if proc.returncode==0 and re.search(r'frame=\s*[1-9]',text):return True,('Gambar dan audio terdeteksi' if 'Audio:' in text else 'Video terdeteksi; sumber tanpa audio')
    for code in ('401','403','404','410','451'):
        if re.search(r'(?i)(?:HTTP[^\n]*|server returned|error|status)[^\n]*\b'+code+r'\b',text):return False,'Sumber menolak HTTP '+code
    if 'Audio:' in text and 'Video:' not in text:return False,'Hanya audio / radio'
    return False,'Video tidak dapat didekode / sumber offline'

class TuneTV(QThread):
    checked=Signal(str,str);ready=Signal(object);failed=Signal(str)
    def __init__(self,rows,selected):super().__init__();self.rows=candidates(rows,selected);self.stop_event=threading.Event()
    def cancel(self):self.stop_event.set();self.requestInterruption()
    def run(self):
        video_only=None
        for i,row in enumerate(self.rows):
            if self.stop_event.is_set():return
            self.checked.emit(row['key'],f'Memeriksa gambar {i+1}/{len(self.rows)} …')
            try:ok,status=decode_frame(row,self.stop_event.is_set)
            except InterruptedError:return
            except Exception:ok,status=False,'Sumber/header tidak dapat diproses'
            self.checked.emit(row['key'],status)
            if ok:
                if status=='Gambar dan audio terdeteksi':
                    if not self.stop_event.is_set():self.ready.emit({**row,'_has_audio':True})
                    return
                if video_only is None:video_only={**row,'_has_audio':False}
        if video_only is not None and not self.stop_event.is_set():self.ready.emit(video_only);return
        if not self.stop_event.is_set():self.failed.emit('Tidak ada sumber bergambar yang dapat dipakai saat ini. Perbarui katalog atau pilih saluran lain. Pembatasan wilayah/izin siaran tidak dibuka oleh aplikasi.')
