"""Apply the 2026-10-26 PP02 revision without rebuilding unrelated geometry.

Run with FreeCAD's Python runtime; --render preserves GUI appearance and updates
PP02.png. An explicit report distinguishes solid/export checks from assembly fit.
"""
import argparse
import hashlib
import json
from pathlib import Path

import FreeCAD as App
import Part
import Mesh
import MeshPart
from bubble_gun_mount import (ring_shape, SLOT_WALL_IDS, RING_BORE_MM,
                              RING_BORE_RISE_MM, RING_NOTCH_WIDTH_MM,
                              RING_NOTCH_DEPTH_MM)
from gun_pitch import moved

ROOT = Path(__file__).resolve().parents[1] / 'hardware/model'
REMOVED = ('BubbleGunSlotWall1', 'BubbleGunSlotWall6')
MEMBERS = ['BubbleGunCradle', 'BubbleGunRing'] + ['BubbleGunSlotWall'+str(i) for i in SLOT_WALL_IDS]
REPORT = 'pp02-adjustment-audit.json'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')


def signature(shape):
    b = shape.optimalBoundingBox(False)
    return [shape.Volume, shape.Area, len(shape.Solids), len(shape.Faces),
            len(shape.Edges)] + [getattr(b, k) for k in ('XMin','YMin','ZMin','XMax','YMax','ZMax')]


def same(a, b):
    return all(abs(x-y) < 1e-5 for x,y in zip(a,b))


def shape_rows(doc):
    return {o.Name:signature(o.Shape) for o in doc.Objects if hasattr(o,'Shape')
            and not o.isDerivedFrom('App::DocumentObjectGroup')}


def overlap(shape, objects):
    rows=[]
    for obj in objects:
        if not shape.BoundBox.intersect(obj.Shape.BoundBox):continue
        volume=shape.common(obj.Shape).Volume
        if volume>.01:rows.append(dict(object=obj.Name,volume_mm3=volume))
    return rows


def update_object_row(row, doc):
    obj=doc.getObject(row['name'])
    if not obj:return None
    b=obj.Shape.optimalBoundingBox(False)
    row.update(volume_mm3=obj.Shape.Volume,valid=obj.Shape.isValid(),solids=len(obj.Shape.Solids),
               bbox_mm=[getattr(b,k) for k in ('XMin','YMin','ZMin','XMax','YMax','ZMax')])
    return row


