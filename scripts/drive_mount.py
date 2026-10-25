"""Drive interfaces at the retained +/-14 mm lateral translation.

Local interfaces reproduce the reference: four-mm motor face, six PCD31 holes
(four complete seats), 13-mm downward channel and the TrackMount screw seats.
The connecting housing and independent service covers belong to CyberTrack.
All fasteners are non-threaded candidates, not supplier-selected hardware.
"""
import math
import FreeCAD as App
import Part
V=App.Vector
SHIFT=14.0
FACE=73.0
AXIS=57.0
CENTER=50.0
HOLES=[(15.5*math.cos(i*math.pi/3),50+15.5*math.sin(i*math.pi/3)) for i in range(6)]
COVER_POINTS=[(22.5,-16),(22.5,16),(64,-22),(64,22)]


def box(x0,y0,z0,x1,y1,z1):
    return Part.makeBox(x1-x0,y1-y0,z1-z0,V(x0,y0,z0))


def cx(r,x0,x1,y,z):
    return Part.makeCylinder(r,x1-x0,V(x0,y,z),V(1,0,0))


def cz(r,z0,z1,x,y):
    return Part.makeCylinder(r,z1-z0,V(x,y,z0))


def union(parts):
    return parts[0].multiFuse(parts[1:]).removeSplitter() if len(parts)>1 else parts[0]


def side_shape(shape,sign):
    return shape.copy() if sign>0 else shape.mirror(V(),V(1,0,0))


def motor_loading_tools():
    return [box(48.5,-19.1,-60,73,19.1,50),
            box(25.7,-16.6,-60,49.5,16.6,50),
            box(73,-6.5,-60,95.5,6.5,57)]


def motor_interface():
    # End-face outline and posts match the reference's functional adapter.
    plate=union([cx(22,73,77,0,50),box(73,-28.1,30.4,77,28.1,44.4),
                 cx(7,73,77,-28.1,37.4),cx(7,73,77,28.1,37.4)])
    plate=union([plate]+[cx(5.5,76.9,87,y,37.4) for y in (-28.1,28.1)])
    cuts=[cx(6.5,72.9,87.1,0,57),box(73,-6.5,-60,95.5,6.5,57)]
    cuts += [cx(1.7,72.9,87.1,y,z) for y,z in HOLES]
    cuts += [cx(1.7,72.9,87.1,y,37.4) for y in (-28.1,28.1)]
    cuts += [cx(2.9,72.9,76,y,37.4) for y in (-28.1,28.1)]
    return plate.cut(Part.makeCompound(cuts)).removeSplitter()


def track_screw(y):
    return cx(2.7,73.2,76,y,37.4).fuse(cx(1.5,76,102,y,37.4)).removeSplitter()


def motor_screw(y,z):
    # 2 mm represented engagement in the reference's 3 mm blind-hole envelope.
    head=cx(2.7,77,79.8,y,z).cut(cx(1.1,78.3,79.9,y,z))
    return head.fuse(cx(1.4,71,77,y,z)).removeSplitter()


def widen_lower_tub(shape):
    """132 mm lower width; upper rear wall returns to +/-48 at Z76.

    Preserve the existing upper silhouette and battery datum while replacing
    the lower narrow sides with a 3-mm lateral wall allowance.
    """
    def prism(points,y0,y1):
        vs=[V(x,y0,z) for x,z in points]
        return Part.Face(Part.makePolygon(vs+[vs[0]])).extrude(V(0,y1-y0,0))
    outer=prism([(45,28),(66,28),(66,48),(48,76),(45,76)],-19,74)
    inner=prism([(45,31),(63,31),(63,48),(45,76)],-19,71)
    bridge=box(63,-23,28,66,-19,48)
    rear_join=box(44,71,28,45.1,74,76)
    shape=union([shape,outer,side_shape(outer,-1),bridge,side_shape(bridge,-1),rear_join,side_shape(rear_join,-1)])
    shape=shape.cut(inner).cut(side_shape(inner,-1))
    shape=shape.cut(box(-61,-97,26,61,-22,32))
    return shape.removeSplitter()


