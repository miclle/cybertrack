"""External BOOT button candidate: unselected hardware, nominal geometry only."""
import math
import FreeCAD as App
import Part
from refine_assembly import box
from water_gun_mount import rounded_route

V = App.Vector
CENTER = (-36., -22., 114.)
POINTS = [(-36,-22,102),(-36,22,102),(-36,22,113),(0,22,113),
          (0,6,113),(0,6,170),(0,19,170),(0,19,190)]
RADIUS, BEND = 1.4, 4.
NAMES = ('StopControl', 'StopBody', 'StopNut', 'StopSignalRoute')
BASIS = ('未选型的常开自复位无灯按钮设计预算，不是厂商参数：杆径7、杆下深10、'
         '法兰Ø10×1.5、按帽Ø8×3、螺母对边10×厚2 mm；'
         '配合螺纹、行程、端子、密封及实物尺寸待核；GPIO0/GND仅为软件停止')


def cyl(r, z0, z1, x=CENTER[0], y=CENTER[1]):
    return Part.makeCylinder(r, z1-z0, V(x,y,z0))


def hexagon(z0, z1):
    # Across flats 10; flats at X = centre +/- 5.
    r=5/math.cos(math.pi/6)
    p=[V(CENTER[0]+r*math.cos(math.radians(30+60*i)),
         CENTER[1]+r*math.sin(math.radians(30+60*i)),z0) for i in range(6)]
    return Part.Face(Part.makePolygon(p+[p[0]])).extrude(V(0,0,z1-z0))


def finger():
    # Horizontal fingertip from the front, swept down 1.5 mm. Vertical approach
    # is obstructed by the fixed neck bearing; do not silently shorten that test.
    x,y,_=CENTER
    parts=[Part.makeCylinder(6,36,V(x,y-36,h),V(0,1,0)) for h in (123,124.5)]
    parts += [Part.makeSphere(6,V(x,y,h)) for h in (123,124.5)]
    parts += [box(x-6,y-36,123,x+6,y,124.5),cyl(6,123,124.5)]
    return parts[0].multiFuse(parts[1:]).removeSplitter()


def apply(doc, add):
    x,y,z=CENTER
    # Reuse the shoulder region, fuse the seat into the beam, and remove the
    # formerly unattached decorative plinth. Open rear gives nut/terminal access.
    mount=doc.StopPlinth.Shape.fuse(box(-43,-30,96,-29,-14,114))
    mount=mount.cut(box(-41.2,-28,99,-30.8,-13,112))
    mount=mount.cut(cyl(3.65,111,115))
    for y0,y1 in ((-15.5,-14),):
        mount=mount.fuse(box(-43,y0,114,-29,y1,119.5))
    saddle=box(-43,-16,99,-29,-6,100.5)
    for xx in (-40,-32):
        saddle=saddle.cut(box(xx-1.5,-11,98,xx+1.5,-9.5,101))
    mount=mount.fuse(saddle).removeSplitter()
    shoulder=doc.ShoulderRailR
    shoulder.Shape=shoulder.Shape.fuse(mount).removeSplitter()
    assert shoulder.Shape.isValid() and len(shoulder.Shape.Solids)==1
    shoulder.EvidenceBasis += '；0.54一体BOOT按钮座、后开口螺母腔、护边和扎带鞍座；候选尺寸'
    doc.removeObject('StopPlinth')
    doc.StopControl.Shape=cyl(4,115.5,118.5)
    doc.StopControl.Label='BOOT停止按钮／按帽候选'
    doc.StopControl.EvidenceBasis=BASIS
    body=cyl(3.5,104,114).fuse(cyl(5,114,115.5))
    add('StopBody','BOOT停止按钮／杆体法兰候选',body,'component','dark',BASIS)
    add('StopNut','BOOT停止按钮／后插防转螺母候选',hexagon(110,112).cut(cyl(3.5,109,113)),
        'component','metal',BASIS+'；仅画螺纹大径包络，不模拟螺纹咬合')
    obj=add('StopSignalRoute','BOOT停止按钮／GPIO0与GND双线走廊',
            rounded_route(POINTS,RADIUS,BEND),'clearance','signal',
            'Ø2.8双线空间预算／R4弯曲假设；中央段包含于现有Ø6线束预算，不能相加视为已容纳；'
            '末端停在托盘后槽，面包板内部针位与余量未建模；不是实物导线或护管')
    obj.addProperty('App::PropertyString','InterfaceStatus','Evidence')
    obj.InterfaceStatus='GPIO0/GND logical endpoints; terminal-to-route and in-board tails require actual hardware'
    doc.BubbleGunStopAccess.Shape=finger()
    doc.BubbleGunStopAccess.Label='BOOT按钮Ø12指端从前方接近及1.5 mm按压预算'
    doc.recompute()
    return dict(revision='0.54',centre_xyz_mm=CENTER,old_centre_xyz_mm=[-35,-22,100],
                location='right inner shoulder; 1 mm outward, flange 14 mm above former cap base',
                seat='integral ShoulderRailR; former StopPlinth removed',
                mounting_hole_mm=7.3,panel_thickness_mm=2,guard_top_z_mm=119.5,
                nut_across_flats_mm=10,nut_thickness_mm=2,rear_pocket_width_mm=10.4,
                strap_slots_mm=[3,1.5],button_press_assumed_mm=1.5,
                wire_route_points_mm=POINTS,wire_corridor_diameter_mm=2*RADIUS,
                minimum_centreline_bend_assumed_mm=BEND,
                routed_length_mm=doc.StopSignalRoute.Shape.Volume/(math.pi*RADIUS**2),
                shared_trunk='PowerCableRoute; BOOT pair included within the existing diameter-6 allocation',
                board_endpoint='rear tray opening at (0,19,190); final GPIO0/GND tails not geometrically resolved',
                hardware_selected=False,physical_fit_verified=False,electrical_verified=False)


