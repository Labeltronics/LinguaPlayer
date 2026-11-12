"""One background workspace for subtitles, lyrics and dubbing."""
import os, tempfile, wave, subprocess, sys
from pathlib import Path
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,QLineEdit,QComboBox,QDoubleSpinBox,QSpinBox,QPushButton,QPlainTextEdit,QFileDialog,QMessageBox,QCheckBox,QSystemTrayIcon,QScrollArea,QWidget)
import imageio_ffmpeg
from core import Cue,parse_srt,srt,transcribe
from dubbing import DubbingJob,lrc,protected_target
from video_render import probe

class TextJob(DubbingJob):
    text_ready=Signal(object)
    def __init__(self,source,key,model,language,lyrics=False,stream=0,attachment=False):
        super().__init__(source,'',[],key=key,model=model,language=language,audio_stream=stream);self.lyrics=lyrics;self.attachment=attachment;self.child=None
    def cancel(self):
        super().cancel()
        if self.child:self.child.cancel()
    def run(self):
        try:
            if not self.key:raise ValueError('Isi Gemini API key di panel Subtitle / AI.')
            ff=imageio_ffmpeg.get_ffmpeg_exe();info=probe(ff,self.source)
            if not info['has_audio']:raise ValueError('Sumber tidak memiliki audio.')
            if self.attachment and info['kind']=='video' and not self.lyrics:
                from background_subtitles import BackgroundSubtitleJob
                with tempfile.TemporaryDirectory(prefix='cyber80-language-video-') as temp:
                    result=[];errors=[]
                    self.child=BackgroundSubtitleJob(self.source,str(Path(temp)/'subtitle.srt'),self.key,self.model,self.language,proxy=True,audio_stream=self.audio_stream,persist=False)
                    self.child.progress.connect(self.progress.emit,Qt.DirectConnection)
                    self.child.completed.connect(lambda path,cues:result.extend(cues),Qt.DirectConnection)
                    self.child.failed.connect(errors.append,Qt.DirectConnection)
                    if self.cancelled():raise InterruptedError('Dibatalkan')
                    self.child.run();self.child=None
                    if errors:raise ValueError(errors[0])
                    if self.cancelled():raise InterruptedError('Dibatalkan')
                    self.text_ready.emit(result);return
            cues=[];offset=0.;duration=info['duration']
            with tempfile.TemporaryDirectory(prefix='cyber80-language-') as temp:
                while offset<duration-.05:
                    if self.cancelled():raise InterruptedError('Dibatalkan')
                    length=min(60,duration-offset);audio=Path(temp)/'chunk.wav'
                    self.progress.emit(f'Analisis audio {offset:.0f}–{offset+length:.0f} detik …')
                    self.run_command([ff,'-v','error','-y','-ss',str(offset),'-i',self.source,'-t',str(length),'-map',f'0:a:{self.audio_stream}','-vn','-ac','1','-ar','16000',str(audio)])
                    with wave.open(str(audio)) as w:actual=w.getnframes()/w.getframerate()
                    glossary=('This is song lyric transcription. Transcribe only audible sung words faithfully with line-level timestamps, never invent missing lyrics. No word-level karaoke timing. ' if self.lyrics else '')
                    cues.extend(transcribe(audio.read_bytes(),self.key,self.model,self.language,actual,offset,cancelled=self.cancelled,glossary=glossary,progress=self.progress.emit))
                    offset+=length
            if self.cancelled():raise InterruptedError('Dibatalkan')
            if self.lyrics:cues=[Cue(c.start,c.end,c.source,'',c.language) for c in cues]
            self.text_ready.emit(cues)
        except Exception as exc:
            message=str(exc)
            if self.key:message=message.replace(self.key,'[KEY DISEMBUNYIKAN]')
            self.failed.emit(message[:2000])

