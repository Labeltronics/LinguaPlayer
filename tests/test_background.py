import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import io,json,tempfile,unittest,subprocess
from pathlib import Path
from unittest.mock import patch,MagicMock
import urllib.error
from PySide6.QtWidgets import QApplication
import app,background_subtitles as bg
from core import Cue
from test_advanced_player import fake_engine
q=QApplication.instance() or QApplication([])
REMOTE={'name':'files/test-file','uri':bg.BASE+'/v1beta/files/test-file','state':'ACTIVE','mimeType':'video/mp4'}
def response(cues,finish='STOP'):
    return {'candidates':[{'finishReason':finish,'content':{'parts':[{'text':json.dumps(cues)}]}}]}
def metadata(duration):
    yield {'duration':duration}
class AttachmentTests(unittest.TestCase):
    def test_url_security_and_payload_clipping(self):
        for url in ('http://generativelanguage.googleapis.com/x','https://evil.test/x','https://u:p@generativelanguage.googleapis.com/x'):
            with self.assertRaises(ValueError):bg.safe_url(url)
        payload=bg.attachment_payload(REMOTE['uri'],'video/mp4',120,240,'id','Nama')
        part=payload['contents'][0]['parts'][0];self.assertEqual(part['videoMetadata']['startOffset'],'120.000s');self.assertIn('ABSOLUTE',payload['contents'][0]['parts'][1]['text'])
        with self.assertRaises(ValueError):bg.extract_attachment_cues(response([{'start':0,'end':1,'source':'wrong'}]),120,240)
        with self.assertRaises(bg.APIError):bg.extract_attachment_cues(response([], 'MAX_TOKENS'),0,120)
    def test_upload_chunks_offsets_and_host_validation(self):
        with tempfile.TemporaryDirectory() as d:
            video=Path(d)/'video.mp4';video.write_bytes(b'0123456789');events=[];calls=[]
            def exchange(url,key,method='GET',data=None,headers=None,**kwargs):
                calls.append((url,method,data,headers))
                if len(calls)==1:return {},{'X-Goog-Upload-URL':bg.BASE+'/upload/session'}
                return ({'file':REMOTE} if headers['X-Goog-Upload-Command'].endswith('finalize') else {}),{}
            with patch.object(bg,'BLOCK',4),patch.object(bg,'api_exchange',side_effect=exchange):
                result=bg.upload_video(video,'dummy',lambda:False,events.append)
            self.assertEqual(result,REMOTE);self.assertEqual([c[3]['X-Goog-Upload-Offset'] for c in calls[1:]],['0','4','8']);self.assertIn('100.0%',events[-1]);self.assertEqual(b''.join(c[2] for c in calls[1:]),video.read_bytes())
            with patch.object(bg,'api_exchange') as network:
                with self.assertRaises(InterruptedError):bg.upload_video(video,'dummy',lambda:True,events.append)
                network.assert_not_called()
    def test_permission_error_redacts_key_without_retry(self):
        error=urllib.error.HTTPError(bg.BASE,403,'denied',{},io.BytesIO(json.dumps({'error':{'message':'invalid dummy-secret'}}).encode()))
        opener=MagicMock();opener.open.side_effect=error
        with patch.object(bg.urllib.request,'build_opener',return_value=opener):
            with self.assertRaises(bg.APIError) as raised:bg.api_exchange(bg.BASE+'/v1beta/files','dummy-secret')
        self.assertNotIn('dummy-secret',str(raised.exception));self.assertEqual(opener.open.call_count,1)
    def test_processing_failure_and_cancellation(self):
        with self.assertRaises(bg.APIError):bg.active_file(dict(REMOTE,state='FAILED'),'dummy',lambda:False,lambda _:None)
        with self.assertRaises(InterruptedError):bg.active_file(REMOTE,'dummy',lambda:True,lambda _:None)
    def test_background_saves_complete_srt_and_deletes_remote(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'source.mp4';source.write_bytes(b'video');target=Path(d)/'result.srt';job=bg.BackgroundSubtitleJob(source,target,'dummy','model');completed=[];errors=[]
            job.completed.connect(lambda path,cues:completed.append((path,cues)));job.failed.connect(errors.append)
            data=response([{'start':0,'end':1,'source':'Hello','target':'Halo','language':'en'}])
            with patch.object(bg.imageio_ffmpeg,'read_frames',return_value=metadata(3)),patch.object(bg,'upload_video',return_value=REMOTE),patch.object(bg,'request_json',return_value=data),patch.object(bg,'api_exchange',return_value=({},{})) as cleanup:job.run()
            self.assertFalse(errors);self.assertEqual(len(completed),1);self.assertIn('Halo',target.read_text());self.assertFalse(Path(str(target)+'.progress.json').exists());self.assertEqual(cleanup.call_args.args[2],'DELETE')
    def test_failed_segment_preserves_checkpoint_and_resume_skips_it(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'source.mp4';source.write_bytes(b'video');target=Path(d)/'result.srt'
            first=bg.BackgroundSubtitleJob(source,target,'dummy','model');failures=[];first.failed.connect(failures.append)
            data=response([{'start':0,'end':1,'source':'Hello','target':'Halo'}])
            patches=[patch.object(bg.imageio_ffmpeg,'read_frames',side_effect=lambda _:metadata(130)),patch.object(bg,'upload_video',return_value=REMOTE),patch.object(bg,'api_exchange',return_value=({},{}))]
            with patches[0],patches[1],patches[2],patch.object(bg,'request_json',side_effect=[data,bg.APIError('timeout')]):first.run()
            self.assertTrue(failures);self.assertFalse(target.exists());self.assertEqual(json.loads(Path(str(target)+'.progress.json').read_text())['offset'],120)
            second=bg.BackgroundSubtitleJob(source,target,'dummy','model');done=[];second.completed.connect(lambda *args:done.append(args))
            with patch.object(bg.imageio_ffmpeg,'read_frames',return_value=metadata(130)),patch.object(bg,'upload_video',return_value=REMOTE),patch.object(bg,'api_exchange',return_value=({},{})),patch.object(bg,'request_json',return_value=response([{'start':120,'end':121,'source':'World','target':'Dunia'}])) as request:second.run()
            self.assertEqual(request.call_count,1);self.assertIn('120.000s',str(request.call_args.args[2]));self.assertEqual(len(done[0][1]),2)
    def test_real_ffmpeg_proxy_then_attachment_pipeline(self):
        ff=app.imageio_ffmpeg.get_ffmpeg_exe();flags={'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {}
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'sample.ts';target=Path(d)/'sample.srt'
            subprocess.run([ff,'-v','error','-y','-f','lavfi','-i','color=blue:size=176x144:duration=2','-f','lavfi','-i','sine=frequency=440:duration=2','-c:v','mpeg2video','-c:a','mp2','-shortest',str(source)],check=True,**flags)
            job=bg.BackgroundSubtitleJob(source,target,'dummy','model',proxy=True);errors=[];job.failed.connect(errors.append)
            def upload(path,*args):self.assertGreater(Path(path).stat().st_size,100);return REMOTE
            with patch.object(bg,'upload_video',side_effect=upload),patch.object(bg,'request_json',return_value=response([])),patch.object(bg,'api_exchange',return_value=({},{})):job.run()
            self.assertFalse(errors);self.assertTrue(target.exists());self.assertTrue(source.exists())
            fallback_target=Path(d)/'fallback.srt';fallback=bg.BackgroundSubtitleJob(source,fallback_target,'dummy','model',proxy=True);fallback_errors=[];fallback.failed.connect(fallback_errors.append)
            with patch.object(bg,'upload_video',side_effect=upload),patch.object(bg,'request_json',side_effect=bg.APIError('busy',503)),patch.object(bg,'api_exchange',return_value=({},{})),patch.object(bg,'transcribe',return_value=[Cue(0,1,'Hello','Halo','en')]) as audio:
                fallback.run();self.assertFalse(fallback_errors);self.assertEqual(audio.call_args.args[2],'model');self.assertIn('Halo',fallback_target.read_text())
            self.assertFalse(fallback.transient(bg.APIError('permission',403)));self.assertFalse(fallback.transient(bg.APIError('quota',429)));self.assertTrue(fallback.transient(bg.APITimeout('timeout')))
    @patch.object(app.vlc,'Instance',side_effect=fake_engine)
    def test_finished_notification_does_not_replace_another_movies_subtitles(self,factory):
        w=app.Window();w.path='other.mp4';w.fill([Cue(0,1,'Other')]);w.background_job=MagicMock(source='source.mp4');w.background_job.isRunning.return_value=False
        try:
            with patch.object(app.QMessageBox,'open') as notice:w.background_complete('output.srt',[Cue(0,1,'Hello','Halo')]);notice.assert_called_once()
            self.assertEqual(w.cues[0].source,'Other');self.assertIn('selesai',w.attachment_status.text())
        finally:
            if w.background_notice:w.background_notice.close()
            w.close()
