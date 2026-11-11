import hashlib,json,os,time
from pathlib import Path

def write_json_atomic(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+'.tmp');temp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8');os.replace(temp,path)

def media_key(path,extra=None):
    path=Path(path).resolve();stat=path.stat()
    identity=[str(path),stat.st_size,stat.st_mtime_ns,extra]
    return hashlib.sha256(json.dumps(identity,ensure_ascii=False,sort_keys=True).encode()).hexdigest()

class MediaStore:
    stores={}
    @classmethod
    def shared(cls,path,persist=True):
        key=str(Path(path).resolve())
        if not persist:return cls(path,False)
        if key not in cls.stores:cls.stores[key]=cls(path,True)
        return cls.stores[key]
    def __init__(self,path,persist=True):
        self.path=Path(path);self.persist=persist;self.records={}
        if persist:
            try:
                data=json.loads(self.path.read_text(encoding='utf-8'))
                if isinstance(data,dict):self.records={str(k):v for k,v in data.items() if isinstance(v,dict)}
            except (OSError,ValueError):pass
    def get(self,path):
        try:return self.records.get(media_key(path),{})
        except OSError:return {}
    def update(self,path,**values):
        try:key=media_key(path)
        except OSError:return
        record=self.records.setdefault(key,{'path':str(Path(path).resolve())})
        record.update(values);record['updated']=time.time()
        if len(self.records)>1000:
            self.records=dict(sorted(self.records.items(),key=lambda pair:pair[1].get('updated',0),reverse=True)[:1000])
        if self.persist:write_json_atomic(self.path,self.records)

class SubtitleCache:
    def __init__(self,root):self.root=Path(root)
    def path_for(self,path,context):return self.root/(media_key(path,context)+'.json')
    def read(self,path,context):
        try:
            data=json.loads(self.path_for(path,context).read_text(encoding='utf-8'))
            if not isinstance(data,dict) or not isinstance(data.get('cues'),list):return None
            return data
        except (OSError,ValueError):return None
    def write(self,path,context,data):write_json_atomic(self.path_for(path,context),data)
    def clear(self,path,context):
        try:self.path_for(path,context).unlink(missing_ok=True)
        except OSError:pass
