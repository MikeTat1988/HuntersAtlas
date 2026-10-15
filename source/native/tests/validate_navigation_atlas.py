"""Validate coverage and projection against the game-derived lamp coordinates."""
import json,math,sys
from pathlib import Path
root=Path(sys.argv[1]);atlas=json.loads((root/'atlas.json').read_text())
assert len(atlas['maps'])==16
results=[]
for entry in atlas['maps']:
    a=json.loads((root/(entry['id']+'.json')).read_text())
    assert a['id']==entry['id'] and a['triangles']>0 and a['layers']
    assert all(math.isfinite(v) for v in a['bounds'])
    rects=sum(len(l['rects']) for l in a['layers'])
    assert rects>0
    for layer in a['layers']:
        assert all(len(r)==4 and all(math.isfinite(v) for v in r) and r[2]>0 and r[3]>0 for r in layer['rects'])
    for lamp in a['lamps']:
        x,y,z=lamp['pos'];assert a['bounds'][0]<=x<=a['bounds'][2] and a['bounds'][1]<=z<=a['bounds'][3]
        nearby=[]
        for layer in a['layers']:
            if abs(y-layer['height']-3)>10:continue
            nearby += [r for r in layer['rects'] if r[0]-2<=x<=r[0]+r[2]+2 and r[1]-2<=z<=r[1]+r[3]+2]
        assert nearby,(a['id'],lamp,'No floor near lamp')
    results.append({'map':a['id'],'name':a['name'],'lamps':len(a['lamps']),'rectangles':rects,'omitted_collisions':a['failures']})
print(json.dumps({'status':'NAVIGATION_ATLAS_PASS','areas':len(results),'results':results},indent=2))