class LanguageStudio(QDialog):
    def __init__(self,owner):
        super().__init__(owner,Qt.Window);self.owner=owner;self.job=None;self.text_target='';self.last_output='';self.preview=None;self.setWindowTitle('Cyber80 • Studio Bahasa — Subtitle, Dubbing & Lirik');self.resize(950,790)
        box=QVBoxLayout(self);row=QHBoxLayout();box.addLayout(row);self.source=QLineEdit(owner.path);row.addWidget(self.source,1)
        b=QPushButton('Pilih video / musik');b.clicked.connect(self.pick_source);row.addWidget(b)
        form_widget=QWidget();form=QFormLayout(form_widget);scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(form_widget);scroll.setMinimumHeight(260);scroll.setMaximumHeight(440);box.addWidget(scroll);self.task=QComboBox();self.task.addItems(['Subtitle terjemahan','Lirik asli (SRT / LRC)','Dubbing terjemahan']);form.addRow('Pekerjaan',self.task)
        self.language=QComboBox();self.language.setEditable(True)
        for label,code in [('Indonesia','id'),('English','en'),('Jepang','ja'),('Korea','ko'),('Mandarin','zh'),('Arab','ar'),('Prancis','fr'),('Jerman','de'),('Spanyol','es'),('Hindi','hi'),('Portugis','pt'),('Rusia','ru'),('Turki','tr'),('Vietnam','vi'),('Thailand','th'),('Belanda','nl'),('Italia','it'),('Polandia','pl'),('Ukraina','uk'),('Tamil','ta'),('Bengali','bn'),('Urdu','ur'),('Marathi','mr'),('Telugu','te'),('Rumania','ro'),('Swahili','sw')]:self.language.addItem(label,code)
        form.addRow('Bahasa tujuan / kode ISO',self.language)
        self.stream=QSpinBox();self.stream.setRange(0,99);form.addRow('Track audio sumber (mulai 0)',self.stream)
        self.attachment=QCheckBox('Attachment video Gemini (proxy 720p); musik/lirik memakai potongan audio');form.addRow(self.attachment)
        self.engine=QComboBox();self.engine.addItem('Gemini TTS online (kuota proyek berlaku)','gemini');self.engine.addItem('Suara Windows SAPI offline (harus terpasang)','sapi');form.addRow('Mesin dubbing',self.engine)
        self.model=QLineEdit('gemini-2.5-flash-preview-tts');form.addRow('Model TTS (terpisah dari model subtitle)',self.model)
        from dubbing import VOICES
        self.voice=QComboBox();self.voice.addItems(VOICES);form.addRow('Suara Gemini',self.voice)
        self.sapi=QLineEdit();self.sapi.setPlaceholderText('Kosong = pilih suara sesuai bahasa; nama suara opsional');form.addRow('Suara Windows',self.sapi)
        self.clone=QCheckBox('Pertahankan karakter suara asli • OpenVoice lokal gratis');form.addRow(self.clone)
        from voice_clone import default_tools
        self.tools=QLineEdit(str(default_tools()));row=QHBoxLayout();row.addWidget(self.tools)
        b=QPushButton('Pasang Voice Tools gratis');b.clicked.connect(self.install_tools);row.addWidget(b);form.addRow('Folder tools cloning',row)
        self.reference=QLineEdit();row=QHBoxLayout();row.addWidget(self.reference);b=QPushButton('Pilih sampel suara');b.clicked.connect(self.pick_reference);row.addWidget(b);form.addRow('Referensi (kosong = video sumber)',row)
        row=QHBoxLayout();self.ref_start=QDoubleSpinBox();self.ref_start.setRange(0,86400);self.ref_start.setDecimals(2);row.addWidget(QLabel('Mulai (s)'));row.addWidget(self.ref_start)
        self.ref_duration=QDoubleSpinBox();self.ref_duration.setRange(1,30);self.ref_duration.setValue(6);row.addWidget(QLabel('Durasi (s)'));row.addWidget(self.ref_duration)
        self.per_cue=QCheckBox('Sampel otomatis per dialog dari sumber');row.addWidget(self.per_cue);form.addRow('Sampel satu pembicara yang bersih',row)
        self.mix=QComboBox()
        for title,code in [('Voice-over + audio asli diperkecil','voiceover'),('Ganti semua audio asli','replace'),('Dubbing + instrumental/M&E terpisah','instrumental'),('Dubbing + track audio asli opsional (MKV)','dual')]:self.mix.addItem(title,code)
        form.addRow('Campuran ekspor',self.mix)
        row=QHBoxLayout();self.music=QLineEdit();row.addWidget(self.music);b=QPushButton('Pilih instrumental');b.clicked.connect(self.pick_music);row.addWidget(b);form.addRow('Musik / efek tanpa dialog',row)
        row=QHBoxLayout();self.level=QDoubleSpinBox();self.level.setRange(0,100);self.level.setValue(12);self.level.setSuffix(' % latar');row.addWidget(self.level)
        self.gain=QDoubleSpinBox();self.gain.setRange(10,400);self.gain.setValue(100);self.gain.setSuffix(' % dubbing');row.addWidget(self.gain)
        self.limit=QDoubleSpinBox();self.limit.setRange(1,4);self.limit.setValue(2);self.limit.setSuffix(' x batas tempo');row.addWidget(self.limit);form.addRow('Level / sinkronisasi',row)
        note=QLabel('1. Buat teks di latar belakang atau impor SRT. 2. Periksa/ejaan/waktu di editor. 3. Ekspor dubbing.\nGemini hanya dipakai bila dipilih; tidak mengaktifkan billing atau pindah ke model berbayar. Proyek dengan billing mengikuti tarif Google. Lirik = waktu per baris, bukan suara nyanyian AI. Penggantian audio menghapus musik/efek asli; untuk mempertahankannya sediakan instrumental/M&E.');note.setWordWrap(True);box.addWidget(note)
        row=QHBoxLayout();box.addLayout(row);self.buttons=[]
        for text,fn in [('Buat teks di latar belakang',self.generate),('Impor SRT',self.import_srt),('Ambil subtitle pemutar',self.copy_cues),('Simpan SRT / LRC',self.save_text),('Buat dubbing di latar belakang',self.dub)]:
            b=QPushButton(text);b.clicked.connect(fn);row.addWidget(b);self.buttons.append(b)
        self.editor=QPlainTextEdit();self.editor.setPlaceholderText('SRT yang bisa diedit: waktu dan teks bahasa tujuan.');box.addWidget(self.editor,1)
        row=QHBoxLayout();box.addLayout(row);self.cancel_button=QPushButton('Batalkan');self.cancel_button.clicked.connect(self.cancel);self.cancel_button.setEnabled(False);row.addWidget(self.cancel_button)
        b=QPushButton('Putar hasil');b.clicked.connect(self.play_output);row.addWidget(b);b=QPushButton('Video subtitle / lirik');b.clicked.connect(self.burn_text);row.addWidget(b);b=QPushButton('Sembunyikan • proses tetap jalan');b.clicked.connect(self.hide);row.addWidget(b)
        self.status=QLabel('Siap. Tidak ada file dikirim sebelum tombol Buat teks / dubbing online ditekan.');self.status.setWordWrap(True);box.addWidget(self.status)
        self.tray=None
        if QSystemTrayIcon.isSystemTrayAvailable():self.tray=QSystemTrayIcon(owner.windowIcon(),self);self.tray.setToolTip('Cyber80 Studio Bahasa');self.tray.show()
    def code(self):return self.language.currentData() if self.language.currentIndex()>=0 and self.language.currentText()==self.language.itemText(self.language.currentIndex()) else self.language.currentText().strip()
    def install_tools(self):
        if os.name!='nt':self.failed('Installer Voice Tools tersedia untuk Windows.');return
        script=Path(__file__).resolve().parent/'voice_tools'/'setup_windows.ps1'
        # Explicit install button launches the bundled installer in its own console.
        subprocess.Popen(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-NoExit','-File',str(script),'-Destination',self.tools.text()],creationflags=subprocess.CREATE_NEW_CONSOLE)
        self.status.setText('Installer dibuka. Unduhan dapat melebihi 1 GB. Tunggu tulisan Selesai sebelum cloning. Tidak ada biaya API untuk OpenVoice.')
    def pick_reference(self):
        p,_=QFileDialog.getOpenFileName(self,'Sampel satu pembicara yang bersih','','Media (*.*)')
        if p:self.reference.setText(p);self.per_cue.setChecked(False)
    def pick_source(self):
        p,_=QFileDialog.getOpenFileName(self,'Pilih media',self.source.text(),'Media (*.*)')
        if p:self.source.setText(p);self.editor.clear();self.last_output=''
    def pick_music(self):
        p,_=QFileDialog.getOpenFileName(self,'Pilih instrumental / M&E','','Audio (*.*)')
        if p:self.music.setText(p)
    def start(self,job):
        if self.job is not None:return
        self.job=job;job.progress.connect(self.status.setText);job.failed.connect(self.failed);job.finished.connect(self.finished)
        for b in self.buttons:b.setEnabled(False)
        for w in (self.source,self.task,self.stream,self.language):w.setEnabled(False)
        self.editor.setReadOnly(True);self.cancel_button.setEnabled(True);job.start()
    def generate(self):
        if self.job:return
        if not Path(self.source.text()).is_file():self.failed('Pilih file media lokal.');return
        if self.editor.toPlainText().strip() and QMessageBox.question(self,'Buat teks','Teks editor akan diganti ketika analisis selesai. Lanjutkan?')!=QMessageBox.Yes:return
        target,_=QFileDialog.getSaveFileName(self,'Simpan teks latar belakang dengan nama baru',str(Path(self.source.text()).with_suffix(''))+'.Cyber80.srt','SRT (*.srt)')
        if not target:return
        try:
            protected_target(self.source.text(),target,[self.music.text()])
            if self.task.currentIndex()==1:protected_target(self.source.text(),str(Path(target).with_suffix('.lrc')),[target,self.music.text()])
        except Exception as exc:self.failed(str(exc));return
        self.text_target=target
        job=TextJob(self.source.text(),self.owner.key.text().strip(),self.owner.model.text().strip(),self.code(),self.task.currentIndex()==1,self.stream.value(),self.attachment.isChecked());job.text_ready.connect(self.text_ready);self.start(job)
    def text_ready(self,cues):
        self.editor.setPlainText(srt(cues))
        try:
            if self.text_target:
                target=protected_target(self.source.text(),self.text_target,[self.music.text()])
                with target.open('x',encoding='utf-8') as out:out.write(srt(cues))
                if self.task.currentIndex()==1:
                    with target.with_suffix('.lrc').open('x',encoding='utf-8') as out:out.write(lrc(cues))
        except Exception as exc:self.failed('Teks tersedia di editor, tetapi penyimpanan gagal: '+str(exc));return
        self.notify(f'Teks selesai: {len(cues)} baris. Periksa sebelum membuat dubbing.');self.owner.last_attachment_subtitle={'source':self.source.text(),'cues':cues,'path':''}
    def import_srt(self):
        p,_=QFileDialog.getOpenFileName(self,'Impor SRT','','SRT (*.srt)')
        if p:
            try:
                if Path(p).stat().st_size>16*1024*1024:raise ValueError('SRT terlalu besar.')
                self.editor.setPlainText(srt(parse_srt(Path(p).read_text(encoding='utf-8-sig'))))
            except Exception as exc:self.failed(str(exc))
    def copy_cues(self):
        if Path(self.source.text()).resolve()!=Path(self.owner.path or '.').resolve():self.failed('Sumber Studio berbeda dari media pemutar. Pilih sumber yang sama sebelum mengambil subtitle.');return
        self.editor.setPlainText(srt(self.owner.cues))
    def save_text(self):
        try:
            cues=parse_srt(self.editor.toPlainText())
            if not cues:raise ValueError('Teks kosong.')
            p,_=QFileDialog.getSaveFileName(self,'Simpan teks',str(Path(self.source.text()).with_suffix(''))+'.Cyber80.srt','SRT (*.srt);;LRC (*.lrc)')
            if not p:return
            target=protected_target(self.source.text(),p,[self.music.text(),self.reference.text()])
            with target.open('x',encoding='utf-8') as out:out.write(lrc(cues) if target.suffix.lower()=='.lrc' else srt(cues))
            self.notify('Teks disimpan: '+str(target))
        except Exception as exc:self.failed(str(exc))
    def dub(self):
        if self.job:return
        try:
            cues=parse_srt(self.editor.toPlainText())
            if not cues:raise ValueError('Buat/impor teks terlebih dahulu; periksa bahasa tujuan.')
            p,_=QFileDialog.getSaveFileName(self,'Simpan dubbing dengan nama baru',str(Path(self.source.text()).with_suffix(''))+'.Dubbing.mkv','MKV (*.mkv);;MP4 (*.mp4);;WAV (*.wav);;M4A (*.m4a)')
            if not p:return
            protected_target(self.source.text(),p,[self.music.text(),self.reference.text()])
            job=DubbingJob(self.source.text(),p,cues,self.engine.currentData(),self.owner.key.text().strip(),self.model.text().strip(),self.voice.currentText(),self.code(),self.mix.currentData(),self.music.text(),self.level.value()/100,self.gain.value()/100,self.sapi.text(),self.limit.value(),self.stream.value(),clone={'tools':self.tools.text(),'reference':self.reference.text(),'start':self.ref_start.value(),'duration':self.ref_duration.value(),'per_cue':self.per_cue.isChecked()} if self.clone.isChecked() else None)
            job.completed.connect(self.dub_ready);self.start(job)
        except Exception as exc:self.failed(str(exc))
    def dub_ready(self,path):self.last_output=path;self.notify('Dubbing selesai: '+path)
    def notify(self,message):
        self.status.setText(message);self.owner.status.setText(message)
        if self.tray:self.tray.showMessage('Cyber80 • Studio Bahasa',message,QSystemTrayIcon.Information,10000)
        else:
            self.notice=QMessageBox(self);self.notice.setWindowTitle('Studio Bahasa');self.notice.setTextFormat(Qt.PlainText);self.notice.setText(message);self.notice.open()
    def failed(self,message):self.status.setText('Belum selesai: '+message)
    def finished(self):
        self.job.deleteLater();self.job=None
        for b in self.buttons:b.setEnabled(True)
        for w in (self.source,self.task,self.stream,self.language):w.setEnabled(True)
        self.editor.setReadOnly(False);self.cancel_button.setEnabled(False)
    def cancel(self):
        if self.job:self.job.cancel();self.status.setText('Membatalkan … permintaan API aktif dapat menunggu timeout.')
    def burn_text(self):
        try:
            cues=parse_srt(self.editor.toPlainText())
            if not cues:raise ValueError('Buat/impor teks terlebih dahulu.')
            self.owner.start_hardsub(self.source.text(),cues)
        except Exception as exc:self.failed(str(exc))
    def play_output(self):
        if self.last_output:
            from cut_editor import PreviewPlayer
            if self.preview and not self.preview.released:self.preview.close()
            self.preview=PreviewPlayer(self.owner,self.last_output,'Hasil dubbing');self.preview.show()
    def closeEvent(self,event):
        # Persistent owned dialog: closing hides, so active workers are never destroyed.
        self.hide();event.ignore()
