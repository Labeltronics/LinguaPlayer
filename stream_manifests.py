"""Strict offline plans for unencrypted HLS VOD and static DASH."""
import re,urllib.parse,xml.etree.ElementTree as ET,math
from web_transfer import checked_url
LIMIT=10000
def attributes(line):return {k:v.strip('"') for k,v in re.findall(r'([A-Z0-9-]+)=("[^"]*"|[^,]*)',line)}
def hls_plan(text,url):
    if not text.lstrip().startswith('#EXTM3U'):raise ValueError('Manifest HLS tidak sah.')
    lines=[v.strip() for v in text.splitlines() if v.strip()];variants=[];audio={};segments=[];local=[];pending=None
    for line in lines:
        if line.startswith('#EXT-X-KEY:') or line.startswith('#EXT-X-SESSION-KEY:'):
            if attributes(line.split(':',1)[1]).get('METHOD')!='NONE':raise ValueError('HLS terenkripsi/DRM tidak didukung.')
        if line.startswith(('#EXT-X-BYTERANGE','#EXT-X-PART:')):raise ValueError('HLS byte-range/low-latency belum didukung.')
        if line.startswith('#EXT-X-MEDIA:'):
            a=attributes(line.split(':',1)[1])
            if a.get('TYPE')=='AUDIO' and a.get('URI'):audio[a.get('GROUP-ID','')]=checked_url(urllib.parse.urljoin(url,a['URI']))
        elif line.startswith('#EXT-X-STREAM-INF:'):pending=attributes(line.split(':',1)[1])
        elif not line.startswith('#'):
            if pending:
                variants.append({'url':checked_url(urllib.parse.urljoin(url,line)),'bandwidth':int(pending.get('BANDWIDTH','0')),'label':pending.get('RESOLUTION','Audio')+' / '+pending.get('BANDWIDTH','?')+' bps','audio_group':pending.get('AUDIO','')});pending=None
            else:segments.append(checked_url(urllib.parse.urljoin(url,line)));local.append(f'seg{len(segments)-1:05}.bin')
        elif line.startswith('#EXT-X-MAP:'):
            a=attributes(line.split(':',1)[1])
            if a.get('BYTERANGE'):raise ValueError('HLS map byte-range belum didukung.')
            if not a.get('URI'):raise ValueError('Map HLS tidak sah.')
            segments.append(checked_url(urllib.parse.urljoin(url,a['URI'])));local.append(f'#EXT-X-MAP:URI="seg{len(segments)-1:05}.bin"')
        elif not line.startswith(('#EXT-X-MEDIA:','#EXT-X-I-FRAME')):local.append(line)
    for v in variants:v['audio_url']=audio.get(v['audio_group'])
    if not variants and '#EXT-X-ENDLIST' not in lines:raise ValueError('HLS live tidak diunduh tanpa batas. Gunakan sumber VOD yang selesai.')
    if len(segments)>LIMIT or len(variants)>100:raise ValueError('Manifest terlalu panjang.')
    return {'variants':variants,'segments':segments,'local':'\n'.join(local)+'\n'}
def seconds(value):
    match=re.fullmatch(r'PT(?:(\d+(?:\.\d+)?)H)?(?:(\d+(?:\.\d+)?)M)?(?:(\d+(?:\.\d+)?)S)?',value or '')
    return sum(float(v or 0)*factor for v,factor in zip(match.groups(),(3600,60,1))) if match else 0

