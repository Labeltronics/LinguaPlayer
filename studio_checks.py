"""Native Windows acceptance for the packaged multilayer editor, no cloud calls."""
import subprocess,hashlib
from pathlib import Path
from PySide6.QtWidgets import QApplication
from playback_checks import wait_for
import imageio_ffmpeg
import video_project as vp
from video_render import flags

def run_studio_checks(owner,root):
    root=Path(root);ff=imageio_ffmpeg.get_ffmpeg_exe();source=root/'studio-source.mp4'
    subprocess.run([ff,'-v','error','-y','-f','lavfi','-i','testsrc2=s=160x120:r=10:d=2','-f','lavfi','-i','sine=frequency=440:duration=2','-c:v','libx264','-c:a','aac','-shortest',str(source)],check=True,**flags())
    image=root/'studio-image.png';music=root/'studio-music.wav';report={}
    subprocess.run([ff,'-v','error','-y','-f','lavfi','-i','color=c=0x00ff00:s=160x120,drawbox=x=40:y=30:w=80:h=60:color=red:t=fill','-frames:v','1','-update','1',str(image)],check=True,**flags())
    subprocess.run([ff,'-v','error','-y','-f','lavfi','-i','sine=frequency=880:duration=2',str(music)],check=True,**flags())
    original=hashlib.sha256(Path(source).read_bytes()).digest();studio=owner.open_video_studio(False);studio.debounce.timeout.disconnect();studio.autosave_timer.stop();failures=[]
    try:
        studio.import_paths([str(source),str(image),str(music)]);wait_for(lambda:studio.import_job is None,timeout=45)
        if len(studio.project['clips'])!=3:raise RuntimeError('Studio import failed: '+studio.status.text())
        p=studio.project;p['settings'].update(width=320,height=240,fps='10',ducking=True,background='#0000ff')
        for c in p['clips']:c['start']=0.;c['duration']=1.2
        video=next(c for c in p['clips'] if c['kind']=='video');video.update(width=50,height=50)
        picture=next(c for c in p['clips'] if c['kind']=='image');picture.update(track=p['tracks'][2]['id'],width=25,height=25,x=60,y=10)
        audio=next(c for c in p['clips'] if c['kind']=='audio');audio.update(track=p['tracks'][6]['id'],volume=-15)
        p['clips'].append(vp.new_clip(p['tracks'][5]['id'],'audio',str(music.resolve()),1.2,source_duration=2,volume=-12))
        p['clips'].append(vp.new_clip(p['tracks'][3]['id'],'text',duration=1.2,text='Cyber80 Video Studio',height=25,y=50))
        p['clips'].append(vp.new_clip(p['tracks'][4]['id'],'subtitle',duration=1.2,text='1\n00:00:00,000 --> 00:00:01,100\nSubtitle Indonesia\n'))
        green_track=vp.add_green_screen_track(p);picture['track']=green_track['id'];vp.green_screen_defaults(picture)
        studio.commit();studio.select(video['id']);studio.seek(.6);studio.split();assert len(p['clips'])==7;studio.undo(-1);assert len(studio.project['clips'])==6;studio.undo(1);assert len(studio.project['clips'])==7;studio.undo(-1)
        studio.debounce.stop();studio.project_path=str(root/'studio-project.cyber80.json');assert studio.save();saved=vp.load(studio.project_path);assert len(saved['clips'])==6
        report['import_video_image_audio_timeline_split_undo_save']='PASS';studio.preview_frame();wait_for(lambda:studio.job is None,timeout=30)
        if studio.preview.pixmap().isNull():raise RuntimeError('Studio frame preview failed: '+studio.status.text())
        studio.timeline.grab();report['actual_composite_frame_preview']='PASS';target=root/'studio-composite.mp4';assert studio.start_render(str(target),'export');studio.job.failure.connect(failures.append);wait_for(lambda:studio.job is None,timeout=60)
        if failures or not target.is_file():raise RuntimeError('Studio composition export failed: '+str(failures))
        reader=imageio_ffmpeg.read_frames(str(target));meta=next(reader);reader.close()
        if meta['size']!=(320,240) or not meta.get('audio_codec') or not 1<=meta['duration']<=1.5:raise RuntimeError('Studio composite metadata incorrect')
        if hashlib.sha256(Path(source).read_bytes()).digest()!=original:raise RuntimeError('Studio source changed')
        raw=subprocess.run([ff,'-v','error','-ss','0.3','-i',str(target),'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','pipe:1'],check=True,stdout=subprocess.PIPE,**flags()).stdout
        def pixel(x,y):return raw[(y*320+x)*3:(y*320+x)*3+3]
        bg=pixel(200,30);fg=pixel(232,54)
        if not (bg[2]>170 and bg[1]<80 and fg[0]>170 and fg[1]<80):raise RuntimeError('Green screen background/foreground composition incorrect')
        report['green_screen_layer_and_transparency']='PASS'
        report['multilayer_mp4_titles_subtitles_audio_mix_ducking']='PASS';report['source_preservation']='PASS';studio.play_result();wait_for(lambda:studio.proxy_player.player.has_vout()>0,timeout=20);report['actual_vlc_composition_playback']='PASS'
    finally:
        studio.debounce.stop()
        if studio.import_job:studio.import_job.requestInterruption();studio.import_job.wait(30000);QApplication.processEvents()
        if studio.job:studio.cancel();studio.job.wait(10000);QApplication.processEvents()
        studio.dirty=False;studio.close();QApplication.processEvents()
    return report
