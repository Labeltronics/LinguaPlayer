import tempfile,unittest,urllib.request,urllib.error,threading
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from unittest.mock import patch
from lan_cast import ShareSession,byte_range,vtt
from core import Cue
from cast_devices import CastAction
class CastTests(unittest.TestCase):
    def test_token_range_traversal_and_closed_server(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'film.mp4';source.write_bytes(b'0123456789');session=ShareSession(source,'127.0.0.1',[Cue(0,1,'Hello','Halo')]);base=session.url('127.0.0.1','media')
            try:
                with urllib.request.urlopen(base) as r:self.assertEqual(r.read(),b'0123456789')
                with urllib.request.urlopen(urllib.request.Request(base,headers={'Range':'bytes=2-5'})) as r:self.assertEqual(r.status,206);self.assertEqual(r.read(),b'2345')
                with urllib.request.urlopen(urllib.request.Request(base,headers={'Range':'bytes=-3'})) as r:self.assertEqual(r.read(),b'789')
                for url in (base.replace(session.token,'wrong'),session.url('127.0.0.1','../../secret')):
                    with self.assertRaises(urllib.error.HTTPError):urllib.request.urlopen(url)
                with urllib.request.urlopen(session.url('127.0.0.1')) as r:self.assertIn(b'<video',r.read())
                with urllib.request.urlopen(session.url('127.0.0.1','subtitle.vtt')) as r:self.assertIn(b'Halo',r.read())
            finally:session.close()
            self.assertTrue(session.closed.is_set())
    def test_invalid_ranges(self):
        for value in ('bytes=99-100','bytes=3-1','bytes=0-1,4-5','bytes=-0'):
            with self.assertRaises(ValueError):byte_range(value,10)
    def test_google_cast_command_adapter(self):
        from unittest.mock import MagicMock
        device=MagicMock();job=CastAction({'kind':'chromecast','cast':device},'load','http://192.168.1.2/media','video/mp4',position=7);job.run();device.media_controller.play_media.assert_called_once();self.assertEqual(device.media_controller.play_media.call_args.kwargs['current_time'],7)
    def test_actual_dlna_soap_loopback(self):
        calls=[]
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*a):pass
            def do_POST(self):
                calls.append((self.headers['SOAPAction'],self.rfile.read(int(self.headers['Content-Length']))));self.send_response(200);self.send_header('Content-Length','0');self.end_headers()
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
        try:
            device={'kind':'dlna','control':f'http://127.0.0.1:{server.server_port}/control','service':'urn:schemas-upnp-org:service:AVTransport:1'}
            job=CastAction(device,'load','http://192.168.1.2/video.mp4?key=test','video/mp4','Film & Test');errors=[];job.failed.connect(errors.append);job.run();self.assertFalse(errors);self.assertEqual(len(calls),2);self.assertIn('SetAVTransportURI',calls[0][0]);self.assertIn(b'Film &amp;amp; Test',calls[0][1]);self.assertIn('Play',calls[1][0])
        finally:server.shutdown();server.server_close()
