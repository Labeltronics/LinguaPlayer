"""Packaged Windows playback checks using synthetic clips, never user videos."""
import json, subprocess, tempfile, time
from pathlib import Path
import vlc, imageio_ffmpeg
from PySide6.QtWidgets import QApplication

def wait_for(predicate,timeout=10):
    until=time.monotonic()+timeout
    while time.monotonic()<until:
        QApplication.processEvents()
        if predicate():return
        time.sleep(.03)
    raise RuntimeError('Playback check timed out')

def picture_stats(window):
    stats=vlc.MediaStats()
    media=window.player.get_media()
    if media:media.get_stats(stats)
    return {'decoded':stats.decoded_video,'displayed':stats.displayed_pictures,
            'audio_decoded':stats.decoded_audio,'time_ms':window.player.get_time()}

def run_playback_checks(window):
    ff=imageio_ffmpeg.get_ffmpeg_exe()
    formats=[('mp4','libx264','aac'),('flv','flv1','libmp3lame'),('ts','mpeg2video','mp2'),
             ('avi','mpeg4','libmp3lame'),('3gp','h263','aac'),('mkv','libx264','aac'),
             ('mov','libx264','aac'),('webm','libvpx-vp9','libopus')]
    report={'formats':{},'pip':{}}
    flags={'creationflags':subprocess.CREATE_NO_WINDOW} if __import__('os').name=='nt' else {}
    with tempfile.TemporaryDirectory(prefix='lingua-playback-') as tmp:
        for suffix,vcodec,acodec in formats:
            clip=Path(tmp)/('Uji video dengan spasi.'+suffix)
            args=[ff,'-v','error','-y','-f','lavfi','-i','testsrc2=size=176x144:rate=12:duration=3',
                  '-f','lavfi','-i','sine=frequency=440:duration=3','-c:v',vcodec,'-pix_fmt','yuv420p',
                  '-c:a',acodec,'-ar','48000' if suffix=='webm' else '44100','-ac','1','-shortest',str(clip)]
            subprocess.run(args,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,**flags)
            window.open_path(str(clip))
            wait_for(lambda:picture_stats(window)['displayed']>=3)
            stats=picture_stats(window)
            if stats['decoded']<1 or window.player.has_vout()<1:raise RuntimeError('Video output missing: '+suffix)
            report['formats'][suffix]={'status':'PASS',**stats}
            window.player.stop()
        # Rebind the real native video window while media is playing.
        window.open_path(str(Path(tmp)/'Uji video dengan spasi.mp4'))
        wait_for(lambda:picture_stats(window)['displayed']>=3)
        window.toggle_pip()
        wait_for(lambda:window.pip is not None and window.pending_seek is None and picture_stats(window)['displayed']>=3)
        if window.player.get_hwnd()!=int(window.video.winId()):raise RuntimeError('PiP HWND not bound')
        report['pip']['native_window']='PASS'
        window.player.set_pause(1)
        wait_for(lambda:window.player.get_state()==vlc.State.Paused)
        window.leave_pip()
        wait_for(lambda:window.pip is None and window.pending_seek is None and window.player.get_state()==vlc.State.Paused)
        report['pip']['return_preserves_pause']='PASS'
        window.play()
        wait_for(lambda:window.player.get_state()==vlc.State.Playing and picture_stats(window)['displayed']>=3)
        report['pip']['resume']='PASS'
        window.player.stop()
    return report
