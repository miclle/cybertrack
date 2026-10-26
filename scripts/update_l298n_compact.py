"""Apply and export the measured-gap L298N revision without rebuilding other parts.

Run using FreeCAD's Python with its Resources/lib on sys.path. Old component
assets remain read-only. Existing unrelated fit failures are not cleared.
"""
import hashlib
import json
import shutil
from pathlib import Path

import FreeCAD as A
import Part
import Mesh
import MeshPart
import l298n_compact_mount as compact
from update_pp02 import shape_rows, same, signature

ROOT=Path(__file__).resolve().parents[1]
MODEL=ROOT/'hardware/model'
OUT=MODEL/'l298n-compact'
REPORT=MODEL/'l298n-compact-audit.json'
V=A.Vector


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def dump(path,data):path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')


def export_parts(doc,folder):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    rows=[]
    for stem,name in [('LC01-Carrier','L298NCarrier'),('LC02-TopRetainer','L298NTopRetainer'),
                      ('LC03-BottomServiceCover','BottomServiceCover'),('LC04-KeelLid','KeelLid')]:
        original=doc.getObject(name).Shape
        expected_solids=3 if name=='KeelLid' else 1
        assert original.isValid() and len(original.Solids)==expected_solids,(name,len(original.Solids))
        b=original.BoundBox;delta=V(-(b.XMin+b.XMax)/2,-(b.YMin+b.YMax)/2,-b.ZMin)
        local=original.copy();local.translate(delta)
        step=folder/(stem+'.step');local.exportStep(str(step))
        back=Part.Shape();back.read(str(step))
        diff=local.cut(back).Volume+back.cut(local).Volume
        assert back.isValid() and len(back.Solids)==expected_solids and diff<.01,(name,diff)
        stl=folder/(stem+'.stl')
        mesh=MeshPart.meshFromShape(Shape=local,LinearDeflection=.06,AngularDeflection=.12,Relative=False)
        mesh.write(str(stl));read=Mesh.Mesh(str(stl))
        assert read.isSolid() and not read.hasNonManifolds(),name
        assert read.countComponents()==len(local.Shells),(name,read.countComponents(),len(local.Shells))
        rows.append(dict(name=name,stem=stem,valid=True,solids=expected_solids,volume_mm3=original.Volume,
            size_xyz_mm=[b.XLength,b.YLength,b.ZLength],translation_xyz_mm=list(delta),
            step_difference_mm3=diff,stl_closed=True,stl_nonmanifold=False,stl_facets=read.CountFacets,
            stl_components=read.countComponents(),cad_shells=len(local.Shells),
            files_sha256={p.name:sha(p) for p in (step,stl)},manufacturing_released=False,
            note='KeelLid retains its three pre-existing solids; not a newly verified one-piece print.' if name=='KeelLid' else 'Single-solid fit candidate.'))
    dump(folder/'parts-readback.json',rows)
    return rows


def connected_component():
    folder=ROOT/'hardware/components/L298N/revisions/connected-28.5-2026-10-26'
    folder.mkdir(parents=True,exist_ok=True)
    native=folder/'L298N-connected-envelope.FCStd';step=folder/'L298N-connected-envelope.step'
    expected=Part.makeBox(46.2,43.5,28.5)
    if not native.exists():
        d=A.newDocument('L298NConnectedEnvelope');o=d.addObject('Part::Feature','L298NConnectedEnvelope');o.Shape=expected
        o.Label='L298N 插线包络／厚28.5实测／长宽沿用原输入'
        o.addProperty('App::PropertyString','EvidenceBasis');o.EvidenceBasis=compact.BASIS
        d.recompute();d.saveAs(str(native));Part.export([o],str(step));A.closeDocument(d.Name)
    d=A.openDocument(str(native));actual=d.Objects[0].Shape
    diff=expected.cut(actual).Volume+actual.cut(expected).Volume
    assert actual.isValid() and diff<1e-5
    A.closeDocument(d.Name)
    s=Part.Shape();s.read(str(step));diff_step=expected.cut(s).Volume+s.cut(expected).Volume
    assert s.isValid() and diff_step<.01
    result=dict(date='2026-10-26',connected_thickness_mm=28.5,length_width_mm=[46.2,43.5],
                evidence='User measured maximum connected thickness; previous overall length/width retained, not remeasured.',
                shape='complete rectangular connected envelope; no inferred PCB contacts/holes/terminals',
                native_difference_mm3=diff,step_difference_mm3=diff_step,passed=True,
                files_sha256={p.name:sha(p) for p in (native,step)},physical_mount_verified=False)
    dump(folder/'readback.json',result)
    return str(native.relative_to(ROOT)),result


