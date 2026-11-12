"""Copy bundled dependency notices from installed wheel distributions."""
import importlib.metadata,shutil,re
from pathlib import Path
root=Path('dist/Cyber80Players/THIRD_PARTY_LICENSES');root.mkdir(parents=True,exist_ok=True)
for dist in importlib.metadata.distributions():
    name=dist.metadata.get('Name','')
    if not name.lower().replace('-','_').startswith(('pyside6','shiboken6','onnxruntime','numpy','imageio_ffmpeg','python_vlc','langdetect','pychromecast','zeroconf','casttube','protobuf','ifaddr','requests','urllib3','charset_normalizer','certifi','idna')):continue
    for file in dist.files or []:
        lower=str(file).lower();base=Path(file).name.lower()
        if '/licenses/' not in lower and not base.startswith(('license','copying','copyright','notice','thirdparty')):continue
        source=Path(dist.locate_file(file))
        if not source.is_file():continue
        parts=[p for p in Path(file).parts if p not in ('.','..','/')];target=root/re.sub('[^A-Za-z0-9_.-]','_',name)/Path(*parts);target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
print('Dependency license files copied:',len(list(root.rglob('*.*'))))
