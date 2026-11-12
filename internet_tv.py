"""Public free-to-air catalog, bounded M3U/XMLTV import, no premium unlocking."""
import datetime,gzip,hashlib,json,re,xml.etree.ElementTree as ET
from urllib.parse import urljoin
from web_transfer import checked_url,read_document
API='https://iptv-org.github.io/api/'
MAX_ROWS=100000

def adult(row):return bool(row.get('adult'))
def parse_m3u(text,base=''):
    if len(text.encode('utf-8'))>32*1024*1024:raise ValueError('Playlist terlalu besar.')
    if '#EXT-X-' in text:raise ValueError('Ini manifest HLS satu saluran, bukan daftar saluran M3U.')
    rows=[];meta=None
    for line in text.lstrip('\ufeff').splitlines():
        line=line.strip()
        if line.startswith('#EXTINF:'):
            # Commas may occur inside quoted attributes.
            match=re.match(r'#EXTINF:(?:[^"\n]|"[^"\n]*")*?,',line)
            if not match:meta=None;continue
            attrs=dict(re.findall(r'([\w-]+)="([^"\n]*)"',line[:match.end()-1]));name=line[match.end():].strip()[:300]
            group=attrs.get('group-title','Impor')[:150];meta={'id':attrs.get('tvg-id','')[:200],'name':name or 'Saluran','country':attrs.get('tvg-country','').upper()[:8],'category':group,'adult':bool(re.search(r'(?i)(?:\b18\+|adult|xxx|porn|dewasa)',group))}
        elif line and not line.startswith('#'):
            try:url=checked_url(urljoin(base,line) if base else line)
            except ValueError:meta=None;continue
            row=meta or {'id':'','name':'Saluran','country':'','category':'Impor','adult':False}
            row={**row,'url':url};row['key']=hashlib.sha256((row['id']+'|'+url).encode()).hexdigest();rows.append(row);meta=None
            if len(rows)>MAX_ROWS:raise ValueError('Terlalu banyak saluran.')
    if not rows:raise ValueError('Playlist tidak memiliki URL HTTP/HTTPS yang valid.')
    return rows

def catalog(channels,streams):
    if not isinstance(channels,list) or not isinstance(streams,list) or len(channels)>MAX_ROWS or len(streams)>MAX_ROWS:raise ValueError('Format katalog tidak valid.')
    # Never curate explicit adult/porn streams from the public directory.
    metadata={c['id']:c for c in channels if isinstance(c,dict) and isinstance(c.get('id'),str) and not c.get('is_nsfw') and not c.get('closed')}
    rows=[];seen=set()
    for stream in streams:
        if not isinstance(stream,dict):continue
        c=metadata.get(stream.get('channel'))
        if not c:continue
        try:url=checked_url(stream.get('url',''))
        except ValueError:continue
        key=hashlib.sha256((c['id']+'|'+url).encode()).hexdigest()
        if key in seen:continue
        seen.add(key);rows.append({'id':c['id'],'name':str(c.get('name',c['id']))[:300],'url':url,'country':str(c.get('country','')),'category':', '.join(c.get('categories') or ['general']),'adult':False,'key':key})
    return rows

def xmltv_time(value):
    value=str(value).strip();match=re.fullmatch(r'(\d{14})\s*([+-]\d{4})?',value)
    if not match:raise ValueError('Waktu XMLTV tidak valid.')
    return datetime.datetime.strptime(match[1]+(match[2] or '+0000'),'%Y%m%d%H%M%S%z').timestamp()
def parse_xmltv(data):
    if data[:2]==b'\x1f\x8b':
        import io
        with gzip.GzipFile(fileobj=io.BytesIO(data)) as src:data=src.read(32*1024*1024+1)
    if len(data)>32*1024*1024 or b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():raise ValueError('XMLTV terlalu besar atau memiliki deklarasi terlarang.')
    root=ET.fromstring(data)
    if root.tag!='tv':raise ValueError('Dokumen bukan XMLTV.')
    programs=[]
    for p in root.findall('programme'):
        try:a=xmltv_time(p.get('start'));b=xmltv_time(p.get('stop'))
        except (ValueError,TypeError):continue
        if b<=a:continue
        programs.append({'channel':p.get('channel','')[:200],'start':a,'end':b,'title':(p.findtext('title') or '')[:500]})
        if len(programs)>200000:raise ValueError('Program XMLTV terlalu banyak.')
    return programs

def filter_rows(rows,query='',country='',category='',favorites=None,only_favorites=False,unlocked=False,programs=()):
    query=query.casefold().strip();matches={p['channel'] for p in programs if query and query in p['title'].casefold()}
    return [r for r in rows if (unlocked or not adult(r)) and (not country or r['country']==country) and (not category or category in r['category'].split(', ')) and (not only_favorites or r['key'] in (favorites or set())) and (not query or query in (r['name']+' '+r['id']).casefold() or r['id'] in matches)]
