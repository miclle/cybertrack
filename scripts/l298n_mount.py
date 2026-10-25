"""0.34 removable L298N cassette: photo-informed topology, unmeasured interfaces.

The original whole-module box stays authoritative for collision avoidance.
Contact patches, M2/M2.5 hardware, terminal corridors and vents are design
allocations, not measurements extracted from either perspective photograph.
"""
import hashlib
import json
from pathlib import Path
import FreeCAD as A
import Part
from refine_assembly import box
V = A.Vector
ROOT = Path(__file__).resolve().parents[1]
TOL = 0.01
CLAMP_Z = (37.0, 74.5)
MOUNT_X = (-20.0, 20.0)
MOUNT_Y = -12.0


def union(parts):
    return parts[0].multiFuse(parts[1:]).removeSplitter() if len(parts)>1 else parts[0]


def mirrored(shape, sign):
    if sign>0:return shape.copy()
    matrix=A.Matrix();matrix.A11=-1
    return shape.transformGeometry(matrix)


def zc(radius, z0, z1, x, y):
    return Part.makeCylinder(radius,z1-z0,V(x,y,z0))


def xc(radius, x0, x1, y, z):
    return Part.makeCylinder(radius,x1-x0,V(x0,y,z),V(1,0,0))


def hex_x(radius, x0, x1, y, z):
    import math
    points=[V(x0,y+radius*math.cos(math.pi/6+i*math.pi/3),z+radius*math.sin(math.pi/6+i*math.pi/3)) for i in range(6)]
    return Part.Face(Part.makePolygon(points+[points[0]])).extrude(V(x1-x0,0,0))


def carrier_primitives():
    # Each box is also used for a conservative continuous removal sweep. Their
    # union contains the final carrier, including the nut holders and rear stops.
    parts=[box(-17,19.5,29.2,17,24.5,31.2)]
    for sign in (-1,1):
        parts += [mirrored(box(17,-17,29.2,25.25,24.5,31.2),sign),
                  mirrored(box(22.25,20.5,29.2,25.25,24.5,78.2),sign)]
        for z in CLAMP_Z:
            parts += [mirrored(box(25.2,18,z-3.25,28.75,24.5,z+3.25),sign),
                      mirrored(box(18,24,z-2,22.3,24.5,z+2),sign)]
    return parts


