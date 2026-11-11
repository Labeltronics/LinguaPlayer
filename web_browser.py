"""Tabbed Qt WebEngine browser, media detection and download integration."""
import json,urllib.parse,time,re
from pathlib import Path
from PySide6.QtCore import Qt,QUrl,QTimer,QObject,Signal,QRunnable,QThreadPool
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QPushButton,QLineEdit,QTabWidget,QSplitter,QWidget,QTableWidget,QTableWidgetItem,QLabel,QInputDialog,QFileDialog,QMessageBox,QAbstractItemView,QCheckBox,QComboBox,QSpinBox,QFormLayout,QDialogButtonBox)
from PySide6.QtWebEngineCore import QWebEnginePage,QWebEngineProfile,QWebEngineSettings,QWebEngineUrlRequestInterceptor,QWebEngineUrlRequestInfo
from PySide6.QtWebEngineWidgets import QWebEngineView
from web_transfer import checked_url,origin,safe_headers,inspect_media,read_document,MEDIA_EXT,atomic_json
from stream_manifests import hls_plan,dash_plan

DOM_SCAN="""(()=>{let out=[];for(let e of document.querySelectorAll('video,audio,video source,audio source')){let u=e.currentSrc||e.src;if(u)out.push({url:u,kind:e.tagName.toLowerCase(),mime:e.type||''});}for(let e of document.querySelectorAll('a[download]'))if(e.href)out.push({url:e.href,kind:'file',mime:''});return out.slice(0,100);})()"""
class Interceptor(QWebEngineUrlRequestInterceptor):
    candidate=Signal(object)
    def interceptRequest(self,info):
        try:
            if bytes(info.requestMethod())!=b'GET':return
            url=info.requestUrl().toString();path=urllib.parse.urlsplit(url).path.lower();resource=info.resourceType()
            known=Path(path).suffix in MEDIA_EXT
            if resource not in (QWebEngineUrlRequestInfo.ResourceType.ResourceTypeMedia,QWebEngineUrlRequestInfo.ResourceType.ResourceTypeXhr) and not known:return
            if Path(path).suffix in ('.m4s','.vtt','.srt','.key') or re.search(r'(?:seg(?:ment)?|chunk|frag)[-_]?\d+[^/]*\.ts$',path):return
            headers=safe_headers({bytes(k).decode('latin1'):bytes(v).decode('latin1') for k,v in info.httpHeaders().items()})
            # Never reuse a browser playback Range header as the whole-file download range.
            headers={k:v for k,v in headers.items() if k.lower() not in ('range','if-range')}
            self.candidate.emit({'url':url,'headers':headers,'known':known or resource==QWebEngineUrlRequestInfo.ResourceType.ResourceTypeMedia})
        except Exception:pass
class ProbeSignals(QObject):ready=Signal(object)
class Probe(QRunnable):
    def __init__(self,candidate):super().__init__();self.candidate=candidate;self.signals=ProbeSignals()
    def run(self):
        c=self.candidate
        try:
            data=inspect_media(c['url'],c.get('headers'));data['headers']=c.get('headers',{});data['qualities']=[]
            if data['media'] and data['kind'] in ('hls','dash'):
                text,final=read_document(c['url'],c.get('headers'))
                if data['kind']=='hls':data['qualities']=sorted(hls_plan(text,final)['variants'],key=lambda v:v['bandwidth'])
                else:data['qualities']=sorted([v for v in dash_plan(text,final) if v['kind']=='video'],key=lambda v:v['bandwidth'])
            self.signals.ready.emit(data)
        except Exception:
            if c.get('known'):self.signals.ready.emit({'url':c['url'],'name':Path(urllib.parse.urlsplit(c['url']).path).name or 'Media','mime':'belum terkonfirmasi','size':None,'kind':'hls' if urllib.parse.urlsplit(c['url']).path.lower().endswith('.m3u8') else 'dash' if urllib.parse.urlsplit(c['url']).path.lower().endswith('.mpd') else 'file','media':True,'headers':c.get('headers',{}),'qualities':[],'warning':'Metadata belum tersedia; akses/format mungkin dibatasi.'})
            else:self.signals.ready.emit({'media':False})
