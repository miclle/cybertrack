"""Update the saved design/delivery locally, preserving the PP02 review conflict.

Run with the bundled FreeCAD Python and --render. The source generator also
applies cable_passage, but a full rebuild is not used for this local update.
"""
import argparse
import json
from pathlib import Path
import FreeCAD as App
import Part
import Mesh
import MeshPart
from cable_passage import apply,check,CHANGED,REVISION
from update_pp02 import sha,dump,signature,same,shape_rows,update_object_row

ROOT=Path(__file__).resolve().parents[1]/'hardware/model'
REPORT='cable-passage-audit.json'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--render',action='store_true',required=True,
                        help='Load GUI state so saved colours and visibility are preserved')
    parser.add_argument('--baseline-dir',type=Path,help='Original before-update snapshots for recovery/audit')
    args=parser.parse_args()
    import FreeCADGui as Gui
    from PySide import QtGui
    Gui.showMainWindow()
    source_path=ROOT/'source/CyberTrack-design.FCStd';delivery_path=ROOT/'CyberTrack.FCStd'
    before_hash={str(p.relative_to(ROOT)):sha(p) for p in (source_path,delivery_path)}
    source=App.openDocument(str(source_path));delivery=App.openDocument(str(delivery_path))
    before={doc.Name:shape_rows(doc) for doc in (source,delivery)}
    before_brep={doc.Name:{o.Name:o.Shape.copy() for o in doc.Objects if o.Name in CHANGED or o.Name=='PrintNeck'}
                 for doc in (source,delivery)}
    if args.baseline_dir:
        for doc,filename in ((source,'source-before.FCStd'),(delivery,'delivery-before.FCStd')):
            p=args.baseline_dir/filename
            original=App.openDocument(str(p))
            before[doc.Name]=shape_rows(original)
            before_brep[doc.Name]={o.Name:o.Shape.copy() for o in original.Objects if o.Name in CHANGED or o.Name=='PrintNeck'}
            key='source/CyberTrack-design.FCStd' if doc==source else 'CyberTrack.FCStd'
            before_hash[key]=sha(p)
            App.closeDocument(original.Name)
    layout=apply(source)
    result=check(source)
    print('PASSAGE_CHECK',result['passed'],flush=True)
    assert result['passed'],result
    source.recompute()
    changed_source=set(CHANGED)|{'PrintNeck'}
    changed_delivery={n for n in changed_source if delivery.getObject(n)}
    for name in changed_delivery:
        a,b=source.getObject(name),delivery.getObject(name)
        b.Shape=a.Shape.copy()
        if name in CHANGED:b.EvidenceBasis=a.EvidenceBasis
    for doc in (source,delivery):
        doc.Label='CyberTrack 双履带交互机器人 · 0.55 通道 / PP02配合待解决'
        doc.PrintNeck.EvidenceBasis='0.55净径10穿线通道／局部更新；PP06单实体与导出检查，不代表制造及强度验收。'
        for n in changed_source:
            obj=doc.getObject(n)
            if obj:
                # Topology changes invalidate per-face appearance lists. Keep
                # each part's original base colour, visibility and line style.
                obj.ViewObject.DiffuseColor=[obj.ViewObject.ShapeColor]
        doc.recompute()
    assert len(source.PrintNeck.Shape.Solids)==1 and source.PrintNeck.Shape.isValid()
    unchanged={}
    for doc,changed in ((source,changed_source),(delivery,changed_delivery)):
        old=before[doc.Name]
        assert set(shape_rows(doc))==set(old)
        unaffected=set(old)-changed
        assert all(same(old[n],signature(doc.getObject(n).Shape)) for n in unaffected)
        unchanged[doc.Name]=len(unaffected)
        for n in changed:
            # No new disconnected pieces are accepted, including existing
            # multipart lid geometry (already three solids in the baseline).
            assert len(doc.getObject(n).Shape.Solids)<=len(before_brep[doc.Name][n].Solids),n
    deltas={}
    for n in changed_source:
        a=before_brep[source.Name][n];b=source.getObject(n).Shape
        deltas[n]=dict(removed_mm3=a.cut(b).Volume,added_mm3=b.cut(a).Volume)
    # Preserve GUI state when producing the close/reopen verification pair.
    for doc in (source,delivery):doc.save()
    expected={str(source_path):shape_rows(source),str(delivery_path):shape_rows(delivery)}
    source_name,delivery_name=source.Name,delivery.Name
    App.closeDocument(source.Name);App.closeDocument(delivery.Name)
    source=App.openDocument(str(source_path));delivery=App.openDocument(str(delivery_path))
    for doc,p in ((source,source_path),(delivery,delivery_path)):
        rows=shape_rows(doc);assert set(rows)==set(expected[str(p)])
        assert all(same(rows[n],expected[str(p)][n]) for n in rows)
    # Only PP06 changed among the consolidated printable parts.
    shape=delivery.PrintNeck.Shape;b=shape.optimalBoundingBox(False)
    t=App.Vector(-(b.XMin+b.XMax)/2,-(b.YMin+b.YMax)/2,-b.ZMin)
    local=shape.copy();local.translate(t)
    folder=ROOT/'print-parts';step=folder/'PP06-Neck.step';stl=folder/'PP06-Neck.stl'
    # Use the established basename from the existing manifest.
    consolidation=json.loads((ROOT/'print-consolidation-audit.json').read_text())
    row=next(r for r in consolidation['parts'] if r['id']=='PP06')
    step=folder/next(n for n in row['files'] if n.endswith('.step'))
    stl=folder/next(n for n in row['files'] if n.endswith('.stl'))
    local.exportStep(str(step));back=Part.Shape();back.read(str(step))
    delta=local.cut(back).Volume+back.cut(local).Volume
    assert back.isValid() and len(back.Solids)==1 and delta<.01
    MeshPart.meshFromShape(Shape=local,LinearDeflection=.08,AngularDeflection=.15,Relative=False).write(str(stl))
    mesh=Mesh.Mesh(str(stl));assert mesh.isSolid() and not mesh.hasNonManifolds()
    assert mesh.countComponents()==len(local.Shells)
    assembly=[o for o in delivery.Objects if hasattr(o,'Shape') and not o.isDerivedFrom('App::DocumentObjectGroup')
              and getattr(o,'Category','') not in ('envelope','clearance')]
    Part.export(assembly,str(ROOT/'CyberTrack.step'))
    exchange=Part.Shape();exchange.read(str(ROOT/'CyberTrack.step'))
    compound=Part.makeCompound([o.Shape for o in assembly])
    assert exchange.isValid() and len(exchange.Solids)==len(compound.Solids)
    # Render directly from updated native geometry, without saving temporary
    # transparency/isolation settings back into the delivery model.
    App.setActiveDocument(delivery.Name)
    view=Gui.activeDocument().activeView();view.setCameraType('Orthographic')
    visible={o.Name:(o.ViewObject.Visibility,getattr(o.ViewObject,'Transparency',None)) for o in delivery.Objects}
    selections={
        'cable-passage-layout.png':{'PrintNeck','KeelLid','HeadShell','ElectronicsTray','BreadboardEnvelope',
            'BaseCableGrommet','HeadCableGrommet','NeckCableBridge','PowerCableRoute','StopSignalRoute'},
        'cable-passage-head.png':{'HeadShell','ElectronicsTray','BreadboardEnvelope','HeadCableGrommet','PowerCableRoute'},
        'print-parts/PP06.png':{'PrintNeck'}}
    for filename,names in selections.items():
        for o in delivery.Objects:
            o.ViewObject.Visibility=o.Name in names
            if hasattr(o.ViewObject,'Transparency'):
                o.ViewObject.Transparency=75 if o.Name in ('HeadShell','KeelLid','BreadboardEnvelope') else 0
        view.setCameraOrientation(App.Rotation(App.Vector(1,1,0),App.Vector(-1,1,3),App.Vector(1,-1,.75),'ZXY').Q)
        view.fitAll()
        for _ in range(8):QtGui.QApplication.processEvents()
        view.saveImage(str(ROOT/filename),1600,1200,'White')
    for o in delivery.Objects:
        o.ViewObject.Visibility=visible[o.Name][0]
        if visible[o.Name][1] is not None:o.ViewObject.Transparency=visible[o.Name][1]
    audit=dict(date='2026-10-26',revision=REVISION,baseline_files=before_hash,
        source_document='source/CyberTrack-design.FCStd',source_sha256=sha(source_path),delivery_sha256=sha(delivery_path),
        layout=layout,checks=result,changed_source=sorted(changed_source),changed_delivery=sorted(changed_delivery),
        geometry_deltas=deltas,unchanged_source_signature_count=unchanged[source_name],
        unchanged_delivery_signature_count=unchanged[delivery_name],
        unchanged_method='volume, area, topology counts and optimal bounding box; not full assembly Boolean equivalence',
        saved_and_reopened=True,source_delivery_changed_geometry_agrees=all(same(signature(source.getObject(n).Shape),signature(delivery.getObject(n).Shape)) for n in changed_delivery),
        pp06_step_symmetric_difference_mm3=delta,pp06_stl_closed=True,pp06_stl_nonmanifold=False,
        scope_passed=True,whole_assembly_passed=False,
        prior_conflict_retained='PP02 vs BubbleGunShell; see pp02-adjustment-audit.json',
        physical_fit_verified=False,manufacturing_released=False)
    row.update(volume_mm3=shape.Volume,size_xyz_mm=[b.XLength,b.YLength,b.ZLength],
        stl_translation_xyz_mm=list(t),stl_facets=mesh.CountFacets,stl_connected_components=mesh.countComponents(),
        cad_boundary_shells=len(local.Shells),step_volume_difference_mm3=abs(back.Volume-local.Volume),
        step_volume_comparison_passed=True,local_change_audit=REPORT,files={p.name:sha(p) for p in (step,stl)})
    consolidation.update(source_sha256=sha(source_path),cable_passage_change_audit=REPORT)
    dump(ROOT/'print-consolidation-audit.json',consolidation)
    rb=json.loads((ROOT/'readback.json').read_text())
    rb.update(local_revision='0.55-cable10+PP02-review',cable_passage_layout=layout,cable_passage_check=result,cable_passage_audit=REPORT)
    rb['objects']=[update_object_row(r,delivery) if r['name'] in changed_delivery else r for r in rb['objects']]
    rb['source_feature_objects']=[update_object_row(r,source) if r['name'] in changed_source else r for r in rb['source_feature_objects']]
    rb['print_consolidation']['parts']=consolidation['parts']
    rb['breadboard_check']=result['tray'];rb['boot_button_check']=result['boot']
    rb['boot_button_layout'].update(wire_route_points_mm=layout['boot_points_mm'],
        routed_length_mm=layout['boot_routed_length_mm'],
        shared_trunk='15 conductors total in the net-diameter-10 passage; see cable-passage-audit.json',
        board_endpoint='X60/Y6/Z194; in-board tails unmodelled')
    # Never replace the inherited PP02 collision/service failures with this
    # task's localized success or upgrade historical assembly acceptance.
    assert not rb['collision_check']['passed'] and not rb['service_paths']['passed']
    rb['step_readback'].update(solids=len(exchange.Solids),expected_solids=len(compound.Solids),
        volume_difference_mm3=abs(exchange.Volume-compound.Volume),volume_comparison_passed=abs(exchange.Volume-compound.Volume)<=.01)
    rb['files_sha256'].update({str(p.relative_to(ROOT)):sha(p) for p in (source_path,delivery_path,ROOT/'CyberTrack.step')})
    rb['current_preview_scope']='cable-passage-layout/head.png and PP06.png are current; other previews retain their stated revision'
    tree=json.loads((ROOT/'model-tree-audit.json').read_text())
    tree.update(source_sha256=sha(source_path),delivery_sha256=sha(delivery_path),cable_passage_change_audit=REPORT,
        geometry_scope='Localized cable passage update; saved source/delivery changed shape signatures agree; see '+REPORT)
    rb['model_tree']={k:v for k,v in tree.items() if k!='shape_checks'}
    dump(ROOT/'model-tree-audit.json',tree);dump(ROOT/'readback.json',rb);dump(ROOT/REPORT,audit)
    print(json.dumps({'scope_passed':True,'unchanged':unchanged,'board_clearance_mm':result['board_clearance_mm'],
        'tray_clearance_mm':result['tray_clearance_mm'],'changed':sorted(changed_delivery)},ensure_ascii=False),flush=True)


if __name__=='__main__':main()
