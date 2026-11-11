"""Optional local Whisper.cpp + Ollama adapters. Never sends a Gemini API key."""
import json,uuid,urllib.request,urllib.parse,urllib.error
from core import Cue,validate,APIError

def local_url(value,default_path):
    url=urllib.parse.urlsplit(value)
    if url.scheme!='http' or url.hostname not in ('localhost','127.0.0.1','::1') or url.username or url.password:
        raise ValueError('AI lokal hanya mengizinkan HTTP localhost/127.0.0.1/::1 tanpa kredensial URL.')
    if url.query or url.fragment:raise ValueError('URL lokal tidak boleh berisi query/fragment.')
    return urllib.parse.urlunsplit((url.scheme,url.netloc,url.path.rstrip('/') or default_path,'',''))

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None

def _open_local(request):
    # Direct loopback only, with redirects and environment proxies disabled.
    return urllib.request.build_opener(urllib.request.ProxyHandler({}),_NoRedirect()).open(request,timeout=180)

def transcribe_local(audio,config,language,duration,offset,cancelled=lambda:False,progress=lambda text:None,context_seconds=0):
    if cancelled():raise InterruptedError('Dibatalkan')
    stt=local_url(config.get('speech_url','http://127.0.0.1:8080/inference'),'/inference')
    translate=local_url(config.get('translate_url','http://127.0.0.1:11434/api/generate'),'/api/generate')
    boundary='Cyber80-'+uuid.uuid4().hex;parts=[]
    for name,value in [('response_format','verbose_json'),('language','auto'),('temperature','0')]:
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="audio.wav"\r\nContent-Type: audio/wav\r\n\r\n'.encode()+audio+b'\r\n')
    parts.append(f'--{boundary}--\r\n'.encode())
    progress('AI lokal: mengenali suara melalui Whisper lokal …')
    request=urllib.request.Request(stt,data=b''.join(parts),headers={'Content-Type':'multipart/form-data; boundary='+boundary})
    try:
        with _open_local(request) as response:data=json.load(response)
    except (OSError,ValueError) as exc:raise APIError('Whisper lokal tidak tersedia atau respons tidak valid. Jalankan server/model Whisper lokal dan periksa URL.') from None
    if not isinstance(data,dict):raise APIError('Respons Whisper lokal bukan JSON object.')
    raw=[]
    for segment in (data.get('segments') or data.get('transcription') or []):
        if 'start' in segment:a,b=float(segment['start']),float(segment['end'])
        elif 'offsets' in segment:a,b=float(segment['offsets']['from'])/1000,float(segment['offsets']['to'])/1000
        elif 't0' in segment:a,b=float(segment['t0'])/100,float(segment['t1'])/100
        else:continue
        if b<=a:continue
        raw.append({'start':max(0,a),'end':min(duration,b),'source':segment.get('text',''),'language':data.get('language','auto')})
    if not raw and str(data.get('text','')).strip():raw=[{'start':0,'end':duration,'source':data['text'],'language':data.get('language','auto')}]
    cues=validate(raw,duration,offset-context_seconds)
    cues=[Cue(max(offset,c.start),c.end,c.source,c.target,c.language) for c in cues if c.end>offset+.02]
    if not cues:return []
    if cancelled():raise InterruptedError('Dibatalkan')
    prompt='Translate these subtitles to '+language+'. Use natural, correct spelling and punctuation, preserve meaning/names. For Indonesian use formal standard Indonesian. Return JSON object {"translations":["..."]} in exactly the same order. Text:\n'+json.dumps([c.source for c in cues],ensure_ascii=False)
    payload={'model':config.get('model','qwen2.5:3b'),'prompt':prompt,'stream':False,'format':'json','options':{'temperature':0}}
    progress('AI lokal: menerjemahkan melalui model Ollama …')
    try:
        request=urllib.request.Request(translate,data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
        with _open_local(request) as response:answer=json.load(response)
        texts=json.loads(answer['response'])['translations']
        if len(texts)!=len(cues) or not all(isinstance(t,str) for t in texts):raise ValueError()
    except (OSError,ValueError,KeyError,TypeError):raise APIError('Ollama lokal tidak tersedia, model belum diunduh, atau jumlah hasil terjemahan tidak cocok.') from None
    for cue,text in zip(cues,texts):cue.target=text
    return cues
