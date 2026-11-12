"""Local parental gate: salted PBKDF2, locked per session, timed retry limit."""
import hashlib,hmac,re,secrets,time
DEFAULT_SALT='271877df02b5e1b98f23cb166c32b807'
DEFAULT_DIGEST='a8a88dc82fc02191045f349c5bdd748d3e9f728f1d23be29479e432c4b77872d'
class ParentalLock:
    def __init__(self,settings=None):
        self.settings=settings;self.unlocked=False;self.attempts=0;self.retry_at=0.
    def values(self):
        salt=self.settings.value('iptv/pin_salt',DEFAULT_SALT) if self.settings else DEFAULT_SALT
        digest=self.settings.value('iptv/pin_hash',DEFAULT_DIGEST) if self.settings else DEFAULT_DIGEST
        if not re.fullmatch(r'[a-f0-9]{32}',str(salt)) or not re.fullmatch(r'[a-f0-9]{64}',str(digest)):raise ValueError('Profil parental control tidak valid.')
        return salt,digest
    def verify(self,pin):
        if time.monotonic()<self.retry_at:return False
        salt,digest=self.values();actual=hashlib.pbkdf2_hmac('sha256',str(pin).encode(),bytes.fromhex(salt),200000).hex()
        if hmac.compare_digest(actual,digest):self.attempts=0;return True
        self.attempts+=1
        if self.attempts>=5:self.retry_at=time.monotonic()+30;self.attempts=0
        return False
    def unlock(self,pin):
        self.unlocked=self.verify(pin);return self.unlocked
    def lock(self):self.unlocked=False
    def change(self,old,new):
        if not self.verify(old):raise ValueError('PIN lama salah atau percobaan dibatasi.')
        if not re.fullmatch(r'\d{6}',new):raise ValueError('PIN baru harus enam angka.')
        if self.settings is None:raise ValueError('Penyimpanan dinonaktifkan pada sesi privat.')
        salt=secrets.token_hex(16);digest=hashlib.pbkdf2_hmac('sha256',new.encode(),bytes.fromhex(salt),200000).hex()
        self.settings.setValue('iptv/pin_salt',salt);self.settings.setValue('iptv/pin_hash',digest);self.lock()
