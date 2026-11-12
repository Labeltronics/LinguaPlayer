"""Real Qt thread/signal lifecycle checks; prevents QDialog.finished collisions."""
import tempfile,time,wave,threading
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from unittest.mock import patch
import unittest
from PySide6.QtWidgets import QApplication,QWidget,QLineEdit,QLabel
from PySide6.QtCore import QSettings
from core import Cue

def wait(predicate,seconds=10):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        QApplication.processEvents()
        if predicate():return
        time.sleep(.01)
    raise AssertionError('Background job did not finish')
class BackgroundIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def owner(self):
        o=QWidget();o.path='';o.key=QLineEdit('fixture-key');o.model=QLineEdit('fixture-model');o.status=QLabel();o.cues=[];o.storage_enabled=False;o.private_session=True;o.settings=QSettings('Cyber80Tests','Ephemeral');o.online_job=None;o.online_record_job=None;o.cast_dialogs=[];return o
    def test_subtitle_worker_to_editor_saved_file_and_finish_controls(self):
        from language_studio import LanguageStudio,TextJob
        owner=self.owner();studio=LanguageStudio(owner);messages=[];studio.notify=messages.append
        try:
            with tempfile.TemporaryDirectory() as d:
                source=Path(d)/'source.wav'
                with wave.open(str(source),'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(16000);w.writeframes(b'\0\0'*32000)
                studio.source.setText(str(source));studio.text_target=str(Path(d)/'subtitle.srt')
                job=TextJob(str(source),'fixture-key','fixture-model','id');job.text_ready.connect(studio.text_ready)
                with patch('language_studio.transcribe',return_value=[Cue(0,1,'Hello','Halo','en')]):
                    studio.start(job);wait(lambda:studio.job is None)
                self.assertIn('Halo',studio.editor.toPlainText());self.assertIn('Halo',Path(studio.text_target).read_text());self.assertTrue(messages);self.assertTrue(all(b.isEnabled() for b in studio.buttons))
        finally:studio.deleteLater();owner.deleteLater();QApplication.processEvents()
    def test_tv_playlist_loader_releases_finished_thread(self):
        from iptv_window import InternetTV
        owner=self.owner();tv=InternetTV(owner)
        try:
            # Drain optional bundled snapshot autoload before explicit import.
            QApplication.processEvents()
            if tv.job:wait(lambda:tv.job is None)
            with tempfile.TemporaryDirectory() as d:
                path=Path(d)/'fixture.m3u';path.write_text('#EXTM3U\n#EXTINF:-1 group-title="News",News\nhttps://example.test/live.m3u8\n')
                tv.load('playlist',str(path));wait(lambda:tv.job is None);self.assertEqual(len(tv.rows),1);self.assertEqual(tv.rows[0]['name'],'News')
        finally:
            if tv.job:tv.cancel();wait(lambda:tv.job is None)
            tv.deleteLater();owner.deleteLater();QApplication.processEvents()
    def test_cast_action_worker_finishes_and_stop_does_not_restart_forever(self):
        from cast_dialog import CastDialog
        calls=[]
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                self.rfile.read(int(self.headers['Content-Length']));calls.append(self.headers['SOAPAction']);self.send_response(200);self.send_header('Content-Length','0');self.end_headers()
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start();owner=self.owner()
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'fixture.mp4';source.write_bytes(b'fixture');dialog=CastDialog(owner,str(source));dialog.device={'kind':'dlna','control':f'http://127.0.0.1:{server.server_port}/control','service':'urn:schemas-upnp-org:service:AVTransport:1'}
            try:
                dialog.command('play');wait(lambda:dialog.job is None);dialog.stop();wait(lambda:dialog.job is None);self.assertIsNone(dialog.device);self.assertTrue(dialog.shutdown());self.assertEqual(len(calls),2)
            finally:
                if dialog.job:wait(lambda:dialog.job is None)
                dialog.deleteLater();owner.deleteLater();QApplication.processEvents();server.shutdown();server.server_close()
