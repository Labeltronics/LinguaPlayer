"""Packaged native gain controls; no claim of physical speaker loudness measurement."""
import subprocess
from pathlib import Path
import imageio_ffmpeg
from playback_checks import wait_for,picture_stats
from video_render import flags

def run_audio_boost_checks(window,root):
    root=Path(root);source=root/'quiet-source.mp4';ff=imageio_ffmpeg.get_ffmpeg_exe();report={}
    subprocess.run([ff,'-v','error','-y','-f','lavfi','-i','color=c=blue:s=160x120:r=10:d=10','-f','lavfi','-i','sine=frequency=440:duration=10','-af','volume=0.01','-c:v','libx264','-c:a','aac','-shortest',str(source)],check=True,**flags())
    window.open_path(str(source));wait_for(lambda:picture_stats(window)['audio_decoded']>0)
    try:
        for gain in (12,20):
            window.audio_panel.boost_preset(gain);wait_for(lambda:window.pending_seek is None and picture_stats(window)['audio_decoded']>0)
            if window.audio_panel.native is None or abs(window.audio_panel.native.get_preamp()-gain)>.1:raise RuntimeError('Native boost gain not applied')
        if window.player.audio_get_volume()!=200:raise RuntimeError('Native volume 200% not applied')
        report['native_volume_200_and_preamp_20db']='PASS';window.mute_action.setChecked(True);window.set_muted(True);window.change_renderer(window.renderer.currentIndex());wait_for(lambda:window.pending_seek is None and picture_stats(window)['audio_decoded']>0)
        if not window.player.audio_get_mute() or abs(window.audio_panel.native.get_preamp()-20)>.1:raise RuntimeError('Boost/mute lost on renderer restart')
        report['boost_and_mute_persist_on_renderer_restart']='PASS';window.mute_action.setChecked(False);window.set_muted(False);window.audio_panel.boost_preset(0);wait_for(lambda:window.pending_seek is None and picture_stats(window)['audio_decoded']>0)
        if window.player.audio_get_volume()!=100 or window.audio_panel.state()['boost']!=0:raise RuntimeError('Boost reset failed')
        report['reset_to_normal']='PASS';report['physical_speaker_measurement']='NOT_PERFORMED_ON_CI'
    finally:window.stop()
    return report
