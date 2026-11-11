import os,tempfile,unittest,time
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
from PySide6.QtWidgets import QApplication,QWidget
from PySide6.QtCore import Qt
from video_editor import VideoStudio
import video_project as v
q=QApplication.instance() or QApplication([])
class StudioUITests(unittest.TestCase):
    def test_edit_split_history_properties_save_and_preview(self):
        with tempfile.TemporaryDirectory() as d:
            owner=QWidget();owner.log_path=Path(d)/'playback.log';owner.window_number=99;owner.storage_enabled=False;owner.private_session=False;owner.cues=[]
            editor=VideoStudio(owner)
            try:
                editor.show();p=editor.project;p['settings'].update(width=320,height=240,fps='10');c=v.new_clip(p['tracks'][1]['id'],'color',duration=2,color='#ff0000');editor.insert(c);editor.debounce.stop();editor.seek(1);editor.debounce.stop();editor.split();editor.debounce.stop();self.assertEqual(len(editor.project['clips']),2);editor.undo(-1);editor.debounce.stop();self.assertEqual(len(editor.project['clips']),1)
                editor.select(c['id']);editor.fields['x'].setValue(25);editor.apply_properties();editor.debounce.stop();self.assertEqual(editor.current()['x'],25)
                editor.project_path=str(Path(d)/'project.cyber80.json');self.assertTrue(editor.save());self.assertTrue(Path(editor.project_path).is_file());editor.preview_frame();deadline=time.monotonic()+15
                while editor.job and time.monotonic()<deadline:q.processEvents();time.sleep(.01)
                self.assertIsNone(editor.job);self.assertIsNotNone(editor.preview.pixmap());self.assertFalse(editor.preview.pixmap().isNull());editor.timeline.grab();self.assertGreater(editor.timeline.width(),150)
            finally:
                editor.debounce.stop()
                if editor.job:editor.cancel();editor.job.wait(5000);q.processEvents()
                editor.dirty=False;editor.close();owner.close();q.processEvents()
