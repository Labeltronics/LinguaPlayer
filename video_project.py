"""Non-destructive multilayer timeline model, JSON persistence and undo snapshots."""
import copy,json,math,uuid,os
from pathlib import Path
from fractions import Fraction
KINDS=('video','image','color','text','audio','subtitle')
KEYS={'x':(-200,200),'y':(-200,200),'scale':(.01,10),'opacity':(0,1),'volume':(-60,12)}
def uid():return uuid.uuid4().hex
def new_project():
    tracks=[]
    for name,kind in [('Latar','visual'),('Video 1','visual'),('Overlay / gambar','visual'),('Judul','visual'),('Subtitle','subtitle'),('Suara / narasi','voice'),('Musik','music'),('Efek suara','audio')]:tracks.append(new_track(name,kind))
    return {'schema':1,'settings':{'width':1920,'height':1080,'fps':'25','background':'#101827','ducking':False},'tracks':tracks,'clips':[]}
def new_track(name,kind):return {'id':uid(),'name':str(name)[:80],'kind':kind,'hidden':False,'locked':False,'muted':False,'solo':False,'volume':0.0}
def new_clip(track,kind,path='',duration=5,**extra):
    c={'id':uid(),'track':track,'kind':kind,'path':str(path),'name':Path(path).name if path else kind,'start':0.,'in':0.,'duration':float(duration),'speed':1.,'source_duration':float(duration) if kind in ('video','audio') else 0.,'has_audio':kind=='audio','source_has_audio':kind in ('video','audio'),'x':0.,'y':0.,'width':100.,'height':100.,'scale':1.,'opacity':1.,'volume':0.,'pan':0.,'fade_in':0.,'fade_out':0.,'rotation':0,'brightness':0.,'contrast':1.,'saturation':1.,'color':'#ffffff','fit':'contain','blur':0.,'chroma':False,'chroma_color':'#00ff00','chroma_similarity':.1,'chroma_blend':.03,'font_size':5.,'text':'','keyframes':[]}
    c.update(extra);return c
def fps(p):return float(Fraction(p['settings']['fps']))
def snap(p,t):return round(float(t)*fps(p))/fps(p)
def duration(p):return max((c['start']+c['duration'] for c in p['clips']),default=0.)
def numeric(value,low,high,label):
    if isinstance(value,bool) or not isinstance(value,(float,int)) or not math.isfinite(value) or not low<=value<=high:raise ValueError(label+' di luar batas.')
def color(value):
    import re
    if not isinstance(value,str) or not re.fullmatch('#[0-9a-fA-F]{6}',value):raise ValueError('Gunakan warna #RRGGBB.')
    return '0x'+value[1:]
def validate(p,sources=False):
    if not isinstance(p,dict) or p.get('schema')!=1:raise ValueError('Versi proyek tidak didukung.')
    s=p['settings'];numeric(s['width'],64,4096,'Lebar');numeric(s['height'],64,4096,'Tinggi')
    if int(s['width'])!=s['width'] or int(s['height'])!=s['height'] or s['width']%2 or s['height']%2:raise ValueError('Resolusi harus bilangan genap.')
    if len(str(s['fps']))>20 or not 1<=fps(p)<=120:raise ValueError('FPS tidak sah.')
    color(s['background'])
    if not isinstance(p['tracks'],list) or not 1<=len(p['tracks'])<=32:raise ValueError('Maksimum 32 layer.')
    ids=set()
    for t in p['tracks']:
        if not isinstance(t['id'],str) or t['id'] in ids or t['kind'] not in ('visual','subtitle','voice','music','audio'):raise ValueError('Layer tidak sah.')
        ids.add(t['id']);numeric(t['volume'],-60,12,'Volume layer')
    if not isinstance(p['clips'],list) or len(p['clips'])>128:raise ValueError('Edisi ini mendukung maksimum 128 klip per proyek.')
    clipids=set()
    for c in p['clips']:
        if c['id'] in clipids or c['track'] not in ids or c['kind'] not in KINDS:raise ValueError('Klip tidak sah.')
        clipids.add(c['id'])
        if not compatible(track(p,c['track']),c):raise ValueError('Jenis klip tidak cocok dengan layer.')
        if c['kind']=='video' and c['has_audio'] and not c.get('source_has_audio',True):raise ValueError('Sumber video tidak memiliki audio.')
        numeric(c['start'],0,86400,'Posisi');numeric(c['in'],0,86400,'Source in');numeric(c['duration'],1/fps(p)-1e-7,86400,'Durasi');numeric(c['speed'],.1,10,'Speed')
        numeric(c['source_duration'],0,864000,'Durasi sumber')
        if c['kind'] in ('video','audio') and c['source_duration'] and c['in']+c['duration']*c['speed']>c['source_duration']+.1:raise ValueError('Rentang klip melewati akhir sumber.')
        for k,(lo,hi) in KEYS.items():numeric(c[k],lo,hi,k)
        for k,lo,hi in [('width',1,400),('height',1,400),('pan',-1,1),('fade_in',0,c['duration']),('fade_out',0,c['duration']),('brightness',-1,1),('contrast',0,3),('saturation',0,3),('font_size',1,30)]:numeric(c[k],lo,hi,k)
        if c['rotation'] not in (0,90,180,270):raise ValueError('Rotasi tidak sah.')
        color(c['color']);color(c.get('chroma_color','#00ff00'))
        if c.get('fit','contain') not in ('contain','cover','stretch'):raise ValueError('Mode fitting tidak sah.')
        numeric(c.get('blur',0),0,20,'Blur');numeric(c.get('chroma_similarity',.1),.01,1,'Chroma similarity');numeric(c.get('chroma_blend',.03),0,1,'Chroma blend')
        if not isinstance(c['text'],str) or len(c['text'])>2*1024*1024:raise ValueError('Teks terlalu besar.')
        if c['kind'] in ('video','image','audio'):
            if not isinstance(c['path'],str) or not Path(c['path']).is_absolute():raise ValueError('Sumber harus berupa file lokal dengan path absolut.')
            if sources and not Path(c['path']).is_file():raise ValueError('Sumber hilang: '+Path(c['path']).name+'. Gunakan Relink.')
        if len(c['keyframes'])>200:raise ValueError('Maksimum 200 keyframe per klip.')
        times=set()
        for kf in c['keyframes']:
            numeric(kf['time'],0,c['duration'],'Waktu keyframe')
            if kf['time'] in times:raise ValueError('Keyframe ganda.')
            times.add(kf['time'])
            for key,(lo,hi) in KEYS.items():numeric(kf[key],lo,hi,key)
    if duration(p)>86400:raise ValueError('Durasi proyek maksimum 24 jam.')
    return p
