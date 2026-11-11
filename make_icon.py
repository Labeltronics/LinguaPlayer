from pathlib import Path
import struct
from PySide6.QtGui import QGuiApplication,QImage,QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtCore import QBuffer,QIODevice,Qt

if __name__=='__main__':
    app=QGuiApplication([]);root=Path(__file__).parent/'assets';renderer=QSvgRenderer(str(root/'cyber80.svg'));pngs=[]
    for size in (32,64,256):
        image=QImage(size,size,QImage.Format_ARGB32);image.fill(Qt.transparent);painter=QPainter(image);renderer.render(painter);painter.end()
        buffer=QBuffer();buffer.open(QIODevice.WriteOnly);image.save(buffer,'PNG');pngs.append((size,bytes(buffer.data())))
    offset=6+16*len(pngs);header=struct.pack('<HHH',0,1,len(pngs));data=b''
    for size,png in pngs:
        header+=struct.pack('<BBBBHHII',0 if size==256 else size,0 if size==256 else size,0,0,1,32,len(png),offset)
        offset+=len(png);data+=png
    (root/'cyber80.ico').write_bytes(header+data)
