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
