from pathlib import Path
import json

def read_playlist(path):
    path=Path(path)
    if path.suffix.lower()=='.json':
        data=json.loads(path.read_text(encoding='utf-8-sig'))
        values=data.get('videos',[]) if isinstance(data,dict) else data
        if not isinstance(values,list):raise ValueError('Playlist JSON harus berisi daftar video')
    else:values=[line.strip() for line in path.read_text(encoding='utf-8-sig').splitlines() if line.strip() and not line.lstrip().startswith('#')]
    result=[]
    for value in values:
        if not isinstance(value,str):raise ValueError('Lokasi video dalam playlist tidak valid')
        p=Path(value)
        if not p.is_absolute():p=path.parent/p
        result.append(str(p.resolve()))
    return result

def write_playlist(path,videos):
    path=Path(path)
    if path.suffix.lower()=='.json':text=json.dumps({'videos':videos},ensure_ascii=False,indent=2)
    else:text='#EXTM3U\n'+'\n'.join(videos)+'\n'
    path.write_text(text,encoding='utf-8')
