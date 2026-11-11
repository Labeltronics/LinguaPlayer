import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import unittest,tempfile,subprocess
from pathlib import Path
from unittest.mock import MagicMock,patch
from PySide6.QtWidgets import QApplication
import app
from core import Cue

q=QApplication.instance() or QApplication([])

class PlayerTests(unittest.TestCase):
    def test_default_and_buffering(self):
        with patch.object(app.vlc,'Instance',return_value=MagicMock()):
            w=app.Window()
            try:
                self.assertEqual(w.lang.currentData(),'id');self.assertEqual(w.mode.currentIndex(),1)
                w.processing=True;w.buffering=True;w.want_play=True;w.player.get_time.return_value=0
                w.receive_chunk([Cue(0,2,'Hello','Halo','en')],10)
                self.assertFalse(w.buffering);self.assertTrue(w.player.play.called)
                self.assertIn('en',w.detected.text())
                w.player.get_time.return_value=9900;w.tick();self.assertTrue(w.buffering)
                w.want_play=False;w.player.play.reset_mock()
                w.receive_chunk([Cue(10,12,'world','dunia','en')],20)
                self.assertFalse(w.player.play.called)
            finally:w.processing=False;w.close()
    def test_real_ffmpeg_incremental_worker(self):
        ff=app.imageio_ffmpeg.get_ffmpeg_exe()
        flags={'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {}
        with tempfile.TemporaryDirectory() as d:
            video=str(Path(d)/'sample.mp4')
            subprocess.run([ff,'-v','error','-f','lavfi','-i','color=black:s=160x120:d=12','-f','lavfi','-i','sine=frequency=440:duration=12','-c:v','mpeg4','-c:a','aac','-shortest',video],check=True,**flags)
            job=app.Job(video,'dummy-test-key','model','id','','')
            chunks=[];results=[];errors=[]
            job.chunk_ready.connect(lambda cues,coverage:chunks.append(coverage))
            job.result.connect(results.append);job.failed.connect(errors.append)
            with patch.object(app,'transcribe',side_effect=lambda audio,key,model,lang,duration,offset,*args:[Cue(offset,offset+min(duration,1),'Hello','Halo','en')]) as api:
                job.run()
                self.assertEqual(api.call_count,2)
            self.assertFalse(errors);self.assertEqual(len(results),1)
            self.assertAlmostEqual(chunks[0],10,places=1);self.assertAlmostEqual(chunks[1],12,places=1)
            self.assertEqual(results[0][1].start,10)
