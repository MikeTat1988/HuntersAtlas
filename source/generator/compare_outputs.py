"""Developer-only receipts; no changes to game or installed Atlas."""
from pathlib import Path
import json,hashlib,sys
root=Path(__file__).parent
fresh=Path(sys.argv[1]);baseline=Path(sys.argv[2]) if len(sys.argv)>2 else None
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
manifest=json.loads((fresh/'maps/generated-assets.json').read_text(encoding='utf-8'))
assert all(sha(fresh/path)==digest for path,digest in manifest['files'].items())
report={'generated_manifest_hashes_pass':True,'fresh_counts':manifest['counts'],'maps':{},'baseline':str(baseline) if baseline else None}
atlas=json.loads((fresh/'maps/atlas.json').read_text(encoding='utf-8'))
def markers(data):return sorted([(m['kind'],m['name'],tuple(m['pos']),m.get('entity_id'),m.get('part')) for m in data['markers']])
if baseline:
    for item in atlas['maps']:
        mid=item['id'];a=json.loads((fresh/'maps'/f'{mid}.json').read_text(encoding='utf-8'));b=json.loads((baseline/'maps'/f'{mid}.json').read_text(encoding='utf-8'))
        report['maps'][mid]={'geometry_layers_equal':a['layers']==b['layers'],'bounds_equal':a['bounds']==b['bounds'],'lamp_coordinates_names_equal':[(x['name'],x['pos']) for x in a['lamps']]==[(x['name'],x['pos']) for x in b['lamps']],'semantic_markers_equal':markers(a)==markers(b),'fresh_markers':len(a['markers']),'baseline_markers':len(b['markers'])}
    report['all_geometry_layers_equal']=all(x['geometry_layers_equal'] for x in report['maps'].values())
    report['all_marker_semantics_equal']=all(x['semantic_markers_equal'] for x in report['maps'].values())
catalog=json.loads((fresh/'maps/catalog.json').read_text(encoding='utf-8'));report['runtime_catalog_indices']={mid:{'landmarks':len(e['landmarks']),'regions':len(e['regions']),'names':sorted(set(r['name'] for r in e['regions']))} for mid,e in catalog.items()}
report['portable_paths_pass']=not any(token in (fresh/'maps/catalog.json').read_text(encoding='utf-8') for token in ('D:\\','C:\\','D:/Bloodborne','working/'))
target=root/'logs'/('comparison-'+fresh.name.replace(' ','_')+'.json');target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=False,indent=2))
