"""Gemini Files attachment -> background subtitle generation, bounded upload memory.
Protocol references: https://ai.google.dev/gemini-api/docs/files
https://ai.google.dev/gemini-api/docs/generate-content/video-understanding
No video or credential is ever embedded in a public repository.
"""
import json,math,re,time,urllib.request,urllib.error,urllib.parse,socket,subprocess,tempfile,os,uuid
from pathlib import Path
from PySide6.QtCore import QThread,Signal
import imageio_ffmpeg
from core import APIError,api_message,request_json,validate,srt,wait_cancel
from storage import media_key,write_json_atomic
BASE='https://generativelanguage.googleapis.com'
MIMES={'.mp4':'video/mp4','.m4v':'video/mp4','.mpeg':'video/mpeg','.mpg':'video/mpeg','.mov':'video/quicktime','.avi':'video/avi','.flv':'video/x-flv','.webm':'video/webm','.wmv':'video/wmv','.3gp':'video/3gpp'}
MAX_UPLOAD=2_000_000_000
BLOCK=4*1024*1024
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):return None

def safe_url(url):
    p=urllib.parse.urlsplit(url)
    if p.scheme!='https' or p.hostname!='generativelanguage.googleapis.com' or p.port not in (None,443) or p.username or p.password:raise ValueError('Alamat upload Gemini tidak sah.')
    return url

def file_name(value):
    if not isinstance(value,str) or not re.fullmatch(r'files/[A-Za-z0-9_-]+',value):raise ValueError('Identitas file Gemini tidak sah.')
    return value

def api_exchange(url,key,method='GET',data=None,headers=None,timeout=60):
    safe_url(url)
    request=urllib.request.Request(url,data=data,headers={**(headers or {}),'x-goog-api-key':key},method=method)
    opener=urllib.request.build_opener(NoRedirect())
    try:
        with opener.open(request,timeout=timeout) as response:
            raw=response.read(8*1024*1024)
            return (json.loads(raw) if raw else {}),dict(response.headers)
    except urllib.error.HTTPError as exc:
        try:detail=json.loads(exc.read(32768)).get('error',{}).get('message','')
        except (ValueError,AttributeError):detail=''
        detail=str(detail).replace(key,'[KEY DISEMBUNYIKAN]') if key else str(detail)
        detail=re.sub(r'(?:AIza|AQ\.)[A-Za-z0-9_.-]+','[KEY DISEMBUNYIKAN]',detail)[:1000]
        raise APIError(api_message(exc.code,detail),exc.code) from None
    except (TimeoutError,socket.timeout):raise APIError('Upload/metadata Gemini timeout. Coba lagi; sumber dan hasil parsial dipertahankan.') from None
    except (urllib.error.URLError,ConnectionError):raise APIError('Koneksi Files API terputus. Periksa jaringan; sumber dan hasil parsial dipertahankan.') from None

def upload_video(path,key,cancelled,progress):
    path=Path(path);size=path.stat().st_size
    if not 0<size<=MAX_UPLOAD:raise ValueError('Attachment harus berukuran 1 byte sampai 2 GB. Aktifkan proxy video untuk memperkecil file besar.')
    mime=MIMES.get(path.suffix.lower())
    if not mime:raise ValueError('Format attachment tidak didukung Gemini; aktifkan proxy MP4.')
    if cancelled():raise InterruptedError('Dibatalkan')
    _,headers=api_exchange(BASE+'/upload/v1beta/files',key,'POST',json.dumps({'file':{'display_name':'Cyber80 video'}}).encode(),{
        'Content-Type':'application/json','X-Goog-Upload-Protocol':'resumable','X-Goog-Upload-Command':'start',
        'X-Goog-Upload-Header-Content-Length':str(size),'X-Goog-Upload-Header-Content-Type':mime})
    upload_url=next((v for k,v in headers.items() if k.lower()=='x-goog-upload-url'),None)
    if not upload_url:raise APIError('Gemini tidak mengembalikan sesi upload.')
    safe_url(upload_url);offset=0;result={}
    with path.open('rb') as source:
        while offset<size:
            if cancelled():raise InterruptedError('Dibatalkan')
            block=source.read(min(BLOCK,size-offset))
            if not block:raise ValueError('Attachment berubah atau terpotong saat upload.')
            last=offset+len(block)==size
            result,_=api_exchange(upload_url,key,'POST',block,{'Content-Type':'application/octet-stream','Content-Length':str(len(block)),
                'X-Goog-Upload-Offset':str(offset),'X-Goog-Upload-Command':'upload, finalize' if last else 'upload'})
            offset+=len(block);progress(f'Upload video: {offset/size*100:.1f}%')
    metadata=result.get('file',{})
    file_name(metadata.get('name'));safe_url(metadata.get('uri',''))
    return metadata

