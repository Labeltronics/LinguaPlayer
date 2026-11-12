"""Native libVLC EQ, persistent presets and audio controls; no network calls."""
import json,math,os,sys
from pathlib import Path
import vlc
from audio_gain import boost_value,boosted_preamp,audio_signature
from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,QCheckBox,QComboBox,QSlider,
    QPushButton,QDoubleSpinBox,QSpinBox,QInputDialog,QFileDialog,QMessageBox)

FREQUENCIES=(60,170,310,600,1000,3000,6000,12000,14000,16000)
# Frequency order follows the ten native libVLC bands, queried again at runtime.
PRESETS={
 'Normal / Flat':[0,0,0,0,0,0,0,0,0,0],
 'Film — seimbang':[3,2,0,-1,1,2,2,1,0,0],
 'Film — aksi':[5,4,1,-1,0,2,3,2,1,0],
 'Dialog / Vokal':[-4,-3,-1,2,4,4,2,0,-1,-2],
 'Musik — seimbang':[2,1,0,0,1,1,1,0,0,0],
 'Rock':[4,3,0,-2,-1,2,4,3,2,1],
 'Pop':[-1,1,3,3,2,0,-1,-1,0,0],
 'Jazz':[2,1,0,1,2,2,1,1,0,0],
 'Klasik':[2,1,0,-1,-1,0,2,3,2,1],
 'Bass boost':[6,5,3,1,0,-1,-1,-1,-1,-1],
 'Treble jernih':[-2,-1,0,0,1,2,4,4,3,2],
 'Headphone — lembut':[2,1,0,0,1,1,0,-1,-2,-2],
 'Malam / Lembut (EQ)':[-5,-4,-2,0,2,2,0,-2,-3,-3],
}

def validate_settings(value):
    def number(x):
        n=float(x)
        if not math.isfinite(n):raise ValueError('Gain harus angka terbatas')
        return max(-20.,min(20.,n))
    bands=value.get('bands',[0.]*10)
    if not isinstance(bands,list) or len(bands)!=10:raise ValueError('Equalizer memerlukan 10 band')
    return {'enabled':bool(value.get('enabled',False)),'preamp':number(value.get('preamp',0)),
            'bands':[number(x) for x in bands],'headroom':bool(value.get('headroom',True)),
            'boost':boost_value(value.get('boost',0)),'peak_guard':bool(value.get('peak_guard',True))}

def effective_preamp(preamp,bands,headroom=True):
    return max(-20.,min(20.,float(preamp)-(max(0.,max(bands)) if headroom else 0.)))

def write_json_atomic(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+'.tmp');temp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8');os.replace(temp,path)

