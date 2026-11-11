"""Remove only unused UI/data assets; preserve codecs and browser runtime DLLs."""
import json,shutil
from pathlib import Path

def optimize(root):
    root=Path(root)
    if not (root/'Cyber80Players.exe').is_file() or not (root/'_internal').is_dir():
        raise ValueError('Expected a Cyber80 portable build directory.')
    before=sum(p.stat().st_size for p in root.rglob('*') if p.is_file())
    removed=[]
    def remove(path):
        if path.is_dir():
            removed.extend(str(p.relative_to(root)).replace('\\','/') for p in path.rglob('*') if p.is_file());shutil.rmtree(path)
        elif path.is_file():removed.append(str(path.relative_to(root)).replace('\\','/'));path.unlink()
    internal=root/'_internal';qt=internal/'PySide6'
    for path in (qt/'resources').glob('*.debug.pak'):remove(path)
    for path in (qt/'translations').glob('*.qm'):
        if not path.stem.endswith(('_en','_id')):remove(path)
    for path in (qt/'translations'/'qtwebengine_locales').glob('*.pak'):
        if path.name not in ('en-US.pak','id.pak'):remove(path)
    # Widgets frontend uses no external QML. libVLC uses our own Qt UI, not VLC's.
    for path in (qt/'qml',internal/'vlc'/'locale',internal/'vlc'/'skins',internal/'vlc'/'plugins'/'gui'):remove(path)
    after=sum(p.stat().st_size for p in root.rglob('*') if p.is_file())
    report={'before_bytes':before,'after_bytes':after,'removed_bytes':before-after,'removed_file_count':len(removed),'removed':removed,'preserved':'WebEngine runtime, TLS/sandbox, VLC codecs/access/demux, FFmpeg, MiDaS/ONNX, English/Indonesian browser locales'}
    (root/'OPTIMASI_PAKET.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return {k:v for k,v in report.items() if k!='removed'}
if __name__=='__main__':print(json.dumps(optimize(Path(__file__).parent/'dist'/'Cyber80Players')))