def active_file(metadata,key,cancelled,progress,max_wait=1800):
    deadline=time.monotonic()+max_wait
    while True:
        if cancelled():raise InterruptedError('Dibatalkan')
        state=metadata.get('state')
        if state=='ACTIVE':return metadata
        if state=='FAILED':raise APIError('Gemini gagal memproses attachment. Coba proxy MP4 atau mode potongan audio.')
        if state not in ('PROCESSING',None):raise APIError('Status file Gemini tidak dikenali.')
        if time.monotonic()>=deadline:raise APIError('Attachment belum siap setelah 30 menit. Proses dihentikan; coba lagi nanti.')
        progress('Gemini sedang menyiapkan attachment video …');wait_cancel(3,cancelled)
        metadata,_=api_exchange(BASE+'/v1beta/'+file_name(metadata['name']),key)

def attachment_payload(uri,mime,start,end,language,glossary):
    safe_url(uri)
    prompt=(f'Act as a professional audiovisual translator. Listen to the actual speech in this video interval [{start:.3f}, {end:.3f}] seconds. '
        f'Detect spoken language and translate to {language}. Return only a JSON array of cues with numeric start, end, source, target and language (ISO code). '
        f'Use ABSOLUTE seconds from the beginning of the ORIGINAL video, NOT relative to the selected interval. All cues must be within {start:.3f} and {end:.3f}. '
        'Do not summarize. Transcribe all audible dialogue faithfully, without inventing words from visual content or silence. '
        'Use correct spelling, punctuation, concise readable lines and natural professional translation. For Indonesian use standard Indonesian/EYD. '
        'Preserve names, numbers and meaning. Empty array for silence. Preferred spelling reference only: '+glossary[:6000])
    return {'contents':[{'parts':[{'fileData':{'fileUri':uri,'mimeType':mime},'videoMetadata':{'startOffset':f'{start:.3f}s','endOffset':f'{end:.3f}s'}},{'text':prompt}]}],
        'generationConfig':{'responseMimeType':'application/json'}}

def extract_attachment_cues(response,start,end):
    candidates=response.get('candidates') or []
    if not candidates or candidates[0].get('finishReason')!='STOP':raise APIError('Gemini belum menghasilkan subtitle lengkap; checkpoint dipertahankan. Coba bagian yang gagal lagi.')
    raw=''.join(p.get('text','') for p in candidates[0].get('content',{}).get('parts',[]) if not p.get('thought'))
    cues=validate(json.loads(raw),end)
    if any(c.start<start-.05 or c.end>end+.05 for c in cues):raise ValueError('Timestamp attachment di luar interval; hasil ditolak agar tidak salah sinkron.')
    return cues

def write_srt_atomic(path,cues):
    path=Path(path);temp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:temp.write_text(srt(cues),encoding='utf-8');os.replace(temp,path)
    finally:temp.unlink(missing_ok=True)

