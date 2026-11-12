"""Bounded subtitle-to-speech and aligned export; no credentials persisted."""
import base64, json, math, os, re, subprocess, tempfile, time, uuid, wave, threading, shutil
from contextlib import contextmanager
from pathlib import Path
from PySide6.QtCore import QThread, Signal
import imageio_ffmpeg
from core import request_json, srt
from video_render import probe, flags, tempo

VOICES=('Kore','Puck','Charon','Fenrir','Aoede','Leda','Orus','Zephyr')

def checked_cues(cues,duration):
    if not cues or len(cues)>10000:raise ValueError('Isi 1–10000 baris subtitle terlebih dahulu.')
    previous=0
    for c in cues:
        if not all(math.isfinite(v) for v in (c.start,c.end)) or not 0<=c.start<c.end<=duration+.05 or c.start<previous-.001:raise ValueError('Waktu subtitle bertumpuk atau di luar durasi. Perbaiki SRT.')
        if not (c.target or c.source).strip() or len(c.target or c.source)>4000:raise ValueError('Teks cue kosong/terlalu panjang.')
        previous=c.end
    return cues

def lrc(cues):
    lines=['[re:Cyber80 Players]']
    for c in cues:
        for t,text in ((c.start,(c.target or c.source).replace('\n',' ')),(c.end,'')):
            ticks=round(t*100);minutes,cs=divmod(ticks,6000);seconds,cs=divmod(cs,100)
            lines.append(f'[{minutes:02}:{seconds:02}.{cs:02}]{text}')
    return '\n'.join(lines)+'\n'

def decode_audio(response):
    candidates=response.get('candidates') or []
    if not candidates or candidates[0].get('finishReason')!='STOP':raise ValueError('TTS tidak menghasilkan audio lengkap. Coba lagi atau perpendek teks.')
    chunks=[];rate=None
    for part in candidates[0].get('content',{}).get('parts',[]):
        inline=part.get('inlineData',{});mime=inline.get('mimeType','')
        if not inline:continue
        pieces=[piece.strip() for piece in mime.lower().split(';')];parameters={}
        for piece in pieces[1:]:
            if '=' not in piece:raise ValueError('Parameter audio TTS tidak valid.')
            k,v=piece.split('=',1);parameters[k.strip()]=v.strip()
        if pieces[0] not in ('audio/l16','audio/pcm') or parameters.get('codec','pcm')!='pcm' or parameters.get('channels','1')!='1' or not parameters.get('rate','').isdigit():raise ValueError('Format audio TTS tidak didukung; diharapkan PCM 16-bit mono.')
        current=int(parameters['rate'])
        if current not in (16000,22050,24000,44100,48000) or rate not in (None,current):raise ValueError('Sample rate TTS tidak valid.')
        rate=current;chunks.append(base64.b64decode(inline.get('data',''),validate=True))
    pcm=b''.join(chunks)
    if not pcm or len(pcm)%2 or len(pcm)>64*1024*1024:raise ValueError('Data audio TTS kosong/rusak/terlalu besar.')
    return pcm,rate

def write_pcm(path,pcm,rate):
    with wave.open(str(path),'wb') as out:out.setnchannels(1);out.setsampwidth(2);out.setframerate(rate);out.writeframes(pcm)

def protected_target(source,target,extras=()):
    source=Path(source).resolve();target=Path(target).resolve()
    if target in {source,*(Path(p).resolve() for p in extras if p)}:raise ValueError('Hasil tidak boleh menimpa sumber, subtitle, atau musik latar.')
    if target.exists():raise ValueError('Nama hasil sudah ada. Pilih nama baru agar file lama aman.')
    if not target.parent.is_dir():raise ValueError('Folder hasil tidak ditemukan.')
    return target

