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
