"""Build a bundled, non-NSFW public IPTV snapshot. No private playlist input."""
import datetime,json
from pathlib import Path
from internet_tv import API,catalog
from web_transfer import read_document
from storage import write_json_atomic

def prepare(root):
    channels=json.loads(read_document(API+'channels.json',limit=32*1024*1024)[0]);streams=json.loads(read_document(API+'streams.json',limit=32*1024*1024)[0]);rows=catalog(channels,streams)
    if len(rows)<100:raise ValueError('Katalog publik kosong/tidak lengkap. Build dihentikan.')
    info={'schema':1,'generated_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source':API,'rows':len(rows),'countries':len({r['country'] for r in rows}),'nsfw_entries_included':False,'availability':'metadata snapshot; individual stream availability not guaranteed'}
    write_json_atomic(Path(root)/'TV_CATALOG.json',{'info':info,'channels':rows});write_json_atomic(Path(root)/'IPTV_CATALOG_INFO.json',info);return info
if __name__=='__main__':print(json.dumps(prepare(Path(__file__).resolve().parent)))
