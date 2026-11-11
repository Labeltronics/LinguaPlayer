"""User-selected proxy and Google search preferences; no TLS/sandbox disabling."""
import json,threading,urllib.parse,urllib.request
from credentials import save_key,load_key
_lock=threading.Lock();_config={'mode':'system','host':'','port':8080,'username':'','password':''};_loaded=False

def google_search_url(text,safe_off=True):
    return 'https://www.google.com/search?'+urllib.parse.urlencode({'q':text,**({'safe':'off'} if safe_off else {})})
def google_safe_url(url,off=True):
    p=urllib.parse.urlsplit(url);host=(p.hostname or '').lower().removeprefix('www.')
    domains={'google.com','google.co.id','google.co.uk','google.com.au','google.co.jp','google.de','google.fr','google.ca','encrypted.google.com'}
    if not off or host not in domains or p.path!='/search':return url
    pairs=[(k,v) for k,v in urllib.parse.parse_qsl(p.query,keep_blank_values=True) if k.lower()!='safe'];pairs.append(('safe','off'))
    return urllib.parse.urlunsplit((p.scheme,p.netloc,p.path,urllib.parse.urlencode(pairs),p.fragment))
def configure(mode,host='',port=8080,username='',password=''):
    if mode not in ('system','direct','http'):raise ValueError('Mode proxy tidak dikenal.')
    host=host.strip()
    if mode=='http' and (not host or any(c in host for c in '/@?# \r\n\x00') or not 1<=int(port)<=65535):raise ValueError('Host/port proxy tidak sah. Masukkan host atau IP, tanpa skema URL.')
    value={'mode':mode,'host':host,'port':int(port),'username':username,'password':password}
    with _lock:_config.update(value)
    return value
def current():
    with _lock:return dict(_config)
def urllib_proxy_handler():
    value=current()
    if value['mode']=='system':return urllib.request.ProxyHandler()
    if value['mode']=='direct':return urllib.request.ProxyHandler({})
    host=value['host'];host='['+host+']' if ':' in host and not host.startswith('[') else host
    auth=(urllib.parse.quote(value['username'],safe='')+':'+urllib.parse.quote(value['password'],safe='')+'@') if value['username'] else ''
    uri=f'http://{auth}{host}:{value["port"]}';return urllib.request.ProxyHandler({'http':uri,'https':uri})
def apply_qt():
    from PySide6.QtNetwork import QNetworkProxy,QNetworkProxyFactory
    value=current()
    if value['mode']=='system':QNetworkProxyFactory.setUseSystemConfiguration(True);return
    QNetworkProxyFactory.setUseSystemConfiguration(False)
    proxy=QNetworkProxy(QNetworkProxy.ProxyType.NoProxy) if value['mode']=='direct' else QNetworkProxy(QNetworkProxy.ProxyType.HttpProxy,value['host'],value['port'],value['username'],value['password'])
    QNetworkProxy.setApplicationProxy(proxy)
def initialize(persist=False):
    global _loaded
    if _loaded:return
    _loaded=True
    if persist:
        try:
            raw=load_key('BrowserProxy')
            if raw:configure(**json.loads(raw))
        except Exception:pass
    apply_qt()
def save_private_configuration():save_key('BrowserProxy',json.dumps(current()))


def proxy_credentials(host):
    value=current()
    if value['mode']=='http' and str(host).strip('[]').lower()==value['host'].strip('[]').lower():return value['username'],value['password']
    return None
