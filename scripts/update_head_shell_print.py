"""Locally consolidate PP07 and adapt head fasteners; preserve all chassis geometry.

Run with FreeCAD's bundled Python (Resources/lib on PYTHONPATH). GUI is loaded
before opening documents to preserve saved appearance. --root allows staging.
"""
import argparse
import json
from pathlib import Path

import FreeCAD as App
import Part
import Mesh
import MeshPart
from head_shell_print import (MEMBERS, CROWN_MOUNTS, TRAY_MOUNTS, SCREW,
                             PILOT_DIAMETER, geometry, screw, print_shape, coupon, box)
from update_pp02 import sha, dump, same, shape_rows

ROOT = Path(__file__).resolve().parents[1]/'hardware/model'
REPORT = 'head-shell-print-audit.json'


def mesh_export(shape, path):
    MeshPart.meshFromShape(Shape=shape, LinearDeflection=.08, AngularDeflection=.15,
                          Relative=False).write(str(path))
    mesh = Mesh.Mesh(str(path))
    assert mesh.isSolid() and not mesh.hasNonManifolds()
    assert mesh.countComponents() == len(shape.Shells)
    return dict(closed=True, nonmanifold=False, components=mesh.countComponents(),
                facets=mesh.CountFacets, sha256=sha(path))


def row(obj):
    b = obj.Shape.optimalBoundingBox(False)
    return dict(name=obj.Name, label=obj.Label, category=getattr(obj, 'Category', 'merged_print_part'),
                valid=obj.Shape.isValid(), solids=len(obj.Shape.Solids), volume_mm3=obj.Shape.Volume,
                bbox_mm=[b.XMin,b.YMin,b.ZMin,b.XMax,b.YMax,b.ZMax])


def check_services(doc, head, crown):
    results = {}
    for name, shape, direction, positions in (
        ('crown_up', crown, App.Vector(0,0,1), [0,.1,.25,.5,1,2,3,5,10,20,40,65]),):
        hits = []
        for distance in positions:
            s = shape.copy(); s.translate(direction*distance)
            volume = s.common(head).Volume
            if volume > .01: hits.append(dict(distance_mm=distance, overlap_mm3=volume))
        results[name] = dict(method='sampled rigid translation against PP07', positions_mm=positions,
                             overlaps=hits, passed=not hits)
    sweep = box((-52.5,-72.5,171.5),(52.5,17.5,295))
    for x,y in TRAY_MOUNTS:
        x0,x1 = (-61,-52) if x<0 else (52,61)
        sweep = sweep.fuse(box((x0,y-4,171.5),(x1,y+4,295)))
    sweep = sweep.cut(box((-24.5,-73,171),(24.5,-70.5,296)))
    volume = sweep.common(head).Volume
    results['tray_up'] = dict(method='continuous conservative prism union against PP07',
        translation_mm=[0,0,85], overlap_mm3=volume, passed=volume<.01,
        prerequisites='remove crown and screws, unplug and park harness; sensor module may remain')
    tools=[]
    for x,y in TRAY_MOUNTS:
        tool=Part.makeCylinder(4,90,App.Vector(x,y,175))
        v=tool.common(head).Volume
        tools.append(dict(x=x,y=y,diameter_mm=8,overlap_mm3=v))
    results['tray_tool_access'] = dict(tests=tools,passed=all(t['overlap_mm3']<.01 for t in tools))
    from ultrasonic_integration import box_sweep, arc_translation_sweep, NAMES
    rear=[];up=[]
    for n in NAMES[:3]:
        t=doc.getObject(n).Shape
        rear.append(box_sweep(t,(0,11,0)))
        u=t.copy();u.translate(App.Vector(0,11,0));up.append(box_sweep(u,(0,0,70)))
    for sign in (-1,1):
        rear.append(Part.makeCylinder(8,21.3,App.Vector(sign*13,-87.8,188),App.Vector(0,1,0)))
        s=Part.makeCylinder(8,10.3,App.Vector(sign*13,-76.8,188),App.Vector(0,1,0))
        up.append(arc_translation_sweep(s,App.Vector(0,0,70)))
    for name,shapes in [('ultrasonic_rear_11mm',rear),('ultrasonic_up_70mm',up)]:
        volume=Part.makeCompound(shapes).common(head).Volume
        results[name]=dict(method='continuous cuboid and cylinder/capsule sweep against PP07',
            overlap_mm3=volume,passed=volume<.01,
            prerequisites='remove crown and tray, unplug and release sensor mounting; actual mount still unmodeled')
    assert all(r['passed'] for r in results.values()), results
    return results


