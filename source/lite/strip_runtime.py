"""Strip only trailing COFF DWARF sections from an unsigned PE copy; never edit input."""
import argparse, hashlib, json, struct
from pathlib import Path

def sha(data): return hashlib.sha256(data).hexdigest()

def sections(data):
    pe=struct.unpack_from('<I',data,60)[0]
    assert data[pe:pe+4]==b'PE\0\0'
    n=struct.unpack_from('<H',data,pe+6)[0]
    sym,nsym=struct.unpack_from('<II',data,pe+12)
    optional=pe+24
    assert struct.unpack_from('<H',data,optional)[0]==0x20b
    section=optional+struct.unpack_from('<H',data,pe+20)[0]
    out=[]
    for i in range(n):
        h=section+40*i
        name=data[h:h+8].split(b'\0')[0].decode('ascii')
        if name.startswith('/'):
            start=sym+18*nsym+int(name[1:]); name=data[start:data.index(b'\0',start)].decode()
        vs,rva,size,offset=struct.unpack_from('<IIII',data,h+8)
        out.append(dict(name=name,header=h,virtual_size=vs,rva=rva,size=size,offset=offset,
                        sha256=sha(data[offset:offset+size])))
    return pe,optional,section,out

def strip(source,target,receipt):
    source,target=Path(source).resolve(),Path(target).resolve()
    if source==target or target.exists(): raise ValueError('Output must be a new distinct file')
    data=source.read_bytes();pe,opt,table,items=sections(data)
    removed=[s for s in items if s['name'].startswith('.debug_')]
    kept=[s for s in items if not s['name'].startswith('.debug_')]
    if not removed: raise ValueError('No DWARF sections')
    end=max(s['offset']+s['size'] for s in kept)
    if any(s['offset']<end for s in removed): raise ValueError('Debug sections are not trailing')
    cert,size=struct.unpack_from('<II',data,opt+112+8*4)
    if cert or size: raise ValueError('Signed binary requires a separate reviewed signing workflow')
    out=bytearray(data[:end])
    struct.pack_into('<H',out,pe+6,len(kept))
    struct.pack_into('<II',out,pe+12,0,0)
    flags=struct.unpack_from('<H',out,pe+22)[0]
    struct.pack_into('<H',out,pe+22,flags|0x0200)
    align=struct.unpack_from('<I',out,opt+32)[0]
    image=max(s['rva']+max(s['virtual_size'],s['size']) for s in kept)
    struct.pack_into('<I',out,opt+56,(image+align-1)//align*align)
    struct.pack_into('<I',out,opt+64,0) # PE checksum is optional for user EXEs.
    headers=[data[s['header']:s['header']+40] for s in kept]
    out[table:table+40*len(items)]=b''.join(headers)+bytes(40*(len(items)-len(kept)))
    _,_,_,actual=sections(out)
    assert [(x['name'],x['sha256'],x['rva']) for x in actual]==[(x['name'],x['sha256'],x['rva']) for x in kept]
    target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(out)
    record=dict(tool='atlas-lite-strip-runtime/1',source=str(source),target=str(target),
                source_sha256=sha(data),target_sha256=sha(out),before_bytes=len(data),after_bytes=len(out),
                removed=removed,preserved=actual,loaded_section_bytes_unchanged=True,
                header_changes=['NumberOfSections','COFF symbol table removed','DEBUG_STRIPPED flag','SizeOfImage','checksum cleared','section headers compacted'])
    Path(receipt).write_text(json.dumps(record,indent=2),encoding='utf-8')
    return record

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('source');p.add_argument('target');p.add_argument('receipt');a=p.parse_args()
    r=strip(a.source,a.target,a.receipt);print(json.dumps({k:r[k] for k in ('before_bytes','after_bytes','source_sha256','target_sha256')}))
