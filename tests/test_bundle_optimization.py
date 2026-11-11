import tempfile,unittest
from pathlib import Path
from unittest.mock import MagicMock,patch
from optimize_bundle import optimize
from web_transfer import inspect_media,MEDIA_EXT
class BundleTests(unittest.TestCase):
    def test_remove_only_unused_assets_and_keep_runtime(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            keep=['Cyber80Players.exe','_internal/PySide6/Qt6WebEngineCore.dll','_internal/PySide6/resources/qtwebengine_resources.pak','_internal/PySide6/resources/qtwebengine_devtools_resources.pak','_internal/PySide6/translations/qtwebengine_locales/en-US.pak','_internal/PySide6/translations/qtwebengine_locales/id.pak','_internal/PySide6/translations/qtbase_id.qm','_internal/vlc/plugins/codec/decoder.dll','_internal/vlc/plugins/access/http.dll','_internal/models/midas-small.onnx']
            drop=['_internal/PySide6/resources/qtwebengine_devtools_resources.debug.pak','_internal/PySide6/translations/qtwebengine_locales/fr.pak','_internal/PySide6/translations/qtbase_fr.qm','_internal/PySide6/qml/unused.qml','_internal/vlc/locale/fr/text.mo','_internal/vlc/plugins/gui/libqt_plugin.dll']
            for name in keep+drop:
                p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'fixture')
            result=optimize(root);self.assertEqual(result['removed_file_count'],len(drop));self.assertGreater(result['removed_bytes'],0)
            for name in keep:self.assertTrue((root/name).is_file(),name)
            for name in drop:self.assertFalse((root/name).exists(),name)
    def test_arbitrary_folder_is_not_optimized(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):optimize(d)
    def test_document_links_and_attachments_are_downloadable(self):
        response=MagicMock();response.__enter__.return_value=response;response.geturl.return_value='https://example.test/document.pdf';response.headers={'Content-Type':'application/pdf','Content-Length':'7'}
        with patch('web_transfer.open_http',return_value=response):
            self.assertFalse(inspect_media('https://example.test/document.pdf')['media'])
            self.assertTrue(inspect_media('https://example.test/document.pdf',allow_file=True)['media'])
            response.headers['Content-Disposition']='attachment; filename="document.pdf"'
            self.assertTrue(inspect_media('https://example.test/document.pdf')['media'])
        for ext in ('.wma','.wmv','.aiff','.m2ts','.vob','.ape'):self.assertIn(ext,MEDIA_EXT)

    def test_dom_json_transport_and_invalid_payloads(self):
        from web_transfer import decode_scan_rows
        rows=[{'url':'https://example.test/document.pdf','kind':'file'}]
        import json
        self.assertEqual(decode_scan_rows(json.dumps(rows)),rows);self.assertEqual(decode_scan_rows(rows),rows)
        for value in ('not json','{}',None,'x'*131073,[{'url':4},None]):self.assertEqual(decode_scan_rows(value),[])
