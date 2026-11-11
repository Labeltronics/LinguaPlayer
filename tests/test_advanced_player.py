import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import tempfile,unittest,ctypes
from pathlib import Path
from unittest.mock import MagicMock,patch
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt,QEvent
from PySide6.QtGui import QKeyEvent
import app
from stereo import MemoryVideo
from core import Cue

q=QApplication.instance() or QApplication([])

def fake_engine(*args):
    engine=MagicMock();p=engine.media_player_new.return_value
    p.get_time.return_value=10000;p.get_length.return_value=120000;p.get_position.return_value=.1
    p.get_state.return_value=app.vlc.State.Stopped;p.play.return_value=0;p.set_rate.return_value=0
    return engine

class AdvancedTests(unittest.TestCase):
    @patch.object(app.vlc,'Instance',side_effect=fake_engine)
    def test_two_players_and_playlist_are_independent(self,factory):
        w=app.Window();other=None
        try:
            with tempfile.TemporaryDirectory() as d:
                a=Path(d)/'a.mp4';b=Path(d)/'b.mp4';a.touch();b.touch()
                w.open_path(str(a));other=w.open_second_player();other.open_path(str(b));q.processEvents()
                self.assertIsNot(w.player,other.player);self.assertEqual(w.path,str(a.resolve()));self.assertEqual(other.path,str(b.resolve()))
                self.assertEqual(w.playlist_widget.count(),1);self.assertEqual(other.playlist_widget.count(),1)
                self.assertTrue(other.mute_action.isChecked())
                self.assertIs(w.open_second_player(),other)
        finally:
            if other:other.close()
            w.close();q.processEvents()
    @patch.object(app.vlc,'Instance',side_effect=fake_engine)
    def test_arrow_keys_seek_exact_intervals(self,factory):
        w=app.Window();w.path='example.mp4'
        try:
            with patch.object(QApplication,'activeWindow',return_value=w),patch.object(QApplication,'focusWidget',return_value=None):
                for key,target in [(Qt.Key_Right,15000),(Qt.Key_Left,5000),(Qt.Key_Up,70000),(Qt.Key_Down,0)]:
                    event=QKeyEvent(QEvent.KeyPress,key,Qt.NoModifier);self.assertTrue(w.eventFilter(w,event));w.player.set_time.assert_called_with(target)
        finally:w.close()
    @patch.object(app.vlc,'Instance',side_effect=fake_engine)
    def test_speed_and_playlist_order(self,factory):
        w=app.Window()
        try:
            w.speed_box.setValue(1.5);w.player.set_rate.assert_called_with(1.5)
            w.add_paths(['first.mp4','second.mp4']);w.playlist_widget.setCurrentRow(1);w.move_playlist(-1)
            self.assertEqual(w.playlist_widget.item(0).text(),'second.mp4')
        finally:w.close()
    @patch.object(app.vlc,'Instance',side_effect=fake_engine)
    def test_free_mode_never_sends_google_translate_key(self,factory):
        w=app.Window();w.path='example.mp4';w.key.setText('dummy');w.google.setText('not-to-be-used')
        fake_job=MagicMock();fake_job.isRunning.return_value=False
        try:
            with patch.object(app,'Job',return_value=fake_job) as job,patch.object(app.QMessageBox,'question',return_value=app.QMessageBox.Yes):
                w.process();self.assertEqual(job.call_args.args[4],'')
                self.assertEqual(job.call_args.args[2],'gemini-3.5-flash-lite')
        finally:w.close()
    def test_memory_format_callback_writes_native_buffer(self):
        capture=MemoryVideo(MagicMock());chroma=ctypes.create_string_buffer(b'I420',5)
        width=ctypes.c_uint(320);height=ctypes.c_uint(180);pitch=ctypes.c_uint();lines=ctypes.c_uint();opaque=ctypes.c_void_p()
        setup=capture.callbacks[3]
        self.assertEqual(setup(ctypes.byref(opaque),chroma,ctypes.byref(width),ctypes.byref(height),ctypes.byref(pitch),ctypes.byref(lines)),1)
        self.assertEqual(chroma.raw[:4],b'RV32');self.assertEqual(ctypes.addressof(capture.buffer)%32,0)
        planes=(ctypes.c_void_p*1)();capture.callbacks[0](None,planes)
        capture.buffer[0]=91;capture.callbacks[1](None,None,planes);capture.callbacks[2](None,None)
        frame,revision=capture.snapshot();self.assertEqual(frame[0,0,0],91);self.assertEqual(revision,1)

    @patch.object(app.vlc,'Instance',side_effect=fake_engine)
    def test_resume_skips_successful_silent_chunk(self,factory):
        w=app.Window();w.path='example.mp4';w.key.setText('dummy');w.resume_offset=10;w.cues=[]
        w.retry_context=(w.path,w.model.text(),'id','')
        fake_job=MagicMock();fake_job.isRunning.return_value=False
        try:
            with patch.object(app,'Job',return_value=fake_job) as job,patch.object(app.QMessageBox,'question',return_value=app.QMessageBox.Yes):
                w.process();self.assertEqual(job.call_args.kwargs['resume_from'],10)
        finally:w.close()
