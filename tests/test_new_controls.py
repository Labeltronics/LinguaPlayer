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