def apply(doc,add):
    tub=widen_lower_tub(doc.getObject('LowerTub').Shape.copy())
    # Replace the four separate ears by the integral functional interface.
    for n in ['MountEar'+s+e for s in ('L','R') for e in ('Front','Rear')]:
        if doc.getObject(n):doc.removeObject(n)
    # Upper cylindrical housing and low front/rear webs bridge into the tub.
    roof=cx(22,46.5,73,0,50).common(box(46,-23,50,74,23,73))
    housing=union([roof,cx(7,65.5,73,-28.1,37.4),cx(7,46.5,73,28.1,37.4),
                   box(46.5,19.1,31,73,23,50)])
    cavity=union([cx(19.1,48.5,73,0,50),cx(16.6,25.7,49.5,0,50)])
    housing=housing.cut(cavity)
    local=union([motor_interface(),housing])
    covers=[];fixed=[]
    for side,sign in [('L',1),('R',-1)]:
        # Thin lower floor plus four raised clamping lands, 0.2 mm seam elsewhere.
        panel=box(25.7,-19.1,28,67.3,31.3,30.8)
        tabs=[cz(3,28,38,x,y) for x,y in COVER_POINTS]
        # Flat necks join the inner pads and outer front pads to the cover floor.
        necks=[box(22.5,-19,28,27,19,30.8),box(61,-26,28,67.3,23,30.8)]
        cover=union([panel]+tabs+necks)
        for x,y in COVER_POINTS:
            cover=cover.cut(cz(1.7,27,39,x,y)).cut(cz(2.9,27,34,x,y))
        cover=cover.removeSplitter()
        # Land/boss arrangement follows the reference cover: diameter6,
        # clearance3.4, counterbore5.8, pilot2.6x8, seat34 and seam38.
        bosses=[cz(3,38,46,x,y) for x,y in COVER_POINTS]
        # Inner bosses join the tub floor through narrow webs beside the motor tail.
        bosses += [box(19.5,y-3,30.5,25.5,y+3,46) for y in (-16,16)]
        bosses += [box(61,y-3,38,67,y+3,46) for y in (-22,22)]
        fixed.append(side_shape(union([local]+bosses),sign))
        covers.append((side,sign,side_shape(cover,sign)))
    tub=union([tub]+fixed)
    cuts=[]
    for sign in (-1,1):
        tools=motor_loading_tools()+[cavity]
        # Open the floor beneath the motors and the rear screw loading column.
        tools += [box(25.5,-19.3,27.5,73,31.5,31.01),
                  box(37.3,25,-60,67,31.2,37.4)]
        # Front screw is loaded after the battery and its carrier are removed.
        tools += [box(37.3,-31.2,-60,67,-25,37.4),
                  box(60.8,-26.2,27.5,67.5,-19.1,31.01)]
        tools += [cx(3.1,25.5,73.1,y,37.4) for y in (-28.1,28.1)]
        tools += [cz(1.3,37.7,46,x,y) for x,y in COVER_POINTS]
        # The removable pads occupy the lower half of each clamping boss.
        tools += [cz(3.2,27.5,38,x,y) for x,y in COVER_POINTS]
        cuts += [side_shape(q,sign) for q in tools]
    tub=tub.cut(Part.makeCompound(cuts)).removeSplitter()
    # Seat reference cylinders have no material overlap with the covers.
    for side,sign,cover in covers:
        tub=tub.cut(cover).removeSplitter()
    doc.getObject('LowerTub').Shape=tub
    doc.getObject('LowerTub').Label='一体底盘／电机端面固定座与履带紧固通道'
    for side,sign,cover in covers:
        add('MotorServiceCover'+side,('左' if sign>0 else '右')+'电机底部独立检修盖',cover,'structure','dark',
            '本项目外形；沿用参考盖紧固孔径／承压面参数，公差及螺纹未验收')
        for i,(x,y) in enumerate(COVER_POINTS):
            screw=cz(2.7,31.2,34,x,y).fuse(cz(1.2,34,43.8,x,y))
            screw=screw.cut(cz(1.1,31.1,32.7,x,y)).removeSplitter()
            add('MotorCoverScrew'+side+str(i),'电机检修盖 M3 级示意螺钉 '+side+str(i),side_shape(screw,sign),'structure','metal',
                'Ø5.4×2.8头；非螺纹示意，最终规格／底孔工艺待试配')
        for end,y in [('Front',-28.1),('Rear',28.1)]:
            add('TrackMountScrew'+side+end,'履带安装件 M3 级固定螺钉 '+side+end,side_shape(track_screw(y),sign),'structure','metal',
                '沿用参考Ø5.4×2.8头、Ø3杆及4mm末端占位；接收螺纹和长度待实测')
        for i,(y,z) in enumerate(HOLES[:4]):
            add('MotorFaceScrew'+side+str(i),'电机端面 M3 级固定螺钉 '+side+str(i),side_shape(motor_screw(y,z),sign),'structure','metal',
                '仅四个完整座；螺纹省略，2mm啮合占位，最终长度／有效牙深待核')
    # The existing front wall window is too close to the gearbox loading margin.
    for n in ('FrontBulkhead','RearBulkhead'):
        obj=doc.getObject(n)
        obj.Shape=obj.Shape.cut(Part.makeCompound([side_shape(q,sign) for sign in (-1,1) for q in motor_loading_tools()+[cavity,box(37.3,25,-60,67,31.2,37.4)]+[cx(3.1,9.5,73.1,y,37.4) for y in (-28.1,28.1)]])).removeSplitter()
    doc.recompute()
    for n in ['LowerTub']+['MotorServiceCover'+s for s in ('L','R')]:
        q=doc.getObject(n).Shape
        if not q.isValid() or len(q.Solids)!=1:raise ValueError((n,q.isValid(),[(v.Volume,str(v.BoundBox)) for v in q.Solids]))


