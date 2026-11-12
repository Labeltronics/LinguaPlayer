"""Cancellable subprocess adapter for optional, local OpenVoice V2 tools."""
import json,os,subprocess,time,uuid
from pathlib import Path
from video_render import flags

def default_tools():return Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'Cyber80 Players'/'VoiceTools'
def validate_tools(root):
    root=Path(root).resolve()
    python=root/'python'/'python.exe' if os.name=='nt' else root/'python'/'bin'/'python'
    for path in (python,root/'worker.py',root/'model'/'config.json',root/'model'/'checkpoint.pth'):
        if not path.is_file():raise ValueError('Voice Tools belum lengkap. Jalankan Pasang Voice Tools gratis terlebih dahulu.')
    return root,python
class CloneSession:
    def __init__(self,root,session,cancelled,progress,device='cpu'):
        self.root,self.python=validate_tools(root);self.session=Path(session).resolve();self.cancelled=cancelled;self.progress=progress;self.proc=None
        self.log=(self.session/'clone-worker.log').open('wb')
        self.proc=subprocess.Popen([str(self.python),str(self.root/'worker.py'),str(self.root),str(self.session),device],stdout=self.log,stderr=self.log,**flags())
        try:self.wait(self.session/'ready.json',180)
        except Exception:self.close();raise
    def wait(self,path,timeout):
        deadline=time.monotonic()+timeout
        while not path.is_file():
            if self.cancelled():raise InterruptedError('Dibatalkan')
            if self.proc.poll() is not None:raise ValueError('OpenVoice berhenti. Pasang ulang tools atau gunakan CPU. Detail teknis hanya berada pada file sementara.')
            if time.monotonic()>deadline:raise ValueError('OpenVoice timeout. Gunakan potongan lebih pendek atau komputer lebih cepat.')
            time.sleep(.05)
        result=json.loads(path.read_text(encoding='utf-8'))
        if not result.get('ok'):raise ValueError('OpenVoice: '+str(result.get('error','Pemrosesan gagal.')))
    def convert(self,source,reference,target):
        request=self.session/('request-'+uuid.uuid4().hex+'.json');temporary=request.with_suffix('.tmp')
        temporary.write_text(json.dumps({'source':str(source),'reference':str(reference),'output':str(target)}),encoding='utf-8');os.replace(temporary,request)
        self.wait(request.with_suffix('.done'),600)
        if not Path(target).is_file():raise ValueError('OpenVoice tidak menghasilkan audio.')
    def close(self):
        if self.proc and self.proc.poll() is None:
            self.proc.kill()
            try:self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:pass
        if self.log:self.log.close();self.log=None
