import unittest,json,threading,tempfile
from pathlib import Path
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from unittest.mock import patch
from local_ai import transcribe_local,local_url
from core import transcribe
from export_tools import export_command,ExportJob

class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        data=self.rfile.read(int(self.headers.get('Content-Length',0)))
        if self.path=='/inference':
            self.server.received_stt=data
            result={'language':'en','segments':[{'start':0,'end':1.5,'text':'Hello world'}]}
        else:
            request=json.loads(data);self.server.received_translate=request
            result={'response':json.dumps({'translations':['Halo dunia']})}
        body=json.dumps(result).encode();self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    def log_message(self,*args):pass

class LocalTests(unittest.TestCase):
    def test_real_loopback_connector_pipeline(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            port=server.server_address[1];config={'speech_url':f'http://127.0.0.1:{port}/inference','translate_url':f'http://127.0.0.1:{port}/api/generate','model':'test'}
            result=transcribe_local(b'fake-audio',config,'id',2,0)
            self.assertEqual(result[0].target,'Halo dunia');self.assertEqual(result[0].language,'en')
            self.assertIn(b'name="language"',server.received_stt);self.assertFalse(server.received_translate['stream'])
        finally:server.shutdown();server.server_close();thread.join(timeout=2)
    def test_local_rejects_external_urls(self):
        for url in ['https://example.com','http://127.0.0.1.evil.com/inference','http://user:secret@localhost/inference','http://localhost/inference?key=secret']:
            with self.assertRaises(ValueError):local_url(url,'/inference')
    @patch('core.request_json')
    def test_overlap_context_is_not_repeated(self,api):
        api.return_value={'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':json.dumps([{'start':0,'end':.5,'source':'Old','target':'Lama'},{'start':.8,'end':2,'source':'New','target':'Baru'}])}]}}]}
        cues=transcribe(b'a','dummy','model','id',3,10,context_seconds=1)
        self.assertEqual(len(cues),1);self.assertEqual(cues[0].source,'New');self.assertEqual(cues[0].start,10);self.assertEqual(cues[0].end,11)

class ExportTests(unittest.TestCase):
    def test_cpu_command_preserves_aspect_and_pads_4k(self):
        args=export_command('ffmpeg','in.mp4','out.mp4',3840,2160,'CPU',.4)
        self.assertIn('libx264',args);self.assertIn('3840:2160',args[args.index('-vf')+1]);self.assertIn('lanczos',args[args.index('-vf')+1])
    def test_gpu_paths_are_explicit_and_not_fake_fallback(self):
        for mode,encoder in [('NVIDIA CUDA','h264_nvenc'),('Intel QSV','h264_qsv'),('AMD AMF','h264_amf')]:
            args=export_command('ffmpeg','in.mp4','out.mp4',1920,1080,mode,source_size=(640,480));self.assertIn(encoder,args);self.assertNotIn('libx264',args)
    def test_export_cannot_overwrite_input(self):
        with tempfile.TemporaryDirectory() as d:
            path=str(Path(d)/'film.mp4');Path(path).touch();job=ExportJob(path,path,'HD 720p','CPU',0);errors=[];job.failure.connect(errors.append);job.run();self.assertIn('menimpa',errors[0]);self.assertTrue(Path(path).exists())
