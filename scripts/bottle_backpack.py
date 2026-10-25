"""Two user-specified 150 mL bottles; conservative capped cylinders, not liquid solids.

Bottle geometry beyond OD/overall height, foam compression, threads, venting,
liquid sealing and physical retention are unverified. No purchased asset is cut.
"""
import hashlib
import json
from pathlib import Path
import FreeCAD as A
import Part
V=A.Vector
RADIUS=24.4
HEIGHT=114.0
BOTTOM=40.0
Y=65.0
CENTRES=(('Water',28.0),('Bubble',-28.0))
SHELL_TOP=124.0
BASIS='用户指定150 mL成品瓶，最大外包络暂按Ø48.8×114含盖；瓶肩／瓶盖／公差未测；固定和软垫为候选'
TOL=.01

def box(x0,y0,z0,x1,y1,z1):
    return Part.makeBox(x1-x0,y1-y0,z1-z0,V(x0,y0,z0))

def cyl(r,z0,z1,x,y=Y):
    return Part.makeCylinder(r,z1-z0,V(x,y,z0))

def ring(ro,ri,z0,z1,x,y=Y):
    return cyl(ro,z0,z1,x,y).cut(cyl(ri,z0,z1,x,y))

def component():
    """Create the independently managed bottle envelope once, then read-only verify."""
    folder=Path(__file__).resolve().parents[1]/'hardware/components/bottle-150ml'
    folder.mkdir(exist_ok=True)
    cad=folder/'Bottle150ml-envelope.FCStd';step=folder/'Bottle150ml-envelope.step'
    expected=Part.makeCylinder(RADIUS,HEIGHT)
    if not cad.exists():
        d=A.newDocument('Bottle150ml')
        o=d.addObject('Part::Cylinder','BottleEnvelope');o.Radius=RADIUS;o.Height=HEIGHT
        o.Label='150 mL成品瓶完整外包络／含盖Ø48.8×114'
        o.addProperty('App::PropertyString','EvidenceBasis','Evidence');o.EvidenceBasis=BASIS
        o.addProperty('App::PropertyInteger','NominalCapacityML','Evidence');o.NominalCapacityML=150
        d.recompute();d.saveAs(str(cad));Part.export([o],str(step));A.closeDocument(d.Name)
    assert step.exists(),'Existing bottle native file has no STEP; inspect before replacing'
    d=A.openDocument(str(cad));shape=d.getObject('BottleEnvelope').Shape.copy();A.closeDocument(d.Name)
    imported=Part.Shape();imported.read(str(step))
    rows=[]
    for kind,q in (('FCStd',shape),('STEP',imported)):
        delta=expected.cut(q).Volume+q.cut(expected).Volume
        rows.append({'format':kind,'valid':q.isValid(),'solids':len(q.Solids),'symmetric_difference_mm3':delta,
                     'passed':q.isValid() and len(q.Solids)==1 and delta<1e-5})
    report={'source':'user specified product dimensions on 2026-10-25; not independently measured',
            'diameter_mm':48.8,'height_with_cap_mm':114,'nominal_capacity_ml':150,
            'local_axes':'cylinder axis +Z, bottom centre origin; no scale',
            'cap_neck_shoulder_and_material_known':False,'saved_and_reopened':True,'checks':rows,
            'files_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (cad,step)},
            'passed':all(r['passed'] for r in rows),'physical_fit_verified':False}
    (folder/'readback.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    assert report['passed'],report
    return shape,report


def apply(doc,add):
    source_shape,source_report=component()
    # Replace only the old wet-bay concept, preserving all other assemblies.
    old={'WaterModule','BubbleModule','BackpackShell','BackpackSpine','RearBaseArmor','RearLowerInset'}
    for name,_ in CENTRES:
        old.update(name+s for s in ('Pod','PodCap','ServiceLid','CapGrip','LidMark','FillPlug','FillSeal'))
    for o in list(doc.Objects):
        if o.Name in old or o.Name.startswith(('PackFrame','PackInset','PackLouver','PackMark','FillInsert','FillScrew')):
            doc.removeObject(o.Name)
    def feature(name,label,shape,category='structure',color='dark'):
        return add(name,label,shape.removeSplitter(),category,color,BASIS)
    # Widen only the rear wet bay. The rear wet bulkhead and all drive interfaces stay.
    wet=box(-58,28,34,58,96,160)
    tub=doc.getObject('LowerTub')
    tub.Shape=tub.Shape.cut(wet).fuse(box(-58,31.5,31,58,95,34)).cut(doc.getObject('WetDivider').Shape).removeSplitter()
    lid=doc.getObject('KeelLid');lid.Shape=lid.Shape.cut(wet).removeSplitter()
    # Low open sleeve: 84 mm above bottle bottom, not derived from label height.
    shell=box(-58,35,34,58,95,SHELL_TOP).cut(box(-55,38,33,55,92,SHELL_TOP+1))
    shell=shell.cut(box(-55,92,33,55,96,97))
    for sx in (-1,1):
        for yy,dy in ((35,1),(95,-1)):
            pts=[V(sx*58,yy,34),V(sx*55,yy,34),V(sx*58,yy+dy*3,34)]
            shell=shell.cut(Part.Face(Part.makePolygon(pts+[pts[0]])).extrude(V(0,0,SHELL_TOP-34)))
    for name,x in CENTRES:
        shell=shell.cut(box(x-14,91,100,x+14,96,SHELL_TOP+1))
    shell=shell.cut(doc.getObject('WetDivider').Shape)
    feature('BackpackShell','150 mL双瓶低位护舱／90 mm高／绑带操作缺口',shell,'exterior','body')
    feature('RearBaseArmor','双瓶背包下后护甲／X镜面对称',box(-55,92,34,55,95,97),'exterior','body')
    feature('BackpackSpine','背包后中央识别脊条',box(-3,95,50,3,97,SHELL_TOP),'exterior','metal')
    for name,x in CENTRES:
        label='清水' if name=='Water' else '泡泡液';color='water' if name=='Water' else 'bubble'
        bottle=source_shape.copy();bottle.translate(V(x,Y,BOTTOM))
        obj=feature(name+'Module',label+'成品瓶完整含盖包络 Ø48.8×114／150 mL',bottle,'envelope',color)
        obj.addProperty('App::PropertyString','SourceFile','Evidence');obj.SourceFile='hardware/components/bottle-150ml/Bottle150ml-envelope.FCStd'
        cup=cyl(26.4,34,39,x).fuse(ring(26.4,25.4,39,105,x))
        # Drain/inspection windows; retain four vertical rails and two pad seats.
        for z0,z1 in ((43,49),(61,89)):
            for dx,dy in ((-1,-1),(-1,1),(1,-1),(1,1)):
                xa,xb=sorted((x+dx*5,x+dx*28));ya,yb=sorted((Y+dy*5,Y+dy*28))
                cup=cup.cut(box(xa,ya,z0,xb,yb,z1))
        for side,sx in (('L',17),('R',-17)):
            xx=x+sx
            cup=cup.cut(cyl(1.7,33,40,xx)).cut(cyl(3,37,40,xx))
            tub.Shape=tub.Shape.cut(cyl(2.1,30,34,xx)).removeSplitter()
            feature(name+'PodInsert'+side,label+'底托M3嵌件候选',ring(2.1,1.5,31,34,xx),'structure','metal')
            screw=cyl(1.4,32,37,xx).fuse(cyl(2.8,37,39,xx))
            screw=screw.cut(box(xx-1.7,Y-.5,38,xx+1.7,Y+.5,40))
            feature(name+'PodScrew'+side,label+'底托M3候选沉孔螺钉',screw,'structure','metal')
        # Front guide captures a flexible 12 mm band without a printed lid.
        sector=box(x-6,Y-28,100,x+6,Y,123)
        guide=ring(26.4,25.8,100,122,x).common(sector)
        guide=guide.fuse(ring(26.4,24.4,106.5,107.5,x).common(sector))
        guide=guide.fuse(ring(26.4,24.4,120.5,122,x).common(sector))
        cup=cup.fuse(guide)
        feature(name+'Pod',label+'开窗底托／前部绑带导槽／双M3固定',cup)
        feature(name+'BottomPad',label+'底部软垫候选1 mm',cyl(24.4,39,40,x),'structure','accent')
        for i,(a,b) in enumerate(((50,60),(90,100))):
            feature(name+'SidePad'+str(i),label+'环形侧垫候选1 mm',ring(25.4,24.4,a,b,x),'structure','accent')
        feature(name+'RetentionBand',label+'可释放环绕绑带候选12×1／张紧防滑未验',ring(25.4,24.4,108,120,x),'structure','accent')
        closure=ring(26.2,25.4,108,120,x).common(box(x-10,Y,107,x+10,Y+30,121))
        closure=closure.fuse(box(x-6,90.5,116,x+6,96,118))
        feature(name+'StrapClosure',label+'魔术贴搭接及后拉片候选／非刚性卡扣',closure,'structure','dark')
        feature(name+'LidMark',label+'低位护舱识别条',box(x-8,95,96,x+8,95.6,99),'exterior',color)
        feature(name+'StrapAccessSpace',label+'后拉片20×23.8×20操作预留',box(x-10,96.2,104,x+10,120,124),'clearance','accent')
        feature(name+'BottleRemovalSpace',label+'整瓶向上150 mm连续抽出空间',cyl(RADIUS,40,304,x),'clearance',color)
        feature(name+'FingerSpace',label+'后侧指槽18×22.4×28预留',box(x-9,89.6,128,x+9,112,156),'clearance','accent')
        feature(name+'DipTubeSpace',label+'瓶内吸管Ø8候选通道／非瓶壁开孔',cyl(4,45,154.5,x),'clearance',color)
    doc.recompute()
    return {'component_readback':source_report,'capacity_ml_each':150,'quantity':2,'bottle_diameter_mm':48.8,'height_with_cap_mm':114,
            'basis':'user specified product dimensions, not independently measured; maximum diameter including cap assumed',
            'centres_xy_mm':[[x,Y] for _,x in CENTRES],'bottle_z_range_mm':[40,154],'shell_z_range_mm':[34,SHELL_TOP],
            'shell_height_mm':SHELL_TOP-34,'exposed_envelope_height_mm':154-SHELL_TOP,
            'retention':'releasable hook-and-loop band candidate, friction-based; holding force not verified',
            'physical_fit_verified':False,'manufacturing_released':False}

def check(doc):
    objects={o.Name:o for o in doc.Objects if hasattr(o,'Category')}
    physical={n:o.Shape for n,o in objects.items() if o.Category!='clearance'}
    def hits(shape,removed=()):
        bb=shape.optimalBoundingBox(False);out=[]
        for n,q in physical.items():
            if n in removed or not bb.intersect(q.optimalBoundingBox(False)):continue
            v=shape.common(q).Volume
            if v>TOL:out.append({'fixed':n,'volume_mm3':v})
        return out
    rows=[]
    for name,x in CENTRES:
        own_hose='WaterHoseRoute' if name=='Water' else 'BubbleGunHoseRoute'
        other_hose='BubbleGunHoseRoute' if name=='Water' else 'WaterHoseRoute'
        bottle=physical[name+'Module']
        straps=[name+'RetentionBand',name+'StrapClosure']
        remove=straps+[own_hose]
        sweep=cyl(RADIUS,40,304,x)
        collisions=hits(sweep,remove+[name+'Module'])
        connected=hits(sweep,straps+[name+'Module'])
        blocked=any(h['fixed']==own_hose for h in connected)
        finger=hits(objects[name+'FingerSpace'].Shape,remove)
        release=hits(objects[name+'StrapAccessSpace'].Shape)
        static=hits(bottle,[name+'Module'])
        tools=[]
        for side,sx in (('L',17),('R',-17)):
            screw=name+'PodScrew'+side;xx=x+sx
            cleared=remove+[name+'Module',name+'BottomPad',screw]
            swept=cyl(1.4,32,57,xx).fuse(cyl(2.8,37,59,xx))
            tools.append({'screw':screw,'removed_first':cleared,
                'tool_overlaps':hits(cyl(2,39,210,xx),cleared),
                'removal_overlaps':hits(swept,cleared)})
        def contact(a,b,z):
            faces=lambda q:[f for f in q.Faces if abs(f.BoundBox.ZMin-z)<1e-6 and abs(f.BoundBox.ZMax-z)<1e-6]
            return sum(f.common(g).Area for f in faces(a) for g in faces(b))
        interfaces={'pod_to_floor_mm2':contact(physical[name+'Pod'],physical['LowerTub'],34),
                    'bottom_pad_to_bottle_mm2':contact(physical[name+'BottomPad'],bottle,40)}
        b=bottle.optimalBoundingBox(False)
        row={'bottle':name,'dimensions_mm':[b.XLength,b.YLength,b.ZLength],'static_overlaps':static,
             'bottle_removal':{'method':'exact vertical cylinder sweep, 150 mm upward','removed_first':remove,
                'opposite_bottle_and_hose_retained':True,'opposite_hose_distance_mm':sweep.distToShape(physical[other_hose])[0],
                'overlaps':collisions,'own_connected_hose_blocks_removal':blocked},
             'rear_finger_space_overlaps':finger,'strap_release_access_overlaps':release,'pod_screws_and_tools':tools,
             'nominal_support_contact_areas':interfaces,
             'retention':'band tension and friction, not a geometric upward stop; flexible peeling/parking and holding force unverified'}
        row['passed']=not(static or collisions or finger or release) and blocked and all(not(t['tool_overlaps'] or t['removal_overlaps']) for t in tools) and min(interfaces.values())>100 and max(abs(a-b) for a,b in zip(row['dimensions_mm'],[48.8,48.8,114]))<1e-5
        rows.append(row)
    forbidden=[n for n in objects if n in [k+s for k,_ in CENTRES for s in ('ServiceLid','TopPad','CapGrip','CapToolL','CapToolR')] or n.startswith(('FillScrew','FillInsert'))]
    sb=physical['BackpackShell'].optimalBoundingBox(False)
    return {'revision':'0.36','tolerance_mm3':TOL,'bottles':rows,'shell_height_mm':sb.ZLength,
            'shell_z_range_mm':[sb.ZMin,sb.ZMax],'exposed_bottle_envelope_height_mm':154-sb.ZMax,
            'removed_lid_hardware_remaining':forbidden,
            'passed':all(r['passed'] for r in rows) and not forbidden and abs(sb.ZLength-90)<1e-5,
            'capacity_source':'150 mL from product image; 48.8 is lower diameter, maximum capped envelope remains provisional',
            'service_prerequisite':'power off; withdraw and park only the target hose; peel/open and park only the target band; lift target bottle 150 mm; opposite bottle/hose stay installed; refill off robot',
            'no_tools_for_routine_refill_design_intent':True,
            'physical_retention_seal_venting_material_fit_verified':False,'manufacturing_released':False}


def render(doc,output):
    import FreeCADGui as G
    from PySide import QtGui
    objects=[o for o in doc.Objects if hasattr(o,'Category')]
    saved={o.Name:(o.Shape.copy(),o.ViewObject.Visibility,o.ViewObject.Transparency) for o in objects}
    view=G.activeDocument().activeView();camera=view.getCameraOrientation()
    def picture(name):
        doc.recompute();view.setCameraOrientation(A.Rotation(V(-1,1,0),V(-1,-1,3),V(1,1,.75),'ZXY').Q);view.fitAll()
        for _ in range(10):QtGui.QApplication.processEvents()
        view.saveImage(str(output/name),1600,1200,'White')
    wetnames={n for n in saved if n.startswith(('WaterPod','BubblePod','Backpack','RearBaseArmor'))}
    for name,_ in CENTRES:
        wetnames.update(name+s for s in ('Module','BottomPad','SidePad0','SidePad1','RetentionBand','StrapClosure','LidMark',
                                         'BottleRemovalSpace','FingerSpace','DipTubeSpace','StrapAccessSpace'))
    try:
        for o in objects:
            o.ViewObject.Visibility=o.Name in wetnames and o.Category!='clearance'
            o.ViewObject.Transparency=85 if o.Name in ('BackpackShell','RearBaseArmor') else 55 if o.Name in ('WaterModule','BubbleModule') else 0
        picture('bottle-backpack-layout.png')
        # Show independent water-bottle service, with the other hose explicitly retained.
        for o in objects:
            if o.Name in ('WaterRetentionBand','WaterStrapClosure'):o.ViewObject.Visibility=False
            if o.Name=='BubbleGunHoseRoute':o.ViewObject.Visibility=True;o.ViewObject.Transparency=0
            if o.Name=='WaterModule':q=o.Shape.copy();q.translate(V(0,0,150));o.Shape=q
        picture('bottle-backpack-service.png')
        for o in objects:
            o.Shape=saved[o.Name][0]
            o.ViewObject.Visibility=o.Name in wetnames
            o.ViewObject.Transparency=90 if o.Category=='clearance' else 85 if o.Name in ('BackpackShell','RearBaseArmor') else 55 if o.Name in ('WaterModule','BubbleModule') else 0
        picture('bottle-backpack-spaces.png')
    finally:
        for o in objects:
            shape,vis,tr=saved[o.Name];o.Shape=shape;o.ViewObject.Visibility=vis;o.ViewObject.Transparency=tr
        doc.recompute();view.setCameraOrientation(camera.Q);view.fitAll()
