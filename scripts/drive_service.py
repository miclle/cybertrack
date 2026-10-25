"""0.32 integral motor mounting, open dry bay and retained rear wet bulkhead.

Retains drive interfaces and a unified bottom cover. Motor service now removes
the battery tray and the serviced track first; no detachable motor end plate.
"""
import FreeCAD as A
import Part
from drive_mount import V,box,cx,cz,union,side_shape,HOLES
COVER_POINTS=[(s*63,y) for s in (-1,1) for y in (-75,-55,37)]


def integrated_motor_face():
    q=box(73,-20.7,32,77,20.7,72)
    q=q.cut(cx(6.5,72.9,77.1,0,57)).cut(box(72.9,-6.5,27,77.1,6.5,57))
    for y,z in HOLES:q=q.cut(cx(1.7,72.9,77.1,y,z))
    return q.removeSplitter()


def fixed_frame():
    # Continuous side walls join the original track posts and the roof.
    walls=[box(63.2,y0,43,77,y1,67) for y0,y1 in [(-27,-20.7),(20.7,27)]]
    for sign in (-1,1):
        points=[V(63.2,sign*y,z) for y,z in [(20.7,67),(27,67),(21.2,72),(20.7,72)]]
        walls.append(Part.Face(Part.makePolygon(points+[points[0]])).extrude(V(13.8,0,0)))
    roof=box(60.8,-21.2,72,77,21.2,75)
    q=union(walls+[roof]).cut(cx(18.8,60.7,73.1,0,50))
    return q


def translated(q,delta):
    q=q.copy();q.translate(V(*delta));return q


