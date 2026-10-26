"""Verify the reduced release, preserved meshes, and native sections in new paths.

Run in FreeCAD's Python environment with Pillow. This is geometry/path evidence,
not a physical retention, adhesive-temperature, or assembly acceptance test.
"""
import hashlib
import json
from pathlib import Path
import tempfile
import xml.etree.ElementTree as E
import zipfile
import FreeCAD as A
import Part
from PIL import Image, ImageDraw
from check_print_project_preservation import read
from check_head_print_paths import layers
from check_completion_paths import material_points
from check_remaining_paths import coverage
from prepare_lean_print import BASE, TARGET, OUT, ROOT, ORDER, REMOVED, archive_write, setmeta, xml


def check():
    report = json.loads((OUT/'delivery-check.json').read_text())
    geometry = json.loads((OUT/'geometry-audit.json').read_text())
    assert hashlib.sha256(TARGET.read_bytes()).hexdigest() == report['project_sha256']
    for label, path in [('delivery', ROOT/'hardware/model/CyberTrack.FCStd'),
                        ('source', ROOT/'hardware/model/source/CyberTrack-design.FCStd')]:
        assert hashlib.sha256(path.read_bytes()).hexdigest() == geometry['documents'][label]['sha256']
    old, old_objects, old_config, old_plates = read(BASE)
    new, objects, config, plates = read(TARGET)
    assert len(new) == 33 and len(objects) == 29 and config == old_config
    assert set(objects) == set(old_objects)-REMOVED
    assert objects == {n:v for n,v in old_objects.items() if n not in REMOVED}
    old_plate_of = {name:i for i,p in enumerate(old_plates,1) for name in p['objects']}
    plate_of = {name:i for i,p in enumerate(plates,1) for name in p['objects']}
    origin = lambda i: (((i-1)%3)*307.2,-((i-1)//3)*307.2)
    preserved = 0
    for key,(vs,ts,md,kind) in new.items():
        ov,ot,om,ok = old[key]; name = key[0]
        assert md == om and kind == ok
        if name in report['modified_geometry']: continue
        assert ts == ot and len(vs) == len(ov)
        a,b = origin(old_plate_of[name]), origin(plate_of[name])
        if name in ('PP01-base','PP02-base'):
            centre = [(min(v[k] for v in ov)+max(v[k] for v in ov))/2 for k in (0,1)]
            x,y = (195,30) if name=='PP01-base' else (211,93)
            expected=[]
            for v in ov:
                dx,dy=v[0]-centre[0],v[1]-centre[1]
                if name=='PP01-base': dx,dy=-dy,dx
                expected.append((b[0]+x+dx,b[1]+y+dy,v[2]))
        else: expected=[(v[0]-a[0]+b[0],v[1]-a[1]+b[1],v[2]) for v in ov]
        assert max(abs(x-y) for v,w in zip(vs,expected) for x,y in zip(v,w)) < 2e-5, name
        preserved += 1
    with zipfile.ZipFile(ROOT/'hardware/model/CyberTrack.FCStd') as z:
        native={o.get('name') for o in E.fromstring(z.read('Document.xml')).findall("ObjectData/Object")
                if o.find("Properties/Property[@name='Shape']/Part") is not None}
    ready=ROOT/'hardware/model/print-ready'
    inventory=json.loads((ready/'completion-inventory.json').read_text())
    prior=json.loads((ready/'completeness-audit.json').read_text())
    expected=(set(prior['included'])|set(inventory['added_print_parts']))-REMOVED
    other=set(inventory['other_objects'])-set(geometry['documents']['delivery']['removed'])
    assert len(expected)==29 and native==expected|other
    with zipfile.ZipFile(TARGET) as z: files={n:z.read(n) for n in z.namelist()}
    with zipfile.ZipFile(BASE) as z:
        for old_index in (1,3,4):
            assert files[f'Metadata/plate_{ORDER.index(old_index)+1}.gcode']==z.read(f'Metadata/plate_{old_index}.gcode')
    hashes={}; paths={}; boundaries={}; sections=[]
    with tempfile.TemporaryDirectory(prefix='cybertrack-lean-check-') as td:
        for i in range(1,7):
            gc=files[f'Metadata/plate_{i}.gcode']
            assert hashlib.md5(gc).hexdigest()==files[f'Metadata/plate_{i}.gcode.md5'].decode().strip().lower()
            hashes[str(i)]=hashlib.sha256(gc).hexdigest()
            if i not in (2,3,6): continue
            p=Path(td)/f'plate_{i}.gcode';p.write_bytes(gc);paths[i]=layers(p,True)
            points=[p for ss in paths[i].values() for a,b,w,f in ss for p in (a,b)]
            bounds=[min(p[0] for p in points),min(p[1] for p in points),max(p[0] for p in points),max(p[1] for p in points)]
            assert min(bounds)>=.5 and max(bounds)<=255.5,(i,bounds)
            boundaries[str(i)]=bounds
    targets={'EffectTray':[.2,.76,1.32,2.16,2.72,3.84],
             'IgnitionMOSCarrier':[.2,.76,1.32,2.16,2.72,3.84],
             'PP01-base':[1.5,3.5,5,8,16,21], 'PP02-base':[1.5,4.5,8,24,37,42],
             'PP03-base':[1.6,18.2,22.5,40.5,78.5,86.5], 'LC04-flipped':[2.5,9,12,15,17,24,27]}
    for name, heights in targets.items():
        index=plate_of[name];dx,dy=origin(index)
        vs=next(v for (n,p),(v,t,m,k) in new.items() if n==name)
        lo=[min(v[k] for v in vs) for k in range(3)];hi=[max(v[k] for v in vs) for k in range(3)]
        lo[0]-=dx;hi[0]-=dx;lo[1]-=dy;hi[1]-=dy
        folder=OUT if name in geometry['parts'] else ROOT/'hardware/model/remaining-print'
        s=Part.Shape();s.read(str(folder/(name+'.brep')))
        if name=='PP01-base':s.rotate(A.Vector(),A.Vector(0,0,1),90)
        b=s.optimalBoundingBox(False)
        s.translate(A.Vector((lo[0]+hi[0]-b.XMin-b.XMax)/2,(lo[1]+hi[1]-b.YMin-b.YMax)/2,lo[2]-b.ZMin))
        model_heights=[h for h,segs in paths[index].items() if any(
            not f.startswith('Support') and f not in ('Brim','Custom')
            and lo[0]-.01<=a[0]<=hi[0]+.01 and lo[1]-.01<=a[1]<=hi[1]+.01
            for a,b,w,f in segs)]
        for target in heights:
            height=min(model_heights,key=lambda h:abs(h-target));mid=height-(.1 if height==.2 else .14)
            contours=[[[p.x,p.y] for p in w.discretize(Deflection=.01)] for w in s.slice(A.Vector(0,0,1),mid)]
            points=material_points(contours);fraction=coverage(points,paths[index][height])
            minimum=.2 if name in ('PP01-base','PP02-base') and height<2 else .55
            sections.append({'part':name,'height':height,'coverage':fraction,'minimum':minimum,
                             'passed':bool(points) and fraction>=minimum})
    assert all(r['passed'] for r in sections),[r for r in sections if not r['passed']]
    # Show the three re-sliced first layers; the other three are byte-identical.
    previews=[]
    for index in (2,3,6):
        im=Image.new('RGB',(840,880),'#f5f7fa');draw=ImageDraw.Draw(im)
        xy=lambda p:(35+p[0]*3,815-p[1]*3)
        draw.rectangle((35,47,803,815),fill='white',outline='#a4adb8',width=2)
        first=min(h for h,s in paths[index].items() if s)
        for a,b,w,f in paths[index][first]:
            color='#d98c27' if f.startswith('Support') else '#3188ce'
            draw.line([xy(a),xy(b)],fill=color,width=max(1,round(w*3)))
        draw.text((35,17),f'Plate {index} | first layer | blue: model/brim, orange: support',fill='#223244')
        im.save(OUT/f'plate-{index}-preview.png');previews.append(im)
        files[f'Metadata/plate_{index}.png']=(OUT/f'plate-{index}-preview.png').read_bytes()
    settings=E.fromstring(files['Metadata/model_settings.config'])
    for i in (2,3,6):setmeta(settings.findall('plate')[i-1],'thumbnail_file',f'Metadata/plate_{i}.png')
    files['Metadata/model_settings.config']=xml(settings);archive_write(TARGET,files)
    sheet=Image.new('RGB',(2520,880),'white')
    for i,im in enumerate(previews):sheet.paste(im,(840*i,0))
    sheet.save(OUT/'first-layers.png')
    report['project_sha256']=hashlib.sha256(TARGET.read_bytes()).hexdigest()
    report.update(verified_native_geometry_objects=len(native),verified_inventory_parts=29,
                  preserved_meshes_including_modifiers=preserved,gcode_sha256=hashes,
                  all_layer_bounds_mm=boundaries,checked_native_sections=sections,
                  passed=True,limits='CAD and sampled paths only; adhesive retention and physical fit unverified.')
    (OUT/'delivery-check.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'passed':True,'parts':29,'sections':len(sections),'saved_seconds':report['saved_seconds']},indent=2))
    return report


if __name__=='__main__':check()