def main(render=False, baseline_dir=None):
    if render:
        import FreeCADGui as Gui
        from PySide import QtGui
        Gui.showMainWindow()
    source_path=ROOT/'source/CyberTrack-design.FCStd'
    delivery_path=ROOT/'CyberTrack.FCStd'
    baseline=dict(source_sha256=sha(source_path),delivery_sha256=sha(delivery_path))
    prior_path=ROOT/REPORT
    if prior_path.exists():
        prior=json.loads(prior_path.read_text())
        if prior['source_sha256']==baseline['source_sha256'] and prior['delivery_sha256']==baseline['delivery_sha256']:
            baseline=prior['baseline']
    source=App.openDocument(str(source_path))
    delivery=App.openDocument(str(delivery_path))
    before_source=shape_rows(source);before_delivery=shape_rows(delivery)
    if baseline_dir:
        for filename,key in (('source-before.FCStd','source'),('delivery-before.FCStd','delivery')):
            path=baseline_dir/filename
            baseline[key+'_sha256']=sha(path)
            original=App.openDocument(str(path))
            if key=='source':before_source=shape_rows(original)
            else:before_delivery=shape_rows(original)
            App.closeDocument(original.Name)
    ring=moved(ring_shape(),'bubble')
    source.BubbleGunRing.Shape=ring
    source.BubbleGunRing.Label2='外径39／偏心内孔32／孔心上移1.3／底部缺口7.5×2.3／支脚宽20 mm'
    source.PrintBubbleCradle.Shapes=[source.getObject(n) for n in MEMBERS]
    for name in REMOVED:
        if source.getObject(name):source.removeObject(name)
    source.recompute()
    shape=source.PrintBubbleCradle.Shape.copy()
    assert shape.isValid() and len(shape.Solids)==1
    expected=ring.multiFuse([source.getObject(n).Shape for n in MEMBERS if n!='BubbleGunRing']).removeSplitter()
    assert shape.cut(expected).Volume+expected.cut(shape).Volume<1e-5
    delivery.PrintBubbleCradle.Shape=shape
    delivery.PrintBubbleCradle.SourceFeatures=MEMBERS
    basis='2026-10-26 PP02局部调整；实体与导出检查，不代表枪体配合或制造验收；见pp02-adjustment-audit.json'
    for doc in (source,delivery):
        doc.PrintBubbleCradle.EvidenceBasis=basis
        doc.recompute()
    unaffected_source=set(before_source)-set(REMOVED)-{'BubbleGunRing','PrintBubbleCradle'}
    unaffected_delivery=set(before_delivery)-{'PrintBubbleCradle'}
    assert all(same(before_source[n],signature(source.getObject(n).Shape)) for n in unaffected_source)
    assert all(same(before_delivery[n],signature(delivery.getObject(n).Shape)) for n in unaffected_delivery)
    # Check all installed physical source features, excluding the merged duplicates.
    physical=[o for o in source.Objects if hasattr(o,'Category') and o.Category not in ('clearance','envelope')
              and o.Name not in MEMBERS]
    collisions=overlap(shape,physical)
    local_ring=ring_shape()
    notch_floor=110+RING_BORE_RISE_MM-RING_BORE_MM/2-RING_NOTCH_DEPTH_MM
    notch=Part.makeBox(RING_NOTCH_WIDTH_MM,3,2.3,App.Vector(-55-RING_NOTCH_WIDTH_MM/2,-127,notch_floor))
    assert local_ring.common(notch).Volume<1e-5
    bore_faces=[f for f in local_ring.Faces if isinstance(f.Surface,Part.Cylinder) and abs(f.Surface.Radius-16)<1e-6]
    assert bore_faces and abs(bore_faces[0].Surface.Center.z-111.3)<1e-6
    assert any(abs(f.CenterOfMass.z-notch_floor)<1e-6 and abs(f.Area-22.5)<1e-5 for f in local_ring.Faces)
    for doc in (source,delivery):doc.save()
    saved_expected={doc.Name:shape_rows(doc) for doc in (source,delivery)}
    source_name,delivery_name=source.Name,delivery.Name
    App.closeDocument(source_name);App.closeDocument(delivery_name)
    source=App.openDocument(str(source_path));delivery=App.openDocument(str(delivery_path))
    for doc,key in ((source,source_name),(delivery,delivery_name)):
        after=shape_rows(doc);assert set(after)==set(saved_expected[key])
        assert all(same(after[n],saved_expected[key][n]) for n in after)
    b=shape.optimalBoundingBox(False)
    translation=App.Vector(-(b.XMin+b.XMax)/2,-(b.YMin+b.YMax)/2,-b.ZMin)
    local=shape.copy();local.translate(translation)
    directory=ROOT/'print-parts'
    step=directory/'PP02-BubbleCradle.step';stl=directory/'PP02-BubbleCradle.stl'
    local.exportStep(str(step))
    check=Part.Shape();check.read(str(step))
    step_delta=local.cut(check).Volume+check.cut(local).Volume
    assert check.isValid() and len(check.Solids)==1 and step_delta<.01
    mesh=MeshPart.meshFromShape(Shape=local,LinearDeflection=.08,AngularDeflection=.15,Relative=False)
    mesh.write(str(stl));back=Mesh.Mesh(str(stl))
    assert back.isSolid() and not back.hasNonManifolds() and back.countComponents()==1
    # Only physical assembly geometry; no hidden clearance/envelope duplicates.
    assembly=[o for o in delivery.Objects if hasattr(o,'Shape')
              and not o.isDerivedFrom('App::DocumentObjectGroup')
              and getattr(o,'Category','') not in ('clearance','envelope')]
    Part.export(assembly,str(ROOT/'CyberTrack.step'))
    exchange=Part.Shape();exchange.read(str(ROOT/'CyberTrack.step'))
    assembly_shape=Part.makeCompound([o.Shape for o in assembly])
    assert exchange.isValid() and len(exchange.Solids)==len(assembly_shape.Solids)
    if render:
        App.setActiveDocument(delivery.Name)
        visibility={o.Name:o.ViewObject.Visibility for o in delivery.Objects}
        for o in delivery.Objects:o.ViewObject.Visibility=o.Name=='PrintBubbleCradle'
        delivery.PrintBubbleCradle.ViewObject.ShapeColor=(.4,.48,.51)
        delivery.PrintBubbleCradle.ViewObject.DiffuseColor=[(.4,.48,.51)]
        view=Gui.activeDocument().activeView();view.viewAxonometric();view.fitAll()
        for _ in range(5):QtGui.QApplication.processEvents()
        view.saveImage(str(directory/'PP02.png'),1200,900,'White')
        for o in delivery.Objects:o.ViewObject.Visibility=visibility[o.Name]
        view.fitAll();delivery.save()
    audit=dict(date='2026-10-26',scope='PP02 only',baseline=baseline,
        source_document='source/CyberTrack-design.FCStd',source_sha256=sha(source_path),
        delivery_sha256=sha(delivery_path),removed_source_features=list(REMOVED),members=MEMBERS,
        ring=dict(outer_diameter_mm=39,bore_diameter_mm=RING_BORE_MM,bore_centre_local_z_mm=111.3,
                  bore_centre_rise_local_z_mm=RING_BORE_RISE_MM,bore_bottom_before_notch_local_z_mm=95.3,
                  bore_lower_edge_rise_mm=2.3,axial_width_mm=3,foot_width_mm=20,
                  notch_width_mm=RING_NOTCH_WIDTH_MM,notch_depth_mm=RING_NOTCH_DEPTH_MM,
                  notch_floor_local_z_mm=notch_floor,notch_through_axial_width=True,
                  coordinate_frame='unpitched cradle; final assembly retains 15 degree elevation'),
        changed_source_features=['BubbleGunRing','PrintBubbleCradle'],
        unchanged_source_signature_count=len(unaffected_source),unchanged_delivery_signature_count=len(unaffected_delivery),
        unchanged_check_method='volume, area, topology counts and exact bounding box, tolerance 1e-5',
        valid=True,solids=1,saved_and_reopened=True,geometry_and_export_checks_passed=True,
        assembly_fit_passed=not collisions,assembly_overlaps=collisions,
        service_paths_revalidated=False,manufacturing_released=False,physical_fit_verified=False,
        limits='Requested geometry retained. Existing gun/body/service acceptance is not carried over; no physical fit or strength acceptance.',
        step_symmetric_difference_mm3=step_delta,stl_closed=True,stl_nonmanifold=False,stl_connected_components=1,
        files={p.name:sha(p) for p in (step,stl)})
    consolidation=json.loads((ROOT/'print-consolidation-audit.json').read_text())
    row=next(r for r in consolidation['parts'] if r['id']=='PP02')
    row.update(members=MEMBERS,feature_count=len(MEMBERS),volume_mm3=shape.Volume,
        size_xyz_mm=[b.XLength,b.YLength,b.ZLength],stl_translation_xyz_mm=list(translation),
        stl_facets=back.CountFacets,step_volume_difference_mm3=abs(check.Volume-local.Volume),
        step_volume_comparison_passed=True,files=audit['files'],local_change_audit=REPORT)
    consolidation.update(source_sha256=sha(source_path),source_feature_count=sum(r['feature_count'] for r in consolidation['parts']),
                         local_change_audit=REPORT,assembly_fit_passed=not collisions)
    consolidation['limits']='Solid fusion/export checks only. PP02 changed 2026-10-26; assembly fit is separately recorded in '+REPORT
    dump(ROOT/'print-consolidation-audit.json',consolidation)
    readback=json.loads((ROOT/'readback.json').read_text())
    readback['local_revision']='PP02-2026-10-26'
    readback['pp02_adjustment']=audit
    readback['objects']=[update_object_row(r,delivery) if r['name']=='PrintBubbleCradle' else r for r in readback['objects']]
    readback['source_feature_objects']=[update_object_row(r,source) if r['name']=='BubbleGunRing' else r
        for r in readback['source_feature_objects'] if r['name'] not in REMOVED]
    readback['print_consolidation']['parts']=consolidation['parts']
    readback['print_consolidation']['feature_count']=consolidation['source_feature_count']
    readback['bubble_gun_layout']['mount']['ring']=audit['ring']
    readback['bubble_gun_layout']['mount']['slot'].update(retained_wall_ids=list(SLOT_WALL_IDS),removed_wall_ids=[1,6])
    # Keep historical full-model results identifiable, never relabel them as new checks.
    for key in ('collision_check','bubble_gun_check','service_paths'):
        previous=readback[key].get('baseline_result',readback[key])
        readback[key]=dict(passed=False,current_validation='superseded for PP02; see '+REPORT,
                           baseline_source_sha256=baseline['source_sha256'],baseline_result=previous)
    readback['collision_check'].update(overlaps=collisions,scope='Current PP02 against installed physical source features')
    readback['assembly_paths_verified']=False
    readback['step_readback'].update(solids=len(exchange.Solids),expected_solids=len(assembly_shape.Solids),
        volume_difference_mm3=abs(exchange.Volume-assembly_shape.Volume),volume_comparison_passed=abs(exchange.Volume-assembly_shape.Volume)<=.01)
    readback['files_sha256'].update({'CyberTrack.FCStd':sha(delivery_path),'source/CyberTrack-design.FCStd':sha(source_path),
                                    'CyberTrack.step':sha(ROOT/'CyberTrack.step')})
    if render:readback['files_sha256']['print-parts/PP02.png']=sha(directory/'PP02.png')
    readback['current_preview_scope']='PP02.png updated; other previews remain baseline illustrations'
    tree=json.loads((ROOT/'model-tree-audit.json').read_text())
    tree.update(source_sha256=sha(source_path),delivery_sha256=sha(delivery_path),local_change_audit=REPORT)
    tree['removed_duplicate_inputs']=[n for n in tree['removed_duplicate_inputs'] if n not in REMOVED]
    tree['shape_checks']=[dict(name=o.Name,geometry_signature_matches=True) for o in delivery.Objects
                          if hasattr(o,'Shape') and not o.isDerivedFrom('App::DocumentObjectGroup')]
    for o in delivery.Objects:
        if not hasattr(o,'Shape') or o.isDerivedFrom('App::DocumentObjectGroup'):continue
        assert same(signature(o.Shape),signature(source.getObject(o.Name).Shape)),o.Name
    tree['geometry_scope']='Updated delivery/source geometry signatures agree; PP02 Boolean union equality separately checked in '+REPORT
    tree['geometry_unchanged']=False
    readback['model_tree']={k:v for k,v in tree.items() if k!='shape_checks'}
    dump(ROOT/'model-tree-audit.json',tree)
    dump(ROOT/'readback.json',readback)
    dump(ROOT/REPORT,audit)
    print(json.dumps(audit,ensure_ascii=False,indent=2),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--render',action='store_true')
    parser.add_argument('--baseline-dir',type=Path)
    args=parser.parse_args();main(args.render,args.baseline_dir)
