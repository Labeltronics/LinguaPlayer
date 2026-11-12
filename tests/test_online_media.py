import tempfile,subprocess,threading,unittest
from pathlib import Path
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
import imageio_ffmpeg
from online_media import StreamRecording
from video_render import flags,probe
class OnlineRecordingTests(unittest.TestCase):
    def test_actual_http_clip_record_source_unchanged_and_cancel(self):
        ff=imageio_ffmpeg.get_ffmpeg_exe()
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'source.mp4'
            subprocess.run([ff,'-v','error','-y','-f','lavfi','-i','color=s=160x90:r=5:d=2','-f','lavfi','-i','sine=duration=2','-c:v','libx264','-c:a','aac','-movflags','+faststart','-shortest',str(source)],check=True,**flags());original=source.read_bytes()
            class Handler(SimpleHTTPRequestHandler):
                def __init__(self,*a,**k):super().__init__(*a,directory=d,**k)
                def log_message(self,*a):pass
            server=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start();url=f'http://127.0.0.1:{server.server_port}/source.mp4'
            try:
                out=root/'record.mp4';self.assertEqual(StreamRecording(url,out,1).execute(),str(out.resolve()));self.assertGreater(probe(ff,out)['duration'],.8);self.assertEqual(source.read_bytes(),original)
                with self.assertRaises(ValueError):StreamRecording(url,out,1).execute()
                job=StreamRecording(url,root/'cancel.mp4',1);job.cancel()
                with self.assertRaises(InterruptedError):job.execute()
                self.assertFalse((root/'cancel.mp4').exists());self.assertFalse(list(root.glob('*.partial.*')))
            finally:server.shutdown();server.server_close()
