"""HTTP transport and media inspection. Never log URLs, cookies or auth headers."""
import re,urllib.request,urllib.error,urllib.parse,json,os,hashlib
from pathlib import Path
MEDIA_EXT={'.mp4','.m4v','.mkv','.webm','.mov','.avi','.flv','.ts','.mp3','.m4a','.aac','.wav','.flac','.ogg','.opus','.m3u8','.mpd','.mpeg','.3gp','.ogv','.mpg','.wmv','.wma','.aiff','.aif','.ac3','.eac3','.m2ts','.mts','.vob','.mka','.m2v','.m4b','.asf','.amr','.ape','.alac'}
SENSITIVE={'cookie','authorization','proxy-authorization','referer','origin'}
def checked_url(url):
    p=urllib.parse.urlsplit(str(url))
    if p.scheme not in ('http','https') or not p.hostname or p.username or p.password or any(c in str(url) for c in '\r\n\x00'):raise ValueError('Gunakan URL HTTP/HTTPS tanpa kredensial di alamat.')
    _=p.port
    return urllib.parse.urlunsplit((p.scheme,p.netloc,p.path or '/',p.query,''))
def origin(url):
    p=urllib.parse.urlsplit(checked_url(url));return (p.scheme.lower(),p.hostname.lower(),p.port or (443 if p.scheme=='https' else 80))
def safe_headers(headers):
    allowed={'cookie','authorization','referer','origin','user-agent','accept','range','if-range','accept-encoding'}
    return {str(k):str(v) for k,v in (headers or {}).items() if str(k).lower() in allowed and not any(c in str(v) for c in '\r\n\x00')}
class GuardedRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        newurl=checked_url(newurl)
        if origin(req.full_url)[0]=='https' and origin(newurl)[0]=='http':raise ValueError('Redirect HTTPS ke HTTP ditolak.')
        result=super().redirect_request(req,fp,code,msg,headers,newurl)
        if result is not None and origin(req.full_url)!=origin(newurl):
            for field in list(result.headers):
                if field.lower() in SENSITIVE:result.remove_header(field)
        return result

def open_http(url,headers=None,method='GET',timeout=20):
    req=urllib.request.Request(checked_url(url),headers={**safe_headers(headers),'Accept-Encoding':'identity'},method=method)
    from network_preferences import urllib_proxy_handler
    return urllib.request.build_opener(urllib_proxy_handler(),GuardedRedirect()).open(req,timeout=timeout)
def scoped_headers(source,url,headers):return safe_headers(headers) if origin(source)==origin(url) else {k:v for k,v in safe_headers(headers).items() if k.lower() not in SENSITIVE}
def read_document(url,headers=None,limit=2*1024*1024):
    with open_http(url,headers) as response:
        data=response.read(limit+1)
        if len(data)>limit:raise ValueError('Manifest terlalu besar.')
        return data.decode('utf-8-sig'),response.geturl()
def safe_filename(value,default='media.bin'):
    value=urllib.parse.unquote(str(value));value=re.sub(r'[<>:"/\\|?*\x00-\x1f]','_',value).strip(' .')[:160]
    if not value:value=default
    if value.split('.')[0].upper() in {'CON','PRN','AUX','NUL',*(f'COM{i}' for i in range(1,10)),*(f'LPT{i}' for i in range(1,10))}:value='_'+value
    return value

def inspect_media(url,headers=None,allow_file=False):
    url=checked_url(url)
    try:response=open_http(url,headers,'HEAD')
    except urllib.error.HTTPError as exc:
        if exc.code not in (405,501):raise
        response=open_http(url,{**(headers or {}),'Range':'bytes=0-0'})
    with response:
        mime=response.headers.get('Content-Type','').split(';')[0].strip().lower();size=response.headers.get('Content-Length');cd=response.headers.get('Content-Disposition','');final=response.geturl()
        cr=response.headers.get('Content-Range','')
        if '/' in cr:size=cr.rsplit('/',1)[-1]
        filename=Path(urllib.parse.urlsplit(final).path).name
        match=re.search(r"filename\*=UTF-8''([^;]+)|filename=\"?([^;\"]+)",cd,re.I)
        if match:filename=next(v for v in match.groups() if v)
        suffix=Path(urllib.parse.urlsplit(final).path).suffix.lower()
        kind='hls' if 'mpegurl' in mime or suffix=='.m3u8' else 'dash' if 'dash+xml' in mime or suffix=='.mpd' else 'file'
        return {'url':url,'name':safe_filename(filename),'mime':mime,'size':int(size) if size and size.isdigit() else None,'kind':kind,'media':mime.startswith(('video/','audio/')) or kind!='file' or suffix in MEDIA_EXT or bool(allow_file) or cd.lower().startswith('attachment')}

def atomic_json(path,value):
    import uuid
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);temp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:temp.write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8');os.replace(temp,path)
    finally:temp.unlink(missing_ok=True)

def decode_scan_rows(value):
    """Qt JS transport supports JSON text reliably across PySide versions."""
    if isinstance(value,str):
        if len(value)>128*1024:return []
        try:value=json.loads(value)
        except (ValueError,TypeError):return []
    if not isinstance(value,list):return []
    return [r for r in value[:100] if isinstance(r,dict) and isinstance(r.get('url'),str) and len(r['url'])<=16384]
