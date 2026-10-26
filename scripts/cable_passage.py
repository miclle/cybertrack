"""15-conductor, net-diameter-10 passage candidate; no electrical acceptance."""
import math
import FreeCAD as App
import Part
from refine_assembly import box, tube
from water_gun_mount import rounded_route

V = App.Vector
REVISION = '0.55'
DIAMETER = 10.0
HEAD_POINTS = [(0,6,84),(0,6,166),(60,6,166),(60,6,194)]
CHANGED = ('KeelLid','NeckPedestal','NeckHeadSaddle','HeadShell',
           'NeckCableBridge',
           'ElectronicsTray','PowerCableRoute','StopSignalRoute')


def corridor(radius=5):
    return rounded_route(HEAD_POINTS, radius, 10)


def apply(doc):
    passage = corridor()
    clearance = corridor(5.3)
    seat = corridor(6.3)
    base_seat = Part.makeCylinder(6.3,12,V(0,6,88))
    for name in ('KeelLid','NeckPedestal'):
        obj=doc.getObject(name);obj.Shape=obj.Shape.cut(base_seat).removeSplitter()
    for name in ('NeckHeadSaddle','HeadShell'):
        obj=doc.getObject(name);obj.Shape=obj.Shape.cut(seat).removeSplitter()
    # User removed both separate grommets; preserve existing seat cutouts.
    for name in ('BaseCableGrommet','HeadCableGrommet'):
        if doc.getObject(name):doc.removeObject(name)
    bridge=box(-18,-1,107,18,2,109).fuse(tube(6.2,5,107,109,0,6))
    doc.NeckCableBridge.Shape=bridge.cut(Part.makeCylinder(5,4,V(0,6,106))).removeSplitter()
    doc.ElectronicsTray.Shape=doc.ElectronicsTray.Shape.cut(clearance).removeSplitter()
    doc.PowerCableRoute.Shape=passage
    from boot_button import POINTS
    boot_points=POINTS[:5]+[(0,6,166),(60,6,166),(60,6,194)]
    doc.StopSignalRoute.Shape=rounded_route(boot_points,1.4,4)
    for name in CHANGED:
        obj=doc.getObject(name)
        note=('；15芯总预算，限位桥净径10；上下独立护口已取消，原安装让位12.6保持；'
              '头部转向+X侧，经Z166托盘下方至X60后上行。R10为中心线布置假设，不是线材弯曲规格。')
        if name=='PowerCableRoute':
            obj.EvidenceBasis='15芯共用Ø10空间预算（含BOOT双线），不是导线实体或护管；实际线径、束径、接头与电气验证未完成。'
        elif name=='StopSignalRoute':
            obj.EvidenceBasis='BOOT GPIO0/GND的Ø2.8空间预算；上段包含于15芯Ø10总预算；末端在X60/Y6/Z194，板内末段待实物确认。'
        elif '0.55：' not in obj.EvidenceBasis:obj.EvidenceBasis+=note
    doc.recompute()
    return dict(revision=REVISION,conductor_count=15,net_diameter_mm=10,
        separate_grommets_removed=True,existing_seat_diameter_mm=12.6,
        neck_bridge=dict(bore_mm=10,outer_mm=12.4,z_mm=[107,109]),
        head_points_mm=HEAD_POINTS,head_centreline_bend_radius_mm=10,
        chassis_endpoint_mm=[0,6,84],
        tray_clearance_diameter_mm=10.6,board_endpoint_mm=[60,6,194],
        boot_points_mm=boot_points,boot_included_in_total=True,
        boot_routed_length_mm=doc.StopSignalRoute.Shape.Volume/(math.pi*1.4**2),
        connector_passage_verified=False,physical_fit_verified=False,
        scope='Lower route begins at an existing allocation, not at verified battery/MOS terminals; upper route ends outside the board envelope.')


def overlaps(shape,objects,exclude=()):
    hits=[]
    for obj in objects:
        if obj.Name in exclude or not shape.BoundBox.intersect(obj.Shape.BoundBox):continue
        volume=shape.common(obj.Shape).Volume
        if volume>.01:hits.append(dict(object=obj.Name,volume_mm3=volume))
    return hits


def check(doc):
    physical=[o for o in doc.Objects if hasattr(o,'Category') and o.Category!='clearance']
    passage=corridor()
    obstacles=[o for o in physical if o.Name!='PowerCableRoute']
    static={n:overlaps(doc.getObject(n).Shape,physical,[n]) for n in CHANGED if n!='StopSignalRoute'}
    clear=overlaps(passage,obstacles)
    oversize=corridor(5.1)
    controls={n:oversize.common(doc.getObject(n).Shape).Volume>.01
              for n in ('NeckCableBridge',)}
    from breadboard_layout import check as check_tray
    from boot_button import check as check_boot
    tray=check_tray(doc);boot=check_boot(doc)
    shapes={n:dict(valid=doc.getObject(n).Shape.isValid(),solids=len(doc.getObject(n).Shape.Solids)) for n in CHANGED}
    board=doc.BreadboardEnvelope.Shape
    return dict(net_diameter_mm=10,static_overlaps=static,continuous_corridor_overlaps=clear,
        negative_control_10_2_mm_blocked=controls,shapes=shapes,
        tray=tray,boot=boot,board_clearance_mm=passage.distToShape(board)[0],
        tray_clearance_mm=passage.distToShape(doc.ElectronicsTray.Shape)[0],
        passed=not clear and not any(static.values()) and all(controls.values())
            and all(s['valid'] for s in shapes.values()) and tray['passed'] and boot['passed'],
        limits='Continuous geometric swept corridor and rigid maintenance checks only; flexible threading, wall strength, connectors and electrical operation remain unverified.')
