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
    report={'formats':{},'pip':{},'advanced':{},'modern':{}}
    from themes import THEMES
    for name in THEMES:window.select_theme(name)
    window.select_theme('Cyber Neon');window.set_simple_mode(True)
    if not window.advanced_toolbar.isHidden():raise RuntimeError('Simple mode toolbar not hidden')
    window.set_simple_mode(False);report['modern']['themes_and_simple_mode']='PASS'
    if window.ai_configuration()['chunk_seconds']!=30:raise RuntimeError('AI chunk default incorrect')
    report['modern']['ai_policies_and_source_track']='PASS'
    window.auto_next_box.setChecked(False)
    flags={'creationflags':subprocess.CREATE_NO_WINDOW} if __import__('os').name=='nt' else {}
    with tempfile.TemporaryDirectory(prefix='lingua-playback-') as tmp:
        tmp=str(Path(tmp).resolve())
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
        # A longer clip makes the actual seek and simultaneous playback checks meaningful.
        long_clip=Path(tmp)/'Long sample.mp4'
        subprocess.run([ff,'-v','error','-y','-f','lavfi','-i','testsrc2=size=176x144:rate=6:duration=75',
                        '-c:v','libx264','-preset','ultrafast','-pix_fmt','yuv420p',str(long_clip)],check=True,
                       stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,**flags)
        window.open_path(str(long_clip));wait_for(lambda:picture_stats(window)['displayed']>=3)
        window.player.set_time(10000);wait_for(lambda:window.player.get_time()>=9500)
        window.seek_relative(60);wait_for(lambda:window.player.get_time()>=69000)
        window.seek_relative(-60);wait_for(lambda:8000<=window.player.get_time()<=13000)
        report['advanced']['seek_60_seconds']='PASS'
        window.speed_box.setValue(1.5)
        if abs(window.player.get_rate()-1.5)>.05:raise RuntimeError('Speed setting did not apply')
        report['advanced']['speed_1_5']='PASS'
        other=window.open_second_player();other.auto_next_box.setChecked(False)
        try:
            other.open_path(str(long_clip))
            wait_for(lambda:other.player.get_time()>100 and window.player.get_state()==vlc.State.Playing)
            first=window.player.get_time();second=other.player.get_time()
            wait_for(lambda:window.player.get_time()>first+200 and other.player.get_time()>second+200)
            if window.player==other.player:raise RuntimeError('Players are not independent')
            report['advanced']['two_simultaneous_videos']='PASS'
        finally:other.close();QApplication.processEvents()
        window.stereo_check.setChecked(True)
        wait_for(lambda:window.memory_video is not None and window.memory_video.frame_count>=3 and window.video.image is not None)
        window.red_shift.setValue(-8);window.blue_shift.setValue(8);window.render_stereo(True)
        report['advanced']['real_anaglyph_frames']='PASS'
        count=window.memory_video.frame_count
        window.toggle_pip()
        wait_for(lambda:window.pip is not None and window.pending_seek is None and window.memory_video.frame_count>count+2)
        window.leave_pip()
        wait_for(lambda:window.pip is None and window.pending_seek is None)
        report['advanced']['anaglyph_pip']='PASS'
        window.stereo_check.setChecked(False)
        wait_for(lambda:window.memory_video is None and picture_stats(window)['displayed']>=3)
        report['advanced']['restore_native_video']='PASS'
        window.toggle_fullscreen();QApplication.processEvents()
        if window.pip is None or not window.pip.isFullScreen():raise RuntimeError('Fullscreen did not activate')
        window.toggle_fullscreen();wait_for(lambda:window.pip is None and window.pending_seek is None)
        report['advanced']['fullscreen']='PASS'
        window.player.stop();window.speed_box.setValue(1)
        window.playlist_widget.clear()
        a=str(Path(tmp)/'Uji video dengan spasi.mp4');b=str(Path(tmp)/'Uji video dengan spasi.webm')
        window.add_paths([a,b]);window.repeat_box.setCurrentIndex(0);window.shuffle_box.setChecked(False);window.auto_next_box.setChecked(True)
        window.open_path(a)
        wait_for(lambda:window.path==b and picture_stats(window)['displayed']>=2,timeout=12)
        report['advanced']['playlist_auto_next']='PASS'
        window.auto_next_box.setChecked(False);window.player.stop()
        report['audio_formats']={}
        audio_formats=[('wav','pcm_s16le','wav'),('mp3','libmp3lame','mp3'),('aac','aac','aac'),('flac','flac','flac'),('ogg','libvorbis','ogg'),('opus','libopus','opus'),('m4a-aac','aac','m4a'),('alac','alac','m4a'),('wma','wmav2','wma'),('ac3','ac3','ac3'),('eac3','eac3','eac3'),('aiff','pcm_s16be','aiff')]
        for name,codec,suffix in audio_formats:
            clip=Path(tmp)/('Audio '+name+'.'+suffix)
            subprocess.run([ff,'-v','error','-y','-f','lavfi','-i','sine=frequency=440:duration=3','-ac','2','-ar','48000' if codec=='libopus' else '44100','-c:a',codec,str(clip)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,**flags)
            window.open_path(str(clip));wait_for(lambda:picture_stats(window)['audio_decoded']>2)
            report['audio_formats'][name]={'status':'PASS','decoded_audio':picture_stats(window)['audio_decoded']};window.player.stop()
        window.open_path(str(long_clip));wait_for(lambda:picture_stats(window)['displayed']>=3)
        window.audio_panel.preset.setCurrentText('Film — aksi');window.audio_panel.apply()
        if window.audio_panel.native is None:raise RuntimeError('Native equalizer handle missing')
        for i,gain in enumerate([5,4,1,-1,0,2,3,2,1,0]):
            if abs(window.audio_panel.native.get_amp_at_index(i)-gain)>.01:raise RuntimeError('EQ band value mismatch')
        report['advanced']['equalizer_10_bands']='PASS'
        window.toggle_pip();wait_for(lambda:window.pip is not None and window.pending_seek is None)
        window.leave_pip();wait_for(lambda:window.pip is None and window.pending_seek is None)
        if not window.audio_panel.enabled.isChecked():raise RuntimeError('EQ settings lost')
        report['advanced']['equalizer_pip_persistence']='PASS'
        window.player.set_time(10000);wait_for(lambda:window.player.get_time()>=9800)
        window.mark_ab();window.player.set_time(12000);wait_for(lambda:window.player.get_time()>=11800);window.mark_ab()
        window.player.set_time(window.ab_b+100);wait_for(lambda:window.player.get_time()<window.ab_b)
        window.mark_ab();report['advanced']['ab_repeat']='PASS'
        window.save_film_profile()
        if 'profile' not in window.media_store.get(window.path):raise RuntimeError('Media profile missing')
        report['advanced']['media_profile']='PASS'
        snapshot=Path(tmp)/'snapshot.png';window.capture_frame(str(snapshot));wait_for(lambda:snapshot.is_file() and snapshot.stat().st_size>0)
        report['advanced']['snapshot']='PASS'
        window.sharpness.setValue(.1);wait_for(lambda:window.pending_seek is None and picture_stats(window)['displayed']>=3)
        report['advanced']['native_sharpen']='PASS'
        window.sharpness.setValue(0);window.player.stop()
        window.select_rotation('90');window.player.play();wait_for(lambda:window.pending_seek is None and picture_stats(window)['displayed']>=3)
        report['modern']['native_rotation_playback']='PASS';window.select_rotation('off');window.player.stop()
        audio_source=str(Path(tmp)/'Audio wav.wav')
        window.open_path(audio_source);wait_for(lambda:picture_stats(window)['audio_decoded']>2)
        for mode in ('night','normalize'):
            window.select_dsp(mode);wait_for(lambda:window.pending_seek is None and picture_stats(window)['audio_decoded']>2);report['modern']['native_audio_'+mode]='PASS'
        window.select_dsp('off');window.player.stop()
        tiny=Path(tmp)/'Upscale input.mp4'
        subprocess.run([ff,'-v','error','-y','-f','lavfi','-i','color=blue:size=176x144:rate=1:duration=1','-frames:v','1','-c:v','libx264','-pix_fmt','yuv420p',str(tiny)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,**flags)
        from export_tools import ExportJob,RESOLUTIONS,export_capabilities
        report['upscale_cpu']={}
        for resolution,expected in RESOLUTIONS.items():
            target=Path(tmp)/(resolution.replace(' ','_')+'.mp4');job=ExportJob(str(tiny),str(target),resolution,'CPU',.1,1);failures=[];success=[]
            job.failure.connect(failures.append);job.success.connect(success.append);job.run()
            if failures or not success:raise RuntimeError('CPU upscale failed: '+str(failures))
            reader=imageio_ffmpeg.read_frames(str(target));size=next(reader)['size'];reader.close()
            if tuple(size)!=expected:raise RuntimeError('Upscale resolution mismatch')
            report['upscale_cpu'][resolution]={'status':'PASS','size':list(size)}
        report['gpu_export']={'physical_gpu_test':'NOT_PERFORMED_ON_CI','compiled_support':export_capabilities(ff)}
        from extended_checks import run_extended_checks
        report['extended']=run_extended_checks(window,Path(tmp),long_clip)
    return report
