from contextlib import contextmanager
import hashlib,json,os,time,sqlite3,uuid
from pathlib import Path

def write_json_atomic(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:temp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8');os.replace(temp,path)
    finally:temp.unlink(missing_ok=True)

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
        if not persist:return
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.session() as conn:
            conn.execute('PRAGMA journal_mode=WAL')
            conn.execute('CREATE TABLE IF NOT EXISTS media (identity TEXT PRIMARY KEY, path TEXT NOT NULL, updated REAL NOT NULL, data TEXT NOT NULL)')
            conn.execute('CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
            if not conn.execute("SELECT value FROM metadata WHERE key='json_migrated'").fetchone():
                try:
                    data=json.loads(self.path.read_text(encoding='utf-8'))
                    if isinstance(data,dict):
                        for key,record in data.items():
                            if isinstance(record,dict) and isinstance(record.get('path'),str):self.put(conn,str(key),record)
                except (OSError,ValueError,TypeError):pass
                conn.execute("INSERT OR REPLACE INTO metadata VALUES ('json_migrated','1')")
    @contextmanager
    def session(self):
        conn=sqlite3.connect(str(self.path.with_suffix('.sqlite3')),timeout=5)
        try:
            with conn:yield conn
        finally:conn.close()
    def put(self,conn,key,record):
        conn.execute('INSERT INTO media VALUES (?,?,?,?) ON CONFLICT(identity) DO UPDATE SET path=excluded.path,updated=excluded.updated,data=excluded.data',
            (key,record['path'],float(record.get('updated',0)),json.dumps(record,ensure_ascii=False)))
    def get(self,path):
        try:key=media_key(path)
        except OSError:return {}
        if not self.persist:return dict(self.records.get(key,{}))
        with self.session() as conn:row=conn.execute('SELECT data FROM media WHERE identity=?',(key,)).fetchone()
        return json.loads(row[0]) if row else {}
    def update(self,path,**values):
        try:key=media_key(path)
        except OSError:return
        if not self.persist:
            record=self.records.setdefault(key,{'path':str(Path(path).resolve())});record.update(values);record['updated']=time.time();return
        with self.session() as conn:
            conn.execute('BEGIN IMMEDIATE')
            row=conn.execute('SELECT data FROM media WHERE identity=?',(key,)).fetchone()
            record=json.loads(row[0]) if row else {'path':str(Path(path).resolve())}
            record.update(values);record['updated']=time.time();self.put(conn,key,record)
    def entries(self):
        if not self.persist:return sorted(self.records.values(),key=lambda r:r.get('updated',0),reverse=True)
        with self.session() as conn:return [json.loads(row[0]) for row in conn.execute('SELECT data FROM media ORDER BY updated DESC')]
    def relink(self,old_path,new_path):
        key=media_key(new_path);old_path=str(Path(old_path).resolve())
        if not self.persist:
            entry=next(((k,v) for k,v in self.records.items() if os.path.normcase(str(Path(v['path']).resolve()))==os.path.normcase(old_path)),None)
            if not entry:raise ValueError('Riwayat lama tidak ditemukan.')
            if key in self.records and key!=entry[0]:raise ValueError('File tujuan sudah mempunyai riwayat.')
            record=self.records.pop(entry[0]);record['path']=str(Path(new_path).resolve());self.records[key]=record;return
        with self.session() as conn:
            conn.execute('BEGIN IMMEDIATE')
            rows=conn.execute('SELECT identity,data,path FROM media ORDER BY updated DESC').fetchall()
            row=next((r for r in rows if os.path.normcase(str(Path(r[2]).resolve()))==os.path.normcase(old_path)),None)
            if not row:raise ValueError('Riwayat file lama tidak ditemukan.')
            if conn.execute('SELECT 1 FROM media WHERE identity=? AND identity!=?',(key,row[0])).fetchone():raise ValueError('File tujuan sudah mempunyai riwayat.')
            record=json.loads(row[1]);record['path']=str(Path(new_path).resolve());record['updated']=time.time()
            conn.execute('DELETE FROM media WHERE identity=?',(row[0],));self.put(conn,key,record)

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