class BackgroundSubtitleJob(QThread):
    progress=Signal(str);completed=Signal(str,object);failed=Signal(str)
    def __init__(self,source,target,key,model,language='id',glossary='',proxy=False,audio_stream=0,persist=True):
        super().__init__();self.source=str(Path(source).resolve());self.target=str(Path(target).resolve());self.key=key;self.model=model;self.language=language;self.glossary=glossary;self.proxy=proxy;self.audio_stream=audio_stream;self.persist=persist;self.proc=None
    def cancel(self):
        self.requestInterruption()
        if self.proc:
            try:self.proc.kill()
            except OSError:pass
    def prepare_video(self,temp):
        source=Path(self.source)
        if not self.proxy:
            if self.audio_stream!=0:raise ValueError('Pilih proxy MP4 untuk memilih track audio selain yang pertama.')
            return source
        target=Path(temp)/'attachment.mp4';self.progress.emit('Menyiapkan proxy MP4 720p dengan track audio pilihan …')
        flags={'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {}
        with tempfile.TemporaryFile() as errors:
            self.proc=subprocess.Popen([imageio_ffmpeg.get_ffmpeg_exe(),'-v','error','-y','-i',str(source),'-map','0:v:0','-map',f'0:a:{self.audio_stream}',
                '-vf',"scale=w='min(1280,iw)':h='min(720,ih)':force_original_aspect_ratio=decrease:force_divisible_by=2",'-c:v','libx264','-preset','veryfast','-crf','30','-pix_fmt','yuv420p','-c:a','aac','-b:a','96k','-movflags','+faststart',str(target)],stdout=subprocess.DEVNULL,stderr=errors,**flags)
            while True:
                if self.isInterruptionRequested():self.proc.kill();self.proc.wait();raise InterruptedError('Dibatalkan')
                try:self.proc.wait(timeout=.2);break
                except subprocess.TimeoutExpired:pass
            if self.proc.returncode:raise ValueError('Proxy gagal dibuat. Periksa track audio, ruang disk, dan file sumber.')
        self.proc=None;return target
    def run(self):
        remote=None;cues=[];offset=0.;checkpoint=Path(self.target+'.progress.json');partial=Path(self.target+'.partial.srt')
        try:
            if not re.fullmatch(r'[A-Za-z0-9_.-]+',self.model):raise ValueError('Nama model tidak valid.')
            if Path(self.source)==Path(self.target):raise ValueError('Subtitle tidak boleh menimpa video sumber.')
            context=media_key(self.source,[self.model,self.language,self.glossary,self.proxy,self.audio_stream,'attachment-v1'])
            if self.persist and checkpoint.is_file():
                data=json.loads(checkpoint.read_text(encoding='utf-8'))
                if data.get('context')==context:cues=validate(data['cues'],1e12);offset=float(data['offset'])
            with tempfile.TemporaryDirectory(prefix='cyber80-attachment-') as temp:
                video=self.prepare_video(temp)
                reader=imageio_ffmpeg.read_frames(str(video))
                try:duration=float(next(reader).get('duration',0))
                finally:reader.close()
                if not math.isfinite(duration) or duration<=0:raise ValueError('Durasi video tidak dapat dibaca.')
                if not math.isfinite(offset) or offset<0 or offset>duration:raise ValueError('Checkpoint attachment tidak valid.')
                remote=upload_video(video,self.key,self.isInterruptionRequested,self.progress.emit)
                remote=active_file(remote,self.key,self.isInterruptionRequested,self.progress.emit)
                while offset<duration-.05:
                    if self.isInterruptionRequested():raise InterruptedError('Dibatalkan')
                    end=min(duration,offset+120)
                    self.progress.emit(f'Analisis suara / terjemahan: {offset/duration*100:.1f}% ({offset:.0f}–{end:.0f} detik)')
                    data=request_json(BASE+'/v1beta/models/'+self.model+':generateContent',self.key,
                        attachment_payload(remote['uri'],remote.get('mimeType',MIMES.get(video.suffix.lower(),'video/mp4')),offset,end,self.language,self.glossary),
                        self.isInterruptionRequested,self.progress.emit,180)
                    cues.extend(extract_attachment_cues(data,offset,end));offset=end
                    if self.persist:
                        write_srt_atomic(partial,cues);write_json_atomic(checkpoint,{'context':context,'offset':offset,'cues':[vars(c) for c in cues]})
                if self.isInterruptionRequested():raise InterruptedError('Dibatalkan')
                self.progress.emit('Menyimpan subtitle SRT …');write_srt_atomic(self.target,cues)
            if self.persist:checkpoint.unlink(missing_ok=True);partial.unlink(missing_ok=True)
            self.completed.emit(self.target,cues)
        except Exception as exc:
            # Never expose a signed upload URL, raw transport exception, or credential.
            message=str(exc).replace(self.key,'[KEY DISEMBUNYIKAN]') if self.key else str(exc)
            message=re.sub(r'https?://\S+','[alamat layanan]',message)
            self.failed.emit(message+'\nHasil parsial/checkpoint dipertahankan jika tersedia.')
        finally:
            self.proc=None
            if remote:
                try:api_exchange(BASE+'/v1beta/'+file_name(remote['name']),self.key,'DELETE',timeout=15)
                except Exception:self.progress.emit('Pembersihan attachment di Google belum terkonfirmasi; periksa Files API. File layanan mempunyai masa simpan terbatas.')
