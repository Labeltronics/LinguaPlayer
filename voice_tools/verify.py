"""Real converter smoke test after installer, synthetic references, no API call."""
import json,math,struct,subprocess,sys,tempfile,time,wave
from pathlib import Path
root=Path(sys.argv[1]).resolve()
def wav(path,freq):
 with wave.open(str(path),'wb') as out:
  out.setnchannels(1);out.setsampwidth(2);out.setframerate(22050)
  out.writeframes(b''.join(struct.pack('<h',int(4000*math.sin(i*2*math.pi*freq/22050))) for i in range(22050*3)))
def wait(path,p,timeout=180):
 deadline=time.monotonic()+timeout
 while not path.exists():
  if p.poll() is not None:raise RuntimeError('Worker stopped')
  if time.monotonic()>deadline:raise TimeoutError('Worker timed out')
  time.sleep(.1)
 data=json.loads(path.read_text());assert data.get('ok'),data
with tempfile.TemporaryDirectory() as d:
 session=Path(d);wav(session/'source.wav',220);wav(session/'reference.wav',330)
 p=subprocess.Popen([sys.executable,str(root/'worker.py'),str(root),str(session),'cpu'])
 try:
  wait(session/'ready.json',p)
  req={'source':str(session/'source.wav'),'reference':str(session/'reference.wav'),'output':str(session/'result.wav')}
  (session/'request-test.json').write_text(json.dumps(req));wait(session/'request-test.done',p)
  import soundfile as sf,numpy as np
  data,rate=sf.read(session/'result.wav');assert 2.8<len(data)/rate<3.2 and np.isfinite(data).all() and max(abs(data))>0
  report={'openvoice_v2_model_load':'PASS','reference_embedding':'PASS','actual_cpu_conversion':'PASS','output_finite_audio':'PASS','speaker_similarity_quality':'NOT_MEASURED_SYNTHETIC_TONES','gemini_live_tts':'NOT_RUN_NO_CREDENTIAL'}
  (root/'VOICE_TOOLS_TEST.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
 finally:
  p.kill();p.wait()
