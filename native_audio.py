"""VLC 3.x per-player audio variables (Windows x64 bundle ABI).

LibVLC creates non-inheriting audio variables; configure the player object rather
than relying on instance CLI inheritance. No user-provided native code or names.
"""
import ctypes,sys,functools
import vlc
from audio_gain import audio_plan
class Value(ctypes.Union):
    _fields_=[('integer',ctypes.c_int64),('floating',ctypes.c_float),('string',ctypes.c_char_p),('pointer',ctypes.c_void_p)]
@functools.lru_cache(maxsize=1)
def core():
    version=vlc.libvlc_get_version().decode(errors='replace')
    if not version.startswith('3.') or ctypes.sizeof(ctypes.c_void_p)!=8 or ctypes.sizeof(Value)!=8:raise RuntimeError('Konfigurasi audio memerlukan bundel VLC 3.x 64-bit.')
    name='libvlccore'+('.dll' if sys.platform=='win32' else '.so.9');dll=ctypes.CDLL(name)
    dll.var_Create.argtypes=[ctypes.c_void_p,ctypes.c_char_p,ctypes.c_int];dll.var_Create.restype=ctypes.c_int
    # VLC's mixed scalar union is 8 bytes, passed in an integer argument slot on x64.
    dll.var_SetChecked.argtypes=[ctypes.c_void_p,ctypes.c_char_p,ctypes.c_int,ctypes.c_uint64];dll.var_SetChecked.restype=ctypes.c_int
    return dll
def configure(player,state,mode='off'):
    if not isinstance(player,vlc.MediaPlayer):return False # Unit-test player doubles have no native pointer.
    dll=core();ptr=player._as_parameter_;plan=audio_plan(state,mode)
    def set_value(name,kind,value):
        name=name.encode('ascii');item=Value()
        if kind==0x40:item.string=str(value).encode('utf-8')
        elif kind==0x50:item.floating=float(value)
        else:item.integer=int(value)
        if dll.var_Create(ptr,name,kind)!=0:raise RuntimeError('Tidak dapat membuat pengaturan audio VLC.')
        bits=ctypes.c_uint64.from_buffer_copy(item).value
        if dll.var_SetChecked(ptr,name,kind,bits)!=0:raise RuntimeError('VLC menolak pengaturan audio '+name.decode())
    set_value('equalizer-preamp',0x50,plan['eq_preamp']);set_value('equalizer-bands',0x40,' '.join(format(v,'.9g') for v in plan['bands']));set_value('equalizer-2pass',0x20,False);set_value('gain-value',0x50,plan['multiplier'])
    for name,value in plan['parameters'].items():set_value(name,0x50,value)
    set_value('audio-filter',0x40,':'.join(plan['filters']))
    return True
