"""Template selection UI. Generated tracks/clips remain ordinary editable project data."""
from pathlib import Path
from PySide6.QtWidgets import QDialog,QFormLayout,QHBoxLayout,QComboBox,QPushButton,QListWidget,QLineEdit,QTextEdit,QDoubleSpinBox,QLabel,QDialogButtonBox,QFileDialog
from video_templates import PRESETS
class TemplateDialog(QDialog):
    def __init__(self,parent):
        super().__init__(parent);self.setWindowTitle('Template • Kolase / Opening / Ending');self.resize(620,590);self.photos=[];self.logo='';form=QFormLayout(self);self.preset=QComboBox()
        for key,label in PRESETS:self.preset.addItem(label,key)
        form.addRow('Template',self.preset);button=QPushButton('Pilih banyak foto…');button.clicked.connect(self.choose_photos);form.addRow(button);self.list=QListWidget();self.list.setMaximumHeight(110);form.addRow('Urutan foto',self.list)
        order=QHBoxLayout()
        for label,fn in [('Foto ↑',lambda:self.move_photo(-1)),('Foto ↓',lambda:self.move_photo(1)),('Hapus foto',self.remove_photo)]:
            button=QPushButton(label);button.clicked.connect(fn);order.addWidget(button)
        form.addRow(order)
        self.title=QLineEdit();self.title.setMaxLength(300);self.title.setPlaceholderText('Judul / nama / kutipan');form.addRow('Judul',self.title);self.subtitle=QTextEdit();self.subtitle.setMaximumHeight(80);form.addRow('Subjudul / keterangan',self.subtitle)
        self.seconds=QDoubleSpinBox();self.seconds.setRange(.5,60);self.seconds.setValue(4);self.seconds.setSuffix(' s per halaman / foto');form.addRow('Durasi',self.seconds);self.background=QLineEdit('#101827');form.addRow('Warna latar',self.background)
        self.logo_button=QPushButton('Pilih logo opsional…');self.logo_button.clicked.connect(self.choose_logo);self.logo_button.setEnabled(False);form.addRow(self.logo_button);self.place=QComboBox()
        for label,value in [('Di akhir proyek','append'),('Di awal • geser semua klip','prepend'),('Di playhead • overlay','playhead')]:self.place.addItem(label,value)
        form.addRow('Penempatan',self.place);self.preset.currentIndexChanged.connect(self.selection)
        note=QLabel('Kolase membagi foto menjadi halaman jika melebihi jumlah kotak. Slideshow memakai urutan pilihan foto dan gerak zoom halus. Opening/ending memakai foto pertama sebagai latar, jika tersedia. Semua layer tetap bisa diedit; musik ditambahkan melalui layer Musik.');note.setWordWrap(True);form.addRow(note)
        buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel);buttons.button(QDialogButtonBox.Ok).setText('Buat template');buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);form.addRow(buttons)
    def selection(self):
        key=self.preset.currentData();self.logo_button.setEnabled(key in ('opening','ending'))
        if key=='opening':self.place.setCurrentIndex(self.place.findData('prepend'))
        elif key=='ending':self.place.setCurrentIndex(self.place.findData('append'))
    def choose_photos(self):
        paths,_=QFileDialog.getOpenFileNames(self,'Pilih foto sesuai urutan slideshow/kolase','','Foto (*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff)')
        if paths:self.photos=paths;self.list.clear();self.list.addItems([str(i+1)+'. '+Path(p).name for i,p in enumerate(paths)])
    def refresh_photos(self,row=0):
        self.list.clear();self.list.addItems([str(i+1)+'. '+Path(p).name for i,p in enumerate(self.photos)]);self.list.setCurrentRow(min(row,len(self.photos)-1))
    def move_photo(self,delta):
        i=self.list.currentRow();j=i+delta
        if 0<=i<len(self.photos) and 0<=j<len(self.photos):self.photos[i],self.photos[j]=self.photos[j],self.photos[i];self.refresh_photos(j)
    def remove_photo(self):
        i=self.list.currentRow()
        if 0<=i<len(self.photos):self.photos.pop(i);self.refresh_photos(i)
    def choose_logo(self):
        path,_=QFileDialog.getOpenFileName(self,'Pilih logo opsional','','Gambar (*.png *.jpg *.jpeg *.webp *.bmp)')
        if path:self.logo=path;self.logo_button.setText('Logo: '+Path(path).name)
    def values(self):return {'preset':self.preset.currentData(),'photos':self.photos,'title':self.title.text(),'subtitle':self.subtitle.toPlainText(),'duration':self.seconds.value(),'placement':self.place.currentData(),'logo':self.logo,'background':self.background.text()}
