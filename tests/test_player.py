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
            with patch.object(app,'transcribe',side_effect=lambda audio,key,model,lang,duration,offset,*args,**kwargs:[Cue(offset,offset+min(duration,1),'Hello','Halo','en')]) as api:
                job.run()
                self.assertEqual(api.call_count,2)
            self.assertFalse(errors);self.assertEqual(len(results),1)
            self.assertAlmostEqual(chunks[0],10,places=1);self.assertAlmostEqual(chunks[1],12,places=1)
            self.assertEqual(results[0][1].start,10)

    def test_pip_moves_native_surface_and_restores(self):
        with patch.object(app.vlc,'Instance',return_value=MagicMock()):
            w=app.Window();w.player.get_time.return_value=1000;w.player.get_state.return_value=app.vlc.State.Stopped
            try:
                w.toggle_pip();q.processEvents()
                self.assertIsNotNone(w.pip);self.assertEqual(w.video.parentWidget(),w.pip)
                w.fill([Cue(0,2,'Original','Subtitle Indonesia')]);w.player.get_position.return_value=0.;w.tick()
                self.assertEqual(w.pip.caption.text(),'Subtitle Indonesia')
                w.leave_pip();q.processEvents()
                self.assertIsNone(w.pip);self.assertEqual(w.video.parentWidget(),w.video_host)
            finally:w.close();q.processEvents()

    def test_resume_after_failed_chunk_preserves_completed_cues(self):
        ff=app.imageio_ffmpeg.get_ffmpeg_exe()
        flags={'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {}
        with tempfile.TemporaryDirectory() as d:
            video=str(Path(d)/'sample.mp4')
            subprocess.run([ff,'-v','error','-f','lavfi','-i','color=black:s=160x120:d=12','-f','lavfi','-i','sine=frequency=440:duration=12','-c:v','mpeg4','-c:a','aac','-shortest',video],check=True,**flags)
            job=app.Job(video,'dummy','model','id','','');received=[];errors=[]
            job.chunk_ready.connect(lambda cues,coverage:received.extend(cues));job.failed.connect(errors.append)
            with patch.object(app,'transcribe',side_effect=[[Cue(0,1,'Hello','Halo','en')],TimeoutError('timed out')]):job.run()
            self.assertEqual(job.resume_from,10);self.assertEqual(len(received),1);self.assertTrue(errors)
            resumed=app.Job(video,'dummy','model','id','','',resume_from=job.resume_from,initial_cues=received);results=[]
            resumed.result.connect(results.append)
            with patch.object(app,'transcribe',return_value=[Cue(10,11,'World','Dunia','en')]) as api:
                resumed.run();self.assertEqual(api.call_count,1);self.assertEqual(api.call_args.args[5],10)
            self.assertEqual([c.start for c in results[0]],[0,10])
