import unittest,tempfile,subprocess,copy
from pathlib import Path
import video_project as vp
from video_templates import apply_template
import video_render as vr
from test_video_project import ffmpeg
class TemplateTests(unittest.TestCase):
    def test_opening_prepend_ending_append_and_atomic_failure(self):
        p=vp.new_project();original=vp.new_clip(p['tracks'][1]['id'],'color',duration=2);p['clips'].append(original)
        result=apply_template(p,'opening',title='Pembukaan',duration=1,placement='prepend');self.assertEqual(next(c for c in p['clips'] if c['id']==original['id'])['start'],1);self.assertEqual(result['duration'],1)
        result=apply_template(p,'ending',title='Terima kasih',duration=1);self.assertEqual(result['start'],3);self.assertEqual(vp.duration(p),4)
        before=copy.deepcopy(p)
        with self.assertRaises(ValueError):apply_template(p,'collage4',photos=[])
        self.assertEqual(p,before);p['tracks'][1]['locked']=True;before=copy.deepcopy(p)
        with self.assertRaises(ValueError):apply_template(p,'opening',placement='prepend')
        self.assertEqual(p,before)
    def test_real_collage_pixels_and_paged_photo_timing(self):
        ff=ffmpeg()
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);photos=[]
            for name,color in [('red','0xff0000'),('green','0x00ff00'),('blue','0x0000ff'),('yellow','0xffff00')]:
                path=root/(name+'.png');subprocess.run([ff,'-v','error','-y','-f','lavfi','-i',f'color=c={color}:s=80x60','-frames:v','1','-update','1',str(path)],check=True,**vr.flags());photos.append(str(path))
            p=vp.new_project();p['settings'].update(width=160,height=120,fps='10');apply_template(p,'collage4',photos=photos,duration=1);target=root/'collage.mp4';vr.render(ff,p,target)
            raw=subprocess.run([ff,'-v','error','-ss','0.4','-i',str(target),'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','pipe:1'],check=True,stdout=subprocess.PIPE,**vr.flags()).stdout
            pixels=[tuple(raw[(y*160+x)*3:(y*160+x)*3+3]) for x,y in [(40,30),(120,30),(40,90),(120,90)]]
            self.assertTrue(pixels[0][0]>180 and pixels[0][1]<60);self.assertTrue(pixels[1][1]>180 and pixels[1][0]<60);self.assertTrue(pixels[2][2]>180);self.assertTrue(pixels[3][0]>180 and pixels[3][1]>180)
            p=vp.new_project();result=apply_template(p,'collage2',photos=photos,duration=1);self.assertEqual(result['duration'],2);self.assertEqual([c['start'] for c in p['clips'] if c['kind']=='image'],[0,0,1,1])
            p=vp.new_project();p['settings'].update(width=160,height=120,fps='10');apply_template(p,'slideshow',photos=photos[:2],duration=.5);vr.render(ff,p,root/'slideshow.mp4');self.assertEqual(vp.duration(p),1)
    def test_lowerthird_quote_and_template_render(self):
        ff=ffmpeg()
        with tempfile.TemporaryDirectory() as d:
            p=vp.new_project();p['settings'].update(width=320,height=240,fps='10');apply_template(p,'quote',title='Cerita indah hari ini',subtitle='Cyber80',duration=.5);apply_template(p,'lowerthird',title='Nama pembicara',subtitle='Keterangan',duration=.5);vr.render(ff,p,Path(d)/'cards.mp4');self.assertEqual(vp.duration(p),1)
