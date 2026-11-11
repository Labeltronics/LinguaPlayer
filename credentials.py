"""Windows Credential Manager only. No plaintext fallback."""
import ctypes
from ctypes import wintypes
import os

class FILETIME(ctypes.Structure):
    _fields_=[('low',wintypes.DWORD),('high',wintypes.DWORD)]

class CREDENTIAL(ctypes.Structure):
    _fields_=[('Flags',wintypes.DWORD),('Type',wintypes.DWORD),('TargetName',wintypes.LPWSTR),
              ('Comment',wintypes.LPWSTR),('LastWritten',FILETIME),('CredentialBlobSize',wintypes.DWORD),
              ('CredentialBlob',ctypes.POINTER(ctypes.c_ubyte)),('Persist',wintypes.DWORD),
              ('AttributeCount',wintypes.DWORD),('Attributes',ctypes.c_void_p),
              ('TargetAlias',wintypes.LPWSTR),('UserName',wintypes.LPWSTR)]

def api():
    if os.name!='nt':raise RuntimeError('Penyimpanan key memerlukan Windows Credential Manager.')
    dll=ctypes.WinDLL('Advapi32.dll',use_last_error=True)
    dll.CredWriteW.argtypes=[ctypes.POINTER(CREDENTIAL),wintypes.DWORD];dll.CredWriteW.restype=wintypes.BOOL
    dll.CredReadW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,ctypes.POINTER(ctypes.POINTER(CREDENTIAL))];dll.CredReadW.restype=wintypes.BOOL
    dll.CredDeleteW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD];dll.CredDeleteW.restype=wintypes.BOOL
    dll.CredFree.argtypes=[ctypes.c_void_p];dll.CredFree.restype=None
    return dll

def save_key(name,value):
    encoded=value.encode('utf-16-le')
    if not encoded or len(encoded)>2560:raise ValueError('API key kosong atau terlalu panjang.')
    blob=(ctypes.c_ubyte*len(encoded)).from_buffer_copy(encoded)
    credential=CREDENTIAL();credential.Type=1;credential.TargetName='Cyber80Players/'+name
    credential.UserName='Cyber80 Players';credential.CredentialBlobSize=len(encoded);credential.CredentialBlob=blob;credential.Persist=2
    if not api().CredWriteW(ctypes.byref(credential),0):raise ctypes.WinError(ctypes.get_last_error())

def load_key(name):
    dll=api()
    for prefix in ('Cyber80Players/','LinguaPlayer/'):
        pointer=ctypes.POINTER(CREDENTIAL)()
        if not dll.CredReadW(prefix+name,1,0,ctypes.byref(pointer)):
            code=ctypes.get_last_error()
            if code==1168:continue
            raise ctypes.WinError(code)
        try:return ctypes.string_at(pointer.contents.CredentialBlob,pointer.contents.CredentialBlobSize).decode('utf-16-le')
        finally:dll.CredFree(pointer)
    return ''

def delete_key(name):
    dll=api()
    for prefix in ('Cyber80Players/','LinguaPlayer/'):
        if not dll.CredDeleteW(prefix+name,1,0):
            code=ctypes.get_last_error()
            if code!=1168:raise ctypes.WinError(code)
