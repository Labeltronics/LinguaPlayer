import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import unittest,tempfile,json
from pathlib import Path
from unittest.mock import patch,MagicMock
from PySide6.QtWidgets import QApplication
import app
from core import Cue
from themes import THEMES,validate_theme,stylesheet
from subtitle_tools import parse_vtt,vtt,synchronize,quality_report
from storage import MediaStore,media_key
from test_advanced_player import fake_engine
q=QApplication.instance() or QApplication([])
class ModernTests(unittest.TestCase):
    def test_theme_import_rejects_script_and_qss(self):
        for data in ({'background':'url(http://bad)'},{**THEMES['Light'],'accent':'red;script()'},dict(THEMES['Light'],script='x')):
            with self.assertRaises(ValueError):validate_theme(data)
        for theme in THEMES.values():self.assertIn(theme['accent'],stylesheet(theme))
    def test_vtt_and_sync_preserve_source(self):
        cues=parse_vtt('WEBVTT\n\n00:01.000 --> 00:03.000 align:start\n<b>Halo dunia</b>\n')
        self.assertEqual(cues[0].source,'Halo dunia');self.assertEqual(parse_vtt(vtt(cues)),cues)
        updated=synchronize(cues,1,2,3,6);self.assertEqual((updated[0].start,updated[0].end),(2,6));self.assertEqual(cues[0].start,1)
        with self.assertRaises(ValueError):synchronize(cues,2,1,1,2)
    def test_subtitle_qa_flags_readability_and_overlap(self):
        issues=quality_report([Cue(0,.2,'a'*60),Cue(.1,2,'next')]);self.assertEqual(len(issues),2);self.assertIn('tumpang tindih',issues[1]['issues'])
    def test_sqlite_migration_relink_and_process_updates(self):
        with tempfile.TemporaryDirectory() as d:
            a=Path(d)/'old.mp4';a.write_bytes(b'x');db=Path(d)/'library.json';key=media_key(a)
            db.write_text(json.dumps({key:{'path':str(a),'position':12345}}))
            first=MediaStore(db);second=MediaStore(db);self.assertEqual(first.get(a)['position'],12345)
            first.update(a,favorite=True);second.update(a,watched=True);self.assertTrue(first.get(a)['favorite']);self.assertTrue(first.get(a)['watched'])
            new=Path(d)/'new.mp4';a.rename(new);first.relink(a,new)
            self.assertEqual(first.get(new)['position'],12345);self.assertEqual(len(first.entries()),1)
            self.assertTrue(db.with_suffix('.sqlite3').exists())
    @patch.object(app.vlc,'Instance',side_effect=fake_engine)
    def test_theme_mode_and_private_store_isolation(self,factory):
        w=app.Window()
        try:
            w.select_theme('Light');self.assertEqual(w.theme_data,THEMES['Light']);w.set_simple_mode(True);self.assertTrue(w.advanced_toolbar.isHidden())
            self.assertEqual(w.ai_configuration()['chunk_seconds'],30);w.ai_stream.setValue(1);self.assertEqual(w.ai_configuration()['audio_stream'],1)
            old=w.media_store;w.set_private(True);self.assertIsNot(w.media_store,old);self.assertFalse(w.storage_enabled)
            w.processing=True;w.set_private(False);self.assertTrue(w.private_session);w.processing=False
        finally:w.close()
    @patch.object(app.vlc,'Instance',side_effect=fake_engine)
    def test_continue_mode_never_pauses_at_unavailable_subtitles(self,factory):
        w=app.Window()
        try:
            w.ai_policy.setCurrentIndex(w.ai_policy.findData('continue'));w.processing=True;w.want_play=True;w.coverage=0;w.player.get_time.return_value=10000
            w.player.set_pause.reset_mock();w.tick();w.player.set_pause.assert_not_called()
        finally:w.processing=False;w.close()
    @patch.object(app.vlc,'Instance',side_effect=fake_engine)
    def test_prepare_mode_does_not_autoplay_partial_or_finished_results(self,factory):
        w=app.Window();w.path='test.mp4';w.key.setText('dummy')
        try:
            w.ai_policy.setCurrentIndex(w.ai_policy.findData('prepare'));job=MagicMock();job.isRunning.return_value=False
            with patch.object(app,'Job',return_value=job),patch.object(app.QMessageBox,'question',return_value=app.QMessageBox.Yes):w.process()
            self.assertFalse(w.want_play);w.player.play.reset_mock();w.receive_chunk([Cue(0,1,'Hi','Halo')],30);w.done(w.cues);w.player.play.assert_not_called()
        finally:w.close()

    @patch.object(app.vlc,'Instance',side_effect=fake_engine)
    def test_native_dsp_and_transform_options_survive_rebuild(self,factory):
        w=app.Window()
        try:
            w.select_dsp('night');self.assertIn('--audio-filter=compressor',factory.call_args.args)
            w.select_rotation('90');self.assertIn('--transform-type=90',factory.call_args.args);self.assertIn('--audio-filter=compressor',factory.call_args.args)
            w.select_dsp('normalize');self.assertIn('--audio-filter=normvol',factory.call_args.args)
        finally:w.close()
    @patch.object(app.vlc,'Instance',side_effect=fake_engine)
    def test_overlay_follows_video_without_intercepting_mouse(self,factory):
        from PySide6.QtCore import Qt
        w=app.Window();w.show();q.processEvents()
        try:
            w.subtitle.setText('Subtitle Indonesia');w.video.audio_title=''
            with patch.object(app.Window,'isActiveWindow',return_value=True):w.update_overlay()
            self.assertTrue(w.overlay.testAttribute(Qt.WA_TransparentForMouseEvents));self.assertEqual(w.overlay.text(),'Subtitle Indonesia');self.assertLessEqual(w.overlay.width(),w.video.width());self.assertFalse(w.overlay.isHidden())
            w.toggle_overlay(False);self.assertTrue(w.overlay.isHidden())
        finally:w.close();q.processEvents()
