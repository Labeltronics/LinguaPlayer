import os,tempfile,threading,hashlib,time,unittest,json,subprocess
from pathlib import Path
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from unittest.mock import patch
from download_engine import DownloadJob,target_stamp
from web_transfer import checked_url,inspect_media,safe_filename
from stream_manifests import hls_plan,dash_plan
import imageio_ffmpeg
DATA=bytes(range(256))*8192
class Server:
    def __init__(self,folder=None):
        self.folder=Path(folder) if folder else None;self.requests=[];self.redirect=None;outer=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_HEAD(self):self.serve(False)
            def do_GET(self):self.serve(True)
            def serve(self,body):
                from urllib.parse import urlsplit
                path=urlsplit(self.path).path;outer.requests.append((self.command,path,dict(self.headers)))
                if path=='/deny':self.send_error(403);return
                if path=='/redirect':self.send_response(302);self.send_header('Location',outer.redirect);self.end_headers();return
                if path=='/nohead' and self.command=='HEAD':self.send_error(405);return
                data=DATA;mime='video/mp4'
                if outer.folder and (outer.folder/path.lstrip('/')).is_file():
                    data=(outer.folder/path.lstrip('/')).read_bytes();mime='application/vnd.apple.mpegurl' if path.endswith('.m3u8') else 'application/dash+xml' if path.endswith('.mpd') else 'text/html' if path.endswith('.html') else 'video/webm' if path.endswith('.webm') else 'audio/wav' if path.endswith('.wav') else 'application/octet-stream'
                elif outer.folder:
                    self.send_error(404);return
                etag='"new"' if path=='/changed' else '"fixture"';a=0;b=len(data)-1;status=200
                if self.headers.get('Range') and path!='/norange':
                    import re
                    match=re.fullmatch(r'bytes=(\d+)-(\d*)',self.headers['Range'])
                    if match:
                        a=int(match[1]);b=min(b,int(match[2]) if match[2] else b);status=206
                        if a>len(data)-1:self.send_response(416);self.send_header('Content-Range',f'bytes */{len(data)}');self.end_headers();return
                self.send_response(status);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(b-a+1));self.send_header('ETag',etag);self.send_header('Accept-Ranges','bytes')
                if status==206:self.send_header('Content-Range',f'bytes {a}-{b}/{len(data)}')
                self.end_headers()
                if body:
                    try:self.wfile.write(data[a:b+1])
                    except (BrokenPipeError,ConnectionResetError):pass
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler);self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start();self.base=f'http://127.0.0.1:{self.server.server_port}'
    def close(self):self.server.shutdown();self.server.server_close();self.thread.join()
def record(target,**extra):return {'id':'test','target':str(target),'kind':'file','connections':1,'target_stamp':target_stamp(target),**extra}
def run(job):
    results=[];updates=[];job.done.connect(lambda a,b:results.append((a,b)));job.update.connect(updates.append);job.run();return results[-1],updates
class TransferTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.http=Server()
    @classmethod
    def tearDownClass(cls):cls.http.close()
    def test_direct_and_resume_validate_bytes(self):
        with tempfile.TemporaryDirectory() as d:
            target=Path(d)/'movie.mp4';job=DownloadJob(record(target,validator='"fixture"'),self.http.base+'/file');job.part.write_bytes(DATA[:1000]);result,_=run(job)
            self.assertEqual(result[0],'Completed');self.assertEqual(target.read_bytes(),DATA)
            self.assertTrue(any(h.get('Range')=='bytes=1000-' for _,p,h in self.http.requests if p=='/file'))
    def test_server_ignoring_range_restarts_without_duplicate_bytes(self):
        with tempfile.TemporaryDirectory() as d:
            target=Path(d)/'movie.mp4';job=DownloadJob(record(target,validator='"fixture"'),self.http.base+'/norange');job.part.write_bytes(DATA[:123]);result,_=run(job);self.assertEqual(result[0],'Completed');self.assertEqual(target.read_bytes(),DATA)
    def test_changed_validator_restarts(self):
        with tempfile.TemporaryDirectory() as d:
            target=Path(d)/'movie.mp4';job=DownloadJob(record(target,validator='"old"'),self.http.base+'/changed');job.part.write_bytes(b'wrong');result,_=run(job);self.assertEqual(result[0],'Completed');self.assertEqual(target.read_bytes(),DATA)
    def test_parallel_and_range_fallback(self):
        for route in ('/file','/norange','/nohead'):
            with self.subTest(route=route),tempfile.TemporaryDirectory() as d:
                target=Path(d)/'movie.mp4';job=DownloadJob(record(target,connections=4),self.http.base+route);result,_=run(job);self.assertEqual(result[0],'Completed',result);self.assertEqual(hashlib.sha256(target.read_bytes()).digest(),hashlib.sha256(DATA).digest())
    def test_http403_has_no_retry_and_no_secret_in_error(self):
        before=len(self.http.requests)
        with tempfile.TemporaryDirectory() as d:
            result,_=run(DownloadJob(record(Path(d)/'movie.mp4'),self.http.base+'/deny?token=never-log'))
            self.assertEqual(result[0],'Failed');self.assertNotIn('never-log',result[1]);self.assertEqual(len(self.http.requests)-before,1)
    def test_redirect_drops_credentials_to_different_origin(self):
        second=Server();self.http.redirect=second.base+'/file'
        try:
            with tempfile.TemporaryDirectory() as d:
                result,_=run(DownloadJob(record(Path(d)/'movie.mp4'),self.http.base+'/redirect',{'Cookie':'secret=1','Authorization':'Bearer private'}));self.assertEqual(result[0],'Completed');headers=second.requests[0][2];self.assertNotIn('Cookie',headers);self.assertNotIn('Authorization',headers)
        finally:second.close()
    def test_disk_full_checksum_and_changed_target_never_commit(self):
        with tempfile.TemporaryDirectory() as d:
            target=Path(d)/'movie.mp4';target.write_bytes(b'original');r=record(target);target.write_bytes(b'changed')
            result,_=run(DownloadJob(r,self.http.base+'/file'));self.assertEqual(result[0],'Failed');self.assertEqual(target.read_bytes(),b'changed')
            result,_=run(DownloadJob(record(target,sha256='0'*64),self.http.base+'/file'));self.assertEqual(result[0],'Failed');self.assertEqual(target.read_bytes(),b'changed')
            with patch('download_engine.shutil.disk_usage',return_value=type('Disk',(),{'free':0})()):result,_=run(DownloadJob(record(target),self.http.base+'/file'));self.assertEqual(result[0],'Failed')
    def test_pause_before_network_and_cancel_remove_partial(self):
        with tempfile.TemporaryDirectory() as d:
            target=Path(d)/'movie.mp4';job=DownloadJob(record(target),self.http.base+'/file');job.part.write_bytes(b'partial');job.stop();result,_=run(job);self.assertEqual(result[0],'Paused');self.assertTrue(job.part.exists())
            job=DownloadJob(record(target),self.http.base+'/file');job.stop(True);result,_=run(job);self.assertEqual(result[0],'Cancelled');self.assertFalse(job.part.exists())
    def test_probe_and_filename_security(self):
        info=inspect_media(self.http.base+'/nohead');self.assertEqual(info['size'],len(DATA));self.assertTrue(info['media'])
        for value in ('file:///etc/passwd','javascript:alert(1)','https://user:pass@example.com/x'):
            with self.assertRaises(ValueError):checked_url(value)
        self.assertNotIn('/',safe_filename('../../CON.mp4'));self.assertTrue(safe_filename('CON.mp4').startswith('_'))
class ManifestTests(unittest.TestCase):
    def test_hls_master_audio_and_reject_encryption_live(self):
        master='#EXTM3U\n#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="audio",URI="a.m3u8"\n#EXT-X-STREAM-INF:BANDWIDTH=1000,RESOLUTION=640x360,AUDIO="audio"\nv.m3u8\n'
        plan=hls_plan(master,'https://example.com/master.m3u8');self.assertEqual(plan['variants'][0]['audio_url'],'https://example.com/a.m3u8')
        for text in ('#EXTM3U\n#EXT-X-KEY:METHOD=AES-128,URI="key"\n#EXT-X-ENDLIST','#EXTM3U\n#EXTINF:1,\na.ts'):
            with self.assertRaises(ValueError):hls_plan(text,'https://example.com/a.m3u8')
    def test_dash_drm_and_dynamic_rejected(self):
        for text in ('<MPD type="dynamic"><Period/></MPD>','<MPD><Period><ContentProtection/></Period></MPD>'):
            with self.assertRaises(ValueError):dash_plan(text,'https://example.com/a.mpd')
    def test_real_hls_dash_download_and_remux(self):
        ff=imageio_ffmpeg.get_ffmpeg_exe();flags={'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {}
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'source.mp4'
            subprocess.run([ff,'-v','error','-y','-f','lavfi','-i','testsrc2=size=160x120:rate=10:duration=2','-f','lavfi','-i','sine=frequency=440:duration=2','-c:v','libx264','-g','10','-c:a','aac','-shortest',str(source)],check=True,**flags)
            subprocess.run([ff,'-v','error','-y','-i',str(source),'-c','copy','-hls_time','1','-hls_playlist_type','vod','-hls_segment_filename',str(root/'hls%02d.ts'),str(root/'test.m3u8')],check=True,**flags)
            subprocess.run([ff,'-v','error','-y','-i',str(source),'-c','copy','-f','dash','-seg_duration','1',str(root/'test.mpd')],check=True,**flags)
            server=Server(root)
            try:
                for kind,manifest in [('hls','test.m3u8'),('dash','test.mpd')]:
                    with self.subTest(kind=kind):
                        target=root/(kind+'_out.mp4');job=DownloadJob(record(target,kind=kind),server.base+'/'+manifest);result,_=run(job);self.assertEqual(result[0],'Completed',(result,getattr(job,'ffmpeg_error',''),(root/manifest).read_text(),[(p.name,p.stat().st_size) for p in root.iterdir() if p.is_file()],[p for _,p,_ in server.requests]))
                        reader=imageio_ffmpeg.read_frames(str(target));meta=next(reader);reader.close();self.assertEqual(meta['size'],(160,120));self.assertTrue(meta.get('audio_codec'))
            finally:server.close()