def apply(doc, add):
    parts=[]
    for sign in (-1,1):
        parts += [mirrored(box(17,-16,31.2,23,-8,90.1),sign),
                  mirrored(box(17,-16,79,23,24.5,81.5),sign)]
    lid=doc.getObject('KeelLid')
    lid.Shape=union([lid.Shape]+parts)
    carrier=union(carrier_primitives())
    for x in MOUNT_X:
        carrier=carrier.cut(zc(1.4,29.1,31.3,x,MOUNT_Y))
        lid.Shape=lid.Shape.cut(zc(1.4,31.1,34.2,x,MOUNT_Y)).cut(zc(2.1,34.1,40,x,MOUNT_Y))
    for side,sign in [('L',1),('R',-1)]:
        for i,z in enumerate(CLAMP_Z):
            carrier=carrier.cut(mirrored(xc(1.15,22.15,28.9,21.25,z),sign))
            carrier=carrier.cut(mirrored(hex_x(2.43,26.1,28.9,21.25,z),sign))
            nut=hex_x(2.31,26.2,27.8,21.25,z).cut(xc(1,26.1,27.9,21.25,z))
            screw=xc(.9,22.25,29.5,21.25,z).fuse(xc(1.8,29.5,30.9,21.25,z))
            screw=screw.cut(box(30.0,20.85,z-2,31,21.65,z+2))
            add('L298NClampNut'+side+str(i),'M2级侧压螺母占位 '+side+str(i),mirrored(nut,sign),'structure','metal','M2级示意；槽口装入，真实螺纹、材料与防松待验')
            add('L298NClampScrew'+side+str(i),'M2级可调侧压螺钉 '+side+str(i),mirrored(screw,sign),'structure','metal','在机外调整压块；不使用未测的PCB孔距；扭矩与板边接触待实物确认')
            add('L298NSidePad'+side+str(i),'绝缘侧压垫候选 '+side+str(i),mirrored(box(21.75,19.75,z-1.5,22.25,22.75,z+1.5),sign),'structure','dark','0.5厚接触垫候选；接触点只按外包络分配，须核实PCB安全边缘、材料及压缩量')
            add('L298NRearPad'+side+str(i),'四角后挡软垫候选 '+side+str(i),mirrored(box(18.5,23.5,z-1.5,21.5,24,z+1.5),sign),'structure','dark','背面中央完全避空，仅四角候选接触；不等于已验证PCB与焊脚位置')
        add('L298NBottomPad'+side,'PCB下沿承托垫候选 '+side,mirrored(box(18,21,31.2,21.5,23.5,32),sign),'structure','dark','0.8厚候选垫；下沿与背面基准需要实物校准')
    carrier=carrier.removeSplitter()
    add('L298NCarrier','L298N 开口可拆托框／四点侧压',carrier,'structure','body','下托框2厚、后导柱3×4、中央与端子面开放；尺寸为设计候选，不是PCB测量')
    for side,x in [('R',-20),('L',20)]:
        insert=zc(2,34.2,39.8,x,MOUNT_Y).cut(zc(1.3,34.1,39.9,x,MOUNT_Y))
        screw=zc(1.2,29.2,39.5,x,MOUNT_Y).fuse(zc(2.2,27.6,29.2,x,MOUNT_Y))
        screw=screw.cut(zc(.9,27.5,28.5,x,MOUNT_Y))
        add('L298NMountInsert'+side,'吊架盲孔嵌件候选 '+side,insert,'structure','metal','M2.5级占位；盲孔不贯穿干舱顶盖，不打通湿舱隔板')
        add('L298NMountScrew'+side,'底部托框锁紧螺钉 '+side,screw,'structure','metal','M2.5级示意；先拆底盖再托住托框、断线、退两颗螺钉，沿-Z抽出')
    cover=doc.getObject('BottomServiceCover')
    for x in MOUNT_X:cover.Shape=cover.Shape.cut(zc(2.8,25.9,28.9,x,MOUNT_Y))
    for side,sign in [('L',1),('R',-1)]:
        xs=sorted((sign*11,sign*16));x0,x1=xs
        cover.Shape=cover.Shape.cut(box(x0,-22,25.9,x1,-17,28.9))
        lid.Shape=lid.Shape.cut(box(x0,21,89.4,x1,24,94))
        air=union([box(x0,-22,28.8,x1,-17,84),box(x0,-22,82,x1,24,88.5),box(x0,21,88.5,x1,24,104)])
        add('L298NAirSpace'+side,'进风及上排风几何预留 '+side,air,'clearance','signal','每侧底口5×5、顶口5×3；自由空气体积，不是实体风管或散热能力证明')
        wire=mirrored(box(22.25,-7,42,25.5,19.5,70),sign)
        add('L298NMotorWireSpace'+side,'电机端子引线侧廊候选 '+side,wire,'clearance','power','3.25宽侧廊；端子位置、线径、弯曲半径须实测。端子螺钉在托框抽出后操作')
    add('L298NConnectorSpace','下沿电源与控制接线区候选',box(-16,-17,31.5,16,-5.5,41.5),'clearance','power','32×11.5×10候选；朝底部检修口开放，真实插头和手指空间待核')
    lid.Shape=lid.Shape.removeSplitter();cover.Shape=cover.Shape.removeSplitter()
    lid.EvidenceBasis='0.34增加两根干舱吊柱与顶部止挡，吊柱与顶盖一体；两个干区排风口，不贯通后湿舱隔板；材料与承载未验'
    cover.EvidenceBasis='0.34底盖增加两处Ø5.6锁紧螺钉避让孔及2个5×5进风口；托框由上部吊架承重，底盖不承托板卡'
    assert carrier.isValid() and len(carrier.Solids)==1
    for obj in (lid,cover):assert obj.Shape.isValid() and len(obj.Shape.Solids)==1,obj.Name
    return {'revision':'0.34','photo_manifest':'hardware/components/L298N/reference/photos.json',
            'mount_method':'open cassette with four adjustable edge-pressure pads; no assumed PCB mounting-hole pattern',
            'interface_assumptions':['PCB lower-edge and corner contact regions require actual confirmation.',
                                     'Overall supplied height may or may not include solder tails; no protrusion height inferred.',
                                     'Screw sizes, pad thicknesses and connector corridors are proposed design values.'],
            'mount_screw_centres_xy_mm':[[-20,-12],[20,-12]],'mount_screw_type':'2 x M2.5-class candidate',
            'clamp_screw_type':'4 x M2-class candidate','upper_stop_gap_mm':0.8,
            'vent_open_area_mm2':{'bottom_total':50,'top_total':30},
            'rear_wet_bulkhead_perforated':False,'bottom_cover_carries_driver':False,
            'mount_holes_verified':False,'pcb_contact_verified':False,'thermal_verified':False,'physical_fit_verified':False}


