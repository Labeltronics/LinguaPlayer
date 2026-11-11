import base64, html, json, math, re, time, urllib.request, urllib.error, socket, random, threading, http.client
from dataclasses import dataclass

@dataclass
class Cue:
    start: float
    end: float
    source: str
    target: str = ''
    language: str = ''

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
            cues.append(Cue(offset+a, offset+min(b,duration), text, str(item.get('target','')).strip(),str(item.get('language','')).strip()))
    cues.sort(key=lambda c:c.start)
    for a,b in zip(cues,cues[1:]):
        if a.end > b.start:
            a.end = b.start
    return cues

class APIError(RuntimeError):
    def __init__(self,message,status=None):super().__init__(message);self.status=status

class APITimeout(APIError):pass

_API_GATE=threading.Lock()
_NEXT_REQUEST=0.

def wait_cancel(seconds,cancelled,progress=lambda text:None):
    deadline=time.monotonic()+max(0,seconds)
    previous=-1
    while time.monotonic()<deadline:
        if cancelled():raise InterruptedError('Dibatalkan')
        remaining=int(deadline-time.monotonic())+1
        if remaining!=previous:progress(f'Menunggu {remaining} detik sebelum mencoba lagi …');previous=remaining
        time.sleep(min(.1,max(0,deadline-time.monotonic())))

def api_message(status,detail):
    hints={400:'Parameter/model tidak cocok atau prasyarat proyek tidak terpenuhi.',
           401:'API key tidak valid atau kedaluwarsa.',403:'Akses proyek/model ditolak. Periksa izin dan ketersediaan Free Tier; aplikasi tidak mengaktifkan billing.',
           404:'Model tidak tersedia. Pilih model yang tersedia pada proyek Free Tier Anda.',
           429:'Batas permintaan atau kuota gratis tercapai. Tunggu kuota tersedia kembali; tidak ada perpindahan ke layanan berbayar.',
           503:'Layanan Gemini sedang sibuk.',504:'Server Gemini kehabisan waktu memproses audio.'}
    return f'API HTTP {status}: '+hints.get(status,'Permintaan API gagal.')+('\nDetail Google: '+detail if detail else '')

def request_json(url, key, payload, cancelled=lambda:False, progress=lambda text:None, timeout=180):
    global _NEXT_REQUEST
    for attempt in range(2):
        if cancelled():raise InterruptedError('Dibatalkan')
        # Serialise requests across both player windows, including retries.
        while not _API_GATE.acquire(timeout=.1):
            if cancelled():raise InterruptedError('Dibatalkan')
            progress('Menunggu giliran API dari pemutar lain …')
        delay=0.;last=None
        try:
            wait_cancel(max(0,_NEXT_REQUEST-time.monotonic()),cancelled,progress)
            if cancelled():raise InterruptedError('Dibatalkan')
            _NEXT_REQUEST=time.monotonic()+15
            progress(f'Menghubungi Gemini (percobaan {attempt+1}/2, batas waktu {timeout} detik) …')
            req=urllib.request.Request(url,data=json.dumps(payload).encode(),headers={
                'Content-Type':'application/json','x-goog-api-key':key},method='POST')
            try:
                with urllib.request.urlopen(req,timeout=timeout) as response:return json.load(response)
            except urllib.error.HTTPError as exc:
                error={}
                try:
                    error=json.loads(exc.read(32768)).get('error',{})
                    detail=str(error.get('message','')).replace(key,'[KEY DISEMBUNYIKAN]')[:1600]
                except Exception:detail=''
                detail=re.sub(r'(?:AIza|AQ\.)[A-Za-z0-9_.-]+','[KEY DISEMBUNYIKAN]',detail)
                last=APIError(api_message(exc.code,detail),exc.code)
                # Hard quota failures and access failures must not trigger more calls.
                hard_quota=exc.code==429 and any(x in detail.lower() for x in ['perday','per_day','per day','daily','limit: 0','limit is 0'])
                if exc.code not in (408,429,500,502,503,504) or hard_quota:raise last from None
                try:delay=float(exc.headers.get('Retry-After',''))
                except (ValueError,TypeError,AttributeError):delay=15 if exc.code==429 else 3
                for item in error.get('details',[]) if 'error' in locals() and isinstance(error,dict) else []:
                    if isinstance(item,dict) and 'retryDelay' in item:
                        try:delay=max(delay,float(str(item['retryDelay']).rstrip('s')))
                        except ValueError:pass
            except (TimeoutError,socket.timeout) as exc:
                last=APITimeout(f'Gemini timeout setelah {timeout} detik. Hasil yang sudah selesai dipertahankan. Tekan Buat / Lanjutkan subtitle untuk mencoba bagian yang gagal.');delay=3
            except urllib.error.URLError as exc:
                if isinstance(exc.reason,(TimeoutError,socket.timeout)):
                    last=APITimeout('Koneksi Gemini timeout. Periksa koneksi/proxy atau coba lagi nanti.')
                else:last=APIError('Koneksi Gemini gagal. Periksa internet, proxy, atau firewall; API key tidak ditampilkan.')
                delay=3
            except (ConnectionError,http.client.IncompleteRead) as exc:
                last=APIError('Koneksi Gemini terputus sebelum respons selesai.');delay=3
        finally:_API_GATE.release()
        if attempt==1 or delay>120:raise last from None
        progress(str(last))
        wait_cancel(max(0,delay)+random.uniform(0,.5),cancelled,progress)
    raise APIError('API gagal')

