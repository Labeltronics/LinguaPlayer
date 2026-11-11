import unittest, json
from unittest.mock import patch
from core import Cue,validate,srt,transcribe,request_json,parse_srt,APIError

class CoreTests(unittest.TestCase):
    def test_timestamp_and_unicode(self):
        result=srt([Cue(59.9996,61.2,'Halo','你好')])
        self.assertIn('00:01:00,000 --> 00:01:01,200',result)
        self.assertIn('你好',result)
    def test_reject_bad_timing(self):
        for a,b in [(2,1),(-1,2),(0,float('nan')),(0,100)]:
            with self.assertRaises(ValueError):validate([{'start':a,'end':b,'source':'x'}],45)
    def test_offset_overlap(self):
        cues=validate([{'start':0,'end':3,'source':'A'},{'start':2,'end':4,'source':'B'}],45,90)
        self.assertEqual(cues[0].start,90);self.assertEqual(cues[0].end,92)
    @patch('core.request_json')
    def test_gemini_and_translation(self,api):
        api.side_effect=[{'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':json.dumps([{'start':0,'end':2,'source':'Hello'}])}]}}]}, {'data':{'translations':[{'translatedText':'Halo &amp; dunia'}]}}]
        cues=transcribe(b'audio','secret','gemini-2.5-flash','id',3,45,'other')
        self.assertEqual(cues[0].target,'Halo & dunia');self.assertEqual(cues[0].start,45)
        self.assertEqual(api.call_args_list[1].args[2]['target'],'id')
    @patch('core.request_json')
    def test_incomplete_response(self,api):
        api.return_value={'candidates':[{'finishReason':'MAX_TOKENS'}]}
        with self.assertRaises(APIError):transcribe(b'a','key','model','en',10,0)
    def test_cancel_before_network(self):
        with self.assertRaises(InterruptedError):request_json('https://example.com','key',{},lambda:True)
    def test_silence(self):self.assertEqual(validate([],45),[])
    def test_srt_roundtrip(self):
        cues=parse_srt(srt([Cue(1.25,3.5,'Halo\ndunia')],False))
        self.assertEqual(cues[0].start,1.25);self.assertEqual(cues[0].source,'Halo\ndunia')
    def test_source_export(self):self.assertIn('Hello',srt([Cue(0,1,'Hello','Halo')],False))

if __name__=='__main__':unittest.main()


class LanguageLabelTests(unittest.TestCase):
    def test_source_language_is_not_translation_language(self):
        from core import Cue
        from language_check import check_source_languages
        cue=Cue(0,4,'Hello world welcome to Cyber80player this is a subtitle test','Halo dunia','id')
        self.assertEqual(check_source_languages([cue],'id')[0].language,'en')
        short=Cue(0,1,'Hi','Hai','id');self.assertEqual(check_source_languages([short],'id')[0].language,'id')