def moving_names(doc):
    prefixes=('L298NClamp','L298NSidePad','L298NRearPad','L298NBottomPad')
    return ['L298NEnvelope','L298NCarrier']+[o.Name for o in doc.Objects if o.Name.startswith(prefixes)]


def bb(shape):
    b=shape.optimalBoundingBox(False)
    return [b.XMin,b.YMin,b.ZMin,b.XMax,b.YMax,b.ZMax]


def box_sweep(shape, distance=80):
    x0,y0,z0,x1,y1,z1=bb(shape)
    return box(x0,y0,z0-distance,x1,y1,z1)


def check(doc):
    objects={o.Name:o for o in doc.Objects if hasattr(o,'Category')}
    physical={n:o.Shape for n,o in objects.items() if o.Category!='clearance'}
    def hits(parts,absent=()):
        rows=[]
        for label,shape in parts.items():
            for name,other in physical.items():
                if name in absent or not shape.BoundBox.intersect(other.BoundBox):continue
                common=shape.common(other)
                assert common.isValid(),(label,name)
                if common.Volume>TOL:rows.append({'moving':label,'fixed':name,'volume_mm3':common.Volume})
        return rows
    cover=['BottomServiceCover']+[n for n in physical if n.startswith('BottomCoverScrew')]
    screws=[n for n in physical if n.startswith('L298NMountScrew')]
    moving=moving_names(doc)
    sweep_parts={n:box_sweep(physical[n]) for n in moving if n!='L298NCarrier'}
    sweep_parts.update({'carrier_'+str(i):box_sweep(q) for i,q in enumerate(carrier_primitives())})
    sweep_hits=hits(sweep_parts,moving+cover+screws)
    closed_hits=hits(sweep_parts,moving+screws)
    fasteners=[]
    for name in screws:
        x=20 if name.endswith('L') else -20
        swept=union([zc(2.2,27.6-80,29.2,x,-12),zc(1.2,29.2-80,39.5,x,-12)])
        collisions=hits({name:swept},cover+[name])
        tool=zc(1.8,-20,27.6,x,-12)
        tool_hits=hits({'bit':tool},cover+[name])
        fasteners.append({'name':name,'sweep_overlaps':collisions,'tool_overlaps':tool_hits,
                          'tool_diameter_mm':3.6,'passed':not collisions and not tool_hits})
    spaces=[]
    for name,o in objects.items():
        if name.startswith(('L298NAirSpace','L298NMotorWireSpace','L298NConnectorSpace')):
            collisions=hits({name:o.Shape})
            spaces.append({'name':name,'bbox_mm':bb(o.Shape),'overlaps':collisions,'passed':not collisions})
    access=hits({'under_connector_access':box(-16,-17,-20,16,-5.5,41.5)},cover)
    # Opposing functional reservations must not silently share occupied volume.
    air=[o.Shape for n,o in objects.items() if n.startswith('L298NAirSpace')]
    wires=[o.Shape for n,o in objects.items() if n.startswith(('L298NMotorWireSpace','L298NConnectorSpace'))]
    reservation_overlap=sum(a.common(w).Volume for a in air for w in wires)
    # Board can be lifted out of the cassette on the bench after loosening pads.
    bench_parts={n:s for n,s in physical.items() if n in moving and n!='L298NEnvelope' and not n.startswith('L298NSidePad')}
    board=physical['L298NEnvelope'];b=bb(board)
    up=box(b[0],b[1],b[2],b[3],b[4],b[5]+80)
    bench_hits=[{'object':n,'volume_mm3':up.common(s).Volume} for n,s in bench_parts.items() if up.BoundBox.intersect(s.BoundBox) and up.common(s).Volume>TOL]
    nearby=[]
    assembly=Part.makeCompound([physical[n] for n in moving])
    for name in ('MotorL','MotorR','RearBulkhead','PowerBank','PowerCableRoute','BottomServiceCover'):
        nearby.append({'object':name,'distance_mm':assembly.distToShape(physical[name])[0]})
    negative=any(row['fixed']=='BottomServiceCover' for row in closed_hits)
    carrier_coverage=physical['L298NCarrier'].cut(union(carrier_primitives())).Volume
    def planar_contact(a,b,z):
        faces=lambda q:[f for f in q.Faces if abs(f.BoundBox.ZMin-z)<1e-6 and abs(f.BoundBox.ZMax-z)<1e-6]
        return sum(f.common(g).Area for f in faces(a) for g in faces(b))
    support_area=planar_contact(physical['L298NCarrier'],physical['KeelLid'],31.2)
    head_areas=[{'name':n,'area_mm2':planar_contact(physical[n],physical['L298NCarrier'],29.2)} for n in screws]
    vent_rows=[]
    for sign in (-1,1):
        x0,x1=sorted((sign*11,sign*16))
        for name,region,obstacle in [('intake',box(x0,-22,26,x1,-17,28.8),'BottomServiceCover'),('exhaust',box(x0,21,89.4,x1,24,94),'KeelLid')]:
            v=region.common(physical[obstacle]).Volume
            vent_rows.append({'side':sign,'opening':name,'remaining_material_mm3':v,'passed':v<TOL})
    result={'revision':'0.34','tolerance_mm3':TOL,'spaces':spaces,
            'cassette_removal':{'method':'80 mm downward continuous conservative union of primitive boxes; all final carrier material contained',
                'moving':moving,'removed_first':cover+screws,'disconnect_first':'motor, power and control wires; connectors and flexible service loops are not measured',
                'overlaps':sweep_hits,'closed_cover_blocks':negative,'passed':not sweep_hits and negative},
            'mount_screws_and_tools':fasteners,'connector_access':{'overlaps':access,'passed':not access},
            'vent_wire_reservation_overlap_mm3':reservation_overlap,
            'bench_board_removal':{'method':'80 mm up after cassette removed from robot and side pads released','overlaps':bench_hits,'passed':not bench_hits},
            'cassette_nearby_distances':nearby,
            'interfaces':{'carrier_to_hanger_contact_area_mm2':support_area,'screw_head_contacts':head_areas,
                'passed':support_area>70 and all(r['area_mm2']>5 for r in head_areas)},
            'sweep_carrier_uncovered_volume_mm3':carrier_coverage,'vent_openings':vent_rows,
            'pcb_corner_contact_verified':False,'connector_fit_verified':False,'thermal_verified':False,
            'physical_fit_verified':False,'manufacturing_released':False}
    result['passed']=result['interfaces']['passed'] and carrier_coverage<1e-5 and all(v['passed'] for v in vent_rows) and not sweep_hits and negative and all(v['passed'] for v in fasteners+spaces) and not access and reservation_overlap<TOL and not bench_hits
    return result


