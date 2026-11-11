"""Cyber80 Video Studio: layered timeline, properties, history, preview and offline render."""
import copy,json,time,os,tempfile,uuid
from pathlib import Path
from PySide6.QtCore import Qt,QTimer,QThread,Signal,QRectF,QPointF
from PySide6.QtGui import QColor,QPainter,QPen,QPixmap,QShortcut,QKeySequence
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QSplitter,QWidget,QScrollArea,QListWidget,QListWidgetItem,QFormLayout,QDoubleSpinBox,QSpinBox,QComboBox,QCheckBox,QLineEdit,QTextEdit,QFileDialog,QMessageBox,QInputDialog,QColorDialog,QDialogButtonBox)
import imageio_ffmpeg
import video_project as vp
from video_render import render,probe
class RenderJob(QThread):
    progress=Signal(float);success=Signal(str);failure=Signal(str)
    def __init__(self,p,path,mode='CPU',preview=False,still=None):super().__init__();self.p=copy.deepcopy(p);self.path=path;self.mode=mode;self.preview=preview;self.still=still;self.proc=None
    def cancel(self):
        self.requestInterruption()
        if self.proc:
            try:self.proc.kill()
            except OSError:pass
    def run(self):
        try:self.success.emit(render(imageio_ffmpeg.get_ffmpeg_exe(),self.p,self.path,self.mode,self.preview,self.still,self.isInterruptionRequested,self.progress.emit,lambda proc:setattr(self,'proc',proc)))
        except Exception as exc:self.failure.emit(str(exc))
class ProbeJob(QThread):
    asset=Signal(object);failure=Signal(str)
    def __init__(self,paths):super().__init__();self.paths=paths
    def run(self):
        for path in self.paths:
            if self.isInterruptionRequested():break
            try:self.asset.emit(probe(imageio_ffmpeg.get_ffmpeg_exe(),path))
            except Exception as exc:self.failure.emit(str(exc))
