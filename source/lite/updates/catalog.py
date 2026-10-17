"""Authenticated, explicit compatibility entries. No version-range acceptance."""
from __future__ import annotations
import base64,datetime,hashlib,json,re
from pathlib import Path

COORDINATOR=2
def canonical(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')
def encoded(value,size):
    suffix=bytes.fromhex('3031300d060960864801650304020105000420')+hashlib.sha256(canonical(value)).digest()
    return b'\0\1'+b'\xff'*(size-len(suffix)-3)+b'\0'+suffix

def sign(value,private):
    n=int(private['n'],16);d=int(private['d'],16);size=(n.bit_length()+7)//8
    if n.bit_length()<3072:raise ValueError('Catalog key is too small')
    return base64.b64encode(pow(int.from_bytes(encoded(value,size),'big'),d,n).to_bytes(size,'big')).decode('ascii')

def verify(value,signature,public):
    n=int(public['n'],16);e=int(public['e']);size=(n.bit_length()+7)//8
    if n.bit_length()<3072 or e!=65537:raise ValueError('Unsupported catalog trust key')
    raw=base64.b64decode(signature,validate=True)
    if len(raw)!=size or int.from_bytes(raw,'big')>=n:raise ValueError('Invalid catalog signature')
    actual=pow(int.from_bytes(raw,'big'),e,n).to_bytes(size,'big')
    if actual!=encoded(value,size):raise ValueError('Catalog signature verification failed')
    return value

def load(path,public=None,*,allow_expired=False):
    path=Path(path)
    if path.stat().st_size>1024*1024:raise ValueError('Catalog exceeds size limit')
    envelope=json.loads(path.read_text(encoding='utf-8'))
    public=public or json.loads(Path(__file__).with_name('trusted-key.json').read_text())
    data=verify(envelope['catalog'],envelope['signature'],public)
    if data.get('schema')!=1 or data.get('minimum_coordinator',999)>COORDINATOR:raise ValueError('A newer Atlas update coordinator is required')
    expires=datetime.datetime.fromisoformat(data['expires'].replace('Z','+00:00'))
    if not allow_expired and expires<datetime.datetime.now(datetime.timezone.utc):raise ValueError('The update catalog has expired; installed Atlas can still run offline')
    entries=data.get('targets')
    if not isinstance(entries,list) or len(entries)>128:raise ValueError('Invalid catalog target list')
    seen=set()
    for entry in entries:
        tag=entry.get('upstream_release','')
        if not re.fullmatch(r'windows-v\d+(?:\.\d+){1,3}',tag) or tag in seen:raise ValueError('Invalid or duplicate upstream target')
        seen.add(tag)
        if entry.get('platform')!='windows-x86_64' or entry.get('adapter_protocol')!=1:raise ValueError('Unsupported target platform or adapter protocol')
        if not re.fullmatch('[0-9a-f]{40}',entry.get('upstream_commit','')):raise ValueError('Missing immutable upstream commit')
        if entry.get('minimum_coordinator',999)>COORDINATOR:raise ValueError('Target requires a newer coordinator')
        for field in ('upstream_sha256','atlas_manifest_sha256'):
            if not re.fullmatch('[0-9a-f]{64}',entry.get(field,'')):raise ValueError('Missing target artifact digest: '+field)
        if entry.get('validation_status') not in ('candidate','validated'):raise ValueError('Target is not accepted for installation')
        if entry.get('atlas_artifact_url') and (not entry['atlas_artifact_url'].startswith('https://') or not re.fullmatch('[0-9a-f]{64}',entry.get('atlas_sha256',''))):
            raise ValueError('Remote Atlas artifacts require an authenticated archive SHA-256')
        if entry.get('atlas_sha256') and not re.fullmatch('[0-9a-f]{64}',entry['atlas_sha256']):
            raise ValueError('Invalid bundled Atlas archive digest')
        shared=entry.get('shared_files',{})
        if not isinstance(shared,dict) or len(shared)>10000:raise ValueError('Invalid shared Atlas file list')
        for name,digest in shared.items():
            if not isinstance(name,str) or not name or '\\' in name or ':' in name or name.startswith('/') or any(p in ('','.','..') for p in name.split('/')):
                raise ValueError('Unsafe shared Atlas file path')
            if name in ('manifest.json','updates/catalog.json') or name.startswith('.distribution/'):
                raise ValueError('Reserved shared Atlas file path')
            if not isinstance(digest,str) or not re.fullmatch('[0-9a-f]{64}',digest):raise ValueError('Invalid shared Atlas file digest')
        launcher=entry.get('launcher_files',{})
        if not isinstance(launcher,dict) or len(launcher)>10000:raise ValueError('Invalid launcher dependency list')
        for name,digest in launcher.items():
            if not isinstance(name,str) or not re.fullmatch(r'bin/[A-Za-z0-9_.+-]+\.dll',name,re.I):raise ValueError('Unsafe launcher dependency path')
            if not isinstance(digest,str) or not re.fullmatch('[0-9a-f]{64}',digest):raise ValueError('Invalid launcher dependency digest')
            if name in shared:raise ValueError('Duplicate dependency source')
        if not entry.get('upstream_url','').startswith('https://github.com/Supermedo/bloodborne_pc/releases/download/'+tag+'/'):
            raise ValueError('Target must use the official immutable upstream release asset')
    return data

def resolve(data,tag,*,allow_candidate=False):
    matches=[e for e in data['targets'] if e['upstream_release']==tag]
    if len(matches)!=1:raise ValueError('Atlas compatibility is not available for '+tag+'. Keep the working Atlas installation.')
    entry=matches[0]
    if entry['validation_status']!='validated' and not allow_candidate:raise ValueError('This target is a local candidate awaiting owner approval')
    return entry