def style(doc):
    for o in doc.Objects:
        if not o.Name.startswith('L298N'):continue
        cat=getattr(o,'Category','')
        visible=cat not in ('envelope','clearance')
        if 'Pad' in o.Name:color=(.18,.21,.23)
        elif 'Nut' in o.Name or 'Screw' in o.Name:color=(.7,.72,.75)
        elif cat=='clearance':color=(.67,.36,.82)
        elif cat=='envelope':color=(.95,.47,.12)
        else:color=(.22,.48,.7)
        o.ViewObject.ShapeColor=color;o.ViewObject.DiffuseColor=[color]
        o.ViewObject.Visibility=visible
        o.ViewObject.Transparency=65 if cat=='clearance' else 0
        o.Label2=compact.BASIS
        if cat=='clearance':o.Label='L298N · 接线/通风预留 · '+o.Name.removeprefix('L298N')
        elif 'BaseScrew' in o.Name:o.Label='L298N · 底盖锁紧螺钉 M2.5×8 · '+o.Name[-1]
        elif 'BaseNut' in o.Name:o.Label='L298N · 底部防转螺母 M2.5 · '+o.Name[-1]
        elif 'CapScrew' in o.Name:o.Label='L298N · 上压框螺钉 M2×4 · '+o.Name[-1]
        elif 'CapNut' in o.Name:o.Label='L298N · 上压框薄螺母 M2×1.2 · '+o.Name[-1]
        elif 'Pad' in o.Name:o.Label='L298N · 绝缘接触垫候选 · '+o.Name.removeprefix('L298N')
    doc.L298NEnvelope.addProperty('App::PropertyString','SourceFile')
    doc.L298NEnvelope.SourceFile='hardware/components/L298N/revisions/connected-28.5-2026-10-26/L298N-connected-envelope.FCStd'
    doc.L298NEnvelope.addProperty('App::PropertyString','AxisMapping')
    doc.L298NEnvelope.AxisMapping='local +X -> world +Z, +Y -> -Y, +Z -> +X; origin (-14.25,22.25,36); scale 1'
    doc.L298NEnvelope.Label='L298N · 插线包络46.2×43.5×28.5／转90°'
    doc.L298NCarrier.Label='L298N · 底盖承载托架／前后限位'
    doc.L298NTopRetainer.Label='L298N · 可拆上压框／两螺钉机外释放'


def render_candidate(doc,folder):
    import FreeCADGui as G
    from pivy import coin  # Load the Coin wrapper before accessing camera fields.
    from PySide import QtGui
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    review=A.newDocument('L298NCompactReview')
    names=compact.moving_names(doc)+[o.Name for o in doc.Objects if o.Name.startswith('L298N') and o.Category=='clearance']
    names += ['MotorL','MotorR','BottomServiceCover','KeelLid','PowerBank','MT3608Envelope']
    for name in names:
        original=doc.getObject(name)
        if not original:continue
        o=review.addObject('Part::Feature',name);o.Shape=original.Shape.copy();o.Label=original.Label
        o.addProperty('App::PropertyString','EvidenceBasis');o.EvidenceBasis=getattr(original,'EvidenceBasis','reference from saved main assembly')
        color=original.ViewObject.ShapeColor;o.ViewObject.ShapeColor=color;o.ViewObject.DiffuseColor=[color]
    tail=review.addObject('Part::Feature','MotorTailStudyKeepout')
    tail.Shape=Part.makeCompound([compact.box((15,-18.5,31.5,26.2,18.5,68.5)),compact.box((-26.2,-18.5,31.5,-15,18.5,68.5))])
    tail.Label='30 mm 尾部检查盒／Y-Z轮廓仍为假设';tail.ViewObject.ShapeColor=(.85,.25,.18);tail.ViewObject.Transparency=65
    review.Label='L298N 28.5 mm 插线包络／底盖承载候选'
    review.recompute();G.activeDocument().activeView().viewAxonometric()
    view=G.activeDocument().activeView();view.setCameraType('Orthographic')
    def visible(selection):
        for o in review.Objects:o.ViewObject.Visibility=o.Name in selection
    def save(name):
        review.recompute();G.updateGui()
        for _ in range(6):QtGui.QApplication.processEvents()
        view.fitAll()
        camera=view.getCameraNode();camera.height.setValue(camera.height.getValue()*1.15)
        G.updateGui()
        view.saveImage(str(folder/name),1500,1100,'White')
    physical=set(compact.moving_names(doc))
    visible(physical|{'MotorL','MotorR','MotorTailStudyKeepout','BottomServiceCover'})
    review.L298NEnvelope.ViewObject.Transparency=75
    review.BottomServiceCover.ViewObject.Transparency=75
    save('installed.png')
    review.saveAs(str(folder/'L298N-compact-review.FCStd'))
    originals={o.Name:o.Shape.copy() for o in review.Objects}
    visible(physical-{'L298NEnvelope'}|{'L298NEnvelope'})
    for o in review.Objects:
        q=o.Shape.copy()
        if o.Name.startswith(('L298NTop','L298NCapScrew')):q.translate(V(0,0,28))
        elif o.Name=='L298NEnvelope':q.translate(V(0,0,12))
        o.Shape=q
    save('exploded.png')
    for o in review.Objects:o.Shape=originals[o.Name]
    spaces={n for n in names if n.endswith('Space')}
    visible(spaces|{'L298NCarrier','L298NTopRetainer','L298NEnvelope','MotorTailStudyKeepout'})
    review.L298NEnvelope.ViewObject.Transparency=85
    for n in spaces:review.getObject(n).ViewObject.Transparency=30
    save('wiring.png')
    A.closeDocument(review.Name)


