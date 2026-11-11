import unittest,io,json,urllib.error
from unittest.mock import patch,Mock
import core

class NetworkTests(unittest.TestCase):
    def setUp(self):core._NEXT_REQUEST=0
    def http_error(self,status,message,headers=None):
        return urllib.error.HTTPError('https://generativelanguage.googleapis.com/test',status,'error',headers or {},io.BytesIO(json.dumps({'error':{'message':message}}).encode()))
    @patch('core.wait_cancel')
    @patch('core.urllib.request.urlopen')
    def test_socket_timeout_retries_same_endpoint(self,net,wait):
        net.side_effect=[TimeoutError('timed out'),io.BytesIO(b'{"ok":true}')]
        result=core.request_json('https://generativelanguage.googleapis.com/test','dummy',{},progress=Mock())
        self.assertTrue(result['ok']);self.assertEqual(net.call_count,2)
        self.assertEqual(net.call_args_list[0].args[0].full_url,net.call_args_list[1].args[0].full_url)
        self.assertEqual(net.call_args.kwargs['timeout'],180)
    @patch('core.wait_cancel')
    @patch('core.urllib.request.urlopen',side_effect=TimeoutError('timed out'))
    def test_timeout_has_useful_error(self,net,wait):
        with self.assertRaises(core.APITimeout) as caught:core.request_json('https://example.com','dummy',{})
        self.assertIn('Lanjutkan',str(caught.exception));self.assertEqual(net.call_count,2)
    @patch('core.wait_cancel')
    @patch('core.urllib.request.urlopen')
    def test_permission_does_not_retry_or_leak_key(self,net,wait):
        net.side_effect=self.http_error(403,'Key dummy-secret is not authorised')
        with self.assertRaises(core.APIError) as caught:core.request_json('https://example.com','dummy-secret',{})
        self.assertNotIn('dummy-secret',str(caught.exception));self.assertEqual(net.call_count,1)
    @patch('core.wait_cancel')
    @patch('core.random.uniform',return_value=0)
    @patch('core.urllib.request.urlopen')
    def test_retry_after_is_respected(self,net,jitter,wait):
        net.side_effect=[self.http_error(429,'RequestsPerMinute exceeded',{'Retry-After':'7'}),io.BytesIO(b'{}')]
        core.request_json('https://example.com','dummy',{})
        self.assertTrue(any(c.args[0]==7 for c in wait.call_args_list))
    @patch('core.wait_cancel')
    @patch('core.urllib.request.urlopen')
    def test_daily_quota_stops(self,net,wait):
        net.side_effect=self.http_error(429,'RequestsPerDay free quota exhausted')
        with self.assertRaises(core.APIError):core.request_json('https://example.com','dummy',{})
        self.assertEqual(net.call_count,1)
    @patch('core.urllib.request.urlopen',side_effect=TimeoutError('timed out'))
    def test_cancel_after_first_timeout(self,net):
        state={'cancelled':False}
        def progress(message):
            if 'timeout' in message:state['cancelled']=True
        with self.assertRaises(InterruptedError):core.request_json('https://example.com','dummy',{},lambda:state['cancelled'],progress)
        self.assertEqual(net.call_count,1)
