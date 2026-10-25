"""User-measured replacement battery envelope, without inferred ports or cells."""
import hashlib
import json
from pathlib import Path
import FreeCAD as App
import Part
from refine_assembly import route
from l298n_layout import CABLE_POINTS
from head_lift import LIFT

SIZE=(116,70.5,19.5)
ORIGIN=(-58,-94.75,33)
BASIS='用户2026-10-25提供116×70.5×19.5 mm；照片铭牌辰克CK18650-1234S-NP、5 V；矩形最大包络，不含软线／接头，未称重或实测电气性能'


def apply(doc):
    folder=Path(__file__).resolve().parents[1]/'hardware/components/ck-5v-battery'
    cad=folder/'Battery-envelope.FCStd';step=folder/'Battery-envelope.step'
    expected=Part.makeBox(*SIZE)
    if not cad.exists():
        d=App.newDocument('ReplacementBattery')
        o=d.addObject('Part::Box','BatteryEnvelope');o.Length,o.Width,o.Height=SIZE
        o.Label='辰克5 V电池包／用户尺寸116×70.5×19.5'
        o.addProperty('App::PropertyString','EvidenceBasis','Evidence');o.EvidenceBasis=BASIS
        d.recompute();d.saveAs(str(cad));Part.export([o],str(step));App.closeDocument(d.Name)
    assert step.exists()
    d=App.openDocument(str(cad));native=d.BatteryEnvelope.Shape.copy();App.closeDocument(d.Name)
    imported=Part.Shape();imported.read(str(step))
    checks=[]
    for kind,shape in [('FCStd',native),('STEP',imported)]:
        delta=expected.cut(shape).Volume+shape.cut(expected).Volume
        checks.append(dict(format=kind,valid=shape.isValid(),solids=len(shape.Solids),difference_mm3=delta,
                           passed=shape.isValid() and len(shape.Solids)==1 and delta<1e-5))
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    report=dict(size_lwh_mm=SIZE,source='user dimensions and original photo, 2026-10-25',
        local_axes='length X, width Y, height Z; origin at minimum corner',checks=checks,
        saved_and_reopened=True,files_sha256={str(p.relative_to(folder)):sha(p) for p in [cad,step,folder/'reference/physical-20261025.jpg']},
        passed=all(r['passed'] for r in checks),physical_fit_verified=False)
    (folder/'readback.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    assert report['passed']
    native.translate(App.Vector(*ORIGIN));obj=doc.PowerBank;obj.Shape=native
    obj.Label='辰克5 V电池包116×70.5×19.5／前下方平放候选';obj.EvidenceBasis=BASIS
    obj.addProperty('App::PropertyString','SourceFile','Evidence');obj.SourceFile=str(cad.relative_to(folder.parents[2]))
    # Keep the central trunk only; the former A110M long-face plug is obsolete.
    points=[(x,y,z+LIFT if i>=3 else z) for i,(x,y,z) in enumerate(CABLE_POINTS)]
    doc.PowerCableRoute.Shape=route(points,3)
    doc.PowerCableRoute.Label='中央低压线束预算／新电池端接待确认'
    doc.PowerCableRoute.EvidenceBasis='保留中央Ø6线束空间；移除旧充电宝插头盒。照片短边引线位置仅定性可见，接头尺寸、朝向及新电池至此通路未完成。'
    return dict(component_readback=report,size_lwh_mm=SIZE,origin_mm=ORIGIN,top_z_mm=52.5,
        centre_z_mm=42.75,placement_assumption='same low horizontal bay; length X, width Y, thickness Z',
        port_orientation_verified=False,cable_connection_complete=False,mass_kg=None)
