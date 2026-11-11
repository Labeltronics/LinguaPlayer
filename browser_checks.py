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
    flags={'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {};ff=imageio_ffmpeg.get_ffmpeg_exe();report={};stage='fixture'
    with tempfile.TemporaryDirectory(prefix='cyber80-web-') as d:
        root=Path(d);video=root/'fixture.webm';audio=root/'fixture.wav';payload=b'CYBER80 DOWNLOAD FIXTURE'*4096;(root/'download.bin').write_bytes(payload);document=b'%PDF-1.4\nCyber80 document fixture\n%%EOF';(root/'document.pdf').write_bytes(document)
        subprocess.run([ff,'-v','error','-y','-f','lavfi','-i','testsrc2=size=176x144:rate=10:duration=4','-c:v','libvpx','-b:v','150k',str(video)],check=True,**flags)
        subprocess.run([ff,'-v','error','-y','-f','lavfi','-i','sine=frequency=440:duration=4',str(audio)],check=True,**flags)
        (root/'index.html').write_text('<!doctype html><title>Cyber80 browser acceptance</title><h1>Local media test</h1><video id="v" controls muted loop preload="auto" src="fixture.webm"></video><audio id="a" controls loop src="fixture.wav"></audio><a download href="download.bin">Download fixture</a><a download href="document.pdf">Download document</a>',encoding='utf-8')
        class Handler(SimpleHTTPRequestHandler):
            def __init__(self,*args,**kwargs):super().__init__(*args,directory=d,**kwargs)
            def log_message(self,*args):pass
        http=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start();base=f'http://127.0.0.1:{http.server_port}'
        browser=owner.open_browser();view=browser.current();view.settings().setAttribute(QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture,False)
        load_events=[];view.loadFinished.connect(lambda ok:load_events.append(bool(ok)))
        try:
            stage='page load'
            view.setUrl(QUrl(base+'/index.html'));wait(lambda:view.title()=='Cyber80 browser acceptance');wait(lambda:javascript(view.page(),"document.readyState")=='complete')
            stage='WebM playback';report['page_load']='PASS';javascript(view.page(),"document.getElementById('v').play().then(()=>true).catch(()=>false);true")
            wait(lambda:(javascript(view.page(),"document.getElementById('v').currentTime") or 0)>.2);report['actual_webm_playback']='PASS'
            stage='audio playback';javascript(view.page(),"document.getElementById('a').play().then(()=>true).catch(()=>false);true")
            wait(lambda:(javascript(view.page(),"document.getElementById('a').currentTime") or 0)>.2);report['actual_audio_playback']='PASS'
            stage='media detection';browser.scan();wait(lambda:any(v['name']=='fixture.webm' for v in browser.media));wait(lambda:any(v['name']=='fixture.wav' for v in browser.media));report['dom_network_mime_detection']='PASS'
            stage='HTTP download queue';manager=owner.get_download_manager();target=root/'queued.bin';record=manager.add(base+'/download.bin','queued.bin',target=target,private=True)
            wait(lambda:record['status'] in ('Completed','Failed'));assert record['status']=='Completed',record;assert target.read_bytes()==payload;report['download_queue_real_http']='PASS'
            stage='document detection and download';wait(lambda:any(v['name']=='document.pdf' for v in browser.media));item=next(v for v in browser.media if v['name']=='document.pdf');doc_target=root/'saved-document.pdf';doc_record=manager.add(item['url'],item['name'],target=doc_target,private=True,provider=browser.headers_for);wait(lambda:doc_record['status'] in ('Completed','Failed'));assert doc_record['status']=='Completed',doc_record;assert doc_target.read_bytes()==document;report['document_detection_and_download']='PASS'
            stage='DNS adapter inspection'
            from dns_settings import DnsDialog
            dns=DnsDialog(owner)
            try:
                wait(lambda:dns.process is not None and dns.process.state().name=='NotRunning');assert dns.rows,dns.status.text();report['dns_adapter_inspection_read_only']='PASS'
            finally:dns.close()
            stage='native Chromium download';native=root/'native.bin'
            with patch.object(QFileDialog,'getSaveFileName',return_value=(str(native),'')):
                view.page().download(QUrl(base+'/download.bin'),'native.bin');wait(lambda:native.is_file() or any(r['kind']=='native' and r['status']=='Failed' for r in manager.records))
                assert native.is_file(),'Native browser download failed';assert native.read_bytes()==payload
            report['native_browser_download']='PASS';report['private_profile']=browser.profile.isOffTheRecord();assert browser.private and browser.profile.isOffTheRecord();assert browser.profile.httpCacheMaximumSize()<=16*1024*1024;report['private_by_default_and_cache_limit']='PASS';report['browser_codecs']=javascript(view.page(),"JSON.stringify({webm:document.createElement('video').canPlayType('video/webm; codecs=\"vp8\"'),h264:document.createElement('video').canPlayType('video/mp4; codecs=\"avc1.42E01E\"'),mp3:document.createElement('audio').canPlayType('audio/mpeg')})")
        except Exception as exc:
            diagnostics={'stage':stage,'title':view.title(),'url':view.url().toString(),'load_events':load_events,'status':browser.status.text(),'media_count':len(browser.media),'dom_rows':getattr(browser,'last_dom_rows',None),'requests_in_flight':len(browser.probes),'queue':[{k:r.get(k) for k in ('status','received','total','message')} for r in owner.get_download_manager().records],'queue_timer':owner.get_download_manager().timer.isActive(),'queue_jobs':len(owner.get_download_manager().jobs),'passed':report}
            raise RuntimeError('Browser acceptance: '+json.dumps(diagnostics)+'; '+str(exc)) from exc
        finally:
            try:javascript(view.page(),"document.querySelectorAll('video,audio').forEach(e=>{e.pause();e.removeAttribute('src');e.load();});true")
            except Exception:pass
            browser.hide();view.setUrl(QUrl('about:blank'));QApplication.processEvents();http.shutdown();http.server_close();thread.join()
    return report
