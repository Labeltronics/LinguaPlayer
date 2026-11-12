import gzip,hashlib,unittest
from internet_tv import parse_m3u,catalog,parse_xmltv,filter_rows
from parental_control import ParentalLock
class TVTests(unittest.TestCase):
    def test_playlist_and_parental_filter(self):
        text='#EXTM3U\n#EXTINF:-1 tvg-id="news.id" tvg-country="ID" group-title="News",Berita\nhttps://example.test/live.m3u8\n#EXTINF:-1 group-title="18+",Acara dewasa\nhttps://example.test/age.m3u8\n#EXTINF:-1,Invalid\nfile:///secret\n'
        rows=parse_m3u(text);self.assertEqual(len(rows),2);self.assertEqual(len(filter_rows(rows)),1);self.assertEqual(len(filter_rows(rows,unlocked=True)),2);self.assertEqual(filter_rows(rows,country='ID')[0]['name'],'Berita')
        with self.assertRaises(ValueError):parse_m3u('#EXTM3U\n#EXT-X-TARGETDURATION:6\nseg.ts')
    def test_catalog_omits_nsfw_and_invalid_urls(self):
        channels=[{'id':'a','name':'A','country':'ID'},{'id':'b','name':'B','is_nsfw':True}];streams=[{'channel':'a','url':'https://example.test/a'},{'channel':'b','url':'https://example.test/b'},{'channel':'a','url':'file:///etc/test'}]
        self.assertEqual(len(catalog(channels,streams)),1)
    def test_xmltv_and_program_search(self):
        data=b'<tv><programme channel="news.id" start="20261112080000 +0000" stop="20261112090000 +0000"><title>Berita Dunia</title></programme></tv>'
        programs=parse_xmltv(gzip.compress(data));rows=parse_m3u('#EXTM3U\n#EXTINF:-1 tvg-id="news.id",TV\nhttps://example.test/tv')
        self.assertEqual(len(filter_rows(rows,'Berita',programs=programs)),1)
        with self.assertRaises(ValueError):parse_xmltv(b'<!DOCTYPE tv [<!ENTITY a "x">]><tv/>')
    def test_pin_hash_change_retry_and_session_lock(self):
        class Settings:
            def __init__(self):self.d={}
            def value(self,k,default=None):return self.d.get(k,default)
            def setValue(self,k,v):self.d[k]=v
        settings=Settings();salt='ab'*16;settings.d={'iptv/pin_salt':salt,'iptv/pin_hash':hashlib.pbkdf2_hmac('sha256',b'123456',bytes.fromhex(salt),200000).hex()}
        lock=ParentalLock(settings);self.assertTrue(lock.unlock('123456'));lock.change('123456','654321');self.assertFalse(lock.unlocked);self.assertTrue(lock.unlock('654321'));lock.lock();self.assertFalse(lock.unlocked)
        for _ in range(5):self.assertFalse(lock.verify('wrong'))
        self.assertFalse(lock.verify('654321'))
