import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import unittest,tempfile
from pathlib import Path
from unittest.mock import patch,MagicMock
import numpy as np
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt,QPoint,QPointF
from PySide6.QtGui import QWheelEvent
import app
from test_advanced_player import fake_engine
from cut_editor import trim_range
from depth_stereo import stereo_pair,pack_stereo,unpack_stereo,DepthModel,DEFAULT_MODEL,render
q=QApplication.instance() or QApplication([])
class ControlsTests(unittest.TestCase):
    @patch.object(app.vlc,'Instance',side_effect=fake_engine)
    def test_scroll_steps_settings_and_speed_limits(self,factory):
        w=app.Window();w.path='sample.mp4'
        try:
            self.assertEqual((w.speed_box.minimum(),w.speed_box.maximum()),(.1,10));w.speed_box.setValue(10);w.player.set_rate.assert_called_with(10)
            w.handle_video_wheel(120);w.player.set_time.assert_called_with(15000);w.handle_video_wheel(-120);w.player.set_time.assert_called_with(5000)
            with patch('advanced_addons.QInputDialog.getInt',return_value=(17,True)):w.set_wheel_seconds()
            w.player.set_time.reset_mock();w.handle_video_wheel(60);w.player.set_time.assert_not_called();w.handle_video_wheel(60);w.player.set_time.assert_called_with(27000)
            self.assertEqual((w.zoom_box.minimum(),w.zoom_box.maximum()),(.1,1000))
            from core import Cue
            w.fill([Cue(0,1,'Hello','Halo','en')]);self.assertIn('en',w.detected.text());w.fill([]);self.assertIn('belum dianalisis',w.detected.text());w.fill([Cue(0,1,'Subtitle offline')]);self.assertIn('tidak tersedia',w.detected.text())
        finally:w.close()
    @patch.object(app.vlc,'Instance',side_effect=fake_engine)
    def test_zoom_canvas_and_reset_are_reversible(self,factory):
        w=app.Window()
        try:
            w.zoom_box.setValue(1000);self.assertTrue(w.canvas_active());self.assertEqual(w.video.zoom_factor,10);self.assertIsNotNone(w.memory_video)
            w.zoom_box.setValue(.1);self.assertEqual(w.video.zoom_factor,.001)
            w.zoom_box.setValue(100);self.assertFalse(w.canvas_active());self.assertIsNone(w.memory_video)
        finally:w.close()
    def test_trim_boundaries(self):
        self.assertEqual(trim_range(1,2,3),(1,2))
        for values in ((2,1,3),(-1,2,3),(0,4,3),(0,float('nan'),3)):
            with self.assertRaises(ValueError):trim_range(*values)
    @patch.object(app.vlc,'Instance',side_effect=fake_engine)
    def test_resume_uses_current_cookies_not_deleted_snapshot(self,factory):
        w=app.Window();manager=w.get_download_manager()
        try:
            with tempfile.TemporaryDirectory() as d:
                with patch.object(manager,'pump'):
                    record=manager.add('https://example.test/media.mp4','media.mp4',headers={'Cookie':'expired=session','Authorization':'fixture'},target=Path(d)/'media.mp4')
                manager.providers[record['id']]=lambda url:{'User-Agent':'fixture'}
                with patch('download_manager.DownloadJob') as job:
                    manager.start(record);headers=job.call_args.args[2];self.assertNotIn('Cookie',headers);self.assertEqual(headers['Authorization'],'fixture')
                manager.jobs.clear()
        finally:manager.jobs.clear();w.close();q.processEvents()
    @patch.object(app.vlc,'Instance',side_effect=fake_engine)
    def test_snapshot_fallback_and_source_protection(self,factory):
        import subprocess,time,imageio_ffmpeg
        w=app.Window()
        try:
            with tempfile.TemporaryDirectory() as d:
                source=Path(d)/'source.mp4';target=Path(d)/'frame.png';flags={'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {}
                subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-v','error','-y','-f','lavfi','-i','color=blue:size=160x120:duration=1','-c:v','libx264',str(source)],check=True,**flags)
                w.path=str(source);w.player.get_time.return_value=0;w.player.video_take_snapshot.return_value=-1
                with self.assertRaises(ValueError):w.capture_frame(source)
                w.capture_frame(target);deadline=time.monotonic()+10
                while w.snapshot_job is not None and time.monotonic()<deadline:q.processEvents();time.sleep(.01)
                self.assertTrue(target.is_file());self.assertTrue(source.is_file())
                target2=Path(d)/'frame2.png';w.player.video_take_snapshot.return_value=0;w.capture_frame(target2);deadline=time.monotonic()+10
                while (not target2.is_file() or w.snapshot_job is not None) and time.monotonic()<deadline:q.processEvents();time.sleep(.01)
                self.assertTrue(target2.is_file())
        finally:
            if w.snapshot_job:w.snapshot_job.cancel();w.snapshot_job.wait(2000);q.processEvents()
            w.close();q.processEvents()
class StereoTVTests(unittest.TestCase):
    def test_depth_varies_by_object_not_global_shift(self):
        image=np.zeros((32,64,4),np.uint8);image[:,:,0]=np.arange(64);image[:,:,1]=np.arange(64);image[:,:,2]=np.arange(64);image[:,:,3]=255
        depth=np.zeros((32,64),np.float32);depth[:,32:]=1
        left,right=stereo_pair(image,depth,6,.5);self.assertFalse(np.array_equal(left,right));self.assertGreater(int(left[0,10,0]),int(right[0,10,0]));self.assertLess(int(left[0,50,0]),int(right[0,50,0]))
        flat=stereo_pair(image,depth,0,.5);self.assertTrue(np.array_equal(flat[0],image));self.assertTrue(np.array_equal(flat[1],image))
    def test_pack_native_stereo_all_layouts(self):
        left=np.zeros((20,40,4),np.uint8);right=left.copy();left[:,:,2]=255;right[:,:,0]=255
        for output in ('SBS half','SBS full','TB half','TB full','Interlaced baris','Interlaced kolom','Checkerboard','Mata kiri','Mata kanan'):
            result=pack_stereo(left,right,output);self.assertEqual(result.shape[2],4)
        sbs=pack_stereo(left,right,'SBS full');a,b=unpack_stereo(sbs,'sbs-full');self.assertTrue(np.array_equal(a,left));self.assertTrue(np.array_equal(b,right))
    @unittest.skipUnless(DEFAULT_MODEL.is_file(),'model not staged')
    def test_actual_midas_cpu_inference(self):
        model=DepthModel();image=np.zeros((96,160,4),np.uint8);yy,xx=np.indices((96,160));image[:,:,0]=(xx*3)%256;image[:,:,1]=(yy*4)%256;image[:,:,2]=100;image[:,:,3]=255
        depth=model.infer(image);self.assertEqual(depth.shape,(256,256));self.assertTrue(np.isfinite(depth).all());self.assertGreater(float(depth.max()-depth.min()),.5)
        settings={'input':'2d-ai','output':'SBS half','strength':3,'convergence':.5,'swap':False,'shift':0,'smooth':.3};result,_=render(image,settings,model);self.assertEqual(result.shape,image.shape)
