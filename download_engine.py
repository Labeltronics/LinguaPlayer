"""Cancellable downloader, validated HTTP resume and offline unencrypted streams."""
import os,time,re,json,hashlib,shutil,threading,subprocess,tempfile,urllib.error,socket
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
from PySide6.QtCore import QThread,Signal
import imageio_ffmpeg
from web_transfer import open_http,read_document,scoped_headers,atomic_json,checked_url
from stream_manifests import hls_plan,dash_plan
class Stopped(Exception):pass
class RangeUnsupported(Exception):pass
class RateLimiter:
    def __init__(self):self.rate=0;self.next_time=0.;self.lock=threading.Lock()
    def wait(self,count,event):
        with self.lock:
            if self.rate<=0:self.next_time=0;return
            now=time.monotonic();delay=max(0,self.next_time-now);self.next_time=max(now,self.next_time)+count/self.rate
        if event.wait(delay):raise Stopped()
def content_range(value):
    match=re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)',value or '')
    if not match:raise RangeUnsupported('Server tidak memberi Content-Range yang sah.')
    a,b,total=map(int,match.groups())
    if not 0<=a<=b<total:raise RangeUnsupported('Rentang byte server tidak sah.')
    return a,b,total

def target_stamp(path):
    try:s=Path(path).stat();return [s.st_size,s.st_mtime_ns]
    except FileNotFoundError:return None

