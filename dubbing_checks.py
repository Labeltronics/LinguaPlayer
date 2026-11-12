"""Real FFmpeg alignment/export checks with deterministic synthetic speech fixture.
Network TTS is deliberately not called in CI; no API key or private media needed.
"""
import hashlib, math, struct, subprocess, wave
from pathlib import Path
import imageio_ffmpeg
from core import Cue
from dubbing import DubbingJob,write_pcm,checked_cues,decode_audio,lrc,protected_target
from video_render import flags

class FixtureDubbing(DubbingJob):
    def synthesize(self,text,path,temp):
        if text=='TOO LONG':seconds=3
        else:seconds=.4
        pcm=b''.join(struct.pack('<h',int(2500*math.sin(i*2*math.pi*440/24000))) for i in range(round(seconds*24000)))
        write_pcm(path,pcm,24000)

def run_dubbing_checks(root):
    root=Path(root);root.mkdir(exist_ok=True);ff=imageio_ffmpeg.get_ffmpeg_exe();source=root/'original.mp4'
    subprocess.run([ff,'-v','error','-y','-f','lavfi','-i','color=c=blue:s=160x90:r=10:d=3','-f','lavfi','-i','sine=frequency=220:duration=3','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac','-shortest',str(source)],check=True,**flags())
    before=hashlib.sha256(source.read_bytes()).hexdigest();cues=[Cue(.5,1.,'Halo Indonesia'),Cue(1.7,2.2,'Selamat datang')]
    target=root/'dub.wav';job=FixtureDubbing(source,target,cues,mode='replace');assert job.execute()==str(target.resolve())
    with wave.open(str(target)) as w:
        rate=w.getframerate();samples=struct.unpack('<'+'h'*w.getnframes(),w.readframes(w.getnframes()));assert abs(len(samples)/rate-3)<.05
    rms=lambda a,b:math.sqrt(sum(v*v for v in samples[round(a*rate):round(b*rate)])/max(1,round((b-a)*rate)))
    assert rms(.05,.4)<1 and rms(.55,.8)>500 and rms(1.15,1.5)<1 and rms(1.75,1.95)>500
    for mode,ext in [('voiceover','m4a'),('dual','mkv'),('replace','mp4')]:FixtureDubbing(source,root/(mode+'.'+ext),cues,mode=mode).execute()
    try:FixtureDubbing(source,root/'long.wav',[Cue(.2,.5,'TOO LONG')],mode='replace').execute();raise AssertionError('Long cue accepted')
    except ValueError as exc:assert 'terlalu panjang' in str(exc)
    assert not (root/'long.wav').exists()
    cancelled=FixtureDubbing(source,root/'cancel.wav',cues);cancelled.cancel()
    try:cancelled.execute();raise AssertionError('Cancelled job continued')
    except InterruptedError:pass
    assert not (root/'cancel.wav').exists() and not list(root.glob('*.partial.*'))
    assert hashlib.sha256(source.read_bytes()).hexdigest()==before
    return {'timestamp_alignment_and_silence':'PASS','wav_m4a_mp4_mkv_real_export':'PASS','long_dialogue_not_silently_cut':'PASS','cancel_no_partial_output':'PASS','original_unchanged':'PASS','gemini_live_tts':'NOT_RUN_NO_CI_CREDENTIAL','fixture':'synthetic tone, not a live TTS quality measurement'}
