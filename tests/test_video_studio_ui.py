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

    def test_green_screen_layer_import_and_properties(self):
        from PySide6.QtWidgets import QListWidgetItem
        from PySide6.QtGui import QImage,QColor
        with tempfile.TemporaryDirectory() as d:
            owner=QWidget();owner.log_path=Path(d)/'log';owner.window_number=99;owner.storage_enabled=False;owner.private_session=False;owner.cues=[];editor=VideoStudio(owner);editor.debounce.timeout.disconnect()
            try:
                editor.add_green_screen();target=editor.selected_track;self.assertEqual(v.track(editor.project,target)['preset'],'greenscreen')
                file=Path(d)/'actor.png';image=QImage(16,16,QImage.Format_RGB32);image.fill(QColor('#00ff00'));image.save(str(file));item=QListWidgetItem('actor');item.setData(Qt.UserRole,{'path':str(file.resolve()),'kind':'image','duration':1.,'has_audio':False,'name':'actor'})
                editor.add_asset(item);clip=editor.current();self.assertEqual(clip['track'],target);self.assertTrue(clip['chroma']);self.assertEqual(editor.chroma_color.text(),'#00ff00')
                editor.chroma_color.setText('#0000ff');editor.fields['chroma_similarity'].setValue(.2);editor.apply_properties();self.assertEqual(editor.current()['chroma_color'],'#0000ff');editor.green_screen_preset();self.assertEqual(editor.current()['chroma_color'],'#00ff00')
            finally:editor.debounce.stop();editor.dirty=False;editor.close();owner.close();q.processEvents()

    def test_editable_opening_and_ending_templates(self):
        with tempfile.TemporaryDirectory() as d:
            owner=QWidget();owner.log_path=Path(d)/'log';owner.window_number=99;owner.storage_enabled=False;owner.private_session=False;owner.cues=[];editor=VideoStudio(owner);editor.debounce.timeout.disconnect()
            try:
                editor.apply_template({'preset':'opening','title':'Pembukaan','duration':1,'placement':'prepend'});editor.apply_template({'preset':'ending','title':'Penutup','duration':1,'placement':'append'})
                self.assertEqual(v.duration(editor.project),2);self.assertTrue(any(c['text']=='Pembukaan' for c in editor.project['clips']));editor.undo(-1);self.assertEqual(v.duration(editor.project),1)
            finally:editor.debounce.stop();editor.dirty=False;editor.close();owner.close();q.processEvents()
