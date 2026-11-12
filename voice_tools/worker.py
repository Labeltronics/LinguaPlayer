"""Local OpenVoice V2 tone transfer worker. Only loads bundled official converter.
Protocol: JSON request files in private job dir; .done JSON response per request.
No network, text, API key or voice profile persistence in this worker.
"""
import json,os,sys,time,traceback
from pathlib import Path

def atomic(path,data):
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(data),encoding='utf-8');os.replace(temp,path)
def main():
    root=Path(sys.argv[1]).resolve();session=Path(sys.argv[2]).resolve();device=sys.argv[3]
    try:
        import torch
        from openvoice.api import ToneColorConverter,OpenVoiceBaseClass
        class Converter(ToneColorConverter):
            def __init__(self,config,device):
                OpenVoiceBaseClass.__init__(self,str(config),device=device)
                # No network dependency on the optional wavmark model.
                self.watermark_model=None;self.version=getattr(self.hps,'_version_','v2')
        if device=='cuda' and not torch.cuda.is_available():raise ValueError('CUDA tidak tersedia pada tools ini. Pilih CPU.')
        torch.set_num_threads(max(1,min(8,os.cpu_count() or 1)))
        converter=Converter(root/'model'/'config.json',device)
        state=torch.load(root/'model'/'checkpoint.pth',map_location='cpu',weights_only=True)
        converter.model.load_state_dict(state['model'],strict=True)
        atomic(session/'ready.json',{'ok':True})
        seen=set()
        while not (session/'stop').exists():
            for request in sorted(session.glob('request-*.json')):
                if request.name in seen:continue
                seen.add(request.name)
                try:
                    c=json.loads(request.read_text(encoding='utf-8'))
                    paths=[Path(c[k]).resolve() for k in ('source','reference','output')]
                    if any(p.parent!=session for p in paths):raise ValueError('Path outside private session')
                    source,reference,output=paths
                    with torch.inference_mode():
                        source_se=converter.extract_se(str(source));target_se=converter.extract_se(str(reference))
                        converter.convert(str(source),source_se,target_se,str(output),tau=.3,message='Cyber80 AI dubbing')
                    import soundfile as sf,numpy as np
                    audio,sample_rate=sf.read(str(output))
                    if not np.isfinite(audio).all() or len(audio)<sample_rate*.05:raise ValueError('Audio cloning tidak valid/kosong.')
                    atomic(request.with_suffix('.done'),{'ok':True})
                except Exception as exc:atomic(request.with_suffix('.done'),{'ok':False,'error':type(exc).__name__+': '+str(exc)[:500]})
            time.sleep(.05)
    except Exception as exc:
        atomic(session/'ready.json',{'ok':False,'error':type(exc).__name__+': '+str(exc)[:500]});return 1
    return 0
if __name__=='__main__':sys.exit(main())