def check(doc):
    physical=[o for o in doc.Objects if hasattr(o,'Category') and o.Category!='clearance']
    def hits(shape,exclude=()):
        overlaps=[];pairs=0
        for o in physical:
            if o.Name in exclude or not shape.BoundBox.intersect(o.Shape.BoundBox):continue
            pairs+=1;volume=shape.common(o.Shape).Volume
            if volume>.01:overlaps.append(dict(object=o.Name,volume_mm3=volume))
        return dict(passed=not overlaps,overlaps=overlaps,boolean_pairs=pairs)
    static={n:hits(doc.getObject(n).Shape,[n]) for n in NAMES[:3]}
    operation=hits(finger(),['StopControl'])
    press=hits(cyl(4,114,118.5),['StopControl','StopBody'])
    route=hits(doc.StopSignalRoute.Shape,['PowerCableRoute'])
    # Source and delivery contain derived unions too; avoid duplicate geometry.
    shared=doc.StopSignalRoute.Shape.common(doc.PowerCableRoute.Shape).Volume
    # The body is unscrewed from the captive nut after its wires are disconnected.
    extraction=hits(cyl(3.5,104,126).fuse(cyl(5,114,127.5)).fuse(cyl(4,115.5,130.5)),NAMES[:3])
    forward=hits(box(-39.5,-55.5,116,-32.5,-18.5,126)
                 .fuse(box(-41,-57,126,-31,-17,127.5))
                 .fuse(box(-40,-56,127.5,-32,-18,130.5)),NAMES[:3])
    # Enclose every nut pose along a straight rearward extraction after body removal.
    nut_sweep=box(-41,-27.774,110,-31,3.774,112)
    nut_removal=hits(nut_sweep,NAMES[:3])
    too_large=cyl(4,104,114).common(doc.ShoulderRailR.Shape).Volume>.01
    nut_rot=doc.StopNut.Shape.copy();nut_rot.rotate(V(CENTER[0],CENTER[1],0),V(0,0,1),30)
    anti_rotation=nut_rot.common(doc.ShoulderRailR.Shape).Volume>.01
    wide_finger=cyl(8,117,148.5).common(doc.ShoulderRailR.Shape).Volume>.01
    # Cable reaches head without entering the liquid containers or the HV corridors.
    routes=[o for o in doc.Objects if o.Name.startswith('IgnitionRoute')]
    hv_distance=min(doc.StopSignalRoute.Shape.distToShape(o.Shape)[0] for o in routes)
    negatives=dict(oversize_shank_blocked=too_large,nut_30deg_rotation_blocked=anti_rotation,
                   oversize_finger_hits_guard=wide_finger)
    result=dict(static=static,finger_approach_and_press=operation,cap_travel=press,
                wiring=route,intentional_shared_bundle_overlap_mm3=shared,
                body_upward_12mm_removal=extraction,body_forward_30mm_removal=forward,nut_rearward_removal=nut_removal,
                nearest_ignition_corridor_mm=hv_distance,negative_controls=negatives,
                physical_fit_verified=False,electrical_verified=False,
                limits='Candidate hardware only. Thread disengagement, whole hand, solder tails, board-internal routing, harness packing, EMC and actual flex/retention unverified.')
    result['passed']=all(r['passed'] for r in list(static.values())+[operation,press,route,extraction,forward,nut_removal]) and all(negatives.values()) and shared>0
    return result


def render(doc,out):
    import FreeCADGui as Gui
    from PySide import QtGui
    from pathlib import Path
    state={o.Name:(o.ViewObject.Visibility,o.ViewObject.Transparency) for o in doc.Objects if hasattr(o,'Category')}
    view=Gui.activeDocument().activeView()
    try:
        for filename,kind in [('boot-button-seat.png','seat'),('boot-button-route.png','route')]:
            for o in doc.Objects:
                if not hasattr(o,'Category'):continue
                o.ViewObject.Visibility=o.Name in NAMES or o.Name=='ShoulderRailR'
                if kind=='route':
                    o.ViewObject.Visibility |= o.Name.startswith('Neck') or o.Name in ('PrintNeck','HeadShell','ElectronicsTray','BreadboardEnvelope','HeadCableGrommet','NeckCableBridge','PowerCableRoute','PowerSwitchBody','PowerSwitchLever','KeelLid')
                    o.ViewObject.Transparency=85 if o.Name in ('HeadShell','BreadboardEnvelope','KeelLid') else 0
                o.ViewObject.Visibility=bool(o.ViewObject.Visibility)
            doc.StopSignalRoute.ViewObject.ShapeColor=(.15,.8,.85)
            doc.StopSignalRoute.ViewObject.Visibility=kind=='route'
            view.setCameraOrientation(App.Rotation(V(-1,1,0),V(-1,-1,3),V(1,1,.75),'ZXY').Q)
            view.fitAll()
            for _ in range(5):QtGui.QApplication.processEvents()
            view.saveImage(str(Path(out)/filename),1600,1200,'White')
    finally:
        for n,(visible,transparency) in state.items():
            doc.getObject(n).ViewObject.Visibility=visible;doc.getObject(n).ViewObject.Transparency=transparency