def transcribe(audio, key, model, language, duration, offset, google_key='', cancelled=lambda:False, glossary='', progress=lambda text:None, timeout=180, context_seconds=0):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+',model): raise ValueError('Nama model tidak valid')
    prompt = ('Transcribe the actual speech, detecting the source language. Do not invent speech in silence/music. '
              'Return only a JSON array of subtitle cues, each with numeric start and end in seconds relative to this audio, '
              'source (faithful original transcript with punctuation), target (translation), and language (ISO code of the ORIGINAL SPOKEN language, NEVER the target translation language). Short readable cues. '
              f'Audio duration {duration:.3f} seconds. Translate to {language}. Use correct spelling, capitalization and punctuation. '
              + ('Leave target empty; another translator handles translation.' if google_key else 'Preserve meaning and proper names.'))
    prompt += (' Act as a professional audiovisual translator. Translate meaning in context using natural, '
               'grammatically correct target-language sentences, not mechanical word-for-word translation. '
               'Do not add, omit or soften factual meaning. Preserve names, numbers, quotations and specialist terminology. '
               'Use concise readable subtitles. If target is Indonesian (id), use standard Indonesian, correct EYD spelling, '
               'capitalization and punctuation, clear idiomatic phrasing and appropriate polite register. '
               'Avoid unnecessary foreign words and slang unless needed to preserve the speaker meaning. '
               'Keep the source transcript faithful to the actual speech. Never invent uncertain or inaudible words. ')
    if context_seconds:prompt+=f' The first {context_seconds} seconds are context from the previous chunk. Return only speech after that boundary; do not repeat preceding subtitles.'
    prompt += '\nPreferred spelling and terminology (reference only): ' + glossary[:6000]
    data=request_json(f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent',key,{
        'contents':[{'parts':[{'text':prompt},{'inlineData':{'mimeType':'audio/wav','data':base64.b64encode(audio).decode()}}]}],
        'generationConfig':{'responseMimeType':'application/json'}},cancelled,progress,timeout)
    candidates=data.get('candidates') or []
    if not candidates:
        reason=data.get('promptFeedback',{}).get('blockReason','tidak ada kandidat')
        raise APIError('Gemini tidak menghasilkan subtitle: '+str(reason))
    candidate=candidates[0]
    if candidate.get('finishReason') != 'STOP':raise APIError('Gemini tidak menyelesaikan subtitle: '+str(candidate.get('finishReason','tidak diketahui')))
    raw=''.join(p.get('text','') for p in candidate.get('content',{}).get('parts',[]) if not p.get('thought'))
    cues=validate(json.loads(raw),duration,offset-context_seconds)
    cues=[Cue(max(offset,c.start),c.end,c.source,c.target,c.language) for c in cues if c.end>offset+.02]
    if google_key and cues:
        translated=request_json('https://translation.googleapis.com/language/translate/v2',google_key,
            {'q':[c.source for c in cues], 'target':language,'format':'text'},cancelled,progress,timeout)
        texts=translated['data']['translations']
        if len(texts)!=len(cues): raise ValueError('Jumlah hasil terjemahan tidak cocok')
        for cue,text in zip(cues,texts): cue.target=html.unescape(text['translatedText'])
    from language_check import check_source_languages
    return check_source_languages(cues,language)

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