def row(obj,prior=None):
    r=dict(prior or {});b=obj.Shape.BoundBox
    r.update(name=obj.Name,label=obj.Label,category=getattr(obj,'Category','merged_print_part'),
             volume_mm3=obj.Shape.Volume,valid=obj.Shape.isValid(),solids=len(obj.Shape.Solids),bbox_mm=compact.bounds(obj.Shape))
    return r


def main():
    import FreeCADGui as G
    G.showMainWindow()
    OUT.mkdir(parents=True,exist_ok=True)
    src_path=MODEL/'source/CyberTrack-design.FCStd';main_path=MODEL/'CyberTrack.FCStd'
    backup=Path('/tmp/cybertrack-l298n-compact-before');backup.mkdir(exist_ok=True)
    baseline={str(p.relative_to(MODEL)):sha(p) for p in (src_path,main_path)}
    protected={p:sha(p) for p in (ROOT/'hardware/components/L298N').glob('*') if p.is_file() and p.suffix in ('.FCStd','.step')}
    for p in (src_path,main_path):
        target=backup/('source-before.FCStd' if p==src_path else 'delivery-before.FCStd')
        if not target.exists():shutil.copy2(p,target)
    src=A.openDocument(str(src_path));delivery=A.openDocument(str(main_path))
    if src.getObject('L298NTopRetainer') or delivery.getObject('L298NTopRetainer'):
        raise ValueError('Compact revision already present; inspect saved audit rather than reapplying')
    before={d.Name:shape_rows(d) for d in (src,delivery)}
    old_names={d.Name:{o.Name for o in d.Objects if o.Name.startswith('L298N')} for d in (src,delivery)}
    for d in (src,delivery):
        compact.apply(d);style(d)
        d.Label='CyberTrack 双履带交互机器人 · 0.57 L298N 28.5 mm插线包络'
        d.recompute()
    component_path,component_report=connected_component()
    checks=compact.check(src);service=compact.check_service(src)
    dump(OUT/'pre-save-check.json',dict(static=checks,service=service))
    assert checks['passed'] and service['passed'],'candidate failed; original files not saved'
    from mt3608_layout import check as check_mt3608
    mt3608=check_mt3608(src)
    assert mt3608['passed'],mt3608
    from drive_service_check import check as check_drive
    drive=check_drive(src)
    dump(OUT/'drive-regression.json',drive)
    assert drive['passed'], 'Drive regression failed; original files not saved'
    for o in list(delivery.Objects):
        if o.Name.startswith('L298N') and o.Category=='clearance':delivery.removeObject(o.Name)
    scope={}
    for d in (src,delivery):
        now=shape_rows(d);unchanged=set(before[d.Name])-old_names[d.Name]-{'KeelLid','BottomServiceCover'}
        assert all(n in now and same(before[d.Name][n],now[n]) for n in unchanged),d.Name
        scope[d.Name]=dict(unchanged_shapes=len(unchanged),removed=sorted(set(before[d.Name])-set(now)),
                          added=sorted(set(now)-set(before[d.Name])),changed_existing=['KeelLid','BottomServiceCover','L298NEnvelope','L298NCarrier'])
        assert all(d.getObject(n).Shape.isValid() for n in now)
    for n in shape_rows(delivery):
        assert src.getObject(n) and same(signature(src.getObject(n).Shape),signature(delivery.getObject(n).Shape)),n
    parts=export_parts(src,OUT)
    # All checks above are on unsaved working documents. Guard against concurrent
    # source updates immediately before saving, then verify the round trip.
    assert all(sha(MODEL/k)==v for k,v in baseline.items()),'Concurrent CAD update detected'
    expected={str(p):shape_rows(d) for p,d in ((src_path,src),(main_path,delivery))}
    for d in (src,delivery):d.save()
    A.closeDocument(src.Name);A.closeDocument(delivery.Name)
    src=A.openDocument(str(src_path));delivery=A.openDocument(str(main_path))
    for p,d in ((src_path,src),(main_path,delivery)):
        now=shape_rows(d);assert now.keys()==expected[str(p)].keys()
        assert all(same(now[n],expected[str(p)][n]) for n in now)
    assembly=[o for o in delivery.Objects if hasattr(o,'Shape') and not o.isDerivedFrom('App::DocumentObjectGroup') and getattr(o,'Category','') not in ('envelope','clearance')]
    Part.export(assembly,str(MODEL/'CyberTrack.step'))
    exchange=Part.Shape();exchange.read(str(MODEL/'CyberTrack.step'))
    combined=Part.makeCompound([o.Shape for o in assembly])
    assert exchange.isValid() and len(exchange.Solids)==len(combined.Solids)
    render_candidate(src,OUT)
    A.setActiveDocument(delivery.Name);G.activeDocument().activeView().viewAxonometric();G.activeDocument().activeView().fitAll()
    G.activeDocument().activeView().saveImage(str(MODEL/'assembly.png'),1600,1200,'White')
    report=dict(date='2026-10-26',revision='0.57',baseline=baseline,scope=scope,
        measurements=dict(motor_lengths_mm=[57,57],direct_tail_gap_mm=30,connected_driver_thickness_mm=28.5,
                          nominal_mount_spacing_mm=146,derived_gap_mm=32,retained_conservative_gap_mm=30),
        static=checks,service=service,mt3608_regression=mt3608,drive_regression=drive,
        connected_component=component_report,print_exports=parts,saved_and_reopened=True,
        connected_board_tail_clearance_each_mm=.75,component_source=component_path,
        fasteners=dict(base='2 x M2.5x8 and matching AF5 / 2 mm nuts (candidate)',cap='2 x M2x4 and DIN439 M2 thin nuts AF4 / 1.2 mm',
                       thin_nut_reference='https://www.accu.co.uk/thin-hexagon-nuts/73069-HFN-M2-A4'),
        source_sha256=sha(src_path),delivery_sha256=sha(main_path),
        unchanged_original_component_assets=all(sha(p)==v for p,v in protected.items()),
        passed=True,manufacturing_released=False,physical_fit_verified=False,
        limits=['Y/Z motor-tail profile remains an assumed full radial box.',
                '28.5 mm is measured connected thickness; exact PCB contact pads and terminal locations remain unmeasured.',
                'Wiring spaces are geometric budgets, not selected cables or pin-to-pin harnesses; verify wire diameter, bends and disconnection/slack.',
                'The complete rigid cassette including fasteners and bottom cover passed continuous withdrawal; no flexible-harness withdrawal claim.',
                'Bottom cover now carries the driver; fastener strength, plastic creep, thermal performance and real assembly remain unverified.',
                'Unrelated existing assembly failures remain; scoped pass is not whole-robot acceptance.'])
    dump(REPORT,report)
    finalize_metadata(src,delivery,report)
    print(json.dumps(dict(passed=True,parts=parts,scope=scope),ensure_ascii=False),flush=True)
    A.closeDocument(src.Name);A.closeDocument(delivery.Name)