def main(root=ROOT):
    import FreeCADGui as Gui
    from PySide import QtGui
    Gui.showMainWindow()
    root=Path(root);source_path=root/'source/CyberTrack-design.FCStd';delivery_path=root/'CyberTrack.FCStd'
    if (root/REPORT).exists():
        previous=json.loads((root/REPORT).read_text())
        if previous['source_sha256']==sha(source_path) and previous['delivery_sha256']==sha(delivery_path):
            print('PP07 already applied; saved files preserved.',flush=True)
            return previous
        raise RuntimeError('PP07 report exists but model changed; inspect newer edits before reapplying')
    baseline={str(p.relative_to(root)):sha(p) for p in (source_path,delivery_path)}
    source=App.openDocument(str(source_path));delivery=App.openDocument(str(delivery_path))
    docs=(source,delivery)
    before={d.Name:shape_rows(d) for d in docs}
    # Exact geometry comparison for unaffected objects, not just volume signatures.
    original={d.Name:{o.Name:o.Shape.copy() for o in d.Objects if o.Name in before[d.Name]} for d in docs}
    appearance={d.Name:{o.Name:{k:getattr(o.ViewObject,k) for k in ('ShapeColor','DiffuseColor','Visibility','Transparency')}
        for o in d.Objects if o.Name in before[d.Name]} for d in docs}
    g=geometry(source)
    print('Geometry built',flush=True)
    assert all(source.getObject(n).Shape.cut(delivery.getObject(n).Shape).Volume+
               delivery.getObject(n).Shape.cut(source.getObject(n).Shape).Volume<1e-5 for n in MEMBERS)
    # Compare added connector material against both installed parts and planned routes.
    old_union=Part.makeCompound([delivery.getObject(n).Shape for n in MEMBERS])
    removed=old_union.cut(g['merged']).Volume
    excluded=set(MEMBERS)|{'PrintCrown'}|{o.Name for o in delivery.Objects if o.Name.startswith(
        ('CrownInsert','CrownScrew','BreadboardInsert','BreadboardScrew'))}
    static=[]
    for o in delivery.Objects:
        if not hasattr(o,'Shape') or o.Name in excluded or o.Shape.isNull():continue
        if g['merged'].BoundBox.intersect(o.Shape.BoundBox):
            volume=g['merged'].common(o.Shape).Volume
            static.append(dict(object=o.Name,category=getattr(o,'Category',''),overlap_mm3=volume))
    assert not [r for r in static if r['overlap_mm3']>.01],static
    assert g['merged'].common(g['crown']).Volume<.01
    services=check_services(delivery,g['merged'],g['crown'])
    print('Static and service checks passed',flush=True)
    connector_rows=[]
    for name,shape in g['connectors']:
        contacts=[]
        for n in MEMBERS:
            s=g['head'] if n=='HeadShell' else source.getObject(n).Shape
            volume=shape.common(s).Volume
            if volume>.001:contacts.append(dict(object=n,overlap_mm3=volume))
        assert len(contacts)>=2,(name,contacts)
        connector_rows.append(dict(name=name,volume_mm3=shape.Volume,contacts=contacts))
    changed_crown=[]
    for member in source.PrintCrown.Shapes:
        new=member.Shape.cut(g['pockets']).removeSplitter()
        if member.Shape.cut(new).Volume>.00001:
            member.Shape=new;member.ViewObject.DiffuseColor=[member.ViewObject.ShapeColor]
            changed_crown.append(member.Name)
    source.HeadShell.Shape=g['head']
    source.HeadShell.ViewObject.DiffuseColor=[source.HeadShell.ViewObject.ShapeColor]
    for name,shape in g['connectors']:
        o=source.addObject('Part::Feature','HeadPrint'+name);o.Shape=shape
        o.Label='头壳 · 背侧连接 · '+name
        o.addProperty('App::PropertyString','Category');o.Category='exterior'
        o.ViewObject.ShapeColor=(.34,.42,.46);o.ViewObject.Visibility=False
    union=source.addObject('Part::Feature','PrintHeadShell')
    union.addProperty('App::PropertyLinkList','Shapes','Sources')
    union.Shape=g['merged'].copy()
    union.Shapes=[source.getObject(n) for n in MEMBERS]+[source.getObject('HeadPrint'+n) for n,_ in g['connectors']]
    if source.getObject('PrintParts'):source.PrintParts.addObject(union)
    source.recompute()
    assert union.Shape.isValid() and len(union.Shape.Solids)==1
    assert union.Shape.cut(g['merged']).Volume+g['merged'].cut(union.Shape).Volume<1e-5
    assert g['crown'].cut(source.PrintCrown.Shape).Volume+source.PrintCrown.Shape.cut(g['crown']).Volume<1e-5
    for n in MEMBERS:source.getObject(n).ViewObject.Visibility=False
    fused=delivery.addObject('Part::Feature','PrintHeadShell');fused.Shape=g['merged']
    for obj in (union,fused):
        obj.Label='PP07 头部下壳及固定装饰'
        obj.addProperty('App::PropertyString','PrintPartID','Manufacturing');obj.PrintPartID='PP07'
        obj.addProperty('App::PropertyString','EvidenceBasis','Manufacturing')
        obj.EvidenceBasis='34个原特征＋14处连接；Ø2.5自攻外形螺丝，Ø2.1导孔待试拧；见'+REPORT
        obj.addProperty('App::PropertyStringList','SourceFeatures','Evidence');obj.SourceFeatures=MEMBERS
        obj.addProperty('App::PropertyString','DesignSource','Evidence');obj.DesignSource='source/CyberTrack-design.FCStd'
        obj.ViewObject.ShapeColor=(.34,.42,.46);obj.ViewObject.LineColor=(.08,.10,.12)
        obj.ViewObject.DisplayMode='Flat Lines';obj.ViewObject.Visibility=True
    # The finished delivery contains only the fused head; source features remain editable in source/.
    for n in MEMBERS:delivery.removeObject(n)
    delivery.PrintCrown.Shape=g['crown']
    delivery.PrintCrown.ViewObject.DiffuseColor=[delivery.PrintCrown.ViewObject.ShapeColor]
    removed_inserts=[];changed_screws=[]
    for doc in docs:
        for tag,x,y in CROWN_MOUNTS:
            name='CrownInsert'+tag
            if doc.getObject(name):doc.removeObject(name)
            name='CrownScrew'+tag;doc.getObject(name).Shape=screw(x,y,218.6)
            changed_screws.append(name)
        for i,(x,y) in enumerate(TRAY_MOUNTS):
            name='BreadboardInsert'+str(i)
            if doc.getObject(name):doc.removeObject(name)
            name='BreadboardScrew'+str(i);doc.getObject(name).Shape=screw(x,y,174)
            changed_screws.append(name)
        for name in set(changed_screws):
            obj=doc.getObject(name);obj.Label2='实测Ø2.5／含帽8.6／帽Ø3.9×1；帽下7.6；光杆包络，非螺纹模型'
            obj.EvidenceBasis='用户确认尺寸；牙型与保持力待试拧，不再配原M2.5嵌件'
            obj.ViewObject.DiffuseColor=[obj.ViewObject.ShapeColor]
        doc.Label='CyberTrack 双履带交互机器人 · 0.58 头壳整体打印'
        doc.recompute()
    removed_inserts=['CrownInsert'+tag for tag,_,_ in CROWN_MOUNTS]+['BreadboardInsert'+str(i) for i in range(4)]
    changed_source={'HeadShell','PrintCrown',*changed_crown,*changed_screws,*removed_inserts}
    changed_delivery={*MEMBERS,'PrintCrown',*changed_screws,*removed_inserts}
    unchanged={}
    for doc,changed in ((source,changed_source),(delivery,changed_delivery)):
        count=0
        for name,old in original[doc.Name].items():
            if name in changed:continue
            obj=doc.getObject(name);assert obj is not None,name
            new=obj.Shape
            if old.cleaned().exportBrepToString()!=new.cleaned().exportBrepToString():
                assert old.cut(new).Volume+new.cut(old).Volume<1e-5,name
            if not (doc==source and name in MEMBERS):
                assert all(getattr(obj.ViewObject,k)==v for k,v in appearance[doc.Name][name].items()),name
            count+=1
        unchanged['source' if doc==source else 'delivery']=count
    # Check screws against the cover/tray; contact with pilot walls is intentional threading stock.
    screw_checks=[]
    for name in sorted(set(changed_screws)):
        obj=delivery.getObject(name);cover=g['crown'] if name.startswith('Crown') else delivery.ElectronicsTray.Shape
        volume=obj.Shape.common(cover).Volume
        assert volume<.01,(name,volume)
        screw_checks.append(dict(name=name,cover_intersection_mm3=volume,thread_engagement_mm=5.1,
            blind_tip_clearance_mm=1.0 if name.startswith('Crown') else 1.9))
    print('Scope and screw checks passed',flush=True)
    out=root/'print-parts';out.mkdir(exist_ok=True)
    exports={}
    for name,shape in [('PP07-HeadShell',g['merged']),('PP05-Crown',g['crown'])]:
        local,translation=print_shape(shape);stl=out/(name+'.stl');step=out/(name+'.step')
        exports[stl.name]=dict(**mesh_export(local,stl),translation_xyz_mm=translation,
            rotation_degrees=0,orientation=('assembly +Z up; open side up' if name.startswith('PP07')
                else 'assembly +Z up; decorated exterior up; supports required inside'))
        local.exportStep(str(step))
        read=Part.Shape();read.read(str(step))
        exports[step.name]=dict(sha256=sha(step),valid=read.isValid(),solids=len(read.Solids),
            volume_difference_mm3=abs(read.Volume-local.Volume),usage='exchange only; native FCStd geometry authoritative')
    coupon_path=out/'Head-ScrewFitCoupon.stl';exports[coupon_path.name]=mesh_export(coupon(),coupon_path)
    # Export the unchanged independent tray for the same head print batch.
    for objname,stem in [('ElectronicsTray','Head-ElectronicsTray')]:
        s=delivery.getObject(objname).Shape.copy()
        local,translation=print_shape(s);p=out/(stem+'.stl');exports[p.name]=mesh_export(local,p)
    assert all(sha(root/rel)==digest for rel,digest in baseline.items()), 'Model changed during analysis; refusing overwrite'
    for doc in docs:doc.recompute();doc.save()
    expected={d.FileName:shape_rows(d) for d in docs}
    # Save an isolated print-oriented editable model as a convenient inspection artifact.
    isolated=App.newDocument('PP07_Print')
    obj=isolated.addObject('Part::Feature','HeadShell');obj.Label='PP07 头壳 · 开口向上';obj.Shape=print_shape(g['merged'])[0]
    obj.ViewObject.ShapeColor=(.34,.42,.46);obj.ViewObject.LineColor=(.08,.10,.12);obj.ViewObject.DisplayMode='Flat Lines'
    isolated.recompute();isolated.saveAs(str(out/'PP07-HeadShell.FCStd'))
    view=Gui.activeDocument().activeView();view.viewAxonometric();view.fitAll()
    for _ in range(5):QtGui.QApplication.processEvents()
    view.saveImage(str(out/'PP07.png'),1400,1050,'White')
    view.viewTop();view.fitAll()
    view.saveImage(str(out/'PP07-top.png'),1400,1050,'White')
    App.closeDocument(isolated.Name)
    App.setActiveDocument(delivery.Name)
    visible={o.Name:o.ViewObject.Visibility for o in delivery.Objects}
    for o in delivery.Objects:o.ViewObject.Visibility=o.Name in {'PrintHeadShell','PrintCrown','SensorMask','SensorStatusStrip'}
    view=Gui.activeDocument().activeView();view.viewAxonometric();view.fitAll()
    for _ in range(5):QtGui.QApplication.processEvents()
    view.saveImage(str(out/'Head-assembled.png'),1400,1050,'White')
    for o in delivery.Objects:o.ViewObject.Visibility=visible[o.Name]
    # Export complete assembly only after geometry and scope checks have passed.
    physical=[o for o in delivery.Objects if hasattr(o,'Shape') and not o.isDerivedFrom('App::DocumentObjectGroup')
              and getattr(o,'Category','') not in ('envelope','clearance')]
    Part.export(physical,str(root/'CyberTrack.step'))
    for doc in docs:App.closeDocument(doc.Name)
    for path,signatures in expected.items():
        saved=App.openDocument(path);actual=shape_rows(saved)
        assert set(actual)==set(signatures)
        assert all(same(actual[n],signatures[n]) for n in actual)
        App.closeDocument(saved.Name)
    b=g['merged'].optimalBoundingBox(False)
    report=dict(date='2026-10-26',revision='0.58',baseline_files=baseline,
        source_document='source/CyberTrack-design.FCStd',source_sha256=sha(source_path),delivery_sha256=sha(delivery_path),
        original_features=MEMBERS,connector_count=len(g['connectors']),connectors=connector_rows,
        size_xyz_mm=[b.XLength,b.YLength,b.ZLength],volume_mm3=g['merged'].Volume,
        valid=True,solids=1,original_material_removed_mm3=removed,
        static_checks=static,services=services,crown_head_overlap_mm3=0,
        screw=SCREW,pilot_diameter_candidate_mm=PILOT_DIAMETER,screw_checks=screw_checks,
        crown_receiver=dict(outer_diameter_mm=7,top_z_mm=216.1,pilot_bottom_z_mm=210,
            clearance_pocket_diameter_mm=7.5,pocket_top_z_mm=216.35,head_seat_z_mm=218.6),
        removed_inserts=removed_inserts,unchanged_geometry_counts=unchanged,
        changed_source=['HeadShell','PrintCrown',*changed_crown,*sorted(set(changed_screws))],
        unchanged_method='cleaned BRep equality; Boolean symmetric difference fallback <1e-5 mm3; saved shape signatures',
        source_visibility_changed_only_for_merged_members=MEMBERS,
        chassis_geometry_unchanged=True,independent_parts=['PrintCrown','ElectronicsTray'],
        files=exports,saved_and_reopened=True,geometry_checks_passed=True,
        slicing_verified=False,physical_fit_verified=False,manufacturing_released=False,
        limits='Local CAD and sampled crown path and continuous sensor sweeps; continuous tray envelope. Existing PP02 conflict retained. Pilot/thread, strength, support removal and physical assembly require print checks.')
    slicing_path=out/'PP07-slicing/report.json'
    if slicing_path.exists():
        slicing=json.loads(slicing_path.read_text())
        if slicing.get('input_stl_sha256')==exports['PP07-HeadShell.stl']['sha256']:
            report['slicing_verified']=True
            report['slicing_report']='print-parts/PP07-slicing/report.json'
    dump(root/REPORT,report)
    # Current readback lists the delivered geometry; old global checks retain their original evidence hashes.
    readback=json.loads((root/'readback.json').read_text())
    delivered=App.openDocument(str(delivery_path))
    readback['objects']=[row(o) for o in delivered.Objects if hasattr(o,'Shape') and not o.isDerivedFrom('App::DocumentObjectGroup')]
    App.closeDocument(delivered.Name)
    readback['local_revision']='0.58'
    readback['head_shell_print']=dict(report=REPORT,geometry_checks_passed=True,whole_assembly_revalidated=False)
    readback['historical_checks_note']='Existing whole-assembly results predate PP07; use head-shell-print-audit.json for 0.58 scope and protected-part proof.'
    readback['files_sha256']['CyberTrack.FCStd']=sha(delivery_path)
    readback['files_sha256']['CyberTrack.step']=sha(root/'CyberTrack.step')
    for filename,data in exports.items():readback['files_sha256']['print-parts/'+filename]=data['sha256']
    dump(root/'readback.json',readback)
    print(json.dumps({k:report[k] for k in ['size_xyz_mm','solids','unchanged_geometry_counts','geometry_checks_passed']},indent=2),flush=True)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',type=Path,default=ROOT)
    main(parser.parse_args().root)
    # Documents are explicitly saved/closed above. The bundled GUI Python runtime
    # can crash in native Qt teardown after successful completion.
    import os
    import sys
    sys.stdout.flush(); sys.stderr.flush()
    os._exit(0)