def render_drive_views(doc,output):
    import FreeCADGui as Gui
    from PySide import QtGui
    view=Gui.activeDocument().activeView()
    view.setAnimationEnabled(False);view.setCameraType('Orthographic')
    names={'LowerTub','MotorL','MotorR','MotorShaftL','MotorShaftR','TrackMountL','TrackMountR','DriveCouplerL','DriveCouplerR'}
    names.update(o.Name for o in doc.Objects if o.Name.startswith(('MotorServiceCover','MotorCoverScrew','MotorFaceScrew','TrackMountScrew')))
    def show():
        for o in doc.Objects:
            if hasattr(o,'Category'):o.ViewObject.Visibility=o.Name in names
    def save(name,rotation):
        view.setCameraOrientation(rotation.Q);view.fitAll()
        for _ in range(10):QtGui.QApplication.processEvents()
        view.saveImage(str(output/name),1600,1200,'White')
    iso=App.Rotation(V(1,1,0),V(-1,1,3),V(1,-1,.75),'ZXY')
    colors={n:doc.getObject(n).ViewObject.ShapeColor for n in names}
    doc.getObject('LowerTub').ViewObject.ShapeColor=(.44,.55,.61)
    for side in ('L','R'):doc.getObject('MotorServiceCover'+side).ViewObject.ShapeColor=(.25,.36,.43)
    show();save('drive-mount.png',iso)
    save('drive-bottom.png',App.Rotation(V(0,1,0),180))
    original={n:doc.getObject(n).Shape.copy() for n in names}
    for side,sign in [('L',1),('R',-1)]:
        for n in names:
            if n.startswith('MotorCoverScrew'+side):delta=V(0,0,-55)
            elif n=='MotorServiceCover'+side:delta=V(0,0,-25)
            elif n.startswith(('TrackMountScrew'+side,'MotorFaceScrew'+side)) or n in ('TrackMount'+side,'DriveCoupler'+side):delta=V(sign*45,0,0)
            else:continue
            q=original[n].copy();q.translate(delta);doc.getObject(n).Shape=q
    doc.recompute();save('drive-service.png',iso)
    for n,q in original.items():
        doc.getObject(n).Shape=q
        doc.getObject(n).ViewObject.ShapeColor=colors[n]
    doc.recompute()
    for o in doc.Objects:
        if hasattr(o,'Category'):o.ViewObject.Visibility=o.Category not in ('envelope','clearance')
    view.setCameraOrientation(iso.Q);view.fitAll()
