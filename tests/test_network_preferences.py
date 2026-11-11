import unittest,urllib.parse,urllib.request
from network_preferences import google_search_url,google_safe_url,configure,urllib_proxy_handler,proxy_credentials
from web_transfer import GuardedRedirect
class NetworkPreferenceTests(unittest.TestCase):
    def tearDown(self):configure('system')
    def test_google_off_search_and_idempotent_rewrite(self):
        url=google_search_url('video musik Indonesia',True);query=urllib.parse.parse_qs(urllib.parse.urlsplit(url).query);self.assertEqual(query['safe'],['off'])
        rewritten=google_safe_url('https://www.google.co.id/search?q=film&safe=active');self.assertEqual(urllib.parse.parse_qs(urllib.parse.urlsplit(rewritten).query)['safe'],['off']);self.assertEqual(google_safe_url(rewritten),rewritten)
    def test_non_google_and_opt_out_are_not_rewritten(self):
        for url in ('https://example.com/search?q=film&safe=active','https://google.com.example.test/search?q=x','https://www.google.com/maps?q=x'):self.assertEqual(google_safe_url(url),url)
        url='https://www.google.com/search?q=x&safe=active';self.assertEqual(google_safe_url(url,False),url)
    def test_proxy_modes_and_validation(self):
        configure('direct');self.assertEqual(urllib_proxy_handler().proxies,{})
        configure('http','127.0.0.1',8080,'fixture user','fixture:password');proxy=urllib_proxy_handler().proxies;self.assertEqual(set(proxy),{'http','https'});self.assertIn('fixture%20user:fixture%3Apassword@127.0.0.1:8080',proxy['https']);self.assertEqual(proxy_credentials('127.0.0.1'),('fixture user','fixture:password'));self.assertIsNone(proxy_credentials('unrelated.example'))
        for host in ('http://proxy','bad\nproxy','user@proxy',''):
            with self.assertRaises(ValueError):configure('http',host)
    def test_https_downgrade_is_rejected(self):
        request=urllib.request.Request('https://example.com/video',headers={'Cookie':'fixture=secret'})
        with self.assertRaises(ValueError):GuardedRedirect().redirect_request(request,None,302,'Found',{},'http://example.com/video')