def track(p,id):return next(t for t in p['tracks'] if t['id']==id)
def compatible(t,c):return (t['kind']=='visual' and c['kind'] in ('video','image','color','text')) or (t['kind']=='subtitle' and c['kind']=='subtitle') or (t['kind'] in ('voice','music','audio') and c['kind']=='audio')
def value_at(c,key,t):
    rows=sorted(c['keyframes'],key=lambda k:k['time'])
    if not rows:return c[key]
    if t<=rows[0]['time']:return rows[0][key]
    for a,b in zip(rows,rows[1:]):
        if t<=b['time']:
            f=(t-a['time'])/(b['time']-a['time']);return a[key]+(b[key]-a[key])*f
    return rows[-1][key]
def slice_clip(c,a,b):
    result=copy.deepcopy(c);elapsed=a-c['start'];length=b-a;result['start']=a;result['in']+=elapsed*c['speed'];result['duration']=length
    times={0.,length}
    times.update(k['time']-elapsed for k in c['keyframes'] if elapsed<k['time']<elapsed+length)
    for v in (c['fade_in'],c['duration']-c['fade_out']):
        if elapsed<v<elapsed+length:times.add(v-elapsed)
    result['keyframes']=[]
    for t in sorted(times):
        orig=elapsed+t;kf={'time':t,**{key:value_at(c,key,orig) for key in KEYS}}
        envelope=min(1,orig/c['fade_in'] if c['fade_in'] else 1,(c['duration']-orig)/c['fade_out'] if c['fade_out'] else 1)
        kf['opacity']*=max(0,envelope);kf['volume']=max(-60,kf['volume']+20*math.log10(max(.001,envelope)))
        result['keyframes'].append(kf)
    result['fade_in']=result['fade_out']=0.
    return result
def split(p,id,at):
    c=next(c for c in p['clips'] if c['id']==id)
    if track(p,c['track'])['locked']:raise ValueError('Layer terkunci.')
    at=snap(p,at)
    if at-c['start']<1/fps(p)-1e-7 or c['start']+c['duration']-at<1/fps(p)-1e-7:raise ValueError('Playhead harus berada di dalam klip, minimal satu frame dari ujung.')
    left=slice_clip(c,c['start'],at);right=slice_clip(c,at,c['start']+c['duration']);right['id']=uid();i=p['clips'].index(c);p['clips'][i:i+1]=[left,right]
def save(p,path):
    validate(p);path=Path(path);tmp=path.with_name(path.name+'.'+uid()+'.tmp')
    try:
        with tmp.open('w',encoding='utf-8') as f:json.dump(p,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:tmp.unlink(missing_ok=True)
def load(path):
    path=Path(path)
    if path.stat().st_size>16*1024*1024:raise ValueError('Proyek terlalu besar.')
    return validate(json.loads(path.read_text(encoding='utf-8-sig')))
class History:
    def __init__(self,p):self.states=[json.dumps(p,sort_keys=True)];self.index=0
    def commit(self,p):
        validate(p);s=json.dumps(p,sort_keys=True)
        if s==self.states[self.index]:return
        self.states=self.states[:self.index+1]+[s];self.states=self.states[-100:];self.index=len(self.states)-1
    def step(self,n):self.index=max(0,min(len(self.states)-1,self.index+n));return json.loads(self.states[self.index])
