import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import unittest,tempfile,json,math
from pathlib import Path
from unittest.mock import patch,MagicMock
from PySide6.QtWidgets import QApplication
import app
from audio_tools import validate_settings,effective_preamp,PRESETS
from storage import MediaStore,SubtitleCache,media_key
from test_advanced_player import fake_engine

q=QApplication.instance() or QApplication([])

class SettingsTests(unittest.TestCase):
    def test_eq_validation_and_headroom(self):
        state=validate_settings({'bands':[30]*10,'preamp':40});self.assertEqual(state['preamp'],20);self.assertEqual(state['bands'],[20]*10)
        self.assertEqual(effective_preamp(0,[6]+[0]*9),-6)
        for state in ({'bands':[0]}, {'bands':[float('nan')]*10}):
            with self.assertRaises(ValueError):validate_settings(state)
        self.assertTrue(all(len(v)==10 for v in PRESETS.values()))
    def test_store_shared_and_restored(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'film.mp4';source.write_bytes(b'video');db=Path(d)/'history.json'
            store=MediaStore.shared(db);store.update(source,position=12345,bookmarks=[{'time':12000,'name':'Adegan'}],profile={'rate':1.5})
            self.assertIs(store,MediaStore.shared(db));self.assertEqual(MediaStore(db).get(source)['position'],12345)
            old=media_key(source);source.write_bytes(b'changed');self.assertNotEqual(media_key(source),old);self.assertEqual(store.get(source),{})
    def test_subtitle_checkpoint_restored_and_cleared(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'film.mp4';source.touch();cache=SubtitleCache(Path(d)/'cache');context=['model','id','']
            data={'cues':[{'start':0,'end':1,'source':'Hello','target':'Halo'}],'next_offset':10,'complete':False}
            cache.write(source,context,data);self.assertEqual(SubtitleCache(Path(d)/'cache').read(source,context),data)
            self.assertIsNone(cache.read(source,['different']));cache.clear(source,context);self.assertIsNone(cache.read(source,context))

class AudioUITests(unittest.TestCase):
    @patch.object(app.vlc,'Instance',side_effect=fake_engine)
    @patch('audio_tools.vlc.AudioEqualizer')
    def test_native_eq_applied_and_survives_player_rebuild(self,constructor,engine):
        constructor.side_effect=lambda:MagicMock(set_preamp=MagicMock(return_value=0),set_amp_at_index=MagicMock(return_value=0))
        w=app.Window()
        try:
            w.audio_panel.preset.setCurrentText('Dialog / Vokal');w.audio_panel.apply();old=w.player
            self.assertTrue(w.audio_panel.enabled.isChecked());self.assertTrue(any(str(v).startswith('--equalizer-preamp=') for v in engine.call_args.args))
            self.assertEqual(w.audio_panel.native.set_amp_at_index.call_count,10)
            w.change_renderer(1);self.assertIsNot(old,w.player);self.assertTrue(any('equalizer' in str(v) for v in engine.call_args.args))
            self.assertEqual(w.audio_panel.state()['bands'],[float(v) for v in PRESETS['Dialog / Vokal']])
        finally:w.close()
    @patch.object(app.vlc,'Instance',side_effect=fake_engine)
    def test_rapid_pip_toggle_does_not_restart_twice(self,engine):
        w=app.Window();w.player.get_state.return_value=app.vlc.State.Playing
        try:
            w.toggle_pip();w.leave_pip();w.player.play.reset_mock();q.processEvents();self.assertEqual(w.player.play.call_count,1)
            w.toggle_pip();w.stop();w.player.play.reset_mock();q.processEvents();self.assertFalse(w.player.play.called)
        finally:w.close();q.processEvents()

    @patch.object(app.vlc,'Instance',side_effect=fake_engine)
    @patch('audio_tools.vlc.AudioEqualizer')
    def test_audio_boost_applies_independently_and_survives_reset(self,constructor,engine):
        constructor.side_effect=lambda:MagicMock(set_preamp=MagicMock(return_value=0),set_amp_at_index=MagicMock(return_value=0))
        w=app.Window()
        try:
            self.assertEqual(w.volume.maximum(),200);w.audio_panel.boost_preset(20);self.assertEqual(w.volume.value(),200);w.audio_panel.native.set_preamp.assert_called_with(20)
            w.audio_panel.enabled.setChecked(False);w.audio_panel.apply();w.audio_panel.native.set_preamp.assert_called_with(20);self.assertTrue(w.audio_panel.state()['peak_guard'])
            w.mute_action.setChecked(True);w.change_renderer(w.renderer.currentIndex());w.player.audio_set_mute.assert_called_with(True);w.audio_panel.boost_preset(0);self.assertEqual(w.volume.value(),100);self.assertEqual(w.audio_panel.state()['boost'],0);self.assertIsNone(w.audio_panel.native);self.assertFalse(w.audio_panel.enabled.isChecked());self.assertEqual(w.audio_dsp,'off')
        finally:w.close();q.processEvents()

    @patch.object(app.vlc,'Instance',side_effect=fake_engine)
    def test_deferred_volume_applied_when_output_becomes_ready(self,engine):
        w=app.Window()
        try:
            w.player.audio_set_volume.side_effect=[-1,0];w.player.audio_get_volume.return_value=100;w.player.audio_get_mute.return_value=0;w.request_audio_sync();w.sync_master_audio();self.assertGreater(w.audio_sync_deadline,0);w.sync_master_audio();self.assertEqual(w.audio_sync_deadline,0);w.player.audio_set_volume.assert_called_with(100)
        finally:w.player.audio_set_volume.side_effect=None;w.close();q.processEvents()

    @patch.object(app.vlc,'Instance',side_effect=fake_engine)
    def test_audio_sync_accepts_success_when_backend_has_no_readback(self,engine):
        w=app.Window()
        try:
            w.player.audio_set_volume.return_value=0;w.player.audio_get_volume.return_value=-1;w.player.audio_get_mute.return_value=-1;w.request_audio_sync();w.sync_master_audio();self.assertEqual(w.audio_sync_deadline,0)
        finally:w.close();q.processEvents()

    @patch.object(app.vlc,'Instance',side_effect=fake_engine)
    def test_successful_volume_setter_does_not_retry_stale_readback(self,engine):
        w=app.Window()
        try:
            w.player.audio_set_volume.return_value=0;w.player.audio_get_volume.return_value=0;w.player.audio_get_mute.return_value=0;w.request_audio_sync();w.sync_master_audio();self.assertEqual(w.audio_sync_deadline,0)
        finally:w.close();q.processEvents()
