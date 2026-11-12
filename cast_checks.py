"""Packaged LAN receiver checks; no hardware discovery or external sharing in CI."""
import urllib.request
from PySide6.QtWidgets import QApplication
from lan_cast import ShareSession
from core import Cue

def run_cast_checks(owner,root):
    import pychromecast,zeroconf
    from cast_devices import CastAction,DiscoverCast
    from cast_dialog import CastDialog
    source=root/'fixture.mp4';source.write_bytes(b'CYBER80-CAST-RANGE-FIXTURE')
    dialog=owner.open_cast(str(source),'Cast acceptance',[Cue(0,1,'Test','Uji')]);dialog.ip.clear();dialog.ip.addItem('127.0.0.1');dialog.start_share();QApplication.processEvents()
    try:
        share=dialog.share;assert share
        with urllib.request.urlopen(share.url('127.0.0.1')) as r:assert b'<video' in r.read()
        with urllib.request.urlopen(urllib.request.Request(share.media_url('127.0.0.1'),headers={'Range':'bytes=0-6'})) as r:assert r.status==206 and r.read()==b'CYBER80'
        with urllib.request.urlopen(share.url('127.0.0.1','subtitle.vtt')) as r:assert b'Uji' in r.read()
    finally:assert dialog.shutdown()
    assert dialog.share is None and not dialog.isVisible()
    return {'cast_dialog_and_protocol_dependencies':'PASS','token_lan_receiver_and_byte_range':'PASS','webvtt_subtitle_sharing':'PASS','stop_closes_server':'PASS','physical_google_cast_dlna_phone_miracast':'NOT_PERFORMED_NO_HARDWARE'}
