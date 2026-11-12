import unittest
from audio_gain import boost_value,boosted_preamp,dsp_options
class GainTests(unittest.TestCase):
    def test_gain_clamps_and_boost_follows_eq_headroom(self):
        self.assertEqual(boost_value(40),20);self.assertEqual(boost_value(-10),0)
        with self.assertRaises(ValueError):boost_value(float('nan'))
        self.assertEqual(boosted_preamp(0,[0]*10,True,20),20);self.assertEqual(boosted_preamp(0,[6]+[0]*9,True,12),6);self.assertEqual(boosted_preamp(20,[0]*10,True,20),20)
    def test_compressor_not_lost_when_normalizer_is_selected(self):
        values=dsp_options('normalize',12,True);self.assertIn('--audio-filter=normvol:compressor',values);self.assertIn('--compressor-ratio=20',values)
        self.assertEqual(dsp_options('off',0,True),[]);self.assertIn('--audio-filter=compressor',dsp_options('night',0,False))

    def test_native_chain_keeps_eq_and_compressor_and_explicit_bypass(self):
        from audio_gain import native_audio_options
        state={'enabled':True,'preamp':0,'bands':[0]*10,'headroom':True,'boost':12,'peak_guard':True}
        values=native_audio_options(state);self.assertIn('--audio-filter=equalizer:gain:compressor',values);self.assertTrue(any(v.startswith('--equalizer-preamp=12.041') for v in values));self.assertIn('--gain-value=3.98107171',values)
        self.assertEqual(native_audio_options({'enabled':False,'boost':0}),['--audio-filter=','--gain-value=1'])

    def test_flat_eq_neutralizes_native_quarter_gain(self):
        from audio_gain import audio_plan,VLC_EQ_NEUTRAL_DB
        p=audio_plan({'enabled':True,'bands':[0]*10,'preamp':0,'boost':0})
        self.assertAlmostEqual(.25*10**(p['eq_preamp']/20)*p['multiplier'],1,places=6)
        p=audio_plan({'enabled':False,'boost':20});self.assertAlmostEqual(p['multiplier'],10);self.assertNotIn('equalizer',p['filters'])
