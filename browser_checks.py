"""Offline packaged browser acceptance: local fixtures only, no user websites."""
import os,time,json,tempfile,subprocess,threading,hashlib
from pathlib import Path
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
from unittest.mock import patch
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QApplication,QFileDialog
from PySide6.QtWebEngineCore import QWebEngineSettings
import imageio_ffmpeg

def wait(predicate,seconds=20):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        QApplication.processEvents()
        if predicate():return
        time.sleep(.02)
    raise RuntimeError('Browser acceptance timed out')
def javascript(page,code):
    result=[];page.runJavaScript(code,result.append);wait(lambda:bool(result));return result[0]
def run_browser_checks(owner):
    flags={'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {};ff=imageio_ffmpeg.get_ffmpeg_exe();report={}
    with tempfile.TemporaryDirectory(prefix='cyber80-web-') as d:
        root=Path(d);video=root/'fixture.webm';audio=root/'fixture.wav';payload=b'CYBER80 DOWNLOAD FIXTURE'*4096;(root/'download.bin').write_bytes(payload)
        subprocess.run([ff,'-v','error','-y','-f','lavfi','-i','testsrc2=size=176x144:rate=10:duration=4','-c:v','libvpx','-b:v','150k',str(video)],check=True,**flags)
        subprocess.run([ff,'-v','error','-y','-f','lavfi','-i','sine=frequency=440:duration=4',str(audio)],check=True,**flags)
        (root/'index.html').write_text('<!doctype html><title>Cyber80 browser acceptance</title><h1>Local media test</h1><video id="v" controls muted loop preload="auto" src="fixture.webm"></video><audio id="a" controls loop src="fixture.wav"></audio><a download href="download.bin">Download fixture</a>',encoding='utf-8')
        class Handler(SimpleHTTPRequestHandler):
            def __init__(self,*args,**kwargs):super().__init__(*args,directory=d,**kwargs)
            def log_message(self,*args):pass
        http=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start();base=f'http://127.0.0.1:{http.server_port}'
        browser=owner.open_browser(True);view=browser.current();view.settings().setAttribute(QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture,False)
        try:
            view.setUrl(QUrl(base+'/index.html'));wait(lambda:view.title()=='Cyber80 browser acceptance');wait(lambda:javascript(view.page(),"document.readyState")=='complete')
            report['page_load']='PASS';javascript(view.page(),"document.getElementById('v').play().then(()=>true).catch(()=>false);true")
            wait(lambda:(javascript(view.page(),"document.getElementById('v').currentTime") or 0)>.2);report['actual_webm_playback']='PASS'
            javascript(view.page(),"document.getElementById('a').play().then(()=>true).catch(()=>false);true")
            wait(lambda:(javascript(view.page(),"document.getElementById('a').currentTime") or 0)>.2);report['actual_audio_playback']='PASS'
            browser.scan();wait(lambda:any(v['name']=='fixture.webm' for v in browser.media));wait(lambda:any(v['name']=='fixture.wav' for v in browser.media));report['dom_network_mime_detection']='PASS'
            manager=owner.get_download_manager();target=root/'queued.bin';record=manager.add(base+'/download.bin','queued.bin',target=target,private=True)
            wait(lambda:record['status'] in ('Completed','Failed'));assert record['status']=='Completed',record;assert target.read_bytes()==payload;report['download_queue_real_http']='PASS'
            native=root/'native.bin'
            with patch.object(QFileDialog,'getSaveFileName',return_value=(str(native),'')):
                view.page().download(QUrl(base+'/download.bin'),'native.bin');wait(lambda:native.is_file() or any(r['kind']=='native' and r['status']=='Failed' for r in manager.records))
                assert native.is_file(),'Native browser download failed';assert native.read_bytes()==payload
            report['native_browser_download']='PASS';report['private_profile']=browser.profile.isOffTheRecord();report['browser_codecs']=javascript(view.page(),"JSON.stringify({webm:document.createElement('video').canPlayType('video/webm; codecs=\"vp8\"'),h264:document.createElement('video').canPlayType('video/mp4; codecs=\"avc1.42E01E\"'),mp3:document.createElement('audio').canPlayType('audio/mpeg')})")
        finally:
            javascript(view.page(),"document.querySelectorAll('video,audio').forEach(e=>{e.pause();e.removeAttribute('src');e.load();});true")
            wait(lambda:not owner.get_download_manager().active());browser.hide();view.setUrl(QUrl('about:blank'));QApplication.processEvents();http.shutdown();http.server_close();thread.join()
    return report
