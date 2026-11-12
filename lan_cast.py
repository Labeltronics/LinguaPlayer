"""Explicit one-media LAN sharing; token protected, byte ranges, no directory serving."""
import hashlib,hmac,html,ipaddress,json,mimetypes,re,secrets,threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit,parse_qs,quote

def byte_range(value,size):
    if not value:return 0,size-1,False
    m=re.fullmatch(r'bytes=(\d*)-(\d*)',value.strip())
    if not m or not any(m.groups()):raise ValueError('Invalid range')
    if not m[1]:start=max(0,size-int(m[2]));end=size-1
    else:start=int(m[1]);end=min(size-1,int(m[2])) if m[2] else size-1
    if start<0 or start>=size or end<start:raise ValueError('Unsatisfiable range')
    return start,end,True

def vtt(cues):
    from core import stamp
    return 'WEBVTT\n\n'+'\n\n'.join(stamp(c.start).replace(',','.')+' --> '+stamp(c.end).replace(',','.')+'\n'+html.escape(c.target or c.source) for c in cues)+'\n'

def lan_peer(host):
    try:
        ip=ipaddress.ip_address(host);return ip.is_private or ip.is_loopback or ip.is_link_local
    except ValueError:return False

class ShareSession:
    def __init__(self,source,host='0.0.0.0',cues=()):
        self.source=str(source);self.path=None if self.source.startswith(('http://','https://')) else Path(source).resolve();self.token=secrets.token_urlsafe(24);self.closed=threading.Event();self.subtitle=vtt(cues).encode('utf-8') if cues else b''
        if self.path and (not self.path.is_file() or self.path.stat().st_size==0):raise ValueError('Pilih file media yang dapat dibaca.')
        if not self.path:
            from web_transfer import checked_url
            self.source=checked_url(self.source)
        self.mime={'.ts':'video/mp2t','.m3u8':'application/vnd.apple.mpegurl','.mkv':'video/x-matroska','.flv':'video/x-flv'}.get(Path(self.source.split('?')[0]).suffix.lower()) or mimetypes.guess_type(self.source)[0] or ('application/vnd.apple.mpegurl' if '.m3u8' in self.source else 'video/mp4')
        session=self
        class Handler(BaseHTTPRequestHandler):
            protocol_version='HTTP/1.1'
            def log_message(self,*args):pass
            def do_HEAD(self):self.serve(False)
            def do_GET(self):self.serve(True)
            def respond(self,status,data=b'',mime='text/plain; charset=utf-8'):
                self.send_response(status);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store');self.send_header('Access-Control-Allow-Origin','*');self.end_headers()
                if self.command!='HEAD' and data:self.wfile.write(data)
            def serve(self,body):
                try:
                    p=urlsplit(self.path);token=parse_qs(p.query).get('key',[''])[0]
                    if session.closed.is_set() or not lan_peer(self.client_address[0]) or not hmac.compare_digest(token,session.token):self.respond(403);return
                    if p.path=='/receiver':
                        media=('/media?key='+quote(session.token)) if session.path else session.source
                        track=('<track kind="subtitles" label="Subtitle" srclang="id" default src="/subtitle.vtt?key='+quote(session.token)+'">') if session.subtitle else ''
                        content='<!doctype html><meta name="viewport" content="width=device-width"><title>Cyber80 Cast</title><body style="margin:0;background:#111;color:white;font:18px sans-serif"><h3>Cyber80 Players • LAN Cast</h3><video style="width:100%;max-height:85vh" controls playsinline src="'+html.escape(media,quote=True)+'">'+track+'</video><p>Tekan Play. Format harus didukung browser/perangkat. Jaringan lokal saja.</p>'
                        self.respond(200,content.encode(),'text/html; charset=utf-8');return
                    if p.path=='/subtitle.vtt':self.respond(200,session.subtitle,'text/vtt; charset=utf-8');return
                    if p.path!='/media' or not session.path:self.respond(404);return
                    size=session.path.stat().st_size
                    try:start,end,partial=byte_range(self.headers.get('Range'),size)
                    except ValueError:
                        self.send_response(416);self.send_header('Content-Range',f'bytes */{size}');self.send_header('Content-Length','0');self.end_headers();return
                    self.send_response(206 if partial else 200);self.send_header('Content-Type',session.mime);self.send_header('Accept-Ranges','bytes');self.send_header('Content-Length',str(end-start+1));self.send_header('Cache-Control','no-store');self.send_header('Access-Control-Allow-Origin','*')
                    if partial:self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
                    self.end_headers()
                    if body:
                        with session.path.open('rb') as src:
                            src.seek(start);remaining=end-start+1
                            while remaining and not session.closed.is_set():
                                data=src.read(min(256*1024,remaining))
                                if not data:break
                                self.wfile.write(data);remaining-=len(data)
                except (BrokenPipeError,ConnectionResetError,OSError):pass
        self.server=ThreadingHTTPServer((host,0),Handler);self.server.daemon_threads=True;self.thread=threading.Thread(target=self.server.serve_forever,kwargs={'poll_interval':.1},daemon=True);self.thread.start()
    def url(self,ip,route='receiver'):return f'http://{ip}:{self.server.server_port}/{route}?key={self.token}'
    def media_url(self,ip):return self.url(ip,'media') if self.path else self.source
    def close(self):
        if self.closed.is_set():return
        self.closed.set();self.server.shutdown();self.server.server_close();self.thread.join(timeout=2)
