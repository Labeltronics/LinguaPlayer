"""Early native Windows audio verification before spending time packaging the EXE."""
import sys,json,tempfile,traceback
from pathlib import Path
sys.argv.append('--self-test')
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from app import Window
from audio_checks import run_audio_boost_checks
application=QApplication([]);window=Window();window.show()
def check():
    code=1
    try:
        with tempfile.TemporaryDirectory(prefix='cyber80-audio-source-') as root:result=run_audio_boost_checks(window,Path(root))
        print(json.dumps({'audio_source_validation':result}),flush=True);code=0
    except Exception as exc:
        print(json.dumps({'audio_source_error':str(exc),'traceback':traceback.format_exc()}),flush=True)
        try:
            lines=window.log_path.read_text(encoding='utf-8',errors='replace').splitlines();print('\n'.join(line for line in lines[-1200:] if any(word in line.lower() for word in ('gain','equalizer','compressor','audio filter')))[-14000:],flush=True)
        except OSError:pass
    finally:window.close();application.exit(code)
QTimer.singleShot(250,check)
sys.exit(application.exec())