def dash_plan(text,url):
    root=ET.fromstring(text)
    def tag(node):return node.tag.split('}')[-1]
    def children(node,name):return [x for x in node if tag(x)==name]
    def child(node,name):return next(iter(children(node,name)),None)
    def base(node,parent):
        v=child(node,'BaseURL');return checked_url(urllib.parse.urljoin(parent,v.text.strip())) if v is not None and v.text else parent
    if tag(root)!='MPD' or root.get('type','static')!='static':raise ValueError('Hanya DASH statis/VOD yang didukung.')
    if any(tag(x)=='ContentProtection' for x in root.iter()):raise ValueError('DASH terenkripsi/DRM tidak didukung.')
    periods=children(root,'Period')
    if len(periods)!=1:raise ValueError('DASH multi-period belum didukung.')
    period=periods[0];duration=seconds(period.get('duration')) or seconds(root.get('mediaPresentationDuration'));result=[]
    rootbase=base(root,url);periodbase=base(period,rootbase)
    for adaptation in children(period,'AdaptationSet'):
        abase=base(adaptation,periodbase)
        for rep in children(adaptation,'Representation'):
            rbase=base(rep,abase);mime=rep.get('mimeType',adaptation.get('mimeType',''));kind=adaptation.get('contentType',mime.split('/')[0]);rid=rep.get('id','');bandwidth=int(rep.get('bandwidth','0'))
            if kind not in ('video','audio'):continue
            template=child(rep,'SegmentTemplate')
            if template is None:template=child(adaptation,'SegmentTemplate')
            seglist=child(rep,'SegmentList')
            if seglist is None:seglist=child(adaptation,'SegmentList')
            segments=[]
            if seglist is not None:
                init=child(seglist,'Initialization')
                if init is not None:
                    if init.get('range'):raise ValueError('DASH byte-range belum didukung.')
                    segments.append(checked_url(urllib.parse.urljoin(rbase,init.get('sourceURL',''))))
                for item in children(seglist,'SegmentURL'):
                    if item.get('mediaRange'):raise ValueError('DASH byte-range belum didukung.')
                    segments.append(checked_url(urllib.parse.urljoin(rbase,item.get('media',''))))
            elif template is not None:
                scale=int(template.get('timescale','1'));number=int(template.get('startNumber','1'))
                if scale<=0:raise ValueError('Timescale DASH tidak valid.')
                def expand(value,n,t):
                    value=value.replace('$$','\x01').replace('$RepresentationID$',rid).replace('$Bandwidth$',str(bandwidth)).replace('$Time$',str(t))
                    value=re.sub(r'\$Number(?:%0(\d+)d)?\$',lambda m:str(n).zfill(min(12,int(m.group(1) or 0))),value).replace('\x01','$')
                    if '$' in value:raise ValueError('Template DASH belum didukung.')
                    return checked_url(urllib.parse.urljoin(rbase,value))
                if template.get('initialization'):segments.append(expand(template.get('initialization'),number,0))
                timeline=child(template,'SegmentTimeline');times=[]
                if timeline is not None:
                    current=0;items=children(timeline,'S')
                    for i,item in enumerate(items):
                        current=int(item.get('t',current));step=int(item.get('d','0'));repeat=int(item.get('r','0'))
                        if step<=0:raise ValueError('Timeline DASH tidak sah.')
                        if repeat<0:
                            end=int(items[i+1].get('t')) if i+1<len(items) and items[i+1].get('t') else int(duration*scale)
                            if end<=current:raise ValueError('Batas timeline DASH tidak diketahui.')
                            repeat=math.ceil((end-current)/step)-1
                        if repeat>LIMIT or len(times)+repeat+1>LIMIT:raise ValueError('DASH terlalu panjang.')
                        for _ in range(repeat+1):times.append(current);current+=step
                else:
                    step=int(template.get('duration','0'))
                    if step<=0 or duration<=0:raise ValueError('Durasi DASH tidak diketahui.')
                    count=math.ceil(duration*scale/step)
                    if count>LIMIT:raise ValueError('DASH terlalu panjang.')
                    times=[i*step for i in range(count)]
                for i,t in enumerate(times):segments.append(expand(template.get('media',''),number+i,t))
            elif rbase!=abase:segments=[rbase]
            else:raise ValueError('Representasi DASH tidak mempunyai sumber yang didukung.')
            if not segments or len(segments)>LIMIT:raise ValueError('Daftar segmen DASH tidak sah.')
            result.append({'kind':kind,'segments':segments,'bandwidth':bandwidth,'label':rep.get('height','?')+'p / '+str(bandwidth)+' bps'})
    if not result:raise ValueError('Tidak ada representasi video/audio DASH.')
    return result
