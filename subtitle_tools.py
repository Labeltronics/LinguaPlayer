"""Subtitle conversion, affine synchronization, and readable-cue QA."""
import copy,math,re
from core import parse_srt,srt

def parse_vtt(text):
    text=text.lstrip('\ufeff').replace('\r\n','\n')
    if not text.startswith('WEBVTT'):raise ValueError('Header WEBVTT tidak ditemukan.')
    blocks=[]
    for block in re.split(r'\n\s*\n',text):
        lines=block.splitlines()
        if not lines or lines[0].startswith(('WEBVTT','NOTE','STYLE','REGION')):continue
        i=next((i for i,v in enumerate(lines) if '-->' in v),None)
        if i is None:continue
        a,b=lines[i].split('-->')
        def stamp(t):
            t=t.strip().split()[0]
            if t.count(':')==1:t='00:'+t
            return t.replace('.',',')
        body=re.sub(r'<[^>]*>','','\n'.join(lines[i+1:]))
        blocks.append(stamp(a)+' --> '+stamp(b)+'\n'+body)
    return parse_srt('\n\n'.join(blocks))
def vtt(cues):return 'WEBVTT\n\n'+re.sub(r'(\d{2}:\d{2}:\d{2}),(\d{3})',r'\1.\2',srt(cues))
def synchronize(cues,source_a,target_a,source_b,target_b):
    values=(source_a,target_a,source_b,target_b)
    if not all(math.isfinite(v) for v in values) or source_b<=source_a or target_b<=target_a:raise ValueError('Dua titik harus berurutan dan terbatas.')
    ratio=(target_b-target_a)/(source_b-source_a)
    result=copy.deepcopy(cues)
    for c in result:
        c.start=target_a+(c.start-source_a)*ratio;c.end=target_a+(c.end-source_a)*ratio
        if c.start<0 or c.end<=c.start:raise ValueError('Sinkronisasi menghasilkan timestamp negatif/tidak valid.')
    return result

def quality_report(cues):
    issues=[];previous_end=0
    for i,c in enumerate(cues,1):
        text=c.target or c.source;duration=c.end-c.start;lines=text.splitlines();flags=[]
        if c.start<previous_end-.001:flags.append('tumpang tindih')
        if len(lines)>2:flags.append('lebih dari 2 baris')
        if any(len(line)>42 for line in lines):flags.append('baris >42 karakter')
        if duration<=0 or len(text.replace('\n',''))/duration>20:flags.append('terlalu cepat dibaca (>20 karakter/detik)')
        if 0<duration<.7:flags.append('durasi <0,7 detik')
        if flags:issues.append({'cue':i,'issues':flags})
        previous_end=c.end
    return issues
