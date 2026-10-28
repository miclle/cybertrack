"""Apply the scoped 2026-10-27 backpack revision to saved current geometry.

Run in FreeCAD Python. Historical full-build scripts are not current release inputs.
"""
import hashlib
import json
from pathlib import Path
import shutil
import FreeCAD as A
import Part
import MeshPart
import Mesh
from effects_mount import housing, mirror, zc, ring
from breadboard_layout import box
from update_pp02 import shape_rows, signature, same
from cad_gui_state import capture as capture_gui, restore as restore_gui

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / 'hardware/model'
BOTTLE = ['BubbleModule','BubblePod','BubbleBottomPad','BubbleSidePad0','BubbleSidePad1',
          'BubbleRetentionBand','BubbleStrapClosure','BubbleLidMark',
          'BubblePodInsertL','BubblePodInsertR','BubblePodScrewL','BubblePodScrewR']
SPACES = ['BubbleStrapAccessSpace','BubbleBottleRemovalSpace','BubbleFingerSpace','BubbleDipTubeSpace']
LINERS = ['ArcLiner'+part+side+str(i) for part in ('Inner','Outer') for side in 'LR' for i in (0,1)]
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()


def revised_shell(original):
    old = housing()
    new = box(57,81,51.5,60.5,89,118).fuse(zc(20,51.5,90,74,85))
    for z in (86,114):
        new = new.fuse(ring(20,17.5,z-4,z+4))
        for y in (66.5,103.5):
            new = new.fuse(box(67,y-4,z-4,80.3,y+4,z+4))
    new = new.cut(zc(17.5,53,119,74,85))
    # Extend the existing chassis relief at the lower inner/front corner.
    new = new.cut(box(57.7,60,50,62.45,74.3,60.75))
    new = new.cut(box(60.5,60,50,64.5,74.75,54))
    result = original.cut(old.fuse(mirror(old,-1))).fuse(new.fuse(mirror(new,-1)))
    for sign in (-1,1):
        result = result.cut(zc(17.5,53,125,sign*74,85))
        relief = box(57.7,60,50,62.45,74.3,60.75)
        result = result.cut(mirror(relief,sign))
    return result.removeSplitter()


