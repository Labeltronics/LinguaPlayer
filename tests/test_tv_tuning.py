import tempfile,subprocess,threading,unittest,time
from pathlib import Path
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
from unittest.mock import patch
from PySide6.QtWidgets import QApplication,QWidget,QLineEdit,QLabel
from PySide6.QtCore import QSettings
import imageio_ffmpeg
from tv_tuning import decode_frame,candidates,media_headers,TuneTV
from internet_tv import catalog,parse_m3u
from video_render import flags

class TVTuningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def test_metadata_headers_preserved_and_crlf_rejected(self):
        rows=catalog([{'id':'one','name':'One','country':'ID'}],[{'channel':'one','url':'https://example.test/live','user_agent':'Required Agent','referrer':'https://example.test/'}]);self.assertEqual(rows[0]['headers']['User-Agent'],'Required Agent');self.assertIn('Referer',rows[0]['headers'])
        rows=parse_m3u('#EXTM3U\n#EXTINF:-1,Station\n#EXTVLCOPT:http-user-agent=Required Agent\n#EXTVLCOPT:http-referrer=https://example.test/\nhttps://example.test/live\n');self.assertEqual(rows[0]['headers']['User-Agent'],'Required Agent')
        with self.assertRaises(ValueError):media_headers({'User-Agent':'x\r\nCookie: secret'})
    def test_real_header_required_video_audio_only_and_fallback(self):
        ff=imageio_ffmpeg.get_ffmpeg_exe()
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);video=root/'video.mp4';audio=root/'audio.wav'
            subprocess.run([ff,'-v','error','-y','-f','lavfi','-i','color=s=160x90:r=5:d=1','-f','lavfi','-i','sine=duration=1','-c:a','aac','-c:v','libx264','-movflags','+faststart',str(video)],check=True,**flags())
            subprocess.run([ff,'-v','error','-y','-f','lavfi','-i','sine=duration=1',str(audio)],check=True,**flags())
            class Handler(SimpleHTTPRequestHandler):
                def __init__(self,*args,**kwargs):super().__init__(*args,directory=d,**kwargs)
                def log_message(self,*args):pass
                def do_GET(self):
                    if self.path.startswith('/video') and (self.headers.get('User-Agent')!='Cyber80-test' or self.headers.get('Referer')!='https://example.test/'):
                        self.send_error(403);return
                    super().do_GET()
            server=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start();base=f'http://127.0.0.1:{server.server_port}'
            bad={'id':'one','url':base+'/missing.mp4','key':'bad','adult':False};good={'id':'one','url':base+'/video.mp4','key':'good','adult':False,'headers':{'User-Agent':'Cyber80-test','Referer':'https://example.test/'}}
            try:
                self.assertFalse(decode_frame({**good,'headers':{}})[0]);self.assertEqual(decode_frame(good),(True,'Gambar dan audio terdeteksi'));self.assertIn('Hanya audio',decode_frame({'url':base+'/audio.wav'})[1])
                job=TuneTV([bad,good],bad);result=[];job.ready.connect(result.append);job.start();end=time.monotonic()+15
                while job.isRunning() and time.monotonic()<end:QApplication.processEvents();time.sleep(.01)
                job.wait(1000);QApplication.processEvents();self.assertEqual(result[0]['key'],'good')
            finally:server.shutdown();server.server_close()
    def test_adult_list_separate_and_hidden_until_unlock(self):
        from iptv_window import InternetTV
        owner=QWidget();owner.path='';owner.storage_enabled=False;owner.private_session=True;owner.settings=QSettings('Cyber80Tests','TV');owner.online_job=None;owner.online_record_job=None;owner.cast_dialogs=[]
        tv=InternetTV(owner);QApplication.processEvents()
        if tv.job:
            deadline=time.monotonic()+10
            while tv.job and time.monotonic()<deadline:QApplication.processEvents();time.sleep(.01)
        rows=parse_m3u('#EXTM3U\n#EXTINF:-1 group-title="News",News\nhttps://example.test/a\n#EXTINF:-1 group-title="18+",Restricted fixture\nhttps://example.test/b\n')
        try:
            tv.got_rows(rows);self.assertEqual(tv.section.count(),1);self.assertFalse(any(r['adult'] for r in tv.visible_rows))
            with patch.object(tv.lock,'unlock',return_value=True) as unlock,patch('iptv_window.QInputDialog.getText',return_value=('test-pin',True)):
                def grant(pin):tv.lock.unlocked=True;return True
                unlock.side_effect=grant;tv.unlock()
            self.assertEqual(tv.section.currentData(),'adult');self.assertEqual(len(tv.visible_rows),1);self.assertTrue(tv.visible_rows[0]['adult']);tv.relock();self.assertEqual(tv.section.count(),1);self.assertTrue(all(not r['adult'] for r in tv.visible_rows))
        finally:tv.deleteLater();owner.deleteLater();QApplication.processEvents()
    def test_alternatives_do_not_cross_adult_boundary(self):
        selected={'id':'one','url':'https://example.test/a','adult':False};self.assertEqual(len(candidates([selected,{'id':'one','url':'https://example.test/b','adult':True}],selected)),1)

    def test_prefers_alternative_with_audio_over_silent_video(self):
        silent={'id':'one','url':'https://example.test/silent','key':'silent'};av={'id':'one','url':'https://example.test/av','key':'av'}
        job=TuneTV([silent,av],silent);result=[];job.ready.connect(result.append)
        with patch('tv_tuning.decode_frame',side_effect=[(True,'Video terdeteksi; sumber tanpa audio'),(True,'Gambar dan audio terdeteksi')]):job.run()
        self.assertEqual(result[0]['key'],'av');self.assertTrue(result[0]['_has_audio'])