def export_carrier(doc, output):
    folder=output/'parts';folder.mkdir(exist_ok=True)
    paths=[folder/'L298N-carrier-0.34.FCStd',folder/'L298N-carrier-0.34.step']
    expected=doc.getObject('L298NCarrier').Shape.copy()
    part=A.newDocument('L298NCarrierExport')
    obj=part.addObject('Part::Feature','Carrier');obj.Shape=expected
    obj.Label='0.34 L298N 开口托框候选／整机坐标；非制造放行'
    part.recompute();part.saveAs(str(paths[0]));Part.export([obj],str(paths[1]))
    A.closeDocument(part.Name)
    saved=A.openDocument(str(paths[0]));native=saved.getObject('Carrier').Shape.copy();A.closeDocument(saved.Name)
    step=Part.Shape();step.read(str(paths[1]))
    rows=[]
    for name,shape in [('FCStd',native),('STEP',step)]:
        delta=expected.cut(shape).Volume+shape.cut(expected).Volume
        rows.append({'format':name,'valid':shape.isValid(),'solids':len(shape.Solids),'symmetric_difference_mm3':delta,'passed':shape.isValid() and len(shape.Solids)==1 and delta<1e-5})
    result={'coordinate_frame':'assembly coordinates, no scale or relocation','checks':rows,
        'files_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
        'passed':all(r['passed'] for r in rows),'manufacturing_released':False}
    assert result['passed'],result
    return result


