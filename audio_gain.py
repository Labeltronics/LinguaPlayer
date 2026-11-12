"""Bounded native playback boost and compressor configuration."""
import math
def boost_value(value):
    n=float(value)
    if not math.isfinite(n):raise ValueError('Audio Boost harus angka terbatas.')
    return max(0.,min(20.,n))
def boosted_preamp(preamp,bands,headroom=True,boost=0.):
    base=float(preamp)-(max(0.,max(bands)) if headroom else 0.)
    return max(-20.,min(20.,base+boost_value(boost)))
def dsp_options(mode='off',boost=0.,guard=True):
    filters=[];options=[]
    if mode=='normalize':filters.append('normvol');options+=['--norm-max-level=2.0']
    guarded=boost_value(boost)>0 and guard
    if guarded or mode=='night':
        filters.append('compressor')
        if guarded:options+=['--compressor-threshold=-6','--compressor-ratio=20','--compressor-attack=1.5','--compressor-release=100','--compressor-knee=1','--compressor-makeup-gain=0']
        else:options+=['--compressor-threshold=-18','--compressor-ratio=4','--compressor-attack=25','--compressor-release=100','--compressor-makeup-gain=2']
    return (['--audio-filter='+':'.join(filters)] if filters else [])+options

def audio_signature(state,mode='off'):
    enabled=bool(state.get('enabled',False));boost=boost_value(state.get('boost',0));eq=enabled or boost>0;bands=tuple(state.get('bands',[0.]*10) if enabled else [0.]*10);gain=boosted_preamp(state.get('preamp',0) if enabled else 0,bands,state.get('headroom',True) if enabled else False,boost)
    return (mode,eq,gain,bands,boost>0 and state.get('peak_guard',True))
def native_audio_options(state,mode='off'):
    mode,eq,gain,bands,guard=audio_signature(state,mode);values=dsp_options(mode,state.get('boost',0),state.get('peak_guard',True));filters=[];rest=[]
    for value in values:
        if value.startswith('--audio-filter='):filters.extend(value.split('=',1)[1].split(':'))
        else:rest.append(value)
    if eq:filters.insert(0,'equalizer');rest+=['--equalizer-preamp='+format(gain,'.9g'),'--equalizer-bands='+' '.join(format(float(v),'.9g') for v in bands),'--no-equalizer-2pass']
    return ['--audio-filter='+':'.join(filters)]+rest