class DubbingJob(QThread):
    progress=Signal(str);completed=Signal(str);failed=Signal(str)
    def __init__(self,source,target,cues,engine='gemini',key='',model='gemini-2.5-flash-preview-tts',voice='Kore',language='id',mode='voiceover',background='',original_volume=.12,gain=1.,sapi_voice='',speed_limit=2.,audio_stream=0,clone=None):
        super().__init__();self.source=str(source);self.target=str(target);self.cues=list(cues);self.engine=engine;self.key=key;self.model=model;self.voice=voice;self.language=language;self.mode=mode;self.background=background;self.original_volume=original_volume;self.gain=gain;self.sapi_voice=sapi_voice;self.speed_limit=speed_limit;self.audio_stream=audio_stream;self.clone=clone;self.clone_session=None;self.proc=None;self.stop_event=threading.Event()
    def cancelled(self):return self.stop_event.is_set() or self.isInterruptionRequested()
    def cancel(self):
        self.stop_event.set();self.requestInterruption()
        if self.clone_session:self.clone_session.close()
        if self.proc:
            try:self.proc.kill()
            except OSError:pass
    def run_command(self,args):
        if self.cancelled():raise InterruptedError('Dibatalkan')
        with tempfile.TemporaryFile() as errors:
            self.proc=subprocess.Popen(args,stdout=subprocess.DEVNULL,stderr=errors,**flags())
            while self.proc.poll() is None:
                if self.cancelled():self.proc.kill();self.proc.wait();raise InterruptedError('Dibatalkan')
                time.sleep(.05)
            result=self.proc.returncode;self.proc=None
            if result:raise ValueError('Pemrosesan audio/video gagal. Periksa track audio, ruang disk dan format sumber.')
    def synthesize(self,text,path,temp):
        if self.engine=='gemini':
            if not self.key or not re.fullmatch(r'[A-Za-z0-9_.-]+',self.model) or self.voice not in VOICES:raise ValueError('Isi API key, model TTS dan suara yang valid.')
            payload={'contents':[{'parts':[{'text':f'Synthesize speech in language {self.language}. Read only the transcript below naturally and faithfully. Do not read these instructions.\nTRANSCRIPT:\n'+text}]}], 'generationConfig':{'responseModalities':['AUDIO'],'speechConfig':{'voiceConfig':{'prebuiltVoiceConfig':{'voiceName':self.voice}}}}}
            response=request_json('https://generativelanguage.googleapis.com/v1beta/models/'+self.model+':generateContent',self.key,payload,self.cancelled,self.progress.emit)
            pcm,rate=decode_audio(response);write_pcm(path,pcm,rate)
        elif self.engine=='sapi':
            if os.name!='nt':raise ValueError('Suara Windows hanya tersedia di Windows.')
            config=Path(temp)/'speech.json';config.write_text(json.dumps({'text':text,'voice':self.sapi_voice,'output':str(path),'language':self.language}),encoding='utf-8')
            script=Path(__file__).resolve().parent/'sapi_dubbing.ps1'
            self.run_command(['powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(script),'-Config',str(config)])
        else:raise ValueError('Mesin suara tidak dikenal.')
    @contextmanager
    def session_directory(self):
        with tempfile.TemporaryDirectory(prefix='cyber80-dubbing-') as folder:
            try:yield folder
            finally:
                if self.clone_session:self.clone_session.close();self.clone_session=None
    def execute(self):
        ff=imageio_ffmpeg.get_ffmpeg_exe();info=probe(ff,self.source);duration=info['duration'];checked_cues(self.cues,duration)
        if not info['has_audio']:raise ValueError('Sumber tidak memiliki audio.')
        if self.mode not in ('voiceover','replace','instrumental','dual'):raise ValueError('Mode dubbing tidak valid.')
        if self.engine not in ('gemini','sapi') or not re.fullmatch(r'[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})?',self.language):raise ValueError('Bahasa/mesin suara tidak valid.')
        if not 0<=self.original_volume<=1 or not .1<=self.gain<=4 or not 1<=self.speed_limit<=4 or not isinstance(self.audio_stream,int) or not 0<=self.audio_stream<=99:raise ValueError('Pengaturan audio di luar batas.')
        target=protected_target(self.source,self.target,[self.background,(self.clone or {}).get('reference','')]);ext=target.suffix.lower()
        if ext not in ('.wav','.m4a','.mp4','.mkv'):raise ValueError('Ekspor mendukung WAV/M4A/MP4/MKV.')
        if ext in ('.mp4','.mkv') and info['kind']!='video':raise ValueError('Untuk sumber musik pilih WAV/M4A.')
        if self.mode=='dual' and ext!='.mkv':raise ValueError('Dua track audio memerlukan MKV.')
        if self.mode=='instrumental' and (not self.background or not probe(ff,self.background)['has_audio']):raise ValueError('Pilih file instrumental/M&E tanpa dialog terlebih dahulu.')
        partial=target.with_name(target.stem+'.'+uuid.uuid4().hex+'.partial'+ext)
        try:
            with self.session_directory() as temp:
                temp=Path(temp);timeline=temp/'timeline.wav';report=[]
                reference=temp/'reference.wav'
                if self.clone:
                    from voice_clone import CloneSession
                    start=float(self.clone.get('start',0));length=float(self.clone.get('duration',6))
                    if not math.isfinite(start+length) or start<0 or not 1<=length<=30:raise ValueError('Sampel cloning harus 1–30 detik, waktu awal valid.')
                    external=self.clone.get('reference','')
                    if external:
                        ref_info=probe(ff,external)
                        if not ref_info['has_audio'] or start+length>ref_info['duration']+.05:raise ValueError('Rentang sampel di luar durasi referensi.')
                    elif not self.clone.get('per_cue') and start+length>duration+.05:raise ValueError('Rentang sampel di luar durasi video.')
                    if external or not self.clone.get('per_cue'):
                        self.run_command([ff,'-v','error','-y','-ss',str(start),'-i',external or self.source,'-t',str(length),'-map','0:a:0' if external else f'0:a:{self.audio_stream}','-vn','-ac','1','-ar','22050',str(reference)])
                    self.progress.emit('Memuat voice cloning lokal OpenVoice (CPU) …')
                    self.clone_session=CloneSession(self.clone['tools'],temp,self.cancelled,self.progress.emit)
                    # Session handles are closed by managed directory before cleanup.
                with wave.open(str(timeline),'wb') as out:
                    out.setnchannels(1);out.setsampwidth(2);out.setframerate(24000)
                    cursor=0
                    for index,c in enumerate(self.cues):
                        if self.cancelled():raise InterruptedError('Dibatalkan')
                        self.progress.emit(f'Dubbing {index+1}/{len(self.cues)} — {c.start:.2f} detik')
                        raw=temp/'raw.wav';aligned=temp/'aligned.wav';self.synthesize((c.target or c.source).strip(),raw,temp)
                        if self.clone_session:
                            if self.clone.get('per_cue') and not self.clone.get('reference'):
                                if c.end-c.start<1:raise ValueError(f'Cue {index+1} lebih pendek dari 1 detik untuk cloning per dialog. Pilih sampel referensi terpisah.')
                                self.run_command([ff,'-v','error','-y','-ss',str(c.start),'-i',self.source,'-t',str(min(30,c.end-c.start)),'-map',f'0:a:{self.audio_stream}','-vn','-ac','1','-ar','22050',str(reference)])
                            converted=temp/'converted.wav';self.progress.emit(f'Cloning karakter suara cue {index+1} …');self.clone_session.convert(raw,reference,converted)
                            # Normalize sample format; converter output may be floating-point WAV.
                            self.run_command([ff,'-v','error','-y','-i',str(converted),'-ac','1','-ar','24000','-c:a','pcm_s16le',str(raw)])
                        with wave.open(str(raw)) as w:spoken=w.getnframes()/w.getframerate()
                        slot=c.end-c.start;speed=max(1.,spoken/slot)
                        if speed>self.speed_limit+.01:raise ValueError(f'Cue {index+1} terlalu panjang ({spoken:.1f}s untuk {slot:.1f}s). Ringkas teks atau perpanjang waktunya; suara tidak dipotong.')
                        self.run_command([ff,'-v','error','-y','-i',str(raw),'-af',tempo(speed),'-ac','1','-ar','24000','-c:a','pcm_s16le',str(aligned)])
                        start=round(c.start*24000);end=round(c.end*24000)
                        remaining=max(0,start-cursor)
                        while remaining:chunk=min(remaining,24000);out.writeframesraw(b'\0\0'*chunk);remaining-=chunk
                        with wave.open(str(aligned)) as w:data=w.readframes(w.getnframes())
                        # Rounding correction only (<25ms), never truncate whole words.
                        if len(data)//2>end-start+600:raise ValueError(f'Cue {index+1} belum muat setelah sinkronisasi. Periksa teks.')
                        frames=min(len(data)//2,end-start);out.writeframesraw(data[:frames*2]);cursor=start+frames
                        report.append({'cue':index+1,'start':c.start,'end':c.end,'speech_duration':spoken,'tempo':speed})
                    remaining=max(0,round(duration*24000)-cursor)
                    while remaining:chunk=min(remaining,24000);out.writeframesraw(b'\0\0'*chunk);remaining-=chunk
                inputs=['-i',self.source,'-i',str(timeline)];filters=f'[1:a]volume={self.gain},apad,atrim=duration={duration}[dub];';label='dub'
                if self.mode=='voiceover':
                    filters+=f'[0:a:{self.audio_stream}]volume={self.original_volume},aresample=24000[bg];[bg][dub]amix=inputs=2:normalize=0:duration=longest,alimiter=limit=0.95:level=0[mix];';label='mix'
                elif self.mode=='instrumental':
                    inputs+=['-i',self.background];filters+=f'[2:a:0]volume={self.original_volume},apad,atrim=duration={duration}[bg];[bg][dub]amix=inputs=2:normalize=0:duration=longest,alimiter=limit=0.95:level=0[mix];';label='mix'
                else:filters+='[dub]alimiter=limit=0.95:level=0[mix];';label='mix'
                args=[ff,'-v','error','-y',*inputs,'-filter_complex',filters.rstrip(';')]
                if ext in ('.mp4','.mkv'):args+=['-map','0:v:0','-c:v','libx264','-preset','veryfast','-crf','20','-pix_fmt','yuv420p']
                args+=['-map',f'[{label}]']
                if self.mode=='dual':args+=['-map',f'0:a:{self.audio_stream}','-metadata:s:a:1','title=Original']
                args+=['-c:a','pcm_s16le' if ext=='.wav' else 'aac','-metadata:s:a:0','title=Cyber80 Dubbing','-metadata:s:a:0',f'language={self.language}','-t',str(duration)]
                if ext in ('.mp4','.m4a'):args+=['-movflags','+faststart']
                self.progress.emit('Menggabungkan dubbing dan media …');self.run_command(args+[str(partial)])
                if self.cancelled():raise InterruptedError('Dibatalkan')
                # Exclusive link publishes completed output without overwriting another job's file.
                try:os.link(partial,target)
                except FileExistsError:raise ValueError('Nama hasil sudah dipakai proses lain. Pilih nama baru.')
                except OSError:
                    # FAT/exFAT do not support hard links. Exclusive creation still protects existing files.
                    created=False
                    try:
                        with target.open('xb') as dest,partial.open('rb') as src:
                            created=True
                            while True:
                                if self.cancelled():raise InterruptedError('Dibatalkan')
                                block=src.read(4*1024*1024)
                                if not block:break
                                dest.write(block)
                    except Exception:
                        if created:target.unlink(missing_ok=True)
                        raise
                partial.unlink()
                if self.clone_session:self.clone_session.close();self.clone_session=None
                return str(target)
        finally:
            if self.clone_session:self.clone_session.close();self.clone_session=None
            partial.unlink(missing_ok=True)
    def run(self):
        try:self.completed.emit(self.execute())
        except Exception as exc:
            message=str(exc)
            if self.key:message=message.replace(self.key,'[KEY DISEMBUNYIKAN]')
            self.failed.emit(re.sub(r'https?://\S+','[layanan]',message)[:2000])