def finalize_metadata(src,delivery,report):
    src_path=MODEL/'source/CyberTrack-design.FCStd';main_path=MODEL/'CyberTrack.FCStd'
    checks=report['static'];service=report['service'];mt3608=report['mt3608_regression'];drive=report['drive_regression']
    component_path=report['component_source']
    report.update(source_sha256=sha(src_path),delivery_sha256=sha(main_path))
    dump(REPORT,report)
    exchange=Part.Shape();exchange.read(str(MODEL/'CyberTrack.step'))
    combined=Part.makeCompound([o.Shape for o in delivery.Objects if hasattr(o,'Shape') and not o.isDerivedFrom('App::DocumentObjectGroup') and getattr(o,'Category','') not in ('envelope','clearance')])
    rb=json.loads((MODEL/'readback.json').read_text())
    old_rows={r['name']:r for r in rb['objects']}
    delivery_names=set(shape_rows(delivery));source_names=set(shape_rows(src))
    rb['objects']=[row(o,old_rows.get(o.Name)) for o in delivery.Objects if o.Name in delivery_names]
    old_source={r['name']:r for r in rb.get('source_feature_objects',[])}
    rb['source_feature_objects']=[row(o,old_source.get(o.Name)) for o in src.Objects if o.Name in source_names]
    rb.update(local_revision='0.57-l298n-compact',l298n_compact_audit=REPORT.name,l298n_compact=report,
              l298n_layout=dict(board_bbox_mm=compact.bounds(src.L298NEnvelope.Shape),connected_thickness_mm=28.5,component_source=component_path),
              l298n_mount=dict(revision='0.57',bottom_cover_carries_driver=True),l298n_check=checks,
              l298n_mount_check=dict(**checks,service=service),mt3608_check=mt3608,drive_mount_check=drive)
    rb['assembly_paths_verified']=False
    rb['service_paths']['current_validation']='Historical whole-assembly result retained; current cover/L298N/drive/MT3608 checks in l298n-compact-audit.json.'
    rb['step_readback'].update(valid=exchange.isValid(),solids=len(exchange.Solids),expected_solids=len(combined.Solids),
        volume_difference_mm3=abs(exchange.Volume-combined.Volume),volume_comparison_passed=abs(exchange.Volume-combined.Volume)<=.01)
    paths=[src_path,main_path,MODEL/'CyberTrack.step',MODEL/'assembly.png']
    rb['files_sha256'].update({str(p.relative_to(MODEL)):sha(p) for p in paths})
    tree=json.loads((MODEL/'model-tree-audit.json').read_text())
    tree.update(source_sha256=sha(src_path),delivery_sha256=sha(main_path),l298n_compact_audit=REPORT.name,
        current_retained_shape_count=len(shape_rows(delivery)),current_source_shape_count=len(shape_rows(src)),
        geometry_scope='New L298N cassette and two supporting lids; all other shape signatures retained. See l298n-compact-audit.json.')
    tree.update(part_count=len(delivery_names),root_part_count=len(delivery_names)-len(tree['drive_members']),
        removed_check_spaces=sorted(o.Name for o in src.Objects if getattr(o,'Category','')=='clearance' and not o.Name.startswith(('IgnitionRoute','StopSignalRoute'))),
        shape_checks=[dict(name=n,geometry_signature_matches=True) for n in sorted(delivery_names)],
        label_audit_scope='Historical naming proof retained; current labels and geometry are listed in readback.json and l298n-compact-audit.json.')
    rb['model_tree']={k:v for k,v in tree.items() if k!='shape_checks'}
    pc=json.loads((MODEL/'print-consolidation-audit.json').read_text());pc.update(source_sha256=sha(src_path),l298n_compact_audit=REPORT.name)
    dump(MODEL/'print-consolidation-audit.json',pc);dump(MODEL/'model-tree-audit.json',tree);dump(MODEL/'readback.json',rb)
    dump(MODEL/'l298n-fit-audit.json',dict(**checks,source_after_sha256=sha(main_path),saved_and_reopened=True))
    dump(MODEL/'l298n-mount-audit.json',dict(**checks,service=service,source_after_sha256=sha(main_path),saved_and_reopened=True))
    dump(MODEL/'drive-mount-audit.json',dict(**drive,source_sha256=sha(src_path),saved_and_reopened=True))
    dump(MODEL/'mt3608-fit-audit.json',dict(**mt3608,source_sha256=sha(src_path),saved_and_reopened=True))


if __name__=='__main__':
    main()
    import os
    os._exit(0)
