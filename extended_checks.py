"""Packaged EXE tests for visual trim, zoom, stereo AI, source-safe exports."""
import os,time,subprocess
from pathlib import Path
from unittest.mock import patch
import imageio_ffmpeg
from PySide6.QtWidgets import QApplication,QFileDialog
from playback_checks import wait_for,picture_stats
from depth_stereo import StereoExport
from media_jobs import UtilityJob

def run_extended_checks(window,root,long_clip):
    root=Path(root);report={};window.open_path(str(long_clip));wait_for(lambda:picture_stats(window)['displayed']>=3)
    for rate in (.1,10.):
        window.speed_box.setValue(rate)
        if abs(window.player.get_rate()-rate)>.05:raise RuntimeError('Extended speed not applied')
    window.speed_box.setValue(1);report['speed_0_1_to_10']='PASS'
    window.player.set_time(10000);wait_for(lambda:window.player.get_time()>=9800);window.handle_video_wheel(120);wait_for(lambda:window.player.get_time()>=14800);report['wheel_seek_5_seconds']='PASS'
    window.zoom_box.setValue(1000);wait_for(lambda:window.video.image is not None and window.pending_seek is None)
    window.zoom_quality.setCurrentIndex(2);wait_for(lambda:window.video.upscaled is not None and window.video.upscaled.height()>=2000)
    screenshot=root/'zoom-view.png'
    with patch.object(QFileDialog,'getSaveFileName',return_value=(str(screenshot),'')):window.capture_view()
    if not screenshot.is_file() or screenshot.stat().st_size==0:raise RuntimeError('Zoom capture missing')
    window.zoom_box.setValue(100);window.zoom_quality.setCurrentIndex(0);wait_for(lambda:window.memory_video is None and window.pending_seek is None);report['zoom_1000_4k_interpolation_capture_reset']='PASS'
    editor=window.open_cut_editor()
    try:
        wait_for(lambda:editor.initialized and editor.player.has_vout()>0);editor.start.setValue(1);editor.end.setValue(2);editor.add_clip();editor.preview_selection();wait_for(lambda:editor.player.get_time()>=900)
        target=root/'visual-trim.mp4'
        with patch.object(QFileDialog,'getSaveFileName',return_value=(str(target),'')):editor.export_selection()
        wait_for(lambda:editor.job is None and target.is_file())
        reader=imageio_ffmpeg.read_frames(str(target));meta=next(reader);reader.close()
        if not .7<=meta['duration']<=1.5:raise RuntimeError('Visual trim duration incorrect')
        report['visual_cut_preview_and_export']='PASS'
    finally:editor.close();QApplication.processEvents()
    window.cut_editor=None;window.open_path(str(long_clip));window.tv_enable.setChecked(True)
    wait_for(lambda:window.video.image is not None and window.tv_worker is not None and window.tv_worker.isRunning(),timeout=40)
    window.tv_output.setCurrentText('SBS full');wait_for(lambda:window.video.image is not None and window.video.image.width()>176,timeout=20)
    report['actual_midas_ai_stereo_preview']='PASS';window.tv_enable.setChecked(False);wait_for(lambda:not window.tv_worker.isRunning());wait_for(lambda:window.memory_video is None);window.stop()
    ff=imageio_ffmpeg.get_ffmpeg_exe();flags={'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {};source=root/'stereo-small.mp4'
    subprocess.run([ff,'-v','error','-y','-f','lavfi','-i','testsrc2=size=160x120:rate=1:duration=1','-f','lavfi','-i','sine=frequency=440:duration=1','-c:v','libx264','-c:a','aac','-shortest',str(source)],check=True,**flags)
    target=root/'stereo-export.mp4';settings=window.tv_settings();settings['output']='SBS full';settings['provider']='CPU';job=StereoExport(str(source),str(target),settings);failures=[];job.failure.connect(failures.append);job.run()
    if failures:raise RuntimeError('Stereo export failed: '+str(failures))
    reader=imageio_ffmpeg.read_frames(str(target));meta=next(reader);reader.close()
    if meta['size']!=(320,120) or not meta.get('audio_codec'):raise RuntimeError('Stereo export dimensions/audio incorrect')
    report['actual_midas_stereo_mp4_export']='PASS'
    for kind,target in [('Bakar subtitle MP4',root/'hard-sub.mp4'),('Video lirik MP4',root/'lyrics.mp4')]:
        failures=[];job=UtilityJob(str(source),str(target),kind,subtitle_text='1\n00:00:00,000 --> 00:00:00,900\nCyber80 test subtitle\n');job.failure.connect(failures.append);job.run()
        if failures or not target.is_file():raise RuntimeError(kind+' failed: '+str(failures))
    report['hard_subtitle_and_lyrics_exports']='PASS';return report
