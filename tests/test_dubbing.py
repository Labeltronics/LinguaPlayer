import base64,tempfile,unittest
from pathlib import Path
from core import Cue
from dubbing import checked_cues,decode_audio,lrc,protected_target
from dubbing_checks import run_dubbing_checks
class DubbingTests(unittest.TestCase):
    def test_overlap_and_invalid_time_rejected(self):
        for cues in ([Cue(1,2,'a'),Cue(1.5,2.5,'b')],[Cue(float('nan'),2,'a')],[Cue(0,5,'a')]):
            with self.assertRaises(ValueError):checked_cues(cues,3)
    def test_lrc_centisecond_rounding(self):
        self.assertIn('[01:00.00]Halo',lrc([Cue(59.999,61,'Halo')]))
    def test_tts_pcm_and_bad_responses(self):
        response={'candidates':[{'finishReason':'STOP','content':{'parts':[{'inlineData':{'mimeType':'audio/L16;codec=pcm;rate=24000','data':base64.b64encode(b'\0\0'*20).decode()}}]}}]}
        self.assertEqual(decode_audio(response),(b'\0\0'*20,24000))
        for value in ({},{'candidates':[{'finishReason':'MAX_TOKENS'}]}):
            with self.assertRaises(ValueError):decode_audio(value)
        response['candidates'][0]['content']['parts'][0]['inlineData']['mimeType']='audio/mp3'
        with self.assertRaises(ValueError):decode_audio(response)
    def test_no_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'source.mp4';source.write_bytes(b'source')
            for p in (source,):
                with self.assertRaises(ValueError):protected_target(source,p)
            target=Path(d)/'old.wav';target.write_bytes(b'old')
            with self.assertRaises(ValueError):protected_target(source,target)
    def test_actual_render_and_cancel(self):
        with tempfile.TemporaryDirectory() as d:self.assertEqual(run_dubbing_checks(d)['original_unchanged'],'PASS')
    def test_gemini_request_payload_without_network(self):
        from unittest.mock import patch
        from dubbing import DubbingJob
        response={'candidates':[{'finishReason':'STOP','content':{'parts':[{'inlineData':{'mimeType':'audio/L16;codec=pcm;rate=24000','data':base64.b64encode(b'\0\0'*100).decode()}}]}}]}
        with tempfile.TemporaryDirectory() as d,patch('dubbing.request_json',return_value=response) as request:
            job=DubbingJob('source','out',[],key='synthetic-test-not-a-real-key')
            job.synthesize('Halo Indonesia',Path(d)/'out.wav',d)
            args=request.call_args.args;self.assertEqual(args[2]['generationConfig']['responseModalities'],['AUDIO']);self.assertIn('Halo Indonesia',args[2]['contents'][0]['parts'][0]['text']);self.assertTrue((Path(d)/'out.wav').is_file())
    def test_clone_missing_tools_is_explicit(self):
        from voice_clone import validate_tools
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError,'Voice Tools'):validate_tools(d)
    def test_studio_default_and_hidden_background_lifecycle(self):
        from PySide6.QtWidgets import QApplication,QWidget,QLineEdit,QLabel
        from language_studio import LanguageStudio
        app=QApplication.instance() or QApplication([])
        class Owner(QWidget):
            def __init__(self):
                super().__init__();self.path='';self.key=QLineEdit();self.model=QLineEdit('model');self.status=QLabel();self.cues=[]
        owner=Owner();studio=LanguageStudio(owner);self.assertEqual(studio.code(),'id');self.assertFalse(studio.clone.isChecked());studio.show();app.processEvents();studio.close();self.assertFalse(studio.isVisible());self.assertIsNone(studio.job);studio.deleteLater();owner.deleteLater();app.processEvents()