def apply(doc,add):
    tub=doc.getObject('LowerTub').Shape.copy()
    # Remove the previous covers, their pilots/bosses and central access hardware.
    for o in list(doc.Objects):
        if o.Name.startswith(('MotorServiceCover','MotorCoverScrew','AccessInsert','AccessScrew')) or o.Name=='CableServiceCover':doc.removeObject(o.Name)
    # Clear former inner bosses and all floor ribs within the new service opening.
    tub=tub.cut(box(-67.5,-97,26.9,67.5,31.6,31.01))
    tub=tub.cut(box(-25.6,-19.1,30.9,25.6,19.1,46.1))
    # The battery remains supported independently of the one-piece outer cover.
    tray=box(-60.8,-96.8,31,60.8,-23.2,32.8).cut(box(-55,-90,30.9,55,-29,32.9))
    tray=tray.fuse(box(-55,-78,31,55,-74,32.8))
    for sign in (-1,1):
        for end,y in [('Front',-85),('Rear',-40)]:
            x=sign*63.5
            tray=tray.fuse(box(min(sign*60.5,sign*65.8),y-4,31,max(sign*60.5,sign*65.8),y+4,32.8))
            tray=tray.cut(cz(2.1,30.9,32.9,x,y))
            name='BatteryScrew'+('L' if sign>0 else 'R')+end
            screw=cz(1.25,30.5,35.7,x,y).fuse(cz(2.2,29,30.5,x,y)).cut(cz(1,28.9,30,x,y))
            doc.getObject(name).Shape=screw
            washer=cz(3.5,30.5,31,x,y).cut(cz(1.4,30.4,31.1,x,y))
            add('BatterySupportWasher'+('L' if sign>0 else 'R')+end,'电源内托架承压垫圈 '+('L' if sign>0 else 'R')+end,washer,'structure','metal','Ø7/Ø2.8×0.5候选垫圈；扩大螺钉头与内托架承压面积')
            # Existing insert starts at31.3; a shoulder seats the tray at32.8.
            tub=tub.cut(box(x-2.5,y-4.2,30.9,x+2.5,y+4.2,32.8))
    tray=tray.fuse(box(-3,-90,31,3,-23.2,32.8))
    for sign in (-1,1):tray=tray.cut(side_shape(box(54.8,-36,30.9,61,-29.6,32.9),sign))
    tray=tray.cut(doc.getObject('BatteryPullStrap').Shape)
    for o in doc.Objects:
        if o.Name.startswith('BatteryPad'):
            b=o.Shape.optimalBoundingBox(False);o.Shape=box(b.XMin,b.YMin,32.8,b.XMax,b.YMax,33)
            tray=tray.cut(o.Shape)
    for x,y in COVER_POINTS:tray=tray.cut(cz(3,30.9,32.9,x,y))
    doc.getObject('BatteryHatch').Shape=tray.removeSplitter();doc.getObject('BatteryHatch').Label='独立内部电源承托架／开底盖时保留'
    # No cross-bay beams: local motor walls connect directly into the tub sides.
    cutters=[]
    for sign in (-1,1):
        # Clear bottom access for the bare motor after its track and face screws are removed.
        cutters += [side_shape(box(-2.2,-18.8,0,73,18.8,69),sign),
                    side_shape(box(44.7,-20.9,0,77.2,20.9,72.3),sign),
                    side_shape(box(-4.3,-23,0,77.2,23,37),sign)]
        for y0,y1 in [(-20.9,-18.7),(18.7,20.9)]:
            cutters.append(side_shape(box(40.7,y0,0,77.2,y1,53.2),sign))
        # Clear historical face material before rebuilding the integral mounting wall.
        cutters.append(side_shape(cx(22.25,72.9,77.2,0,50),sign))
    tub=tub.cut(Part.makeCompound(cutters))
    tub=union([tub]+[side_shape(box(44.7,-21.2,72.3,73,21.2,75),sign) for sign in (-1,1)])
    for sign in (-1,1):
        tub=tub.fuse(side_shape(union([fixed_frame(),integrated_motor_face()]),sign))
    # Original track screw loading corridors remain open.
    for sign in (-1,1):
        for y in (-28.1,28.1):tub=tub.cut(side_shape(cx(3.1,9.5,73.1,y,37.4),sign))
    # Retain the existing connector; disconnect and park the lead for motor service.
    from refine_assembly import route
    doc.getObject('PowerCableRoute').Shape=route([(0,-14,50),(0,6,70),(0,6,142),(0,-5,142)],3).fuse(box(-10,-23,42,10,-5,58)).removeSplitter()
    doc.getObject('PowerCableRoute').Label='电源插头及中央线束／电机维护时拔下并移开'
    # One cover spanning former battery, connector and both motor openings.
    cover=box(-65.8,-96.8,26,65.8,40,28.8)
    for sign in (-1,1):
        for y in (-85,-40):cover=cover.cut(cz(2.5,28.8,30,sign*63.5,y))
    for i,(x,y) in enumerate(COVER_POINTS):
        boss=cz(2.8,28.8,38,x,y).cut(cz(1.3,28.7,36,x,y))
        tub=tub.fuse(boss)
        cover=cover.cut(cz(1.4,25.9,29,x,y)).cut(cz(2.4,25.9,28,x,y))
        screw=cz(2.2,26.5,28,x,y).fuse(cz(1.2,28,35.8,x,y)).cut(cz(.9,26.4,27.4,x,y))
        add('BottomCoverScrew'+str(i),'一体底盖 M2.5 级示意螺钉 '+str(i),screw,'structure','metal','6处底部固定；实际紧固工艺待验')
    # Clear all core holes after fusing bosses into the existing shell.
    tub=tub.cut(box(-66,-97,26.9,66,40.2,28.8))
    for x,y in COVER_POINTS:tub=tub.cut(cz(1.3,28.7,36,x,y))
    # Preserve a full downward route for the independent battery tray.
    tray_sweep=[tray]
    for face in tray.Faces:
        if isinstance(face.Surface,Part.Plane) and abs(face.normalAt(0,0).z)>.999:
            prism=face.extrude(V(0,0,-80))
            if prism.Solids:tray_sweep.append(prism)
    tub=tub.cut(Part.makeCompound(tray_sweep))
    for sign in (-1,1):
        for y in (-85,-40):tub=tub.cut(cz(3.7,30.4,31.1,sign*63.5,y))
    tub=tub.cut(box(-10.5,-23.1,41.5,10.5,-4.5,58.5))
    # Cut adjacent partitions by exactly the redesigned service envelope.
    for n in ('FrontBulkhead','RearBulkhead'):
        o=doc.getObject(n);o.Shape=o.Shape.cut(Part.makeCompound(cutters)).cut(tub).removeSplitter()
    doc.removeObject('FrontBulkhead')
    doc.removeObject('BatteryRoof')
    tub=tub.removeSplitter()
    doc.getObject('LowerTub').Shape=tub
    doc.getObject('LowerTub').Label='等宽一体底盘／电机固定面、开放干舱及底部检修'
    add('BottomServiceCover','一体底部检修盖／6颗螺钉',cover.removeSplitter(),'structure','dark','下表面Z26，较0.29低2mm；不承托充电宝或履带')
    doc.recompute()
    for o in doc.Objects:
        if hasattr(o,'Category') and o.Category=='structure' and (not o.Shape.isValid() or len(o.Shape.Solids)!=1):
            raise ValueError((o.Name,'invalid or disconnected',len(o.Shape.Solids)))


