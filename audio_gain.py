"""Calibrated VLC playback gain and filter-chain configuration."""
import math
VLC_EQ_NEUTRAL_DB=20*math.log10(4.) # VLC equalizer has a fixed 0.25 input coefficient.
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

def audio_plan(state,mode='off'):
    enabled=bool(state.get('enabled',False));boost=boost_value(state.get('boost',0));bands=tuple(float(v) for v in state.get('bands',[0.]*10)) if enabled else (0.,)*10;gain=boosted_preamp(state.get('preamp',0) if enabled else 0,bands,state.get('headroom',True) if enabled else False,boost)
    filters=['equalizer'] if enabled else [];parameters={};dsp=[]
    for value in dsp_options(mode,boost,state.get('peak_guard',True)):
        name,data=value[2:].split('=',1)
        if name=='audio-filter':dsp=data.split(':')
        else:parameters[name]=float(data)
    if 'normvol' in dsp:filters.append('normvol')
    if gain:filters.append('gain')
    if 'compressor' in dsp:filters.append('compressor')
    return {'filters':filters,'parameters':parameters,'eq_preamp':VLC_EQ_NEUTRAL_DB,'bands':bands,'gain_db':gain,'multiplier':10**(gain/20),'enabled':enabled}
def audio_signature(state,mode='off'):
    plan=audio_plan(state,mode);return (tuple(plan['filters']),tuple(sorted(plan['parameters'].items())),plan['bands'],plan['gain_db'])
def native_audio_options(state,mode='off'):
    plan=audio_plan(state,mode);values=['--audio-filter='+':'.join(plan['filters']),'--gain-value='+format(plan['multiplier'],'.9g')]
    if plan['enabled']:values+=['--equalizer-preamp='+format(plan['eq_preamp'],'.9g'),'--equalizer-bands='+' '.join(format(v,'.9g') for v in plan['bands']),'--no-equalizer-2pass']
    return values+['--'+name+'='+format(value,'.9g') for name,value in plan['parameters'].items()]
