"""Conservative offline check for a target-language label mistakenly used as source."""
import threading,re
from functools import lru_cache
_lock=threading.Lock()
@lru_cache(maxsize=2048)
def detected_text_language(text):
    letters=sum(c.isalpha() for c in text)
    if letters<35:return None
    try:
        from langdetect import detect_langs,DetectorFactory
        with _lock:
            DetectorFactory.seed=0;predictions=detect_langs(text)
        if predictions and predictions[0].prob>=.98:return predictions[0].lang
    except Exception:pass
    return None

def check_source_languages(cues,target):
    target=str(target).lower().split('-')[0]
    for cue in cues:
        declared=str(cue.language).lower().split('-')[0]
        if declared not in ('',target,'unknown','auto'):continue
        detected=detected_text_language(cue.source)
        if detected and detected.split('-')[0]!=target:cue.language=detected
    return cues