class Timeline(QWidget):
    selected=Signal(str);seek=Signal(float);edited=Signal();zoomed=Signal(float)
    LEFT=150;TOP=30;ROW=62
    def __init__(self,studio):
        super().__init__();self.studio=studio;self.scale=30.;self.drag=None;self.setMouseTracking(True)
    def refresh(self):
        width=min(16000000,round(self.LEFT+max(20,vp.duration(self.studio.project)+5)*self.scale));height=self.TOP+len(self.studio.project['tracks'])*self.ROW;self.setMinimumSize(width,height);self.resize(width,height);self.update()
    def clip_rect(self,c):
        ids=[t['id'] for t in self.studio.project['tracks']];i=ids.index(c['track']);return QRectF(self.LEFT+c['start']*self.scale,self.TOP+i*self.ROW+5,max(4,c['duration']*self.scale),self.ROW-10)
    def paintEvent(self,event):
        p=QPainter(self);p.fillRect(self.rect_window(),QColor('#111827'));project=self.studio.project
        step=1 if self.scale>=35 else 5 if self.scale>=8 else 30
        lo=max(0,int((event.rect().left()-self.LEFT)/self.scale)//step*step);hi=max(lo,int((event.rect().right()-self.LEFT)/self.scale)+step)
        for t in range(lo,hi+1,step):
            x=self.LEFT+t*self.scale;p.setPen(QColor('#283548'));p.drawLine(int(x),0,int(x),self.height());p.setPen(QColor('#a7b4ca'));p.drawText(int(x)+3,19,f'{t}s')
        for i,track in enumerate(project['tracks']):
            y=self.TOP+i*self.ROW;p.fillRect(0,y,self.LEFT,self.ROW,QColor('#243045' if track['id']==self.studio.selected_track else '#192235'));p.setPen(QColor('#ebf0fa'));p.drawText(8,y+23,track['name'][:21]);p.setPen(QColor('#9eb0c9'));p.drawText(8,y+43,('LOCK ' if track['locked'] else '')+('HIDE ' if track['hidden'] else '')+('MUTE ' if track['muted'] else '')+('SOLO' if track['solo'] else ''))
        colors={'video':'#2867b3','image':'#7e46ae','color':'#6556a0','text':'#a16c29','subtitle':'#967724','audio':'#238675'}
        for c in project['clips']:
            r=self.clip_rect(c);p.setPen(QPen(QColor('#ffe590' if c['id']==self.studio.selected else '#59708d'),2 if c['id']==self.studio.selected else 1));p.setBrush(QColor(colors[c['kind']]));p.drawRoundedRect(r,5,5);p.setPen(QColor('white'));p.drawText(r.adjusted(7,4,-5,-4),Qt.AlignLeft|Qt.AlignVCenter,p.fontMetrics().elidedText(c['name'],Qt.ElideRight,max(1,int(r.width()-12))))
            if c['fade_in']:p.drawLine(r.topLeft(),QPointF(r.left()+min(r.width(),c['fade_in']*self.scale),r.bottom()))
            if c['fade_out']:p.drawLine(QPointF(r.right()-min(r.width(),c['fade_out']*self.scale),r.bottom()),r.topRight())
            for k in c['keyframes']:
                x=r.left()+k['time']*self.scale;p.fillRect(QRectF(x-2,r.bottom()-7,4,4),QColor('#fff1b4'))
        x=self.LEFT+self.studio.playhead*self.scale;p.setPen(QPen(QColor('#ff6b7a'),2));p.drawLine(int(x),0,int(x),self.height())
    def rect_window(self):return super().rect()
    def mousePressEvent(self,event):
        point=event.position();p=self.studio.project
        if point.x()<self.LEFT and point.y()>=self.TOP:
            i=int((point.y()-self.TOP)//self.ROW)
            if i<len(p['tracks']):self.studio.select_track(p['tracks'][i]['id'])
            return
        for c in reversed(p['clips']):
            r=self.clip_rect(c)
            if r.contains(point):
                self.selected.emit(c['id'])
                if vp.track(p,c['track'])['locked']:return
                mode='left' if point.x()-r.left()<8 else 'right' if r.right()-point.x()<8 else 'move';self.drag=(copy.deepcopy(c),point.x(),mode);return
        self.seek.emit(max(0,vp.snap(p,(point.x()-self.LEFT)/self.scale)))
    def mouseMoveEvent(self,event):
        if not self.drag:return
        old,x,mode=self.drag;p=self.studio.project;c=next(c for c in p['clips'] if c['id']==old['id']);delta=vp.snap(p,(event.position().x()-x)/self.scale);changed=copy.deepcopy(old);minimum=1/vp.fps(p)
        if mode=='move':
            changed['start']=max(0,vp.snap(p,old['start']+delta));row=int((event.position().y()-self.TOP)//self.ROW)
            if 0<=row<len(p['tracks']) and not p['tracks'][row]['locked'] and vp.compatible(p['tracks'][row],old):changed['track']=p['tracks'][row]['id']
            if self.studio.snapping.isChecked():
                targets=[self.studio.playhead]+[v for other in p['clips'] if other['id']!=old['id'] for v in (other['start'],other['start']+other['duration'])]
                for target in sorted(targets,key=lambda t:abs(t-changed['start'])):
                    if abs(target-changed['start'])*self.scale<7:changed['start']=max(0,vp.snap(p,target));break
        elif mode=='left':
            delta=max(0,min(old['duration']-minimum,delta));changed=vp.slice_clip(old,old['start']+delta,old['start']+old['duration'])
        else:
            length=max(minimum,old['duration']+delta)
            if old['kind'] in ('video','audio') and old['source_duration']:length=min(length,(old['source_duration']-old['in'])/old['speed'])
            changed['duration']=max(minimum,vp.snap(p,length));changed['keyframes']=[k for k in changed['keyframes'] if k['time']<=changed['duration']]
        c.clear();c.update(changed);self.update()
    def mouseReleaseEvent(self,event):
        if self.drag:self.drag=None;self.edited.emit()
    def wheelEvent(self,event):
        if event.modifiers()&Qt.ControlModifier:self.scale=max(1,min(300,self.scale*(1.2 if event.angleDelta().y()>0 else 1/1.2)));self.refresh();self.zoomed.emit(self.scale);event.accept()
        else:event.ignore()
class VideoStudio(QDialog):
    def __init__(self,owner):
        super().__init__(owner,Qt.Window);self.owner=owner;self.project=vp.new_project();self.history=vp.History(self.project);self.project_path=None;self.selected='';self.selected_track=self.project['tracks'][1]['id'];self.playhead=0.;self.dirty=False;self.released=False;self.job=None;self.import_job=None;self.job_kind='';self.last_output='';self.proxy_player=None;self.assets=[];self.fields={};self.revision=0;self.pending_still=False;self.job_revision=0;self.cache=tempfile.TemporaryDirectory(prefix='cyber80-studio-');self.autosave_path=owner.log_path.parent/f'video-studio-autosave-{owner.window_number}.cyber80.json'
        self.setWindowTitle('Cyber80 Video Studio • Multilayer Editor');self.resize(1400,900);self.setAcceptDrops(True)
        box=QVBoxLayout(self)
        for buttons in [[('Proyek baru',self.new),('Buka proyek',self.open),('Simpan',self.save),('Simpan sebagai',lambda:self.save(True)),('Pulihkan autosave',self.recover),('Undo',lambda:self.undo(-1)),('Redo',lambda:self.undo(1)),('Pengaturan proyek',self.settings_dialog)], [('Impor media',self.import_dialog),('Tambah layer',self.add_track),('Warna / latar',self.add_color),('Teks / judul',self.add_text),('Impor SRT',self.import_srt),('Subtitle AI film aktif',self.copy_ai),('Split di playhead',self.split),('Duplikat',self.duplicate),('Hapus klip',self.delete)], [('Perbarui preview frame',self.preview_frame),('Render & putar proxy',lambda:self.export(True)),('Ekspor MP4',lambda:self.export(False)),('Batalkan render',self.cancel),('Putar hasil',self.play_result),('Relink sumber',self.relink),('Buka sumber di player / AI',self.open_source)]]:
            row=QHBoxLayout();box.addLayout(row)
            for title,fn in buttons:b=QPushButton(title);b.clicked.connect(fn);row.addWidget(b)
        upper=QSplitter(Qt.Horizontal);self.bin=QListWidget();self.bin.setMinimumWidth(150);self.bin.setMaximumWidth(230);self.bin.itemDoubleClicked.connect(self.add_asset);upper.addWidget(self.bin)
        middle=QWidget();mb=QVBoxLayout(middle);self.preview=QLabel('Impor video, gambar, suara atau musik.\nPilih klip untuk mengedit layer.');self.preview.setAlignment(Qt.AlignCenter);self.preview.setMinimumSize(400,230);self.preview.setStyleSheet('background:#090e19;color:#bcd0ee;border:1px solid #334155');mb.addWidget(self.preview,1)
        row=QHBoxLayout();mb.addLayout(row);row.addWidget(QLabel('Playhead'));self.position=QDoubleSpinBox();self.position.setRange(0,86400);self.position.setDecimals(3);self.position.setSuffix(' s');self.position.valueChanged.connect(self.seek);row.addWidget(self.position)
        for title,fn in [('Frame −',lambda:self.seek(max(0,self.playhead-1/vp.fps(self.project)))),('Frame +',lambda:self.seek(self.playhead+1/vp.fps(self.project))),('Awal',lambda:self.seek(0))]:b=QPushButton(title);b.clicked.connect(fn);row.addWidget(b)
        self.summary=QLabel();self.summary.setWordWrap(True);mb.addWidget(self.summary);upper.addWidget(middle)
        panel=QWidget();form=QFormLayout(panel);self.clip_name=QLineEdit();form.addRow('Nama klip',self.clip_name);self.clip_track=QComboBox();form.addRow('Layer tujuan',self.clip_track)
        definitions=[('start','Posisi timeline (s)',0,86400,3),('in','Source in (s)',0,86400,3),('duration','Durasi hasil (s)',.001,86400,3),('speed','Speed',.1,10,2),('x','Posisi X (%)',-200,200,2),('y','Posisi Y (%)',-200,200,2),('width','Lebar kotak (%)',1,400,2),('height','Tinggi kotak (%)',1,400,2),('scale','Skala / zoom',.01,10,2),('opacity','Opacity',0,1,2),('volume','Volume klip (dB)',-60,12,1),('pan','Pan kiri/kanan',-1,1,2),('fade_in','Fade masuk (s)',0,86400,3),('fade_out','Fade keluar (s)',0,86400,3),('brightness','Brightness',-1,1,2),('contrast','Contrast',0,3,2),('saturation','Saturation',0,3,2),('font_size','Ukuran teks (% tinggi)',1,30,2),('blur','Blur',0,20,1),('chroma_similarity','Chroma similarity',.01,1,2),('chroma_blend','Chroma blend',0,1,2)]
        for key,label,lo,hi,decimals in definitions:
            spin=QDoubleSpinBox();spin.setRange(lo,hi);spin.setDecimals(decimals);spin.setSingleStep(.1 if decimals else 1);form.addRow(label,spin);self.fields[key]=spin
        self.fit=QComboBox();self.fit.addItems(['contain','cover','stretch']);form.addRow('Fit / crop',self.fit);self.chroma=QCheckBox('Aktifkan chroma key');form.addRow(self.chroma);self.chroma_color=QLineEdit('#00ff00');form.addRow('Warna chroma',self.chroma_color)
        self.rotation=QComboBox();self.rotation.addItems(['0','90','180','270']);form.addRow('Rotasi',self.rotation);self.color=QLineEdit('#ffffff');form.addRow('Warna #RRGGBB',self.color);self.has_audio=QCheckBox('Gunakan audio video');form.addRow(self.has_audio);self.text=QTextEdit();self.text.setMaximumHeight(110);form.addRow('Teks / SRT',self.text)
        for title,fn in [('Terapkan properti klip',self.apply_properties),('Tambah keyframe di playhead',self.add_keyframe),('Hapus semua keyframe',self.clear_keyframes)]:b=QPushButton(title);b.clicked.connect(fn);form.addRow(b)
        self.keyframes=QListWidget();self.keyframes.setMaximumHeight(90);self.keyframes.itemDoubleClicked.connect(self.goto_keyframe);form.addRow('Keyframe',self.keyframes);scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(panel);scroll.setMinimumWidth(300);upper.addWidget(scroll);upper.setSizes([180,800,330]);box.addWidget(upper,1)
        row=QHBoxLayout();box.addLayout(row);self.track_select=QComboBox();self.track_select.currentIndexChanged.connect(self.track_changed);row.addWidget(self.track_select)
        for title,field in [('Sembunyikan','hidden'),('Kunci','locked'),('Mute','muted'),('Solo audio','solo')]:
            check=QCheckBox(title);setattr(self,'track_'+field,check);row.addWidget(check)
        self.track_volume=QDoubleSpinBox();self.track_volume.setRange(-60,12);self.track_volume.setSuffix(' dB');row.addWidget(self.track_volume)
        for title,fn in [('Terapkan layer',self.apply_track),('Turunkan layer',lambda:self.reorder(-1)),('Naikkan layer',lambda:self.reorder(1))]:b=QPushButton(title);b.clicked.connect(fn);row.addWidget(b)
        self.snapping=QCheckBox('Snapping');self.snapping.setChecked(True);row.addWidget(self.snapping)
        self.timeline=Timeline(self);self.timeline.selected.connect(self.select);self.timeline.seek.connect(self.seek);self.timeline.edited.connect(self.drag_commit);self.timeline_scroll=QScrollArea();self.timeline_scroll.setWidget(self.timeline);self.timeline_scroll.setWidgetResizable(False);self.timeline_scroll.setMinimumHeight(220);self.timeline_scroll.viewport().setStyleSheet('background:#111827');box.addWidget(self.timeline_scroll,1)
        self.status=QLabel('Layer ditumpuk sesuai urutan daftar: dasar → teratas. Drag tengah klip untuk geser; drag ujung untuk trim. Ctrl+scroll mengubah zoom timeline. Preview frame asinkron; proxy untuk playback komposisi.');self.status.setWordWrap(True);box.addWidget(self.status)
        self.debounce=QTimer(self);self.debounce.setSingleShot(True);self.debounce.timeout.connect(self.preview_frame);self.autosave_timer=QTimer(self);self.autosave_timer.timeout.connect(self.autosave);self.autosave_timer.start(30000)
        for sequence,fn in [('Ctrl+S',self.save),('Ctrl+Z',lambda:self.undo(-1)),('Ctrl+Y',lambda:self.undo(1))]:QShortcut(QKeySequence(sequence),self,activated=fn)
        self.refresh()
    def current(self):return next((c for c in self.project['clips'] if c['id']==self.selected),None)
    def message(self,text):self.status.setText(str(text))
    def mutate(self,fn):
        before=copy.deepcopy(self.project)
        try:fn();vp.validate(self.project);self.commit();return True
        except Exception as exc:self.project=before;self.message(exc);self.refresh();return False
    def commit(self):self.history.commit(self.project);self.dirty=True;self.revision+=1;self.refresh();self.debounce.start(350)
    def drag_commit(self):
        try:vp.validate(self.project);self.commit()
        except Exception as exc:self.project=json.loads(self.history.states[self.history.index]);self.refresh();self.message(exc)
    def refresh(self):
        self.timeline.refresh();self.track_select.blockSignals(True);self.track_select.clear()
        for t in self.project['tracks']:self.track_select.addItem(t['name']+' ['+t['kind']+']',t['id'])
        idx=self.track_select.findData(self.selected_track);self.track_select.setCurrentIndex(max(0,idx));self.track_select.blockSignals(False);self.selected_track=self.track_select.currentData();self.track_changed();self.fill_properties()
        s=self.project['settings'];self.summary.setText(f"{s['width']} × {s['height']} • {s['fps']} fps • {vp.duration(self.project):.3f} s • {len(self.project['tracks'])} layer / {len(self.project['clips'])} klip\nPreview maksimal 640×360; render proxy dan ekspor menggunakan komposisi yang sama.");self.setWindowTitle('Cyber80 Video Studio'+(' *' if self.dirty else '')+' • '+(Path(self.project_path).name if self.project_path else 'Proyek baru'))
    def select(self,id):
        self.selected=id;c=self.current()
        if c:self.selected_track=c['track'];self.select_track(c['track'])
        self.fill_properties();self.timeline.update()
    def select_track(self,id):self.selected_track=id;i=self.track_select.findData(id);self.track_select.setCurrentIndex(i);self.track_changed()
    def track_changed(self,*args):
        if not self.track_select.currentData():return
        self.selected_track=self.track_select.currentData();t=vp.track(self.project,self.selected_track)
        for field in ('hidden','locked','muted','solo'):getattr(self,'track_'+field).setChecked(t[field])
        self.track_volume.setValue(t['volume']);self.timeline.update()
    def fill_properties(self):
        c=self.current();self.clip_track.clear();self.keyframes.clear()
        if not c:return
        self.clip_name.setText(c['name'])
        for t in self.project['tracks']:
            if vp.compatible(t,c):self.clip_track.addItem(t['name'],t['id'])
        self.clip_track.setCurrentIndex(self.clip_track.findData(c['track']))
        for key,spin in self.fields.items():spin.setValue(c[key])
        supported=set(self.fields)
        if c['kind']=='audio':supported={'start','in','duration','speed','volume','pan','fade_in','fade_out'}
        elif c['kind']=='subtitle':supported={'start','in','duration','speed','font_size'}
        elif c['kind'] in ('text','color','image'):supported-= {'in','speed','volume','pan'}
        for key,spin in self.fields.items():spin.setEnabled(key in supported)
        self.has_audio.setEnabled(c['kind']=='video' and c.get('source_has_audio',True));self.text.setEnabled(c['kind'] in ('text','subtitle'))
        self.fit.setCurrentText(c.get('fit','contain'));self.chroma.setChecked(c.get('chroma',False));self.chroma_color.setText(c.get('chroma_color','#00ff00'))
        self.rotation.setCurrentText(str(c['rotation']));self.color.setText(c['color']);self.has_audio.setChecked(c['has_audio']);self.text.setPlainText(c['text'])
        for k in sorted(c['keyframes'],key=lambda r:r['time']):item=QListWidgetItem(f"{k['time']:.3f}s  x={k['x']:.1f} y={k['y']:.1f} zoom={k['scale']:.2f}");item.setData(Qt.UserRole,k);self.keyframes.addItem(item)
    def apply_properties(self):
        c=self.current()
        if not c:return
        if vp.track(self.project,c['track'])['locked']:self.message('Layer terkunci.');return
        def change():
            old=copy.deepcopy(c)
            for key,spin in self.fields.items():c[key]=spin.value()
            if c['speed']!=old['speed'] and abs(c['duration']-old['duration'])<.002:c['duration']=old['duration']*old['speed']/c['speed'];c['keyframes']=[{**k,'time':k['time']*old['speed']/c['speed']} for k in c['keyframes']]
            c['start']=vp.snap(self.project,c['start']);c['duration']=max(1/vp.fps(self.project),vp.snap(self.project,c['duration']));c['keyframes']=[k for k in c['keyframes'] if k['time']<=c['duration']];c['fit']=self.fit.currentText();c['chroma']=self.chroma.isChecked();c['chroma_color']=self.chroma_color.text();c['name']=self.clip_name.text()[:160];c['track']=self.clip_track.currentData();c['rotation']=int(self.rotation.currentText());c['color']=self.color.text();c['text']=self.text.toPlainText();c['has_audio']=self.has_audio.isChecked() if c['kind']=='video' else c['kind']=='audio'
            if vp.track(self.project,c['track'])['locked']:raise ValueError('Layer tujuan terkunci.')
        self.mutate(change)
    def apply_track(self):
        def change():
            t=vp.track(self.project,self.selected_track)
            for field in ('hidden','locked','muted','solo'):t[field]=getattr(self,'track_'+field).isChecked()
            t['volume']=self.track_volume.value()
        self.mutate(change)
    def reorder(self,delta):
        def change():
            tracks=self.project['tracks'];i=next(i for i,t in enumerate(tracks) if t['id']==self.selected_track);j=max(0,min(len(tracks)-1,i+delta));tracks[i],tracks[j]=tracks[j],tracks[i]
        self.mutate(change)
    def seek(self,t):
        self.playhead=max(0,vp.snap(self.project,t));self.position.blockSignals(True);self.position.setValue(self.playhead);self.position.blockSignals(False);self.timeline.update();self.debounce.start(300)
    def undo(self,n):self.project=self.history.step(n);self.dirty=True;self.revision+=1;self.refresh();self.debounce.start(350)
    def add_track(self):
        name,ok=QInputDialog.getText(self,'Tambah layer','Nama layer:')
        if not ok or not name:return
        label,ok=QInputDialog.getItem(self,'Jenis layer','Jenis:',['Video / gambar / latar / teks','Subtitle','Suara / narasi','Musik','Audio / SFX'],0,False)
        if ok:self.mutate(lambda:self.project['tracks'].append(vp.new_track(name,{'Video / gambar / latar / teks':'visual','Subtitle':'subtitle','Suara / narasi':'voice','Musik':'music','Audio / SFX':'audio'}[label])))
    def target_track(self,kind):
        sample={'kind':kind};current=vp.track(self.project,self.selected_track)
        if vp.compatible(current,sample) and not current['locked']:return current['id']
        return next((t['id'] for t in self.project['tracks'] if vp.compatible(t,sample) and not t['locked']),None)
    def insert(self,c,at=None):
        if c['track'] is None:self.message('Tidak ada layer cocok yang terbuka.');return
        c['start']=vp.snap(self.project,self.playhead if at is None else at)
        if self.mutate(lambda:self.project['clips'].append(c)):self.select(c['id'])
    def import_dialog(self):
        paths,_=QFileDialog.getOpenFileNames(self,'Impor video / gambar / audio','','Semua media (*.*)');self.import_paths(paths)
    def import_paths(self,paths):
        if not paths:return
        if self.import_job is not None:self.message('Impor sebelumnya belum selesai.');return
        self.import_cursor=max(self.playhead,max((c['start']+c['duration'] for c in self.project['clips'] if c['track']==self.selected_track),default=0));self.import_job=ProbeJob(paths);self.import_job.asset.connect(self.imported);self.import_job.failure.connect(self.message);self.import_job.finished.connect(self.import_finished);self.import_job.start();self.message('Menganalisis media di latar belakang…')
    def imported(self,asset):
        self.assets.append(asset);item=QListWidgetItem(f"{asset['name']}\n{asset['kind']} • {asset['duration']:.2f}s");item.setData(Qt.UserRole,asset);self.bin.addItem(item);self.add_asset(item,at=self.import_cursor);self.import_cursor+=asset['duration']
    def import_finished(self):
        job=self.import_job;self.import_job=None
        if job:job.deleteLater()
        self.message('Impor selesai. Double-click media di koleksi untuk menambahkannya lagi di playhead.')
    def add_asset(self,item,at=None):
        asset=item.data(Qt.UserRole);c=vp.new_clip(self.target_track(asset['kind']),asset['kind'],asset['path'],max(1/vp.fps(self.project),vp.snap(self.project,asset['duration'])),has_audio=asset['has_audio'],source_has_audio=asset['has_audio'],source_duration=asset['duration'],name=asset['name']);self.insert(c,at)
    def add_color(self):
        selected=QColorDialog.getColor(QColor(self.project['settings']['background']),self)
        if selected.isValid():self.insert(vp.new_clip(self.target_track('color'),'color',duration=5,color=selected.name(),name='Latar warna'))
    def add_text(self):self.insert(vp.new_clip(self.target_track('text'),'text',duration=5,text='Judul video',name='Judul',height=30,y=35))
    def insert_subtitle(self,text):
        from core import parse_srt
        cues=parse_srt(text)
        if not cues:self.message('SRT tidak berisi cue yang valid.');return
        length=max(c.end for c in cues);self.insert(vp.new_clip(self.target_track('subtitle'),'subtitle',duration=max(1/vp.fps(self.project),length),text=text,name='Subtitle / lirik'),at=0)
    def import_srt(self):
        path,_=QFileDialog.getOpenFileName(self,'Impor subtitle','','SRT (*.srt)')
        if path:
            try:self.insert_subtitle(Path(path).read_text(encoding='utf-8-sig'))
            except Exception as exc:self.message(exc)
    def copy_ai(self):
        from core import srt
        if not self.owner.cues:self.message('Buat atau impor subtitle pada player utama terlebih dahulu.');return
        from core import Cue
        shift=self.owner.offset.value()/1000
        cues=[Cue(max(0,c.start+shift),max(.001,c.end+shift),c.source,c.target) for c in self.owner.cues if c.end+shift>0]
        self.insert_subtitle(srt(cues,True));self.message('Subtitle film aktif disalin ke proyek. Cocokkan sumber video dan offset sebelum ekspor.')
    def split(self):
        if self.current():self.mutate(lambda:vp.split(self.project,self.selected,self.playhead))
    def delete(self):
        c=self.current()
        if not c:return
        if vp.track(self.project,c['track'])['locked']:self.message('Layer terkunci.');return
        self.mutate(lambda:self.project['clips'].remove(c));self.selected=''
    def duplicate(self):
        c=self.current()
        if c:
            cc=copy.deepcopy(c);cc['id']=vp.uid();self.insert(cc,c['start']+c['duration'])
    def add_keyframe(self):
        c=self.current()
        if not c:return
        if c['kind']=='subtitle':self.message('Keyframe posisi/opacity tidak diterapkan pada track SRT; gunakan judul teks untuk animasi.');return
        local=vp.snap(self.project,self.playhead-c['start'])
        if vp.track(self.project,c['track'])['locked']:self.message('Layer terkunci.');return
        if not 0<=local<=c['duration']:self.message('Pindahkan playhead ke dalam klip.');return
        values={k:self.fields[k].value() for k in vp.KEYS}
        def change():
            if not c['keyframes'] and local>0:c['keyframes'].append({'time':0.,**{k:c[k] for k in vp.KEYS}})
            c['keyframes']=[k for k in c['keyframes'] if abs(k['time']-local)>1e-7]+[{'time':local,**values}]
        self.mutate(change)
    def clear_keyframes(self):
        c=self.current()
        if c and not vp.track(self.project,c['track'])['locked']:self.mutate(lambda:c.update(keyframes=[]))
    def goto_keyframe(self,item):
        c=self.current();kf=item.data(Qt.UserRole);self.seek(c['start']+kf['time'])
        for key in vp.KEYS:self.fields[key].setValue(kf[key])
    def relink(self):
        c=self.current()
        if not c or c['kind'] not in ('video','image','audio'):return
        path,_=QFileDialog.getOpenFileName(self,'Pilih sumber pengganti','','Media (*.*)')
        if path:
            old=c['path']
            def change():
                for clip in self.project['clips']:
                    if clip['path']==old:clip['path']=str(Path(path).resolve())
            self.mutate(change);self.message('Sumber direlink. Periksa lagi durasi dan kesesuaian media pengganti.')
    def open_source(self):
        c=self.current()
        if c and c['kind'] in ('video','audio'):self.owner.open_path(c['path']);self.owner.showNormal();self.owner.raise_()
    def settings_dialog(self):
        dlg=QDialog(self);dlg.setWindowTitle('Format proyek & audio ducking');form=QFormLayout(dlg);s=self.project['settings'];width=QSpinBox();height=QSpinBox()
        for spin,val in ((width,s['width']),(height,s['height'])):spin.setRange(64,4096);spin.setSingleStep(2);spin.setValue(val)
        rate=QComboBox();rate.addItems(['24','24000/1001','25','30','30000/1001','50','60','60000/1001']);rate.setCurrentText(s['fps']);bg=QLineEdit(s['background']);duck=QCheckBox('Turunkan musik otomatis saat layer narasi bersuara');duck.setChecked(s['ducking'])
        for name,widget in [('Lebar',width),('Tinggi',height),('FPS',rate),('Latar #RRGGBB',bg),('Audio ducking',duck)]:form.addRow(name,widget)
        note=QLabel('Contoh: Full HD 1920×1080, 4K 3840×2160, vertikal 1080×1920. Resolusi tidak mengembalikan detail asli yang hilang.');note.setWordWrap(True);form.addRow(note);buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel);buttons.accepted.connect(dlg.accept);buttons.rejected.connect(dlg.reject);form.addRow(buttons)
        if dlg.exec()==QDialog.Accepted:self.mutate(lambda:s.update(width=width.value(),height=height.value(),fps=rate.currentText(),background=bg.text(),ducking=duck.isChecked()))
    def unsaved(self):
        if not self.dirty:return True
        result=QMessageBox.question(self,'Proyek belum disimpan','Simpan perubahan proyek?',QMessageBox.Yes|QMessageBox.No|QMessageBox.Cancel)
        if result==QMessageBox.Cancel:return False
        return self.save() if result==QMessageBox.Yes else True
    def new(self):
        if self.import_job:self.message('Tunggu impor selesai.');return
        if not self.unsaved():return
        self.project=vp.new_project();self.history=vp.History(self.project);self.selected='';self.selected_track=self.project['tracks'][1]['id'];self.project_path=None;self.dirty=False;self.revision+=1;self.assets=[];self.bin.clear();self.refresh();self.seek(0)
    def save(self,save_as=False):
        path=self.project_path
        if save_as or not path:
            path,_=QFileDialog.getSaveFileName(self,'Simpan proyek','video.cyber80.json','Proyek Cyber80 (*.cyber80.json)')
            if not path:return False
            if not path.lower().endswith('.cyber80.json'):path+='.cyber80.json'
        try:vp.save(self.project,path);self.project_path=str(Path(path).resolve());self.dirty=False;self.refresh();self.message('Proyek disimpan. Sumber media tetap berada di lokasi aslinya.');return True
        except Exception as exc:self.message(exc);return False
    def open(self):
        if self.import_job:self.message('Tunggu impor selesai.');return
        if not self.unsaved():return
        path,_=QFileDialog.getOpenFileName(self,'Buka proyek','','Proyek Cyber80 (*.cyber80.json)')
        if path:self.load_path(path)
    def load_path(self,path):
        try:
            self.project=vp.load(path);self.history=vp.History(self.project);self.project_path=path;self.selected='';self.selected_track=self.project['tracks'][1 if len(self.project['tracks'])>1 else 0]['id'];self.dirty=False;self.revision+=1;self.refresh();self.seek(0);self.message('Proyek dibuka. Gunakan Relink jika sumber dipindah.')
        except Exception as exc:self.message(exc)
    def autosave(self):
        if self.dirty and self.owner.storage_enabled and not self.owner.private_session:
            try:vp.save(self.project,self.autosave_path)
            except OSError:self.message('Autosave gagal; simpan proyek secara manual.')
    def recover(self):
        if self.autosave_path.is_file() and self.unsaved():self.load_path(self.autosave_path);self.project_path=None;self.dirty=True;self.refresh()
        elif not self.autosave_path.is_file():self.message('Belum ada autosave untuk dipulihkan.')
    def start_render(self,path,kind,mode='CPU',at=None):
        if self.job is not None:
            if kind=='still':self.pending_still=True
            else:self.message('Tunggu atau batalkan render sebelumnya.')
            return False
        self.job_kind=kind;self.job_revision=self.revision;self.job_time=at;self.pending_still=False;self.job=RenderJob(self.project,path,mode,kind=='proxy',at);self.job.progress.connect(lambda t:self.message(f'Render {kind}: {t:.2f} / {vp.duration(self.project):.2f} detik'));self.job.success.connect(self.rendered);self.job.failure.connect(self.render_failed);self.job.finished.connect(self.render_finished);self.job.start();return True
    def preview_frame(self):
        if self.released:return
        self.start_render(str(Path(self.cache.name)/('frame-'+vp.uid()+'.png')),'still',at=self.playhead)
    def rendered(self,path):
        if self.job_kind=='still':
            if self.job_revision==self.revision and self.job_time is not None and abs(self.job_time-self.playhead)<1/vp.fps(self.project):
                pix=QPixmap(path)
                if not pix.isNull():self.preview.setPixmap(pix.scaled(self.preview.size(),Qt.KeepAspectRatio,Qt.SmoothTransformation))
            Path(path).unlink(missing_ok=True)
        else:
            self.last_output=path;self.message('Selesai: '+Path(path).name)
            if self.job_kind=='proxy':QTimer.singleShot(100,self.play_result)
    def render_failed(self,message):
        if self.job_kind=='still':self.preview.setText('Preview belum tersedia. '+str(message)[:250])
        self.message(message)
    def render_finished(self):
        job=self.job;self.job=None
        if job:job.deleteLater()
        if self.pending_still:self.pending_still=False;self.debounce.start(100)
    def export(self,proxy=False):
        if not self.project['clips']:self.message('Tambahkan klip terlebih dahulu.');return
        self.debounce.stop();mode='CPU'
        if proxy:path=str(Path(self.cache.name)/('proxy-'+vp.uid()+'.mp4'))
        else:
            mode,ok=QInputDialog.getItem(self,'Encoder ekspor','CPU selalu tersedia. GPU memerlukan hardware/driver cocok.',['CPU','NVIDIA NVENC','Intel QSV','AMD AMF'],0,False)
            if not ok:return
            path,_=QFileDialog.getSaveFileName(self,'Ekspor komposisi','Cyber80_Edit.mp4','MP4 (*.mp4)')
            if not path:return
            if not path.lower().endswith('.mp4'):path+='.mp4'
        if self.project_path and Path(path).resolve()==Path(self.project_path).resolve():self.message('Hasil tidak boleh menimpa proyek.');return
        self.start_render(path,'proxy' if proxy else 'export',mode)
    def cancel(self):
        if self.job:self.job.cancel();self.message('Membatalkan render…')
    def play_result(self):
        if not self.last_output or not Path(self.last_output).is_file():self.message('Render proxy/ekspor terlebih dahulu.');return
        from cut_editor import PreviewPlayer
        if self.proxy_player:self.proxy_player.close()
        self.proxy_player=PreviewPlayer(self.owner,self.last_output,'Video Studio • Hasil komposisi');self.proxy_player.show()
    def dragEnterEvent(self,event):
        if event.mimeData().hasUrls() and any(u.isLocalFile() for u in event.mimeData().urls()):event.acceptProposedAction()
    def dropEvent(self,event):self.import_paths([u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]);event.acceptProposedAction()
    def closeEvent(self,event):
        if self.import_job:self.import_job.requestInterruption();self.message('Menunggu impor selesai sebelum menutup.');event.ignore();return
        if self.job:self.cancel();self.message('Menunggu render berhenti sebelum menutup.');event.ignore();return
        if not self.unsaved():event.ignore();return
        self.debounce.stop();self.autosave_timer.stop()
        if self.proxy_player:self.proxy_player.close()
        self.cache.cleanup();self.released=True;event.accept()