class WebPage(QWebEnginePage):
    def __init__(self,profile,view):super().__init__(profile,view);self.browser=view.browser;self.rewrites=[]
    def acceptNavigationRequest(self,url,kind,main):
        if url.scheme()=='about':return True
        try:
            value=checked_url(url.toString())
            from network_preferences import google_safe_url
            target=google_safe_url(value,self.browser.safe_search_off.isChecked())
            if target!=value and main:
                now=time.monotonic();self.rewrites=[v for v in self.rewrites if now-v<10]
                if len(self.rewrites)<3:
                    self.rewrites.append(now);QTimer.singleShot(0,lambda:self.load(QUrl(target)));return False
                self.browser.status.setText('Google/jaringan memaksakan SafeSearch; pengaturan akun/jaringan dapat mengunci preferensi Off.')
            return True
        except ValueError:return False
    def javaScriptConsoleMessage(self,*args):pass
class WebView(QWebEngineView):
    def __init__(self,browser):super().__init__();self.browser=browser
    def createWindow(self,kind):return self.browser.add_tab('about:blank')
class BrowserWindow(QDialog):
    def __init__(self,owner,private=False):
        super().__init__(owner,Qt.Window);self.owner=owner;self.private=private;self.manager=owner.get_download_manager();
        from network_preferences import initialize
        initialize(owner.persistence_available);self.setWindowTitle('Cyber80 Browser'+(' • Privat' if private else ''));self.resize(1250,850)
        self.profile=QWebEngineProfile(self) if private or not owner.storage_enabled else QWebEngineProfile(f'Cyber80Browser-{owner.window_number}',self)
        if not self.profile.isOffTheRecord():
            folder=owner.log_path.parent/'browser'/str(owner.window_number);self.profile.setPersistentStoragePath(str(folder/'profile'));self.profile.setCachePath(str(folder/'cache'))
        self.interceptor=Interceptor(self);self.profile.setUrlRequestInterceptor(self.interceptor);self.interceptor.candidate.connect(self.detect)
        self.profile.downloadRequested.connect(lambda request:self.manager.accept_native(request,self.private));self.cookies={};self.profile.cookieStore().cookieAdded.connect(self.cookie_added);self.profile.cookieStore().cookieRemoved.connect(self.cookie_removed);self.profile.cookieStore().loadAllCookies()
        self.media_epoch=0;self.media=[];self.seen=set();self.probes={};self.unknown_budget=30;self.history=[];self.bookmarks=[];self.preview=None
        self.store=owner.log_path.parent/f'browser-bookmarks-{owner.window_number}.json'
        if not private and owner.storage_enabled:
            try:
                data=json.loads(self.store.read_text(encoding='utf-8'));self.bookmarks=data.get('bookmarks',[])[:500];self.history=data.get('history',[])[:200]
            except (OSError,ValueError,TypeError):pass
        box=QVBoxLayout(self);row=QHBoxLayout();box.addLayout(row)
        for text,fn in [('←',lambda:self.current().back()),('→',lambda:self.current().forward()),('⟳',lambda:self.current().reload()),('+ Tab',lambda:self.add_tab('about:blank')),('Bookmark',self.bookmark),('Daftar',self.list_bookmarks),('Riwayat',self.list_history)]:
            button=QPushButton(text);button.clicked.connect(fn);row.addWidget(button)
        self.address=QLineEdit();self.address.setPlaceholderText('Alamat web atau pencarian …');self.address.returnPressed.connect(self.navigate);row.addWidget(self.address,1)
        for text,fn in [('Buka',self.navigate),('Download',lambda:self.manager.show()),('Hapus data',self.clear_data)]:
            b=QPushButton(text);b.clicked.connect(fn);row.addWidget(b)
        row=QHBoxLayout();box.addLayout(row);self.safe_search_off=QCheckBox('Google SafeSearch: Off');self.safe_search_off.setChecked(owner.settings.value('google_safe_off',True,type=bool));self.safe_search_off.toggled.connect(self.save_search_preference);row.addWidget(self.safe_search_off)
        button=QPushButton('Proxy / akses jaringan');button.clicked.connect(self.proxy_settings);row.addWidget(button);row.addWidget(QLabel('Tidak ada filter konten aplikasi. Blokir ISP/akun tetap bergantung koneksi/proxy yang berfungsi.'));row.addStretch()
        self.tabs=QTabWidget();self.tabs.setTabsClosable(True);self.tabs.tabCloseRequested.connect(self.close_tab);self.tabs.currentChanged.connect(self.tab_changed)
        split=QSplitter(Qt.Vertical);split.addWidget(self.tabs);panel=QWidget();pbox=QVBoxLayout(panel);row=QHBoxLayout();pbox.addLayout(row)
        row.addWidget(QLabel('Media terdeteksi • pilih media lalu Download'))
        for label,fn in [('Deteksi ulang',self.scan),('Download media',self.download_selected),('Putar di Cyber80',self.play_selected),('Download → Playlist',self.queue_playlist),('Kosongkan deteksi',self.clear_media)]:
            b=QPushButton(label);b.clicked.connect(fn);row.addWidget(b)
        self.media_table=QTableWidget(0,5);self.media_table.setHorizontalHeaderLabels(['Nama','Jenis/MIME','Ukuran','Kualitas / info','Situs']);self.media_table.setSelectionBehavior(QAbstractItemView.SelectRows);self.media_table.setEditTriggers(QAbstractItemView.NoEditTriggers);self.media_table.horizontalHeader().setStretchLastSection(True);pbox.addWidget(self.media_table)
        split.addWidget(panel);split.setSizes([580,190]);box.addWidget(split,1)
        self.status=QLabel('Deteksi dari permintaan jaringan, MIME/header server dan elemen video/audio. Tekan Play di situs bila media belum muncul. DRM, blob MSE dan akses situs dapat membatasi unduhan.');self.status.setWordWrap(True);box.addWidget(self.status)
        self.scanner=QTimer(self);self.scanner.timeout.connect(self.scan);self.scanner.start(2500);self.add_tab('about:blank')
    def current(self):return self.tabs.currentWidget()
    def add_tab(self,url):
        view=WebView(self);page=WebPage(self.profile,view);view.setPage(page);view.settings().setAttribute(QWebEngineSettings.WebAttribute.FullScreenSupportEnabled,True)
        view.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls,False);view.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls,False)
        page.fullScreenRequested.connect(self.fullscreen_request);page.proxyAuthenticationRequired.connect(self.proxy_authentication);page.renderProcessTerminated.connect(lambda reason,code:self.status.setText(f'Proses tab berhenti: {reason}, kode {code}. Muat ulang tab.'));page.loadingChanged.connect(self.loading_info)
        if hasattr(page,'permissionRequested'):page.permissionRequested.connect(lambda permission:permission.deny())
        view.titleChanged.connect(lambda title,v=view:self.tabs.setTabText(self.tabs.indexOf(v),title[:50] or 'Tab'));view.urlChanged.connect(lambda value,v=view:self.url_changed(v,value));view.loadFinished.connect(lambda ok:self.scan() if ok else None)
        self.tabs.addTab(view,'Tab');self.tabs.setCurrentWidget(view);view.setUrl(QUrl(url));return view
    def loading_info(self,info):
        if info.errorCode():
            message=re.sub(r'https?://\S+','[alamat]',info.errorString())
            self.status.setText(f'Halaman gagal, kode {info.errorCode()}: {message[:240]}')
    def proxy_authentication(self,url,authenticator,host):
        from network_preferences import proxy_credentials
        credentials=proxy_credentials(host)
        if credentials is not None:authenticator.setUser(credentials[0]);authenticator.setPassword(credentials[1])
    def fullscreen_request(self,request):
        request.accept()
        if request.toggleOn():self.showFullScreen()
        else:self.showNormal()
    def close_tab(self,index):
        if self.tabs.count()==1:self.tabs.widget(index).setUrl(QUrl('about:blank'));return
        view=self.tabs.widget(index);self.tabs.removeTab(index);view.page().deleteLater();view.deleteLater()
    def tab_changed(self,*args):
        view=self.current()
        if view:self.address.setText(view.url().toString());self.unknown_budget=30
    def url_changed(self,view,url):
        if view is self.current():self.address.setText(url.toString());self.unknown_budget=30
        if not self.private and url.scheme() in ('http','https'):
            p=urllib.parse.urlsplit(url.toString());safe=urllib.parse.urlunsplit((p.scheme,p.netloc,p.path,'',''));self.history=[v for v in self.history if v!=safe]+[safe];self.history=self.history[-200:];self.save()
    def navigate(self):
        value=self.address.text().strip()
        if not value:return
        if '://' not in value and '.' in value and not any(c.isspace() for c in value):value='https://'+value
        elif '://' not in value:
            from network_preferences import google_search_url
            value=google_search_url(value,self.safe_search_off.isChecked())
        try:self.current().setUrl(QUrl(checked_url(value)))
        except ValueError as exc:self.status.setText(str(exc))
    def save_search_preference(self,value):
        if not self.private and self.owner.storage_enabled:self.owner.settings.setValue('google_safe_off',value)
        self.status.setText('Preferensi SafeSearch diterapkan pada pencarian Google berikutnya. Google/administrator dapat menguncinya.')
    def proxy_settings(self):
        from network_preferences import current,configure,apply_qt,save_private_configuration
        data=current();dialog=QDialog(self);dialog.setWindowTitle('Proxy browser & Download Manager • seluruh proses');form=QFormLayout(dialog);mode=QComboBox()
        for label,key in [('Ikuti proxy sistem / VPN Windows','system'),('Langsung tanpa proxy','direct'),('Proxy HTTP/HTTPS CONNECT','http')]:mode.addItem(label,key)
        mode.setCurrentIndex(max(0,mode.findData(data['mode'])));host=QLineEdit(data['host']);port=QSpinBox();port.setRange(1,65535);port.setValue(data['port']);user=QLineEdit(data['username']);password=QLineEdit(data['password']);password.setEchoMode(QLineEdit.Password)
        for label,widget in [('Mode',mode),('Host/IP',host),('Port',port),('Username opsional',user),('Password opsional',password)]:form.addRow(label,widget)
        note=QLabel('Gunakan proxy yang Anda percaya. Tidak ada server proxy/VPN gratis bawaan. Berlaku untuk browser dan koneksi HTTP downloader baru dalam proses ini. Verifikasi HTTPS dan sandbox tetap aktif.');note.setWordWrap(True);form.addRow(note)
        remember=QCheckBox('Simpan aman di Windows Credential Manager');remember.setEnabled(self.owner.storage_enabled and not self.private);form.addRow(remember)
        buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel);buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject);form.addRow(buttons)
        if dialog.exec()==QDialog.Accepted:
            try:
                configure(mode.currentData(),host.text(),port.value(),user.text(),password.text());apply_qt()
                if remember.isChecked():save_private_configuration()
                self.status.setText('Proxy diterapkan pada koneksi baru. Muat ulang tab; tidak menjamin semua blokir jaringan dapat dilewati.')
            except Exception:self.status.setText('Konfigurasi proxy tidak sah atau tidak dapat disimpan aman.')
    def save(self):
        if not self.private and self.owner.storage_enabled:
            try:atomic_json(self.store,{'bookmarks':self.bookmarks,'history':self.history})
            except OSError:self.status.setText('Bookmark/riwayat tidak dapat disimpan.')
    def bookmark(self):
        url=self.current().url().toString()
        if self.private:self.status.setText('Bookmark tidak disimpan dari sesi privat.');return
        try:url=checked_url(url)
        except ValueError:return
        if url not in self.bookmarks:self.bookmarks.append(url);self.save();self.status.setText('Bookmark disimpan lokal. URL bookmark mengikuti pilihan Anda.')
    def list_bookmarks(self):self.choose_address(self.bookmarks,'Bookmark')
    def list_history(self):self.choose_address(list(reversed(self.history)),'Riwayat (query tidak disimpan)')
    def choose_address(self,items,title):
        if items:
            value,ok=QInputDialog.getItem(self,title,'Buka:',items,0,False)
            if ok:self.current().setUrl(QUrl(value))
    def clear_data(self):
        if QMessageBox.question(self,'Hapus data browser','Hapus cookie, cache dan riwayat browser ini? Bookmark dipertahankan.')==QMessageBox.Yes:
            self.profile.cookieStore().deleteAllCookies();self.profile.clearHttpCache();self.history=[];self.cookies={};self.clear_media();self.save();self.status.setText('Penghapusan cookie/cache diminta. Halaman aktif mungkin perlu dimuat ulang.')
    def cookie_key(self,cookie):return (bytes(cookie.name()),cookie.domain(),cookie.path())
    def cookie_added(self,cookie):self.cookies[self.cookie_key(cookie)]=cookie
    def cookie_removed(self,cookie):self.cookies.pop(self.cookie_key(cookie),None)
    def headers_for(self,url):
        try:p=urllib.parse.urlsplit(checked_url(url))
        except ValueError:return {}
        now=time.time();values=[]
        for cookie in self.cookies.values():
            domain=cookie.domain().lstrip('.').lower();host=p.hostname.lower();path=cookie.path() or '/';requestpath=p.path or '/'
            # Conservative exact host for host-only cookies, suffix match only for explicit domain cookies.
            match=host==domain or (cookie.domain().startswith('.') and host.endswith('.'+domain))
            pathmatch=requestpath==path or (requestpath.startswith(path) and (path.endswith('/') or requestpath[len(path):].startswith('/')))
            if not match or not pathmatch or (cookie.isSecure() and p.scheme!='https'):continue
            if not cookie.isSessionCookie() and cookie.expirationDate().toSecsSinceEpoch()<=now:continue
            values.append(bytes(cookie.name()).decode('latin1')+'='+bytes(cookie.value()).decode('latin1'))
        return {'User-Agent':self.profile.httpUserAgent(),**({'Cookie':'; '.join(values)} if values else {})}
    def scan(self):
        if not self.isVisible() or not self.current():return
        self.current().page().runJavaScript(DOM_SCAN,self.scan_result)
    def scan_result(self,rows):
        if not isinstance(rows,list):return
        for row in rows:
            if isinstance(row,dict) and row.get('url','').startswith(('http://','https://')):self.detect({'url':row['url'],'known':row.get('kind') in ('video','audio','source'),'headers':{}})
    def detect(self,candidate):
        try:url=checked_url(candidate['url'])
        except (KeyError,ValueError):return
        if url in self.seen or len(self.seen)>=500:return
        if not candidate.get('known'):
            if self.unknown_budget<=0:return
            self.unknown_budget-=1
        if len(self.probes)>=12:return
        self.seen.add(url);candidate['headers']={**self.headers_for(url),**candidate.get('headers',{})};probe=Probe(candidate);token=(url,self.media_epoch);self.probes[token]=probe;probe.signals.ready.connect(lambda data,t=token:self.probed(t,data));QThreadPool.globalInstance().start(probe)
    def probed(self,token,data):
        self.probes.pop(token,None)
        if token[1]!=self.media_epoch:return
        if not data.get('media'):return
        if any(v['url']==data['url'] for v in self.media):return
        self.media.append(data);i=self.media_table.rowCount();self.media_table.insertRow(i)
        size=f'{data["size"]/1024/1024:.1f} MiB' if data.get('size') is not None else 'Belum diketahui';info=data.get('warning') or (f'{len(data["qualities"])} pilihan kualitas' if data.get('qualities') else 'Sumber langsung')
        for j,value in enumerate((data['name'],data['mime'],size,info,urllib.parse.urlsplit(data['url']).hostname)):self.media_table.setItem(i,j,QTableWidgetItem(str(value)))
        if self.media_table.currentRow()<0:self.media_table.selectRow(i)
        self.status.setText(f'{len(self.media)} sumber terdeteksi. Pilih baris dan klik Download media.')
    def selected(self):
        i=self.media_table.currentRow();return self.media[i] if 0<=i<len(self.media) else None
    def download_selected(self,playlist=False):
        data=self.selected()
        if not data:return
        quality=999
        if data.get('qualities'):
            labels=[v['label'] for v in data['qualities']];selected,ok=QInputDialog.getItem(self,'Kualitas unduhan','Pilih kualitas:',labels,len(labels)-1,False)
            if not ok:return
            quality=labels.index(selected)
        try:
            record=self.manager.add(data['url'],data['name'],data['kind'],data.get('headers'),quality,private=self.private)
            if record:
                self.manager.providers[record['id']]=self.headers_for
                if playlist:record['auto_playlist']=True
        except (ValueError,OSError) as exc:self.status.setText(str(exc))
    def queue_playlist(self):self.download_selected(True)
    def play_selected(self):
        data=self.selected()
        if not data:return
        from cut_editor import PreviewPlayer
        if self.preview:self.preview.close()
        self.preview=PreviewPlayer(self.owner,data['url'],'Media online (sumber langsung tanpa sesi login)');self.preview.show()
    def clear_media(self):self.media_epoch+=1;self.media=[];self.seen=set();self.media_table.setRowCount(0);self.unknown_budget=30
    def closeEvent(self,event):self.hide();event.ignore()
    def shutdown(self):
        self.scanner.stop();self.media_epoch+=1;self.hide()
        if self.preview:self.preview.close()
        for i in range(self.tabs.count()):self.tabs.widget(i).stop();self.tabs.widget(i).page().deleteLater()