class AudioPanel(QWidget):
    def __init__(self,owner):
        super().__init__();self.owner=owner;self.native=None;self._loading=True;self.custom={};self.native_presets={}
        self.settings_path=owner.log_path.parent/f'audio-{owner.window_number}.json'
        self.persist='--self-test' not in sys.argv and os.getenv('QT_QPA_PLATFORM')!='offscreen'
        box=QVBoxLayout(self);row=QHBoxLayout();box.addLayout(row)
        self.enabled=QCheckBox('Aktifkan equalizer');row.addWidget(self.enabled)
        self.preset=QComboBox();self.preset.setMinimumWidth(170);row.addWidget(self.preset,1)
        save=QPushButton('Simpan preset');save.clicked.connect(self.save_preset);row.addWidget(save)
        reset=QPushButton('Normal');reset.clicked.connect(lambda:self.boost_preset(0));row.addWidget(reset)
        self.headroom=QCheckBox('Auto-headroom');self.headroom.setChecked(True);self.headroom.setToolTip('Mengurangi preamp sesuai boost terbesar. Ini bukan limiter atau kompresor.');row.addWidget(self.headroom)
        self.sliders=[];self.band_labels=[];bands=QHBoxLayout();box.addLayout(bands)
        frequencies=FREQUENCIES
        try:
            if vlc.libvlc_audio_equalizer_get_band_count()==10:frequencies=tuple(vlc.libvlc_audio_equalizer_get_band_frequency(i) for i in range(10))
        except Exception:pass
        for i,hz in enumerate(frequencies):
            column=QVBoxLayout();bands.addLayout(column)
            column.addWidget(QLabel(f'{hz/1000:g}k' if hz>=1000 else f'{hz:g} Hz'),alignment=Qt.AlignHCenter)
            slider=QSlider(Qt.Vertical);slider.setRange(-200,200);slider.setValue(0);slider.setMinimumHeight(105);slider.setToolTip('Gain −20 sampai +20 dB');column.addWidget(slider,alignment=Qt.AlignHCenter)
            label=QLabel('0.0 dB');column.addWidget(label,alignment=Qt.AlignHCenter)
            self.sliders.append(slider);self.band_labels.append(label)
            slider.valueChanged.connect(self.manual_changed)
        row=QHBoxLayout();box.addLayout(row);row.addWidget(QLabel('Preamp'))
        self.preamp=QDoubleSpinBox();self.preamp.setRange(-20,20);self.preamp.setSingleStep(.5);self.preamp.setSuffix(' dB');row.addWidget(self.preamp)
        self.gain_label=QLabel('');row.addWidget(self.gain_label,1)
        row=QHBoxLayout();box.addLayout(row);row.addWidget(QLabel('Audio Boost'));self.boost=QDoubleSpinBox();self.boost.setRange(0,20);self.boost.setSingleStep(1);self.boost.setSuffix(' dB');row.addWidget(self.boost);self.peak_guard=QCheckBox('Penahan puncak (kompresor)');self.peak_guard.setChecked(True);row.addWidget(self.peak_guard)
        for label,value in [('+6 dB',6),('+12 dB',12),('Boost Maks',20),('Reset suara',0)]:
            button=QPushButton(label);button.clicked.connect(lambda checked=False,v=value:self.boost_preset(v));row.addWidget(button)
        self.boost.valueChanged.connect(self.manual_changed);self.peak_guard.toggled.connect(self.changed)
        row=QHBoxLayout();box.addLayout(row)
        row.addWidget(QLabel('Track audio'));self.track=QComboBox();row.addWidget(self.track,1)
        refresh=QPushButton('Muat track');refresh.clicked.connect(self.refresh_tracks);row.addWidget(refresh)
        row.addWidget(QLabel('Kanal'));self.channel=QComboBox()
        for label,value in [('Stereo',1),('Balik stereo',2),('Kiri',3),('Kanan',4)]:self.channel.addItem(label,value)
        self.channel.currentIndexChanged.connect(self.apply_channel);row.addWidget(self.channel)
        row.addWidget(QLabel('Sinkron audio'));self.delay=QSpinBox();self.delay.setRange(-5000,5000);self.delay.setSingleStep(50);self.delay.setSuffix(' ms');self.delay.valueChanged.connect(self.apply_delay);row.addWidget(self.delay)
        hint=QLabel('Preset Malam adalah pengaturan EQ lembut, bukan penyeragam volume otomatis. Auto-headroom mengurangi risiko clipping; tetap sesuaikan volume. Boost bekerja juga saat EQ tidak aktif. Kompresor menahan puncak, tetapi bukan jaminan bebas clipping; volume Windows/perangkat tetap berpengaruh. Pilihan track ini untuk pemutaran. Track sumber AI dipilih terpisah di panel Subtitle / AI.');hint.setWordWrap(True);box.addWidget(hint)
        row=QHBoxLayout();box.addLayout(row)
        export=QPushButton('Ekspor profil suara');export.clicked.connect(self.export_profile);row.addWidget(export)
        imp=QPushButton('Impor profil suara');imp.clicked.connect(self.import_profile);row.addWidget(imp)
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.timeout.connect(self.apply)
        self.preset.currentTextChanged.connect(self.select_preset)
        self.enabled.toggled.connect(self.changed);self.headroom.toggled.connect(self.changed);self.preamp.valueChanged.connect(self.manual_changed)
        self.track.currentIndexChanged.connect(self.choose_track)
        self.rebuild_presets();self.load();self._loading=False;self.changed()
    def boost_preset(self,value):
        self.owner.audio_dsp='off'
        self.set_state({'enabled':value>0,'preamp':0,'bands':[0.]*10,'headroom':value>0,'boost':value,'peak_guard':True})
        self.preset.blockSignals(True);self.preset.setCurrentText('Normal / Flat' if value==0 else 'Manual');self.preset.blockSignals(False)
        self.owner.volume.setValue(200 if value>=20 else 100 if value==0 else max(100,self.owner.volume.value()));self.apply()
        self.owner.status.setText(f'Audio Boost {value:+g} dB • volume {self.owner.volume.value()}%. Bila suara pecah, kurangi boost. Kompresor bukan limiter brick-wall setelah semua gain.')
    def rebuild_presets(self):
        current=self.preset.currentText();self.preset.blockSignals(True);self.preset.clear()
        self.preset.addItems(list(PRESETS));self.preset.addItems(list(self.custom));self.preset.addItem('Manual')
        if self.preset.findText(current)>=0:self.preset.setCurrentText(current)
        self.preset.blockSignals(False)
    def state(self):return validate_settings({'enabled':self.enabled.isChecked(),'preamp':self.preamp.value(),'bands':[s.value()/10 for s in self.sliders],'headroom':self.headroom.isChecked(),'boost':self.boost.value(),'peak_guard':self.peak_guard.isChecked()})
    def set_state(self,state):
        state=validate_settings(state);self._loading=True
        self.enabled.setChecked(state['enabled']);self.preamp.setValue(state['preamp']);self.headroom.setChecked(state['headroom']);self.boost.setValue(state['boost']);self.peak_guard.setChecked(state['peak_guard'])
        for slider,value in zip(self.sliders,state['bands']):slider.setValue(round(value*10))
        self._loading=False;self.changed()
    def select_preset(self,name):
        if self._loading:return
        if name in PRESETS:self.set_state({'enabled':True,'preamp':0,'bands':PRESETS[name],'headroom':self.headroom.isChecked(),'boost':self.boost.value(),'peak_guard':self.peak_guard.isChecked()})
        elif name in self.custom:self.set_state(self.custom[name])
    def manual_changed(self,*args):
        if self._loading:return
        self.preset.blockSignals(True);self.preset.setCurrentText('Manual');self.preset.blockSignals(False);self.changed()
    def changed(self,*args):
        if self._loading:return
        for s,label in zip(self.sliders,self.band_labels):label.setText(f'{s.value()/10:+.1f} dB')
        state=self.state();gain=boosted_preamp(state['preamp'] if state['enabled'] else 0,state['bands'] if state['enabled'] else [0]*10,state['headroom'] if state['enabled'] else False,state['boost'])
        self.gain_label.setText(f'Gain diterapkan: {gain:+.1f} dB • Boost {state["boost"]:+.1f} dB' if state['enabled'] or state['boost'] else 'Bypass — suara asli')
        self.timer.start(80)
    def apply(self):
        if self._loading or self.owner.closing:return
        state=self.state();signature=audio_signature(state,getattr(self.owner,'audio_dsp','off'))
        if signature!=getattr(self.owner,'engine_audio_signature',None):
            self.owner.change_renderer(self.owner.renderer.currentIndex());return
        player=self.owner.player;new=None
        try:
            if state['enabled'] or state['boost']:
                new=vlc.AudioEqualizer()
                if new is None:raise RuntimeError('Equalizer VLC tidak tersedia.')
                if new.set_preamp(boosted_preamp(state['preamp'] if state['enabled'] else 0,state['bands'] if state['enabled'] else [0]*10,state['headroom'] if state['enabled'] else False,state['boost']))==-1:raise RuntimeError('Preamp tidak didukung.')
                for i,gain in enumerate(state['bands'] if state['enabled'] else [0]*10):
                    if new.set_amp_at_index(gain,i)==-1:raise RuntimeError('Band equalizer tidak didukung.')
            # LibVLC set_equalizer replaces the whole filter chain. The engine now
            # loads EQ + dynamics together at startup; this handle validates the profile.
            old=self.native;self.native=new
            if old is not None:old.release()
            new=None
            self.save()
        except Exception as exc:self.owner.status.setText('Equalizer: '+str(exc))
        finally:
            if new is not None:new.release()
    def save(self):
        if self.persist:write_json_atomic(self.settings_path,{'state':self.state(),'custom':self.custom,'preset':self.preset.currentText()})
    def load(self):
        if not self.persist:return
        try:
            data=json.loads(self.settings_path.read_text(encoding='utf-8'))
            self.custom={str(k)[:80]:validate_settings(v) for k,v in data.get('custom',{}).items()}
            self.rebuild_presets();self.set_state(data['state']);self._loading=True;self.preset.setCurrentText(data.get('preset','Manual'))
        except (OSError,ValueError,TypeError,KeyError):pass
    def save_preset(self):
        name,ok=QInputDialog.getText(self,'Simpan preset pribadi','Nama preset:')
        if ok and name.strip():
            name='Saya: '+name.strip()[:60];self.custom[name]=self.state();self.rebuild_presets();self.preset.setCurrentText(name);self.save()
    def export_profile(self):
        path,_=QFileDialog.getSaveFileName(self,'Ekspor profil suara','Cyber80_Audio.json','JSON (*.json)')
        if path:
            try:write_json_atomic(path,{'state':self.state(),'custom':self.custom})
            except Exception as exc:self.owner.error(str(exc))
    def import_profile(self):
        path,_=QFileDialog.getOpenFileName(self,'Impor profil suara','','JSON (*.json)')
        if path:
            try:
                data=json.loads(Path(path).read_text(encoding='utf-8-sig'));state=validate_settings(data['state'])
                custom={str(k)[:80]:validate_settings(v) for k,v in data.get('custom',{}).items()}
                self.custom.update(custom);self.rebuild_presets();self.preset.setCurrentText('Manual');self.set_state(state);self.save()
            except Exception as exc:self.owner.error('Profil suara tidak valid: '+str(exc))
    def refresh_tracks(self):
        self.track.blockSignals(True);self.track.clear()
        try:
            current=self.owner.player.audio_get_track()
            for track_id,label in self.owner.player.audio_get_track_description() or []:
                if isinstance(label,bytes):label=label.decode('utf-8',errors='replace')
                self.track.addItem(str(label),int(track_id))
            index=self.track.findData(current)
            if index>=0:self.track.setCurrentIndex(index)
        except Exception:pass
        self.track.blockSignals(False)
    def choose_track(self,index):
        if index>=0:
            track=self.track.itemData(index)
            if track is not None:self.owner.player.audio_set_track(track)
    def apply_channel(self,*args):
        # VLC 3 channel enum: Stereo=1, Reverse=2, Left=3, Right=4.
        self.owner.player.audio_set_channel(self.channel.currentData())
    def apply_delay(self,*args):self.owner.player.audio_set_delay(self.delay.value()*1000)
    def reapply(self):
        self.apply();self.apply_channel();self.apply_delay()
    def shutdown(self):
        self.timer.stop()
        try:self.save()
        except Exception:pass
        if self.native is not None:self.native.release();self.native=None
