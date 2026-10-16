"""Atlas protocol 1: upstream launcher settings and runtime identity boundary."""
from __future__ import annotations
import hashlib,json
from pathlib import Path
from urllib.parse import urlsplit

PROTOCOL=1
NETWORK_KEYS=('BB_ONLINE','BB_NET_BACKEND','BB_BRIDGE','BB_BRIDGE_LIVE_MAP','BB_CLIENT_VERSION',
              'BB_SHADNET_SERVER','BB_SHADNET_WEBAPI','BB_SHADNET_NPID','BB_SHADNET_PASSWORD',
              'BB_SHADNET_TOKEN','BB_COMMUNITY_SERVER','BB_UPNP','BB_POOL_NAME',
              'BB_THD_ONLINE_ID','BB_THD_TOKEN','BB_THD_SERVER','BB_THD_AUTH','BB_THD_RULESET')

def truth(value):return value is True or value==1 or isinstance(value,str) and value.lower() in ('1','true','yes','on')

def configure_network(environment,settings,release='1.8.1'):
    """Reconstruct the selected profile; stale inherited backends cannot win."""
    env=dict(environment)
    for key in NETWORK_KEYS:env.pop(key,None)
    env['BB_CLIENT_VERSION']='bbport '+release
    if not truth(settings.get('online',False)):return env
    pool=settings.get('online_pool','shadnet')
    if pool not in ('shadnet','supermedo','huntersdream'):raise ValueError('Unknown online pool')
    community=str(settings.get('online_community') or 'https://thehuntersdream.com').strip().rstrip('/')
    if '://' not in community:community='https://'+community
    env.update(BB_ONLINE='1',BB_COMMUNITY_SERVER=community,
               BB_UPNP='1' if truth(settings.get('online_upnp',True)) else '0')
    if pool=='huntersdream':
        if release=='1.7.2':
            env.update(BB_BRIDGE='1',BB_SHADNET_NPID='',BB_SHADNET_PASSWORD='',
                       BB_BRIDGE_LIVE_MAP='1' if truth(settings.get('bridge_live_map',True)) else '0')
            return env
        env.update(BB_NET_BACKEND='thd',BB_THD_ONLINE_ID=str(settings.get('thd_online_id','')),
                   BB_THD_TOKEN=str(settings.get('thd_token','')),
                   BB_BRIDGE_LIVE_MAP='1' if truth(settings.get('bridge_live_map',True)) else '0')
    else:
        server='www.supermedo.com:31313' if pool=='supermedo' else str(settings.get('online_server') or 'srv.shadps4.net:31313').strip()
        host=urlsplit(server if '://' in server else '//'+server).hostname
        if not host:raise ValueError('Invalid online server')
        host='['+host+']' if ':' in host else host
        webapi='' if pool=='supermedo' else str(settings.get('online_webapi') or '').strip()
        env.update(BB_SHADNET_SERVER=server,BB_SHADNET_WEBAPI=webapi or 'http://'+host+':31315',
                   BB_SHADNET_NPID=str(settings.get('supermedo_user' if pool=='supermedo' else 'online_npid','')).strip(),
                   BB_SHADNET_PASSWORD=str(settings.get('supermedo_password' if pool=='supermedo' else 'online_password','')))
        if pool=='supermedo':env['BB_POOL_NAME']='SuperMedo Server'
    return env

def validate_profile(manifest,dependencies,root):
    """Legacy contracts remain readable; new builds must declare matching identities."""
    declared=manifest.get('compatibility')
    if declared is None:
        legacy=manifest.get('legacy_runtime')
        if legacy:
            if legacy.get('upstream_release')!='windows-v1.7.2' or legacy.get('adapter_protocol')!=PROTOCOL:
                raise ValueError('Unsupported legacy Atlas adapter')
            if hashlib.sha256((Path(root)/manifest['paths']['probe']).read_bytes()).hexdigest()!=legacy.get('runtime_sha256'):
                raise ValueError('Legacy Atlas native digest mismatch')
        return legacy
    profile=dependencies.get('compatibility',{})
    if declared.get('adapter_protocol')!=PROTOCOL or profile.get('adapter_protocol')!=PROTOCOL:
        raise ValueError('Unsupported Atlas launcher adapter protocol')
    for key in ('upstream_release','upstream_commit'):
        if not declared.get(key) or declared[key]!=profile.get(key):raise ValueError('Mixed Atlas runtime and launcher profile: '+key)
    if 'native-build.json' not in manifest.get('files',{}):raise ValueError('Atlas native build proof is not pinned')
    proof=json.loads((Path(root)/'native-build.json').read_text(encoding='utf-8'))
    for key in ('adapter_protocol','upstream_release','upstream_commit'):
        if proof.get(key)!=declared.get(key):raise ValueError('Atlas native build identity mismatch: '+key)
    binary=Path(root)/manifest['paths']['probe']
    if hashlib.sha256(binary.read_bytes()).hexdigest()!=proof.get('runtime_sha256'):
        raise ValueError('Atlas native build digest mismatch')
    return declared
