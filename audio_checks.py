"""Measure actual libVLC software PCM output; no physical speaker claim."""
import subprocess,array,ctypes,threading,math,time
from pathlib import Path
import vlc,imageio_ffmpeg
from playback_checks import wait_for,picture_stats
from video_render import flags
class PCMProbe:
    def __init__(self):
        self.lock=threading.Lock();self.energy=0.;self.count=0;self.discard=8820
        @vlc.CallbackDecorators.AudioPlayCb
        def play(opaque,samples,count,pts):
            data=array.array('h',ctypes.string_at(samples,count*4))
            with self.lock:
                skip=min(len(data),self.discard);self.discard-=skip;values=data[skip:];self.energy+=sum(float(v)*v for v in values);self.count+=len(values)
            time.sleep(min(count/44100,.02))
        self.play=play
        # Typed null callbacks keep ABI signatures valid while leaving optional hooks unset.
        self.pause=vlc.CallbackDecorators.AudioPauseCb();self.resume=vlc.CallbackDecorators.AudioResumeCb();self.flush=vlc.CallbackDecorators.AudioFlushCb();self.drain=vlc.CallbackDecorators.AudioDrainCb()
    def attach(self,player):
        player.audio_set_callbacks(self.play,self.pause,self.resume,self.flush,self.drain,None);player.audio_set_format('S16N',44100,2)
    def reset(self):
        with self.lock:self.energy=0.;self.count=0;self.discard=8820
    def read(self):
        with self.lock:return self.count,math.sqrt(self.energy/self.count) if self.count else 0.

def run_audio_boost_checks(window,root):
    root=Path(root);source=root/'quiet-source.mp4';ff=imageio_ffmpeg.get_ffmpeg_exe();report={};measurements={};capture=PCMProbe();phase='initialization'
    subprocess.run([ff,'-v','error','-y','-f','lavfi','-i','color=c=blue:s=160x120:r=10:d=12','-f','lavfi','-i','sine=frequency=440:duration=12','-af','volume=0.05','-ac','2','-c:v','libx264','-c:a','aac','-shortest',str(source)],check=True,**flags())
    reference=subprocess.run([ff,'-v','error','-ss','0.3','-i',str(source),'-map','0:a:0','-t','0.5','-f','s16le','-ac','2','-ar','44100','pipe:1'],stdout=subprocess.PIPE,check=True,**flags()).stdout;values=array.array('h',reference);reference_rms=math.sqrt(sum(float(v)*v for v in values)/len(values))
    window._selftest_audio_probe=capture;window.change_renderer(window.renderer.currentIndex())
    def ready():return window.pending_seek is None and not getattr(window,'audio_sync_deadline',0) and picture_stats(window)['audio_decoded']>0
    def measure():
        capture.reset();wait_for(lambda:capture.read()[0]>=44100,timeout=15);return capture.read()[1]
    try:
        phase='normal readiness';window.mute_action.setChecked(False);window.set_muted(False);window.audio_panel.boost_preset(0);window.open_path(str(source));wait_for(ready,timeout=15);phase='normal PCM';normal=measure();ratio=normal/reference_rms
        if not .8<=ratio<=1.25:raise RuntimeError(f'Normal PCM unexpectedly attenuated/amplified: ratio={ratio:.3f}, VLC={normal:.3f}, reference={reference_rms:.3f}')
        report['normal_pcm_matches_source_reference']='PASS';measurements.update(normal_rms=round(normal,3),reference_rms=round(reference_rms,3),normal_ratio=round(ratio,3))
        for gain in (12,20):
            phase='boost '+str(gain)+' readiness';window.audio_panel.boost_preset(gain);wait_for(ready,timeout=15)
            if window.audio_panel.native is None or abs(window.audio_panel.native.get_preamp()-gain)>.1:raise RuntimeError('Native boost gain not applied')
            level=measure();measurements['boost_'+str(gain)+'db_ratio']=round(level/normal,3)
            if level<normal*2:raise RuntimeError(f'Boost did not increase actual PCM: gain={gain}, level={level}, normal={normal}')
        read_volume=window.player.audio_get_volume();measurements['reported_native_volume']=read_volume
        max_level=level;phase='master 100 versus 200';window.volume.setValue(100);wait_for(ready,timeout=15);level_100=measure();measurements['master_200_vs_100_ratio']=round(max_level/level_100,3)
        if max_level<level_100*1.5:raise RuntimeError('Volume 200% did not increase PCM over 100%')
        window.volume.setValue(200);wait_for(ready,timeout=15)
        report['native_volume_200_and_preamp_20db']='PASS';report['actual_pcm_boost_increases_level']='PASS';phase='mute persistence';window.mute_action.setChecked(True);window.set_muted(True);window.change_renderer(window.renderer.currentIndex());wait_for(ready,timeout=15)
        muted_level=measure();measurements['muted_rms']=round(muted_level,3)
        if muted_level>normal*.1 or abs(window.audio_panel.native.get_preamp()-20)>.1:raise RuntimeError('Boost/mute lost on renderer restart')
        report['boost_and_mute_persist_on_renderer_restart']='PASS';window.mute_action.setChecked(False);window.set_muted(False);phase='reset normal';window.audio_panel.boost_preset(0);wait_for(ready,timeout=15)
        if window.volume.value()!=100 or window.audio_panel.state()['boost']!=0 or window.audio_panel.native is not None or window.audio_dsp!='off':raise RuntimeError('Unity/bypass reset failed')
        reset=measure();measurements['reset_ratio']=round(reset/reference_rms,3)
        if not .8<=reset/reference_rms<=1.25:raise RuntimeError('Reset did not restore original PCM level')
        report['reset_to_normal_unity_and_eq_dsp_bypass']='PASS';report['measurements']=measurements;report['physical_speaker_measurement']='NOT_PERFORMED_ON_CI'
    except Exception as exc:
        import json,time
        details={'phase':phase,'native_volume':window.player.audio_get_volume(),'native_mute':window.player.audio_get_mute(),'ui_volume':window.volume.value(),'sync_result':getattr(window,'last_audio_sync_result',None),'sync_remaining':round(getattr(window,'audio_sync_deadline',0)-time.monotonic(),2),'pending_seek':window.pending_seek,'samples':capture.read()[0],'state':str(window.player.get_state()),'measurements':measurements}
        raise RuntimeError('Audio acceptance '+json.dumps(details)+': '+str(exc)) from exc
    finally:
        window.stop();window._selftest_audio_probe=None;window.change_renderer(window.renderer.currentIndex())
    return report
