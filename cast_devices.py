"""Google Cast + UPnP AVTransport adapter. Discovery occurs only on user action."""
import html,ipaddress,socket,time,urllib.request,urllib.parse,xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from PySide6.QtCore import QThread,Signal

def local_url(url):
    p=urllib.parse.urlsplit(url)
    if p.scheme not in ('http','https') or not p.hostname or p.username or p.password:raise ValueError('Alamat perangkat tidak valid.')
    if not all(ipaddress.ip_address(a[4][0]).is_private for a in socket.getaddrinfo(p.hostname,p.port or 80,type=socket.SOCK_STREAM)):raise ValueError('Perangkat harus berada pada jaringan lokal.')
    return url
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args):return None
def local_request(url,data=None,headers=None):
    req=urllib.request.Request(local_url(url),data=data,headers=headers or {})
    with urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect()).open(req,timeout=4) as r:
        data=r.read(256*1024+1)
    if len(data)>256*1024 or b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():raise ValueError('Respons perangkat tidak valid.')
    return data

def renderer(location):
    try:
        root=ET.fromstring(local_request(location))
        for node in root.iter():node.tag=node.tag.rsplit('}',1)[-1]
        for service in root.findall('.//service'):
            kind=service.findtext('serviceType') or ''
            if ':service:AVTransport:' in kind:
                control=local_url(urllib.parse.urljoin(location,service.findtext('controlURL') or ''))
                return {'kind':'dlna','name':root.findtext('.//friendlyName') or urllib.parse.urlsplit(location).hostname,'control':control,'service':kind}
    except Exception:return None

def discover_dlna():
    locations=set();request=b'M-SEARCH * HTTP/1.1\r\nHOST:239.255.255.250:1900\r\nMAN:"ssdp:discover"\r\nMX:2\r\nST:urn:schemas-upnp-org:device:MediaRenderer:1\r\n\r\n'
    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM,socket.IPPROTO_UDP) as sock:
        sock.settimeout(.3);sock.setsockopt(socket.IPPROTO_IP,socket.IP_MULTICAST_TTL,2);sock.sendto(request,('239.255.255.250',1900));deadline=time.monotonic()+3
        while time.monotonic()<deadline and len(locations)<16:
            try:data,_=sock.recvfrom(8192)
            except socket.timeout:continue
            for line in data.decode('latin1').splitlines():
                if line.lower().startswith('location:'):locations.add(line.split(':',1)[1].strip())
    with ThreadPoolExecutor(max_workers=8) as pool:return [r for r in pool.map(renderer,locations) if r]

def soap(device,action,values):
    service=device['service'];args=''.join('<'+k+'>'+html.escape(str(v))+'</'+k+'>' for k,v in values.items());body=('<?xml version="1.0"?><s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body><u:'+action+' xmlns:u="'+html.escape(service,quote=True)+'">'+args+'</u:'+action+'></s:Body></s:Envelope>').encode()
    response=local_request(device['control'],body,{'Content-Type':'text/xml; charset="utf-8"','SOAPAction':'"'+service+'#'+action+'"'})
    if response:
        tree=ET.fromstring(response)
        if any(n.tag.rsplit('}',1)[-1]=='Fault' for n in tree.iter()):raise ValueError('Perangkat menolak perintah SOAP.')
    return response

class DiscoverCast(QThread):
    found=Signal(object,object);failed=Signal(str)
    def run(self):
        browser=None;casts=[]
        try:
            import pychromecast
            casts,browser=pychromecast.get_chromecasts(tries=1,timeout=3,retry_wait=1)
            rows=[{'kind':'chromecast','name':c.name or 'Google Cast','cast':c} for c in casts]
            try:rows+=discover_dlna()
            except OSError:pass
            self.found.emit(rows,browser)
        except Exception:
            if browser:
                try:browser.stop_discovery()
                except Exception:pass
            self.failed.emit('Pencarian perangkat gagal. Periksa Wi-Fi/firewall; tautan HP tetap dapat dipakai.')

class CastAction(QThread):
    completed=Signal(str);failed=Signal(str)
    def __init__(self,device,action,url='',mime='video/mp4',title='Cyber80 Players',position=0.,subtitle='',live=False):super().__init__();self.device=device;self.action=action;self.url=url;self.mime=mime;self.title=title;self.position=position;self.subtitle=subtitle;self.live=live
    def run(self):
        try:
            d=self.device
            if d['kind']=='chromecast':
                cast=d['cast'];cast.wait(timeout=10);mc=cast.media_controller
                if self.isInterruptionRequested():return
                if self.action=='load':mc.play_media(self.url,self.mime,title=self.title,current_time=self.position if not self.live else None,stream_type='LIVE' if self.live else 'BUFFERED',subtitles=self.subtitle or None,subtitles_lang='id')
                elif self.action=='play':mc.play()
                elif self.action=='pause':mc.pause()
                elif self.action=='stop':mc.stop()
            else:
                if self.isInterruptionRequested():return
                if self.action=='load':
                    metadata='<DIDL-Lite xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/"><item id="0" parentID="-1" restricted="1"><dc:title>'+html.escape(self.title)+'</dc:title><upnp:class>object.item.videoItem</upnp:class><res protocolInfo="http-get:*:'+html.escape(self.mime,quote=True)+':*">'+html.escape(self.url)+'</res></item></DIDL-Lite>'
                    soap(d,'SetAVTransportURI',{'InstanceID':0,'CurrentURI':self.url,'CurrentURIMetaData':metadata});soap(d,'Play',{'InstanceID':0,'Speed':1})
                else:soap(d,{'play':'Play','pause':'Pause','stop':'Stop'}[self.action],{'InstanceID':0,**({'Speed':1} if self.action=='play' else {})})
            self.completed.emit('Perintah dikirim ke perangkat. Periksa layar penerima.')
        except Exception:self.failed.emit('Perangkat menolak/tidak merespons. Periksa dukungan codec, jaringan dan izin penerima.')