class DownloadJob(QThread):
    update=Signal(object);done=Signal(str,str)
    def __init__(self,record,url,headers=None,limiter=None):
        super().__init__();self.record=dict(record);self.url=checked_url(url);self.headers=dict(headers or {});self.limiter=limiter or RateLimiter();self.event=threading.Event();self.mode='Paused';self.proc=None;self.last_emit=0.;self.started=0.;self.initial=0;self.received=0
        self.target=Path(record['target']);self.part=self.target.with_name(self.target.name+'.'+record['id']+'.part');self.directory=self.target.with_name(self.target.name+'.'+record['id']+'.segments')
    def stop(self,cancel=False):
        self.mode='Cancelled' if cancel else 'Paused';self.event.set()
        if self.proc:
            try:self.proc.kill()
            except OSError:pass
    def check(self):
        if self.event.is_set():raise Stopped()
    def report(self,received,total=0,message='',force=False):
        if not force and time.monotonic()-self.last_emit<.15:return
        self.last_emit=time.monotonic();elapsed=max(.001,time.monotonic()-self.started);speed=max(0,received-self.initial)/elapsed
        self.update.emit({'received':received,'total':total,'speed':speed,'eta':(total-received)/speed if total and speed else None,'message':message,'validator':self.record.get('validator','')})
    def disk_check(self,remaining=0):
        if shutil.disk_usage(self.target.parent).free<max(1024*1024,remaining):raise OSError('Ruang disk tidak cukup untuk unduhan.')
    def copy_response(self,response,path,mode='wb',start=0,total=0):
        count=start
        with Path(path).open(mode) as output:
            while True:
                self.check();data=response.read(64*1024)
                if not data:break
                self.disk_check();output.write(data);count+=len(data);self.limiter.wait(len(data),self.event);self.report(count,total)
        return count
    def single_file(self):
        for attempt in range(3):
            self.check();offset=self.part.stat().st_size if self.part.exists() else 0
            validator=self.record.get('validator','')
            if offset and not validator:offset=0
            headers={**self.headers}
            if offset:headers.update(Range=f'bytes={offset}-',**{'If-Range':validator})
            try:
                try:response=open_http(self.url,headers)
                except urllib.error.HTTPError as exc:
                    if exc.code==416 and offset:
                        self.part.unlink(missing_ok=True);self.record['validator']='';continue
                    raise
                with response:
                    if response.headers.get('Content-Encoding','identity').lower() not in ('identity',''):raise ValueError('Encoding respons tidak sesuai unduhan byte.')
                    mime=response.headers.get('Content-Type','').lower()
                    if 'text/html' in mime and self.target.suffix.lower() in ('.mp4','.mp3','.m4a','.mkv','.webm','.wav','.flac','.avi'):raise ValueError('Server mengembalikan halaman HTML/login, bukan file media.')
                    current=response.headers.get('ETag') or response.headers.get('Last-Modified') or ''
                    if response.status==206:
                        a,b,total=content_range(response.headers.get('Content-Range'))
                        if a!=offset:raise RangeUnsupported('Offset resume server tidak cocok.')
                        if offset and current and current!=validator:
                            self.part.unlink(missing_ok=True);self.record['validator']='';continue
                    elif response.status==200:offset=0;size=response.headers.get('Content-Length','');total=int(size) if size.isdigit() else 0
                    else:raise ValueError('Status respons unduhan tidak didukung.')
                    self.record['validator']=current;self.initial=offset;self.disk_check(max(0,total-offset));self.report(offset,total,'Resume tervalidasi' if offset else 'Mengunduh',True)
                    count=self.copy_response(response,self.part,'ab' if offset else 'wb',offset,total)
                    if total and count!=total:raise ConnectionError('Unduhan terputus sebelum ukuran lengkap.')
                    return
            except (urllib.error.URLError,TimeoutError,socket.timeout,ConnectionError) as exc:
                if isinstance(exc,urllib.error.HTTPError) and exc.code not in (408,429,500,502,503,504):raise
                if attempt==2:raise
                if self.event.wait(attempt+1):raise Stopped()
    def parallel_file(self):
        # Parallel mode needs a strong validator and an independently confirmed byte range.
        with open_http(self.url,self.headers,'HEAD') as response:
            etag=response.headers.get('ETag','');size=response.headers.get('Content-Length','');total=int(size) if size.isdigit() else 0
        if not etag or etag.startswith('W/') or total<1024*1024:raise RangeUnsupported('Mode satu koneksi dipakai: ukuran/ETag kuat belum tersedia.')
        count=max(1,min(4,int(self.record.get('connections',1))));self.directory.mkdir(exist_ok=True)
        identity=hashlib.sha256((self.url+etag+str(total)+str(count)).encode()).hexdigest();meta=self.directory/'ranges.json'
        try:old=json.loads(meta.read_text())
        except (OSError,ValueError):old={}
        if old.get('identity')!=identity:
            for path in self.directory.glob('range*.bin'):path.unlink()
        atomic_json(meta,{'identity':identity});self.record['validator']=etag;self.disk_check(total-sum(p.stat().st_size for p in self.directory.glob('range*.bin')))
        ranges=[(i,i*total//count,(i+1)*total//count-1) for i in range(count)];progress={i:0 for i,_,_ in ranges};lock=threading.Lock()
        def segment(item):
            i,a,b=item;path=self.directory/f'range{i}.bin';have=path.stat().st_size if path.exists() else 0
            if have>b-a+1:path.unlink();have=0
            with lock:progress[i]=have
            if have==b-a+1:return
            with open_http(self.url,{**self.headers,'Range':f'bytes={a+have}-{b}','If-Range':etag}) as response:
                if response.status!=206:raise RangeUnsupported('Server mengabaikan Range; beralih ke satu koneksi.')
                if content_range(response.headers.get('Content-Range'))!=(a+have,b,total) or response.headers.get('ETag')!=etag:raise RangeUnsupported('Validator/rentang paralel tidak konsisten.')
                with path.open('ab') as output:
                    while True:
                        self.check();data=response.read(min(64*1024,b-a+1-have))
                        if not data:break
                        self.disk_check();output.write(data);have+=len(data);self.limiter.wait(len(data),self.event)
                        with lock:progress[i]=have;self.report(sum(progress.values()),total,'Koneksi paralel tervalidasi')
                if have!=b-a+1:raise ConnectionError('Segmen paralel terputus.')
        with ThreadPoolExecutor(max_workers=count) as executor:
            futures=[executor.submit(segment,item) for item in ranges]
            for future in as_completed(futures):future.result()
        with self.part.open('wb') as output:
            for i,_,_ in ranges:
                self.check()
                with (self.directory/f'range{i}.bin').open('rb') as source:shutil.copyfileobj(source,output,64*1024)
        self.report(total,total,'Menggabungkan koneksi',True)
    def resource(self,url,target):
        if target.exists():return
        temporary=target.with_suffix('.partial')
        try:
            with open_http(url,scoped_headers(self.url,url,self.headers)) as response:
                length=response.headers.get('Content-Length','');expected=int(length) if length.isdigit() else 0;count=0
                with temporary.open('wb') as output:
                    while True:
                        self.check();data=response.read(64*1024)
                        if not data:break
                        self.disk_check();output.write(data);count+=len(data);self.received+=len(data);self.limiter.wait(len(data),self.event);self.report(self.received,0,'Mengunduh segmen stream')
                if expected and count!=expected:raise ConnectionError('Segmen stream tidak lengkap.')
            os.replace(temporary,target)
        finally:temporary.unlink(missing_ok=True)
    def streams(self,kind):
        text,final=read_document(self.url,self.headers);self.directory.mkdir(exist_ok=True);inputs=[];plans=[]
        if kind=='hls':
            plan=hls_plan(text,final)
            if plan['variants']:
                variants=sorted(plan['variants'],key=lambda v:v['bandwidth']);choice=variants[min(int(self.record.get('quality',len(variants)-1)),len(variants)-1)]
                vtext,vurl=read_document(choice['url'],scoped_headers(self.url,choice['url'],self.headers));plan=hls_plan(vtext,vurl)
                if plan['variants']:raise ValueError('HLS master bertingkat belum didukung.')
                plans.append(('video',plan))
                if choice.get('audio_url'):
                    atext,aurl=read_document(choice['audio_url'],scoped_headers(self.url,choice['audio_url'],self.headers));plans.append(('audio',hls_plan(atext,aurl)))
            else:plans.append(('video',plan))
        else:
            representations=dash_plan(text,final);videos=sorted([v for v in representations if v['kind']=='video'],key=lambda v:v['bandwidth']);audios=sorted([v for v in representations if v['kind']=='audio'],key=lambda v:v['bandwidth'])
            if videos:plans.append(('video',videos[min(int(self.record.get('quality',len(videos)-1)),len(videos)-1)]))
            if audios:plans.append(('audio',audios[-1]))
        context=hashlib.sha256(json.dumps(plans,sort_keys=True).encode()).hexdigest();meta=self.directory/'stream.json'
        try:previous=json.loads(meta.read_text())
        except (OSError,ValueError):previous={}
        if previous.get('context')!=context:
            for path in self.directory.glob('stream*'):
                if path.is_file():path.unlink()
        atomic_json(meta,{'context':context});total_segments=sum(len(p['segments']) for _,p in plans);index=0
        for role,plan in plans:
            files=[]
            for i,url in enumerate(plan['segments']):
                self.check()
                from urllib.parse import urlsplit
                suffix=Path(urlsplit(url).path).suffix.lower()
                if kind=='hls':
                    suffix='.mp4' if f'#EXT-X-MAP:URI="seg{i:05}.bin"' in plan.get('local','') else '.m4s' if '#EXT-X-MAP:' in plan.get('local','') else suffix if suffix in ('.ts','.aac','.mp3','.ac3','.mp4','.m4s','.m4a') else '.ts'
                else:suffix='.bin'
                path=self.directory/f'stream_{role}_{i:05}{suffix}';self.resource(url,path);files.append(path);index+=1;self.report(self.received,0,f'Segmen {index}/{total_segments}',True)
            if not files:raise ValueError('Stream kosong.')
            if kind=='hls':
                local=plan['local']
                for i in reversed(range(len(files))):local=local.replace(f'seg{i:05}.bin',files[i].name)
                manifest=self.directory/f'{role}.m3u8';manifest.write_text(local,encoding='utf-8');inputs.append((role,manifest))
            else:
                combined=self.directory/f'{role}.mp4'
                with combined.open('wb') as output:
                    for path in files:
                        self.check()
                        with path.open('rb') as source:shutil.copyfileobj(source,output,64*1024)
                inputs.append((role,combined))
        result=self.directory/'result.mp4';command=[imageio_ffmpeg.get_ffmpeg_exe(),'-v','error','-y']
        for _,path in inputs:command+=['-protocol_whitelist','file','-allowed_extensions','ALL','-i',str(path.resolve())] if kind=='hls' else ['-i',str(path.resolve())]
        if len(inputs)==2:command+=['-map','0:v:0','-map','1:a:0']
        command+=['-c','copy','-movflags','+faststart',str(result.resolve())];self.report(self.received,0,'Menggabungkan audio/video dengan FFmpeg',True)
        flags={'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {}
        with tempfile.TemporaryFile() as errors:
            self.proc=subprocess.Popen(command,stdout=subprocess.DEVNULL,stderr=errors,**flags)
            while self.proc.poll() is None:
                if self.event.wait(.1):self.proc.kill();self.proc.wait();raise Stopped()
            if self.proc.returncode:
                errors.seek(0);self.ffmpeg_error=errors.read().decode(errors='replace')[-2000:]
                raise ValueError('FFmpeg tidak dapat menggabungkan stream/codec ini. Segmen dipertahankan untuk dicoba lagi.')
        self.proc=None;os.replace(result,self.part)
    def run(self):
        self.started=time.monotonic();status='Failed';message=''
        try:
            self.target.parent.mkdir(parents=True,exist_ok=True);self.check();self.disk_check()
            kind=self.record.get('kind','file')
            if kind in ('hls','dash'):self.streams(kind)
            elif int(self.record.get('connections',1))>1 and not self.part.exists():
                try:self.parallel_file()
                except (RangeUnsupported,urllib.error.HTTPError):
                    self.report(0,0,'Server tidak mendukung paralel; memakai satu koneksi',True);shutil.rmtree(self.directory,ignore_errors=True);self.single_file()
            else:self.single_file()
            self.check()
            expected=self.record.get('sha256','').strip().lower()
            if expected:
                if not re.fullmatch('[0-9a-f]{64}',expected):raise ValueError('Checksum SHA256 tidak sah.')
                digest=hashlib.sha256()
                with self.part.open('rb') as source:
                    while True:
                        self.check();data=source.read(1024*1024)
                        if not data:break
                        digest.update(data)
                if digest.hexdigest()!=expected:raise ValueError('Checksum SHA256 tidak cocok; hasil final tidak diganti.')
            if target_stamp(self.target)!=self.record.get('target_stamp'):raise ValueError('File tujuan berubah sejak unduhan dibuat. Pilih nama tujuan lain.')
            os.replace(self.part,self.target);shutil.rmtree(self.directory,ignore_errors=True);status='Completed';message='Unduhan selesai'
        except Stopped:
            status=self.mode;message='Dijeda; hasil parsial dipertahankan' if status=='Paused' else 'Dibatalkan'
            if status=='Cancelled':self.part.unlink(missing_ok=True);shutil.rmtree(self.directory,ignore_errors=True)
        except urllib.error.HTTPError as exc:message=f'HTTP {exc.code}. Akses ditolak, tautan kedaluwarsa, atau server bermasalah. Perbarui URL/sesi lalu coba lagi.'
        except (urllib.error.URLError,TimeoutError,socket.timeout,ConnectionError):message='Koneksi terputus/timeout. Hasil parsial dipertahankan; tekan Lanjutkan.'
        except OSError:message='Gagal membaca/menulis file. Periksa ruang disk, izin folder, dan apakah file sedang dikunci.'
        except Exception as exc:message=str(exc) if isinstance(exc,(ValueError,RangeUnsupported)) else 'Unduhan gagal; hasil parsial dipertahankan.'
        finally:self.proc=None;self.done.emit(status,message)