def main():
    paths = {'source':MODEL/'source/CyberTrack-design.FCStd','delivery':MODEL/'CyberTrack.FCStd'}
    gui = {k:capture_gui(p) for k,p in paths.items()}
    assert gui['delivery'], 'Delivery must retain GUI state before editing'
    gui['source'] = gui['source'] or gui['delivery']
    docs = {k:A.openDocument(str(p)) for k,p in paths.items()}
    before = {k:shape_rows(d) for k,d in docs.items()}
    report = {'date':'2026-10-27','baseline_sha256':{k:sha(p) for k,p in paths.items()},
              'bore_diameter_mm':35,'outer_diameter_mm':40,'nominal_wall_mm':2.5,
              'axes_xy_mm':[[74,85],[-74,85]],'floor_thickness_mm':1.5,
              'lower_inner_front_relief_mm':[57.7,60,50,62.45,74.3,60.75],
              'removed':{},'unchanged':{},'exports':{},'physical_fit_verified':False,
              'limits':'CAD and mesh checks only. Lower front/inner relief interrupts the wall locally. Original Ø25.5 body remains a placeholder; radial gap 4.75 mm, retention and liquid supply unverified.'}
    src,d = docs['source'],docs['delivery']
    assert src.getObject('BubbleModule'), 'Revision already applied; restore the recorded baseline before replay.'
    src.BackpackShell.Shape = revised_shell(src.BackpackShell.Shape)
    src.recompute()
    shape = src.PrintBackpack.Shape.copy()
    assert shape.isValid() and len(shape.Solids)==1
    d.PrintBackpack.Shape = shape
    for key,doc in docs.items():
        removed = [n for n in BOTTLE+SPACES+LINERS if doc.getObject(n)]
        for n in removed:doc.removeObject(n)
        report['removed'][key] = removed
        doc.PrintBackpack.Label = 'PP03 背包一体外壳及 Ø35 桶座'
        doc.PrintBackpack.EvidenceBasis = '2026-10-27 双侧筒内径35／外径40 mm；局部下缘避让底盘；泡泡液瓶组件撤销，旧软衬撤销；实物配合与保持力未验。'
        if doc.getObject('BackpackShell'):
            doc.BackpackShell.Label = '背包／一体 Ø35 点火模块桶座'
            doc.BackpackShell.EvidenceBasis = doc.PrintBackpack.EvidenceBasis
        doc.recompute()
        changed = {'PrintBackpack'} | ({'BackpackShell'} if key=='source' else set())
        unaffected = set(before[key])-set(removed)-changed
        assert all(same(before[key][n],signature(doc.getObject(n).Shape)) for n in unaffected)
        report['unchanged'][key] = len(unaffected)
        assert not any(o.Label.startswith('泡泡液瓶 ·') for o in doc.Objects)
    # Analytic bore surfaces and clear axial probes, with retained bottom stops.
    report['bores'] = []
    for x in (-74,74):
        faces=[f for f in shape.Faces if isinstance(f.Surface,Part.Cylinder)
               and abs(f.Surface.Radius-17.5)<1e-6 and abs(f.Surface.Center.x-x)<1e-6]
        clear=shape.common(zc(17.49,53.01,124,x,85)).Volume
        floor=shape.common(zc(12.75,51.5,53,x,85)).Volume
        assert len(faces)>=1 and clear<.01 and floor>700,(x,len(faces),clear,floor)
        report['bores'].append({'x_mm':x,'radius_mm':17.5,'cylindrical_faces':len(faces),'probe_intersection_mm3':clear,'floor_probe_mm3':floor})
    hits=[]
    for o in d.Objects:
        if not hasattr(o,'Shape') or o.isDerivedFrom('App::DocumentObjectGroup') or o.Name=='PrintBackpack' or getattr(o,'Category','')=='clearance':continue
        if not shape.BoundBox.intersect(o.Shape.BoundBox):continue
        v=shape.common(o.Shape).Volume
        if v>.01:hits.append({'object':o.Name,'volume_mm3':v})
    assert not hits,hits
    report['backpack_collisions']=hits
    # Export both current bed-oriented variants and the direct part index.
    for orientation,angle in [('base',0),('back',90)]:
        s=shape.copy()
        if angle:s.rotate(A.Vector(),A.Vector(1,0,0),angle)
        b=s.optimalBoundingBox(False)
        s.translate(A.Vector(-(b.XMin+b.XMax)/2,-(b.YMin+b.YMax)/2,-b.ZMin))
        stem=MODEL/'remaining-print'/('PP03-'+orientation)
        s.exportBrep(str(stem.with_suffix('.brep')));s.exportStep(str(stem.with_suffix('.step')))
        mesh=MeshPart.meshFromShape(Shape=s,LinearDeflection=.06,AngularDeflection=.12,Relative=False)
        mesh.write(str(stem.with_suffix('.stl')))
        back=Mesh.Mesh(str(stem.with_suffix('.stl')))
        assert back.isSolid() and not back.hasNonManifolds() and back.countComponents()==1
        exchange=Part.Shape();exchange.read(str(stem.with_suffix('.step')))
        delta=s.cut(exchange).Volume+exchange.cut(s).Volume
        assert exchange.isValid() and len(exchange.Solids)==1 and delta<.01,delta
        report['exports'][orientation]={'facets':back.CountFacets,'step_delta_mm3':delta,'stl_sha256':sha(stem.with_suffix('.stl')),'step_sha256':sha(stem.with_suffix('.step'))}
    for ext in ('stl','step'):
        shutil.copy2(MODEL/'remaining-print'/('PP03-base.'+ext),MODEL/'print-parts'/('PP03-Backpack.'+ext))
    for key,doc in docs.items():
        expected=shape_rows(doc);doc.save();A.closeDocument(doc.Name)
        restore_gui(paths[key],gui[key])
        check=A.openDocument(str(paths[key]));actual=shape_rows(check)
        assert set(expected)==set(actual) and all(same(expected[n],actual[n]) for n in expected)
        docs[key]=check
    d=docs['delivery']
    assembly=[o for o in d.Objects if hasattr(o,'Shape') and not o.isDerivedFrom('App::DocumentObjectGroup') and getattr(o,'Category','') not in ('clearance','envelope')]
    Part.export(assembly,str(MODEL/'CyberTrack.step'))
    report['files_sha256']={str(p.relative_to(ROOT)):sha(p) for p in [*paths.values(),MODEL/'CyberTrack.step',MODEL/'print-parts/PP03-Backpack.stl',MODEL/'print-parts/PP03-Backpack.step']}
    report['saved_reopened']=True;report['passed']=True
    (MODEL/'backpack-35mm-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)

if __name__=='__main__':main()
