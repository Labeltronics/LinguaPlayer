import base64, html, json, math, re, time, urllib.request, urllib.error
from dataclasses import dataclass

@dataclass
class Cue:
    start: float
    end: float
    source: str
    target: str = ''

def validate(items, duration, offset=0):
    if not isinstance(items, list):
        raise ValueError('Respons subtitle bukan array JSON')
    cues = []
    for item in items:
        a, b = float(item['start']), float(item['end'])
        if not math.isfinite(a+b) or a < 0 or b <= a or b > duration + .5:
            raise ValueError('Timestamp AI tidak valid; coba proses ulang')
        text = str(item['source']).strip()
        if text:
            cues.append(Cue(offset+a, offset+min(b,duration), text, str(item.get('target','')).strip()))
    cues.sort(key=lambda c:c.start)
    for a,b in zip(cues,cues[1:]):
        if a.end > b.start:
            a.end = b.start
    return cues

def request_json(url, key, payload, cancelled=lambda:False):
    for attempt in range(4):
        if cancelled(): raise InterruptedError('Dibatalkan')
        req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={
            'Content-Type':'application/json','x-goog-api-key':key}, method='POST')
        try:
            with urllib.request.urlopen(req, timeout=120) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code not in (429,500,502,503,504) or attempt == 3:
                raise RuntimeError(f'API HTTP {exc.code}. Periksa key, model, billing dan kuota.') from None
        except urllib.error.URLError:
            if attempt == 3: raise RuntimeError('Koneksi API gagal. Periksa internet.') from None
        for _ in range(2**attempt*10):
            if cancelled(): raise InterruptedError('Dibatalkan')
            time.sleep(.1)
    raise RuntimeError('API gagal')

def transcribe(audio, key, model, language, duration, offset, google_key='', cancelled=lambda:False, glossary=''):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+',model): raise ValueError('Nama model tidak valid')
    prompt = ('Transcribe the actual speech, detecting the source language. Do not invent speech in silence/music. '
              'Return only a JSON array of subtitle cues, each with numeric start and end in seconds relative to this audio, '
              'source (original transcript) and target (translation). Short readable cues. '
              f'Audio duration {duration:.3f} seconds. Translate to {language}. Use correct spelling, capitalization and punctuation. '
              + ('Leave target empty; another translator handles translation.' if google_key else 'Preserve meaning and proper names.'))
    prompt += '\nPreferred spelling and terminology (reference only): ' + glossary[:6000]
    data=request_json(f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent',key,{
        'contents':[{'parts':[{'text':prompt},{'inlineData':{'mimeType':'audio/wav','data':base64.b64encode(audio).decode()}}]}],
        'generationConfig':{'temperature':0,'responseMimeType':'application/json'}},cancelled)
    candidate=data.get('candidates',[{}])[0]
    if candidate.get('finishReason') != 'STOP': raise ValueError('Respons AI terpotong atau diblokir. Coba ulang/model lain.')
    raw=''.join(p.get('text','') for p in candidate.get('content',{}).get('parts',[]) if not p.get('thought'))
    cues=validate(json.loads(raw),duration,offset)
    if google_key and cues:
        translated=request_json('https://translation.googleapis.com/language/translate/v2',google_key,
            {'q':[c.source for c in cues], 'target':language,'format':'text'},cancelled)
        texts=translated['data']['translations']
        if len(texts)!=len(cues): raise ValueError('Jumlah hasil terjemahan tidak cocok')
        for cue,text in zip(cues,texts): cue.target=html.unescape(text['translatedText'])
    return cues

def stamp(seconds):
    n=round(seconds*1000)
    return f'{n//3600000:02}:{n//60000%60:02}:{n//1000%60:02},{n%1000:03}'

def srt(cues, translated=True):
    return '\n\n'.join(f'{i}\n{stamp(c.start)} --> {stamp(c.end)}\n{c.target if translated and c.target else c.source}' for i,c in enumerate(cues,1))+'\n'

def parse_srt(text):
    result=[]
    def seconds(t):
        h,m,s= t.replace('.',',').split(':')
        sec,ms=s.split(',')
        return int(h)*3600+int(m)*60+int(sec)+int(ms)/1000
    for block in re.split(r'\n\s*\n',text.lstrip('\ufeff').replace('\r\n','\n').strip()):
        lines=block.splitlines()
        if not lines:continue
        timing=next((i for i,line in enumerate(lines) if '-->' in line),None)
        if timing is None:raise ValueError('Format SRT tidak valid')
        a,b=lines[timing].split('-->')
        result.extend(validate([{'start':seconds(a.strip()),'end':seconds(b.strip().split()[0]),'source':'\n'.join(lines[timing+1:])}],1e12))
    return sorted(result,key=lambda c:c.start)
