import unittest,tempfile
from pathlib import Path
import numpy as np
from stereo import compose_anaglyph
from playlist import read_playlist,write_playlist

class StereoTests(unittest.TestCase):
    def setUp(self):
        self.frame=np.zeros((2,6,4),dtype=np.uint8);self.frame[:,:3,:3]=[10,20,100];self.frame[:,3:,:3]=[200,80,30];self.frame[:,:,3]=255
    def test_zero_shift_2d_preserves_image(self):np.testing.assert_array_equal(compose_anaglyph(self.frame),self.frame)
    def test_sbs_eyes_and_red_blue(self):
        out=compose_anaglyph(self.frame,layout='sbs-full');self.assertEqual(out.shape,(2,3,4));self.assertEqual(list(out[0,0]),[200,80,100,255])
        out=compose_anaglyph(self.frame,layout='sbs-full',scheme='red-blue');self.assertEqual(list(out[0,0]),[200,0,100,255])
    def test_eye_swap(self):self.assertEqual(list(compose_anaglyph(self.frame,layout='sbs-full',swap=True)[0,0]),[10,20,30,255])
    def test_depth_positive_negative_no_wrap(self):
        out=compose_anaglyph(self.frame,red=1,blue=-1);self.assertEqual(out[0,0,2],0);self.assertEqual(out[0,-1,0],0)
    def test_half_sbs_keeps_source_dimensions(self):self.assertEqual(compose_anaglyph(self.frame,layout='sbs-half').shape,self.frame.shape)
    def test_tb_dimensions(self):self.assertEqual(compose_anaglyph(self.frame,layout='tb-full').shape,(1,6,4))

class PlaylistTests(unittest.TestCase):
    def test_unicode_roundtrip_m3u_json(self):
        with tempfile.TemporaryDirectory() as d:
            paths=[str(Path(d)/'Film satu.mp4'),str(Path(d)/'日本語.mkv')]
            for ext in ('m3u8','json'):
                p=Path(d)/('playlist.'+ext);write_playlist(p,paths);self.assertEqual(read_playlist(p),[str(Path(v).resolve()) for v in paths])
    def test_relative_playlist_resolves_from_playlist_folder(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'list.m3u';p.write_text('#EXTM3U\nvideo.mp4\n',encoding='utf-8');self.assertEqual(read_playlist(p),[str((Path(d)/'video.mp4').resolve())])