def render_drive_views(doc,output):
    import FreeCADGui as G
    from PySide import QtGui
    view=G.activeDocument().activeView();view.setAnimationEnabled(False);view.setCameraType('Orthographic')
    original={o.Name:(o.Shape.copy(),o.ViewObject.ShapeColor,o.ViewObject.Transparency) for o in doc.Objects if hasattr(o,'Category')}
    iso=A.Rotation(V(1,1,0),V(-1,1,3),V(1,-1,.75),'ZXY')
    names={'LowerTub','RearBulkhead','WetDivider','MotorL','MotorR','MotorShaftL','MotorShaftR','TrackMountL','TrackMountR','DriveCouplerL','DriveCouplerR','BatteryHatch','BottomServiceCover'}
    names.update(n for n in original if n.startswith(('MotorFaceScrew','TrackMountScrew','BottomCoverScrew','BatteryScrew')))
    def show():
        for n in original:doc.getObject(n).ViewObject.Visibility=n in names
    def save(name,rotation=iso):
        doc.recompute();view.setCameraOrientation(rotation.Q);view.fitAll()
        for _ in range(10):QtGui.QApplication.processEvents()
        view.saveImage(str(output/name),1600,1200,'White')
    doc.getObject('LowerTub').ViewObject.ShapeColor=(.44,.55,.61)
    doc.getObject('RearBulkhead').ViewObject.ShapeColor=(.17,.46,.56)
    doc.getObject('BottomServiceCover').ViewObject.ShapeColor=(.16,.36,.55)
    show();save('drive-mount.png');save('drive-bottom.png',A.Rotation(V(0,1,0),180))
    names.update(n for n in original if n.startswith('TrackRight'))
    names.difference_update({'BottomServiceCover','BatteryHatch','TrackMountL','DriveCouplerL'})
    names.difference_update(n for n in original if n.startswith(('BottomCoverScrew','MotorFaceScrewL','TrackMountScrewL','BatteryScrew')))
    for n in ('MotorL','MotorShaftL'):doc.getObject(n).Shape=translated(original[n][0],(0,0,-80))
    doc.getObject('MotorL').ViewObject.ShapeColor=(.95,.35,.08)
    doc.getObject('LowerTub').ViewObject.Transparency=45
    show();save('drive-service.png',A.Rotation(V(1,1,0),V(-1,1,3),V(1,-1,.2),'ZXY'))
    doc.getObject('LowerTub').ViewObject.Transparency=0
    names={'LowerTub','RearBulkhead','WetDivider'};show();save('drive-frame.png',iso)
    names={'LowerTub'}|{n for n in original if n.startswith('MotorFaceScrewL')}
    doc.getObject('LowerTub').Shape=original['LowerTub'][0].common(box(60,-35,27,88,35,78))
    for n in names:
        if n.startswith('MotorFaceScrew'):doc.getObject(n).ViewObject.ShapeColor=(.92,.12,.06)
    show();save('drive-integrated-face.png',A.Rotation(V(1,1,0),V(-1,1,3),V(1,-1,-.35),'ZXY'))
    for n,(shape,color,trans) in original.items():
        o=doc.getObject(n);o.Shape=shape;o.ViewObject.ShapeColor=color;o.ViewObject.Transparency=trans;o.ViewObject.Visibility=o.Category not in ('envelope','clearance')
    doc.recompute();view.setCameraOrientation(iso.Q);view.fitAll()
