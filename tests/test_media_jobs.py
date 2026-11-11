import unittest,tempfile,subprocess,os
from pathlib import Path
from media_jobs import UtilityJob,utility_arguments
import imageio_ffmpeg
class UtilityTests(unittest.TestCase):
    def test_clip_range_and_source_protection(self):
        for a,b in ((1,0),(float('nan'),3),(-1,2)):
            with self.assertRaises(ValueError):utility_arguments('Potong klip MP4',a,b)
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'source.mp4';source.write_bytes(b'source');errors=[];job=UtilityJob(source,source,'Remux MKV');job.failure.connect(errors.append);job.run();self.assertTrue(errors);self.assertEqual(source.read_bytes(),b'source')
    def test_actual_ffmpeg_utilities(self):
        ff=imageio_ffmpeg.get_ffmpeg_exe();flags={'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {}
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'source.mp4'
            subprocess.run([ff,'-v','error','-y','-f','lavfi','-i','color=blue:size=160x120:duration=2','-f','lavfi','-i','sine=frequency=440:duration=2','-c:v','libx264','-c:a','aac','-shortest',str(source)],check=True,**flags)
            for kind,extension in [('Potong klip MP4','mp4'),('Ekstrak audio WAV','wav'),('Ekstrak audio MP3','mp3'),('Normalisasi audio WAV','wav'),('Remux MKV','mkv'),('Bakar subtitle MP4','mp4')]:
                with self.subTest(kind=kind):
                    target=Path(d)/(kind+'.'+extension);job=UtilityJob(source,target,kind,0,1,'1\n00:00:00,000 --> 00:00:01,000\nHalo\n');errors=[];done=[];job.failure.connect(errors.append);job.success.connect(done.append);job.run();self.assertFalse(errors);self.assertTrue(done);self.assertGreater(target.stat().st_size,100)
