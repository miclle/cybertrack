"""Measured P06 envelope; candidate dry-bay allocation, no inferred PCB details."""
import hashlib
import json
from pathlib import Path
import FreeCAD as A
import Part

ROOT = Path(__file__).resolve().parents[1]
SIZE = (37, 18, 6)
ORIGIN = (43, -17, 82)
BASIS = '用户2026-10-25实测长37×宽18×厚6 mm；完整外包络，无推定PCB、孔位、焊脚或电位器位置'


def bounds(s):
    b = s.optimalBoundingBox(False)
    return [b.XMin,b.YMin,b.ZMin,b.XMax,b.YMax,b.ZMax]


def component():
    folder = ROOT/'hardware/components/MT3608'
    folder.mkdir(exist_ok=True)
    native, step = folder/'MT3608-envelope.FCStd', folder/'MT3608-envelope.step'
    expected = Part.makeBox(*SIZE)
    if not native.exists():
        d=A.newDocument('MT3608Component')
        o=d.addObject('Part::Box','MT3608Envelope')
        o.Label='MT3608 实测包络 37×18×6 mm'
        o.Length,o.Width,o.Height=SIZE
        o.addProperty('App::PropertyString','EvidenceBasis','Evidence');o.EvidenceBasis=BASIS
        d.recompute();d.saveAs(str(native));Part.export([o],str(step));A.closeDocument(d.Name)
    assert step.exists(), 'Existing component STEP missing; inspect instead of overwriting'
    d=A.openDocument(str(native));s=d.getObject('MT3608Envelope').Shape.copy();A.closeDocument(d.Name)
    imported=Part.Shape();imported.read(str(step))
    rows=[]
    for label,shape in [('FCStd',s),('STEP',imported)]:
        delta=expected.cut(shape).Volume+shape.cut(expected).Volume
        rows.append(dict(format=label,valid=shape.isValid(),bbox_mm=bounds(shape),difference_mm3=delta,
                         passed=shape.isValid() and len(shape.Solids)==1 and delta<1e-5))
    r=dict(size_lwt_mm=SIZE,evidence=BASIS,saved_and_reopened=True,checks=rows,
           files_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (native,step)},
           passed=all(row['passed'] for row in rows),physical_fit_verified=False)
    (folder/'readback.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n')
    assert r['passed'],r
    return s


def apply(doc,add):
    shape=component()
    shape.Placement=A.Placement(A.Vector(*ORIGIN),A.Rotation(A.Vector(0,0,1),90))
    o=add('MT3608Envelope','P06 MT3608 升压板／37×18×6 实测包络',shape,'envelope','power',BASIS+'；L298N左上方候选，固定方式待设计')
    o.addProperty('App::PropertyString','SourceFile','Evidence');o.SourceFile='hardware/components/MT3608/MT3608-envelope.FCStd'
    for name,y in [('Front',-21),('Rear',20)]:
        add('MT3608WireSpace'+name,'MT3608 板端4 mm接线预算 '+name,
            Part.makeBox(18,4,8,A.Vector(25,y,81)),'clearance','power',
            '局部接线预算；实际输入输出端方位、焊接、插头和线弯未测；不代表针序或完整线束')
    return dict(size_lwt_mm=SIZE,origin_mm=ORIGIN,local_to_world_axes=['+Y','-X','+Z'],
                bbox_mm=bounds(shape),mounting='allocation only; no fixture or hole pattern inferred',physical_fit_verified=False)


def check(doc):
    board=doc.getObject('MT3608Envelope').Shape
    selected=[o for o in doc.Objects if o.Name.startswith('MT3608')]
    others=[o for o in doc.Objects if hasattr(o,'Category') and not o.Name.startswith('MT3608')]
    overlaps=[];near=[]
    for target in selected:
        for other in others:
            if target.Shape.BoundBox.intersect(other.Shape.BoundBox):
                v=target.Shape.common(other.Shape).Volume
                if v>.01:overlaps.append(dict(target=target.Name,other=other.Name,volume_mm3=v))
    for o in others:
        b=A.BoundBox(board.BoundBox);b.enlarge(8)
        if b.intersect(o.Shape.BoundBox):near.append(dict(object=o.Name,distance_mm=board.distToShape(o.Shape)[0]))
    near.sort(key=lambda x:x['distance_mm'])
    # Bare board can leave downward only after both left motor and driver cassette.
    # This is a service allocation, not a claimed convenient/removable fixture.
    from l298n_mount import moving_names
    removed=set(moving_names(doc))|{'MotorL','BottomServiceCover'}
    removed.update(o.Name for o in others if o.Name.startswith(('BottomCoverScrew','L298NMountScrew','MotorFaceScrewL')))
    sweep=Part.makeBox(18,37,96,A.Vector(25,-17,-8))
    hits=[]
    for o in others:
        if o.Category=='clearance' or o.Name in removed:continue
        if sweep.BoundBox.intersect(o.Shape.BoundBox):
            v=sweep.common(o.Shape).Volume
            if v>.01:hits.append(dict(object=o.Name,volume_mm3=v))
    blocked=sweep.common(doc.getObject('MotorL').Shape).Volume
    expected=Part.makeBox(18,37,6,A.Vector(25,-17,82))
    delta=board.cut(expected).Volume+expected.cut(board).Volume
    return dict(size_lwt_mm=SIZE,bbox_mm=bounds(board),placement_difference_mm3=delta,
        objects_checked=len(others),overlaps=overlaps,nearby_distances=near[:15],
        bare_board_removal=dict(method='exact rectangular continuous sweep 90 mm down',
            removed_first=sorted(removed),disconnect_first='MT3608 leads and left-motor/driver wiring; release future fixture',
            prerequisite='Follow existing left motor and L298N removal procedures, including power tray and left track removal.',
            overlaps=hits,left_motor_retained_negative_control_mm3=blocked,passed=not hits and blocked>.01),
        passed=board.isValid() and delta<1e-5 and not overlaps and not hits and blocked>.01,
        physical_fit_verified=False,thermal_verified=False,mounting_complete=False,
        limits=['Overall measured box only; PCB contacts, terminals and adjustment position unmeasured.',
                'End spaces are design budgets, not a complete wiring or adjustment path.',
                'Service requires driver and left motor removal; fixture and physical handling remain unresolved.'])


def render(doc,output):
    import FreeCADGui as G
    from PySide import QtGui
    objects=[o for o in doc.Objects if hasattr(o,'Category')]
    saved={o.Name:(o.ViewObject.Visibility,o.ViewObject.Transparency) for o in objects}
    view=G.activeDocument().activeView();camera=view.getCameraOrientation()
    names={'MotorL','MotorR','L298NEnvelope','L298NCarrier','PowerBank','LowerTub','KeelLid','EffectTray'}
    try:
        for o in objects:
            o.ViewObject.Visibility=o.Name in names or o.Name.startswith('MT3608')
            o.ViewObject.Transparency=88 if o.Name in ('LowerTub','KeelLid') else 65 if o.Category=='clearance' else 0
        view.setCameraOrientation(A.Rotation(A.Vector(1,1,0),A.Vector(-1,1,3),A.Vector(1,-1,.75),'ZXY').Q)
        view.fitAll()
        for _ in range(10):QtGui.QApplication.processEvents()
        view.saveImage(str(output/'mt3608-layout.png'),1600,1200,'White')
    finally:
        for o in objects:o.ViewObject.Visibility,o.ViewObject.Transparency=saved[o.Name]
        view.setCameraOrientation(camera.Q);view.fitAll()