def render(doc,output):
    import FreeCADGui as G
    from PySide import QtGui
    objects=[o for o in doc.Objects if hasattr(o,'Category')]
    saved={o.Name:(o.Shape.copy(),o.ViewObject.Visibility,o.ViewObject.Transparency,o.ViewObject.ShapeColor) for o in objects}
    view=G.activeDocument().activeView();camera=view.getCameraOrientation()
    rotation=A.Rotation(V(1,1,0),V(-1,1,3),V(1,-1,.75),'ZXY')
    def picture(name):
        doc.recompute();view.setCameraOrientation(rotation.Q);view.fitAll()
        for _ in range(10):QtGui.QApplication.processEvents()
        view.saveImage(str(output/name),1600,1200,'White')
    try:
        moving=moving_names(doc)
        for o in objects:
            o.ViewObject.Visibility=o.Name in moving and o.Name!='L298NEnvelope'
            o.ViewObject.Transparency=0
        picture('l298n-carrier.png')
        for o in objects:
            o.ViewObject.Visibility=o.Name in moving or o.Name=='KeelLid' or o.Name.startswith(('L298NMountScrew','L298NMountInsert'))
            o.ViewObject.Transparency=80 if o.Name=='KeelLid' else 0
            if o.Name in moving or o.Name.startswith('L298NMountScrew'):
                shape=o.Shape.copy();shape.translate(V(0,0,-55 if o.Name in moving else -80));o.Shape=shape
        picture('l298n-service.png')
        for o in objects:
            o.Shape=saved[o.Name][0]
            o.ViewObject.Visibility=o.Name.startswith('L298N') or o.Name in ('KeelLid','BottomServiceCover','RearBulkhead','MotorL','MotorR','PowerBank','PowerCableRoute')
            o.ViewObject.Transparency=75 if o.Category=='clearance' else 88 if o.Name in ('KeelLid','BottomServiceCover') else 65 if o.Name=='L298NEnvelope' else 0
        picture('l298n-spaces.png')
    finally:
        for o in objects:
            shape,vis,tr,col=saved[o.Name];o.Shape=shape;o.ViewObject.Visibility=vis;o.ViewObject.Transparency=tr;o.ViewObject.ShapeColor=col
        doc.recompute();view.setCameraOrientation(camera.Q);view.fitAll()
