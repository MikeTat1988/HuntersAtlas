"""Journalled directory activation and recovery; mutable player data travels with it."""
from __future__ import annotations
import contextlib,json,os,time
from pathlib import Path

def write_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+'.tmp-'+os.urandom(16).hex())
    try:
        with temp.open('x',encoding='utf-8') as stream:
            json.dump(value,stream,ensure_ascii=False,indent=2);stream.write('\n');stream.flush();os.fsync(stream.fileno())
        os.replace(temp,path)
    finally:temp.unlink(missing_ok=True)

def regular_path(path,container=None):
    raw=Path(path).absolute()
    if raw==Path(raw.anchor):raise ValueError('A drive root cannot be an installation')
    for cursor in (raw,*raw.parents):
        if cursor.is_symlink() or getattr(cursor,'is_junction',lambda:False)():raise ValueError('Redirected installation path: '+str(cursor))
    resolved=raw.resolve(strict=False)
    if container is not None:
        # Windows can add the extended prefix only to a long descendant while
        # resolving a short DOS drive alias. Compare both canonical paths in
        # the same spelling; otherwise safe long members look outside the root.
        def comparable(value):
            text=str(value)
            if text.startswith('\\\\?\\UNC\\'):text='\\\\'+text[8:]
            elif text.startswith('\\\\?\\'):text=text[4:]
            return Path(text)
        comparable(resolved).relative_to(comparable(Path(container).resolve(strict=True)))
    return resolved

def alive(pid):
    if not isinstance(pid,int) or pid<=0:return False
    if os.name!='nt':
        try:os.kill(pid,0);return True
        except ProcessLookupError:return False
    import ctypes
    from ctypes import wintypes
    api=ctypes.WinDLL('kernel32',use_last_error=True)
    api.OpenProcess.argtypes=(wintypes.DWORD,wintypes.BOOL,wintypes.DWORD);api.OpenProcess.restype=wintypes.HANDLE
    api.CloseHandle.argtypes=(wintypes.HANDLE,)
    api.GetExitCodeProcess.argtypes=(wintypes.HANDLE,ctypes.POINTER(wintypes.DWORD))
    handle=api.OpenProcess(0x1000,False,pid)
    if not handle:return ctypes.get_last_error()!=87
    try:
        status=wintypes.DWORD();return not api.GetExitCodeProcess(handle,ctypes.byref(status)) or status.value==259
    finally:api.CloseHandle(handle)

@contextlib.contextmanager
def lock(launcher):
    launcher=regular_path(launcher);path=launcher.parent/('.'+launcher.name+'.atlas-maintenance.lock')
    if path.exists():
        try:prior=json.loads(path.read_text())
        except (ValueError,OSError):raise RuntimeError('An unreadable Atlas maintenance lock needs recovery')
        if alive(prior.get('pid')):raise RuntimeError('Another Atlas install or update is active')
        path.unlink()
    token=os.urandom(16).hex()
    with path.open('x',encoding='utf-8') as stream:json.dump({'pid':os.getpid(),'token':token},stream);stream.flush();os.fsync(stream.fileno())
    try:yield path
    finally:
        try:
            if json.loads(path.read_text()).get('token')==token:path.unlink()
        except (FileNotFoundError,ValueError):pass

class Journal:
    def __init__(self,path):
        self.path=Path(path);self.data=json.loads(self.path.read_text(encoding='utf-8'))
        if self.data.get('schema')!=1:raise ValueError('Unsupported Atlas update journal')
        root=regular_path(self.data['transaction_root'])
        if self.path.resolve().parent!=root:raise ValueError('Journal is outside its transaction root')
        self.roots=[regular_path(p) for p in self.data['allowed_roots']]
        for root in self.roots:
            if root.parent==root:raise ValueError('Unsafe journal root')
        for action in self.data.get('actions',[]):self.check(action['source']);self.check(action['destination'])
    def check(self,path):
        path=regular_path(path)
        if not any(path==r or r in path.parents for r in self.roots):raise ValueError('Journal action is outside the exact installation roots')
        return path
    def save(self):write_json(self.path,self.data)
    def state(self,value):self.data['state']=value;self.save()
    def move(self,source,destination):
        source=self.check(source);destination=self.check(destination)
        if not source.exists() or destination.exists():raise FileExistsError('Activation paths changed: '+str(source)+' -> '+str(destination))
        action=dict(source=str(source),destination=str(destination),applied=False)
        self.data['actions'].append(action);self.save() # persist intent before rename
        os.replace(source,destination)
        action['applied']=True;self.save()
    def restore(self):
        self.state('recovery')
        for action in reversed(self.data['actions']):
            if action.get('reversed'):continue
            source=self.check(action['source']);destination=self.check(action['destination'])
            # Includes a crash after rename and before the completion record.
            action['undo_pending']=True;self.save()
            if destination.exists() and not source.exists():os.replace(destination,source)
            elif destination.exists() and source.exists():raise RuntimeError('Ambiguous recovery paths; both editions have been preserved')
            action['applied']=False;action['reversed']=True;self.save()
        self.state('rolled_back')
