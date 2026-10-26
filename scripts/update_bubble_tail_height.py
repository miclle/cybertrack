"""Update the saved assembly's tail shell, preserving the bottom tab and mounts.

Run with FreeCAD's bundled Python on a desktop display. Original component
revisions are read-only; the new independent revision is exported separately.
"""
import json
from pathlib import Path
import FreeCAD as App
import Part
from bubble_gun_layout import (COMPONENT, REVISION, NAMES, ORIGIN, local_shapes,
                               inspection_box, export_component, tail_dimensions)
from gun_pitch import moved
from update_pp02 import sha, dump, signature, same, shape_rows, update_object_row, overlap
from water_gun_layout import bbox

ROOT=Path(__file__).resolve().parents[1]/'hardware/model'
REPORT='bubble-tail-height-audit.json'
CHANGED={'BubbleGunGearcase','BubbleGunInspectionEnvelope'}


def placed(shape):
    result=shape.copy()
    result.rotate(App.Vector(),App.Vector(0,0,1),180)
    result.translate(App.Vector(*ORIGIN))
    return moved(result,'bubble')


def main():
    source_path=ROOT/'source/CyberTrack-design.FCStd';delivery_path=ROOT/'CyberTrack.FCStd'
    before_files={str(p.relative_to(ROOT)):sha(p) for p in (source_path,delivery_path)}
    if (ROOT/REPORT).exists():
        prior=json.loads((ROOT/REPORT).read_text())
        if prior['source_sha256']==sha(source_path) and prior['delivery_sha256']==sha(delivery_path):
            assert prior['measurement']==tail_dimensions()
            assert prior['independent_readback_sha256']==sha(REVISION/'readback.json')
            print('Tail height revision already applied; saved files preserved.',flush=True)
            return
    import FreeCADGui as Gui
    Gui.showMainWindow()
    # Freeze original component assets and measurements, including the previous
    # native model, instead of overwriting them with the newly supplied height.
    protected={p:sha(p) for p in COMPONENT.rglob('*') if p.is_file() and REVISION not in p.parents and p.name!='README.md'}
    source=App.openDocument(str(source_path));delivery=App.openDocument(str(delivery_path))
    before={d.Name:shape_rows(d) for d in (source,delivery)}
    old_shapes={d.Name:{o.Name:o.Shape.copy() for o in d.Objects if o.Name in NAMES} for d in (source,delivery)}
    shapes=local_shapes()
    # Verify every other gun piece against the actual saved assembly before edit.
    for name in NAMES:
        if name=='BubbleGunGearcase':continue
        expected=placed(shapes[name])
        assert expected.cut(source.getObject(name).Shape).Volume+source.getObject(name).Shape.cut(expected).Volume<1e-5,name
    case=placed(shapes['BubbleGunGearcase'])
    envelope=moved(inspection_box(),'bubble')
    evidence='2026-10-26用户确认尾壳35.9不含薄片6.8；承托至尾顶42.7；既有宽长、侧凸和内部轮廓仍为假设，见'+REPORT
    for doc in (source,delivery):
        doc.BubbleGunGearcase.Shape=case.copy()
        doc.BubbleGunGearcase.EvidenceBasis=evidence
        if 'Label2' in doc.BubbleGunGearcase.PropertiesList:
            doc.BubbleGunGearcase.Label2='尾部壳体高35.9／不含底部薄片6.8／宽长轮廓假设'
        doc.BubbleGunGearcase.ViewObject.DiffuseColor=[doc.BubbleGunGearcase.ViewObject.ShapeColor]
        obj=doc.getObject('BubbleGunInspectionEnvelope')
        if obj:
            obj.Shape=envelope.copy();obj.EvidenceBasis='高42.7推导；宽35.8、全长等截面均为保守空间假设，不是实体；见'+REPORT
        doc.Label='CyberTrack 双履带交互机器人 · 0.56 尾壳35.9 / PP02配合待解决'
        doc.recompute()
    unchanged={}
    for doc in (source,delivery):
        current=shape_rows(doc);assert current.keys()==before[doc.Name].keys()
        names=set(current)-CHANGED
        assert all(same(before[doc.Name][n],current[n]) for n in names)
        unchanged[doc.Name]=len(names)
        for name in NAMES:
            obj=doc.getObject(name)
            assert obj.Shape.isValid()
            if name!='BubbleGunGearcase':
                original=old_shapes[doc.Name][name]
                assert original.cut(obj.Shape).Volume+obj.Shape.cut(original).Volume<1e-5,name
    assert len(case.Solids)==1 and case.isValid()
    assert abs(shapes['BubbleGunGearcase'].BoundBox.ZLength-35.9)<1e-6
    assert abs(shapes['BubbleGunMountingTab'].BoundBox.ZLength-6.8)<1e-6
    consumed={s.Name for o in source.Objects if hasattr(o,'PrintPartID') for s in o.Shapes}
    obstacles=[o for o in source.Objects if (hasattr(o,'Category') or hasattr(o,'PrintPartID'))
               and o.Name not in consumed and o.Name not in NAMES and o.Name!='BubbleGunInspectionEnvelope']
    physical=[o for o in obstacles if getattr(o,'Category','merged_print_part') not in ('envelope','clearance')]
    routes=[o for o in obstacles if getattr(o,'Category',None)=='envelope']
    spaces=[o for o in obstacles if getattr(o,'Category',None)=='clearance']
    physical_hits=overlap(case,physical);route_hits=overlap(case,routes);space_hits=overlap(case,spaces)
    assert not physical_hits and not route_hits,(physical_hits,route_hits)
    muzzle_overlap=source.BubbleGunShell.Shape.common(source.PrintBubbleCradle.Shape).Volume
    assert abs(muzzle_overlap-65.1131815957141)<1e-4
    gaps={n:case.distToShape(source.getObject(n).Shape)[0] for n in
          ('PrintBubbleCradle','HeadShell','ShoulderRailR','KeelLid','StopBody','BubbleGunStopAccess','PrintNeck')}
    assert abs(gaps['PrintBubbleCradle']-.3)<1e-5
    assert all(same(signature(source.getObject(n).Shape),signature(delivery.getObject(n).Shape))
               for n in shape_rows(delivery))
    expected={str(p):shape_rows(d) for p,d in ((source_path,source),(delivery_path,delivery))}
    for doc in (source,delivery):doc.save()
    App.closeDocument(source.Name);App.closeDocument(delivery.Name)
    source=App.openDocument(str(source_path));delivery=App.openDocument(str(delivery_path))
    for doc,p in ((source,source_path),(delivery,delivery_path)):
        current=shape_rows(doc);assert current.keys()==expected[str(p)].keys()
        assert all(same(current[n],expected[str(p)][n]) for n in current)
    export_component(shapes,render=True)
    assembly=[o for o in delivery.Objects if hasattr(o,'Shape') and not o.isDerivedFrom('App::DocumentObjectGroup')
              and getattr(o,'Category','') not in ('envelope','clearance')]
    Part.export(assembly,str(ROOT/'CyberTrack.step'))
    exchange=Part.Shape();exchange.read(str(ROOT/'CyberTrack.step'))
    combined=Part.makeCompound([o.Shape for o in assembly])
    assert exchange.isValid() and len(exchange.Solids)==len(combined.Solids)
    # Render from the saved model without persisting camera/isolation changes.
    App.setActiveDocument(delivery.Name);Gui.updateGui()
    from pivy import coin  # noqa: F401
    view=Gui.activeDocument().activeView();view.setCameraType('Orthographic')
    initial={o.Name:o.ViewObject.Visibility for o in delivery.Objects if o.ViewObject}
    selection=set(NAMES)|{'PrintBubbleCradle','ShoulderRailR','BubbleGunLowerPadRear','StopBody','StopNut'}
    for o in delivery.Objects:
        if o.ViewObject:o.ViewObject.Visibility=o.Name in selection
    Gui.updateGui();view.viewAxonometric();view.fitAll();Gui.updateGui()
    view.saveImage(str(ROOT/'bubble-gun-tail-height.png'),1600,1200,'White')
    for n,visible in initial.items():delivery.getObject(n).ViewObject.Visibility=visible
    Gui.updateGui();view.fitAll();Gui.updateGui()
    view.saveImage(str(ROOT/'assembly.png'),1600,1200,'White')
    audit=dict(date='2026-10-26',revision='0.56',baseline_files=before_files,
        source_document='source/CyberTrack-design.FCStd',source_sha256=sha(source_path),delivery_sha256=sha(delivery_path),
        measurement=tail_dimensions(),changed_source=sorted(CHANGED),
        changed_delivery=sorted(CHANGED & set(shape_rows(delivery))),unchanged_signature_counts=unchanged,
        unchanged_method='All other object volume/area/topology/bounds signatures match; other gun pieces also compared by Boolean symmetric difference.',
        bottom_tab_unchanged=True,muzzle_and_mounts_unchanged=True,saved_and_reopened=True,
        local_case_bbox_mm=bbox(shapes['BubbleGunGearcase']),world_case_bbox_mm=bbox(case),
        shell_height_mm=35.9,tab_height_mm=6.8,support_to_tail_top_mm=42.7,
        tail_solid_valid=True,tail_solids=len(case.Solids),physical_collisions=physical_hits,
        equipment_route_overlaps=route_hits,service_space_overlaps=space_hits,clearances_mm=gaps,
        reserved_width_finger_space_overlap_mm3=envelope.common(source.BubbleGunStopAccess.Shape).Volume,
        existing_muzzle_conflict_mm3=muzzle_overlap,geometry_and_export_checks_passed=True,
        assembly_fit_passed=False,service_paths_revalidated=False,physical_fit_verified=False,manufacturing_released=False,
        independent_revision=str(REVISION.relative_to(ROOT.parent)),
        independent_readback_sha256=sha(REVISION/'readback.json'),
        historical_component_assets_unchanged=all(sha(p)==digest for p,digest in protected.items()))
    assert audit['historical_component_assets_unchanged']
    rb=json.loads((ROOT/'readback.json').read_text())
    rb.update(local_revision='0.56-tail35.9+PP02-review',bubble_tail_height_audit=REPORT,bubble_tail_height=audit)
    rb['objects']=[update_object_row(r,delivery) if r['name'] in CHANGED else r for r in rb['objects']]
    rb['source_feature_objects']=[update_object_row(r,source) if r['name'] in CHANGED else r for r in rb['source_feature_objects']]
    rb['bubble_gun_layout'].update(tail_shell_height_mm=35.9,bottom_tab_height_mm=6.8,
        support_to_tail_top_mm=42.7,inspection_bbox_mm=bbox(envelope),component_revision=audit['independent_revision'])
    rb['bubble_gun_layout']['mount'].update(tail_shell_height_mm=35.9,support_to_tail_top_mm=42.7,
        historical_height_conflict_mm=.4)
    rb['bubble_gun_layout']['mount'].pop('height_conflict_mm',None)
    rb['bubble_gun_check'].update(passed=False,current_validation='Tail static geometry checked; original ring conflict retained; removal not revalidated. See '+REPORT)
    rb['service_paths'].update(passed=False,current_validation='Tail height changed; removal paths not revalidated. See '+REPORT)
    assert not rb['collision_check']['passed']
    rb['assembly_paths_verified']=False
    rb['step_readback'].update(solids=len(exchange.Solids),expected_solids=len(combined.Solids),
        volume_difference_mm3=abs(exchange.Volume-combined.Volume),volume_comparison_passed=abs(exchange.Volume-combined.Volume)<=.01)
    paths=(source_path,delivery_path,ROOT/'CyberTrack.step',ROOT/'assembly.png',ROOT/'bubble-gun-tail-height.png')
    rb['files_sha256'].update({str(p.relative_to(ROOT)):sha(p) for p in paths})
    rb['current_preview_scope']='assembly.png and bubble-gun-tail-height.png updated for tail35.9; other previews retain their stated revision'
    tree=json.loads((ROOT/'model-tree-audit.json').read_text())
    tree.update(source_sha256=sha(source_path),delivery_sha256=sha(delivery_path),bubble_tail_height_audit=REPORT,
        geometry_scope='Only tail shell and inspection envelope changed; source/delivery signatures and unchanged gun pieces checked in '+REPORT)
    rb['model_tree']={k:v for k,v in tree.items() if k!='shape_checks'}
    consolidation=json.loads((ROOT/'print-consolidation-audit.json').read_text())
    consolidation.update(source_sha256=sha(source_path),bubble_tail_height_audit=REPORT)
    dump(ROOT/'print-consolidation-audit.json',consolidation)
    dump(ROOT/'model-tree-audit.json',tree);dump(ROOT/'readback.json',rb);dump(ROOT/REPORT,audit)
    print(json.dumps(audit,ensure_ascii=False,indent=2),flush=True)


if __name__=='__main__':
    main()
    import os
    os._exit(0)
