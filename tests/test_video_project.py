import unittest,tempfile,copy,subprocess,shutil,os,hashlib
from pathlib import Path
import video_project as v
import video_render as r

def ffmpeg():
    found=shutil.which('ffmpeg')
    if found:return found
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()
class ProjectTests(unittest.TestCase):
    def fixture(self):
        p=v.new_project();c=v.new_clip(p['tracks'][1]['id'],'color',duration=2,color='#ff0000');p['clips']=[c];return p,c
    def test_json_history_and_split_are_non_destructive(self):
        p,c=self.fixture();c['keyframes']=[{'time':0,**{k:c[k] for k in v.KEYS}},{'time':2,**{k:c[k] for k in v.KEYS},'x':100}];h=v.History(p);v.split(p,c['id'],1);h.commit(p)
        self.assertEqual(len(p['clips']),2);self.assertAlmostEqual(p['clips'][1]['keyframes'][0]['x'],50);self.assertAlmostEqual(p['clips'][1]['start'],1)
        self.assertEqual(len(h.step(-1)['clips']),1);self.assertEqual(len(h.step(1)['clips']),2)
        with tempfile.TemporaryDirectory() as d:
            file=Path(d)/'project.cyber80.json';v.save(p,file);self.assertEqual(v.load(file),p)
    def test_frame_boundaries_locked_layer_and_validation(self):
        p,c=self.fixture();self.assertAlmostEqual(v.snap(p,.041),.04)
        with self.assertRaises(ValueError):v.split(p,c['id'],0)
        p['tracks'][1]['locked']=True
        with self.assertRaises(ValueError):v.split(p,c['id'],1)
        p['tracks'][1]['locked']=False
        for key,value in [('opacity',2),('start',float('nan')),('speed',11),('color','red;movie=bad')]:
            q=copy.deepcopy(p);q['clips'][0][key]=value
            with self.assertRaises(ValueError):v.validate(q)
        q=copy.deepcopy(p);q['clips'][0]['track']=q['tracks'][6]['id']
        with self.assertRaises(ValueError):v.validate(q)
    def test_trim_source_bounds_and_keyframe_interpolation(self):
        p,c=self.fixture();c.update(kind='video',path=str(Path('sample.mp4').resolve()),source_duration=10,duration=4,speed=2,has_audio=False)
        v.validate(p);left=v.slice_clip(c,1,3);self.assertEqual((left['in'],left['duration']),(2,2));self.assertEqual(c['in'],0)
        c['in']=3
        with self.assertRaises(ValueError):v.validate(p)
    def test_real_layer_composition_pixels_audio_subtitles_and_still(self):
        ff=ffmpeg()
        with tempfile.TemporaryDirectory() as d:
            d=Path(d);source=d/'source.mp4';music=d/'music.wav'
            subprocess.run([ff,'-v','error','-y','-f','lavfi','-i','color=c=red:s=160x120:r=10:d=1.6','-f','lavfi','-i','sine=frequency=440:duration=1.6','-c:v','libx264','-c:a','aac','-shortest',str(source)],check=True,**r.flags())
            subprocess.run([ff,'-v','error','-y','-f','lavfi','-i','sine=frequency=880:duration=1.6',str(music)],check=True,**r.flags())
            checksum=hashlib.sha256(source.read_bytes()).digest();meta=r.probe(ff,source);self.assertTrue(meta['has_audio'])
            p=v.new_project();p['settings'].update(width=320,height=240,fps='10',background='#0000ff',ducking=True)
            clip=v.new_clip(p['tracks'][1]['id'],'video',source.resolve(),1.2,source_duration=meta['duration'],has_audio=True,width=50,height=50)
            green=v.new_clip(p['tracks'][2]['id'],'color',duration=1.2,color='#00ff00',x=60,y=10,width=25,height=25)
            voice=v.new_clip(p['tracks'][5]['id'],'audio',music.resolve(),1.2,source_duration=1.6,volume=-12)
            bg=v.new_clip(p['tracks'][6]['id'],'audio',music.resolve(),1.2,source_duration=1.6,volume=-20)
            p['clips']=[clip,green,voice,bg];out=d/'export.mp4';r.render(ff,p,out)
            image=subprocess.run([ff,'-v','error','-ss','0.3','-i',str(out),'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','pipe:1'],check=True,stdout=subprocess.PIPE,**r.flags()).stdout
            def pixel(x,y):return tuple(image[(y*320+x)*3:(y*320+x)*3+3])
            red=pixel(40,40);g=pixel(220,50);blue=pixel(290,210);self.assertGreater(red[0],180);self.assertLess(red[1],50);self.assertGreater(g[1],180);self.assertGreater(blue[2],180)
            audio=subprocess.run([ff,'-v','error','-i',str(out),'-vn','-t','0.5','-f','s16le','-ac','1','pipe:1'],check=True,stdout=subprocess.PIPE,**r.flags()).stdout;self.assertGreater(len(audio),10000);self.assertTrue(any(audio))
            clip['speed']=2;clip['duration']=.6;r.render(ff,p,d/'speed.mp4');clip['speed']=1;clip['duration']=1.2
            p['clips'].append(v.new_clip(p['tracks'][3]['id'],'text',duration=1.2,text="Cyber80's title: video",y=50,height=25))
            p['clips'].append(v.new_clip(p['tracks'][4]['id'],'subtitle',duration=1.2,text='1\n00:00:00,000 --> 00:00:01,100\nSubtitle Indonesia\n'))
            r.render(ff,p,d/'captioned.mp4')
            caption=subprocess.run([ff,'-v','error','-ss','0.3','-i',str(d/'captioned.mp4'),'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','pipe:1'],check=True,stdout=subprocess.PIPE,**r.flags()).stdout
            ys=[y for y in range(130,170) for x in range(20,300) if caption[(y*320+x)*3]>170 and caption[(y*320+x)*3+1]>170]
            self.assertTrue(ys);self.assertGreaterEqual(max(ys)-min(ys),5,'Text became unreadably small inside its box')
            r.render(ff,p,d/'still.png',still=.3);self.assertTrue((d/'still.png').read_bytes().startswith(b'\x89PNG'))
            self.assertEqual(hashlib.sha256(source.read_bytes()).digest(),checksum)
            with self.assertRaises(ValueError):r.render(ff,p,source)
            self.assertEqual(hashlib.sha256(source.read_bytes()).digest(),checksum)
    def test_animated_transforms_opacity_speed_and_cancel_preserve_target(self):
        ff=ffmpeg()
        with tempfile.TemporaryDirectory() as d:
            d=Path(d);p,c=self.fixture();p['settings'].update(width=160,height=120,fps='10');c.update(duration=1,fade_in=.1,fade_out=.1)
            c['keyframes']=[{'time':0,**{k:c[k] for k in v.KEYS},'opacity':.3},{'time':1,**{k:c[k] for k in v.KEYS},'x':50,'scale':.5,'opacity':.8}]
            out=d/'animation.mp4';r.render(ff,p,out);self.assertGreater(out.stat().st_size,1000)
            c.update(chroma=True,chroma_color='#ff0000',blur=1.,fit='cover');r.render(ff,p,d/'chroma.mp4')
            previous=out.read_bytes()
            with self.assertRaises(InterruptedError):r.render(ff,p,out,cancelled=lambda:True)
            self.assertEqual(out.read_bytes(),previous);self.assertFalse(list(d.glob('*.partial.mp4')))
