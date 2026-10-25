"""0.42 passive backpack body clamps and chassis effect-board carrier.

Contact, pads, M2.5-class hardware and actual boards remain candidates. This
module defines no HV wiring, electrode, drive, insulation or protective rating.
"""
import FreeCAD as A
import Part
from breadboard_layout import box
from ultrasonic_integration import inspect as inspect_exact,box_sweep,bounds
V=A.Vector
MOUNTS=[(x,y) for x in (-39,39) for y in (-49,-29)]
PREFIXES=('BackpackArc','ArcClamp','ArcLiner','ArcBottomPad','ArcInsert','ArcScrew','ArcTool','Effect')


def inspect(shape,obstacles):
    # Conservative broad phase retains every possible overlap and every <5 mm
    # neighbour reported by inspect_exact; avoid expensive distant BRep queries.
    nearby=A.BoundBox(shape.BoundBox);nearby.enlarge(5.01)
    return inspect_exact(shape,{n:s for n,s in obstacles.items() if nearby.intersect(s.BoundBox)})


def mirror(shape,sign):
    if sign>0:return shape
    matrix=A.Matrix();matrix.A11=-1
    return shape.transformGeometry(matrix)


def zc(r,z0,z1,x,y):return Part.makeCylinder(r,z1-z0,V(x,y,z0))
def xc(r,x0,x1,y,z):return Part.makeCylinder(r,x1-x0,V(x0,y,z),V(1,0,0))
def ring(ro,ri,z0,z1):return zc(ro,z0,z1,74,85).cut(zc(ri,z0-.1,z1+.1,74,85))


def apply(doc,add):
    fixed=doc.getObject('BackpackShell').Shape.copy()
    lid=doc.getObject('KeelLid').Shape.copy()
    def put(n,label,s,category='structure',color='metal',basis=None):
        return add(n,label,s.removeSplitter(),category,color,basis or '0.42机械候选；夹持面、材料、标准件规格与实物配合待核，不是绝缘或安全外壳')
    for side,sign in [('L',1),('R',-1)]:
        put('BackpackArc'+side,'背包外侧本体候选 Ø25.5×70 '+side,zc(12.75,54,124,sign*74,85),'envelope','accent',
            '历史用户规划Ø25.5×70，非实测；不含端部、引线、电极、驱动、绝缘或屏蔽验收')
        spine=box(57,81,51.5,60.5,89,118).fuse(box(57,81,51.5,80,89,53))
        put('ArcBottomPad'+side,'本体底托1 mm软垫候选 '+side,mirror(box(68,81,53,80,89,54),sign),'structure','dark')
        for i,z in enumerate((86,114)):
            collar=ring(15.75,13.25,z-4,z+4)
            inner=collar.common(box(50,60,z-5,73.7,110,z+5))
            outer=collar.common(box(74.3,60,z-5,95,110,z+5))
            inner=inner.fuse(box(57,81,z-4,60.5,89,z+4))
            for j,y in enumerate((66.5,103.5)):
                inner=inner.fuse(box(67,y-4,z-4,73.7,y+4,z+4))
                outer=outer.fuse(box(74.3,y-4,z-4,80.3,y+4,z+4))
                inner=inner.cut(xc(2.1,67.8,73.8,y,z))
                outer=outer.cut(xc(1.4,74.2,80.4,y,z))
                suffix=side+str(i)+str(j)
                put('ArcInsert'+suffix,'夹环M2.5级盲孔嵌件候选 '+suffix,
                    mirror(xc(2,68,73,y,z).cut(xc(1.25,67.9,73.1,y,z)),sign))
                screw=xc(1.2,69,80.3,y,z).fuse(xc(2.5,80.3,82.3,y,z))
                screw=screw.cut(box(81.5,y-1.4,z-.5,82.4,y+1.4,z+.5))
                put('ArcScrew'+suffix,'夹环外侧M2.5级螺钉候选 '+suffix,mirror(screw,sign))
                put('ArcTool'+suffix,'夹环外侧工具轴线候选 '+suffix,mirror(xc(1.5,82.3,125,y,z),sign),'clearance','accent',
                    '仅Ø3直工具杆，未覆盖手掌／手柄／驱动头配合；不表示规定采购工具规格')
            if i==1:
                outer=outer.fuse(box(87.75,81,114,89.75,89,126)).fuse(box(74.3,81,124,89.75,89,126))
            spine=spine.fuse(inner)
            put('ArcClampOuter'+side+str(i),'分体夹环外半／上环带轴向限位 '+side+str(i),mirror(outer,sign))
            lining=ring(13.25,12.75,z-3,z+3)
            for part,x0,x1 in [('Inner',50,73.7),('Outer',74.3,95)]:
                put('ArcLiner'+part+side+str(i),'夹环0.5 mm软衬候选 '+part+side+str(i),
                    mirror(lining.common(box(x0,60,z-4,x1,110,z+4)),sign),'structure','dark',
                    '名义接触不建压缩；材料、夹持力、灌封壳接触区域与温升均待实测')
        fixed=fixed.fuse(mirror(spine,sign))
        x=sign*18.5
        put('EffectMOS'+side,'效果MOS候选 33×17×12 '+side,box(x-16.5,-40,68.5,x+16.5,-23,80.5),'envelope','electronics',
            '通用图33×17，高12为预算；实际端子及可接触板边未测，未虚构PCB安装孔')
        put('EffectBuck'+side,'降压板用户尺寸20×11×5 '+side,box(x-10,-54,68.5,x+10,-43,73.5),'envelope','bubble',
            '用户提供20×11×5，焊锡／端子／出线范围未单独确认；一效果一板为数量假设')
    doc.getObject('BackpackShell').Shape=fixed.removeSplitter()
    tray=box(-37,-56,66.5,37,-23,68.5)
    for i,(x,y) in enumerate(MOUNTS):
        tray=tray.fuse(box(x-4,y-4,66.5,x+4,y+4,68.5)).cut(zc(1.4,66.4,68.6,x,y))
        # Blind insert sockets open downward; the original roof skin stays whole.
        post=zc(3.5,68.5,79 if y==-49 else 87,x,y).cut(zc(2.1,68.4,74.5,x,y))
        post=post.cut(doc.getObject('LowerTub').Shape)
        lid=lid.fuse(post)
        put('EffectInsert'+str(i),'薄承板M2.5级嵌件候选 '+str(i),zc(2,69,74,x,y).cut(zc(1.25,68.9,74.1,x,y)))
        screw=zc(1.2,66.5,73.5,x,y).fuse(zc(2.4,65,66.5,x,y))
        screw=screw.cut(box(x-1.4,y-.5,64.9,x+1.4,y+.5,65.8))
        put('EffectScrew'+str(i),'薄承板底部M2.5级螺钉候选 '+str(i),screw)
        put('EffectTool'+str(i),'取充电宝后薄承板工具杆 '+str(i),zc(1.5,-12,65,x,y),'clearance','accent',
            '先取充电宝及底盖；仅Ø3直杆空间，手部／手柄与真实工具未验证')
    doc.getObject('KeelLid').Shape=lid.removeSplitter()
    put('EffectTray','底盘效果板四点薄承板／候选',tray,'structure','metal',
        '主体74×33×2，四耳孔X±39/Y-49,-29；固定到顶盖内柱，先拆电源再向下取；板卡自身固定待实测')
    doc.recompute()
    return {'revision':'0.42','arc_body_diameter_length_mm':[25.5,70],'arc_centres_xy_mm':[[74,85],[-74,85]],
        'arc_body_z_mm':[54,124],'clamp_z_centres_mm':[86,114],'split_gap_mm':.6,'liner_thickness_mm':.5,
        'arc_clamp_screw_quantity':8,'effect_tray_screw_quantity':4,'effect_mount_xy_mm':MOUNTS,
        'MOS_lwh_mm':[33,17,12],'MOS_height_assumed':True,'buck_lwh_mm':[20,11,5],
        'quantity_assumption':'one MOS and one buck per effect','board_mounting_complete':False,
        'physical_fit_verified':False,'electrical_or_insulation_verified':False}


def check(doc):
    physical={o.Name:o.Shape for o in doc.Objects if hasattr(o,'Category') and o.Category!='clearance'}
    def hits(shape,obstacles):
        return inspect(shape,{n:s for n,s in obstacles.items() if shape.BoundBox.intersect(s.BoundBox)})
    selected={n:s for n,s in physical.items() if n.startswith(PREFIXES)}
    reserved={o.Name:o.Shape for o in doc.Objects if getattr(o,'Category','')=='clearance' and not o.Name.startswith(PREFIXES)}
    changed={**selected,**{n:physical[n] for n in ('KeelLid','BackpackShell')}}
    static={n:inspect(s,{m:t for m,t in physical.items() if m!=n}) for n,s in changed.items()}
    spaces={n:inspect(s,reserved) for n,s in selected.items()}
    cap_checks={};arc_checks={};screw_checks={};tool_checks={};negative={}
    for side,sign in [('L',1),('R',-1)]:
        screws=[n for n in selected if n.startswith('ArcScrew'+side)]
        caps=[n for n in selected if n.startswith(('ArcClampOuter'+side,'ArcLinerOuter'+side))]
        for i in (0,1):
            names=['ArcClampOuter'+side+str(i),'ArcLinerOuter'+side+str(i)]
            samples=[]
            for step in range(21):
                moving=Part.makeCompound([physical[n] for n in names]);moving.translate(V(sign*35*step/20,0,0))
                samples.append(hits(moving,{n:s for n,s in physical.items() if n not in names+screws}))
            cap_checks[side+str(i)]={'method':'21 discrete poses, outward X35; no continuous claim','poses':samples,'passed':all(r['passed'] for r in samples)}
        sweep=zc(12.75,54,214,sign*74,85)
        arc_checks[side]=inspect(sweep,{n:s for n,s in physical.items() if n not in caps+screws+['BackpackArc'+side]})
        negative['upper_stop_retained_'+side]=inspect(sweep,{'upper_cap':physical['ArcClampOuter'+side+'1']})
        for n in screws:
            b=bounds(physical[n]);y=(b[1]+b[4])/2;z=(b[2]+b[5])/2
            swept=mirror(xc(1.2,69,115.3,y,z).fuse(xc(2.5,80.3,117.3,y,z)),sign)
            screw_checks[n]=inspect(swept,{m:s for m,s in physical.items() if m!=n})
            tool_checks[n]=inspect(doc.getObject(n.replace('Screw','Tool')).Shape,{m:s for m,s in physical.items() if m!=n})
    removed={'PowerBank','BatteryHatch','BatteryPullStrap','BottomServiceCover','PowerCableRoute'}
    removed|={o.Name for o in doc.Objects if o.Name.startswith(('BatteryPad','BatterySupportWasher','BatteryScrew','BottomCoverScrew'))}
    names=['EffectTray','EffectMOSL','EffectMOSR','EffectBuckL','EffectBuckR']
    bolts=[n for n in selected if n.startswith('EffectScrew')]
    tray_sweep=Part.makeCompound([box_sweep(physical[n],(0,0,-100)) for n in names])
    tray=inspect(tray_sweep,{n:s for n,s in physical.items() if n not in removed and n not in names+bolts})
    negative['battery_retained']=inspect(tray_sweep,{'PowerBank':physical['PowerBank']})
    negative['tray_screws_retained']=inspect(tray_sweep,{n:physical[n] for n in bolts})
    for i,(x,y) in enumerate(MOUNTS):
        n='EffectScrew'+str(i)
        swept=zc(1.2,41.5,73.5,x,y).fuse(zc(2.4,40,66.5,x,y))
        obstacles={m:s for m,s in physical.items() if m not in removed and m!=n}
        screw_checks[n]=inspect(swept,obstacles)
        tool_checks[n]=inspect(doc.getObject('EffectTool'+str(i)).Shape,obstacles)
    contacts={}
    def face_contact(a,b):
        return sum(f.common(g).Area for f in a.Faces for g in b.Faces if f.BoundBox.intersect(g.BoundBox))
    for side,sign in [('L',1),('R',-1)]:
        body=physical['BackpackArc'+side]
        contacts['bottom_pad_'+side]=face_contact(body,physical['ArcBottomPad'+side])
        for i in (0,1):
            for part in ('Inner','Outer'):
                contacts['liner_'+part+side+str(i)]=face_contact(body,physical['ArcLiner'+part+side+str(i)])
        moved=physical['ArcClampOuter'+side+'0'].copy();moved.translate(V(sign*.5,0,0))
        negative['cap_screws_retained_'+side]=inspect(moved,{n:s for n,s in physical.items() if n.startswith('ArcScrew'+side+'0')})
    contacts['tray_to_posts']=face_contact(physical['EffectTray'],physical['KeelLid'])
    return {'revision':'0.42','static':static,'reserved_spaces':spaces,'outer_caps':cap_checks,'arc_up_90':arc_checks,
        'tray_down_100':tray,'tray_removed_first':sorted(removed)+bolts,'screw_continuous_sweeps':screw_checks,'tool_rods':tool_checks,
        'negative_controls':negative,'nominal_contact_areas_mm2':contacts,'passed':all(r['passed'] for section in (static,spaces,cap_checks,arc_checks,screw_checks,tool_checks) for r in section.values())
            and tray['passed'] and all(not r['passed'] for r in negative.values()) and all(area>10 for area in contacts.values()),
        'physical_fit_verified':False,'limits':'Cap release sampled; bare body/tray/screws swept continuously. No hand, real wire, pad deformation, screw torque, thermal, HV or liquid acceptance.'}


def render(doc,output):
    import FreeCADGui as G
    from PySide import QtGui
    A.setActiveDocument(doc.Name)
    objects=[o for o in doc.Objects if hasattr(o,'Category')]
    saved={o.Name:(o.Shape.copy(),o.ViewObject.Visibility,o.ViewObject.Transparency) for o in objects}
    front=A.Rotation(V(1,1,0),V(-1,1,3),V(1,-1,.75),'ZXY')
    rear=A.Rotation(V(-1,1,0),V(-1,-1,3),V(1,1,.75),'ZXY')
    bottom=A.Rotation(V(1,0,0),180)
    arc={o.Name for o in objects if o.Name.startswith(PREFIXES[:-1]) and o.Category!='clearance'}
    effect={o.Name for o in objects if o.Name.startswith('Effect') and o.Category!='clearance'}
    packs={'BackpackShell','RearBaseArmor','BackpackSpine','WaterModule','BubbleModule','WaterRetentionBand','BubbleRetentionBand','WaterStrapClosure'}
    # Explicit names avoid treating the L in "Liner" as the side identifier.
    left={n for n in arc if n in ('BackpackArcL','ArcBottomPadL') or any(n.startswith(p+'L') for p in ('ArcClampOuter','ArcLinerInner','ArcLinerOuter','ArcInsert','ArcScrew'))}
    view=G.activeDocument().activeView();view.setCameraType('Orthographic')
    views=[('effects-backpack',rear,arc|packs),('effects-clamp',rear,left|{'BackpackShell'}),
           ('effects-service',rear,arc|packs),('effects-tray',front,effect|{'KeelLid','LowerTub','PowerBank'}),
           ('effects-tray-bottom',bottom,effect),('effects-tray-service',front,effect|{'KeelLid','LowerTub'})]
    try:
        for name,rotation,visible in views:
            for o in objects:
                o.Shape=saved[o.Name][0];o.ViewObject.Visibility=o.Name in visible
                o.ViewObject.Transparency=85 if name.startswith('effects-tray') and o.Name in ('KeelLid','LowerTub') else 40 if o.Name in ('PowerBank','WaterModule','BubbleModule') else 0
            if name=='effects-clamp':
                doc.getObject('BackpackShell').Shape=saved['BackpackShell'][0].common(box(56,60,50,91,109,127))
            if name=='effects-service':
                for n in arc:
                    o=doc.getObject(n);s=o.Shape.copy();sign=1 if n in left else -1
                    if n.startswith('ArcScrew'):o.ViewObject.Visibility=False
                    elif n.startswith(('ArcClampOuter','ArcLinerOuter')):s.translate(V(sign*35,0,0));o.Shape=s
                    elif n.startswith('BackpackArc'):s.translate(V(0,0,90));o.Shape=s
            if name=='effects-tray-bottom':
                for n in effect:
                    if n.startswith('EffectScrew'):
                        s=doc.getObject(n).Shape.copy();s.translate(V(0,0,-15));doc.getObject(n).Shape=s
            if name=='effects-tray-service':
                for n in effect:
                    if n.startswith(('EffectScrew','EffectInsert')):doc.getObject(n).ViewObject.Visibility=False
                    else:
                        s=doc.getObject(n).Shape.copy();s.translate(V(0,0,-100));doc.getObject(n).Shape=s
            doc.recompute();view.setCameraOrientation(rotation.Q);view.fitAll()
            for _ in range(10):QtGui.QApplication.processEvents()
            view.saveImage(str(output/(name+'.png')),1600,1200,'White')
    finally:
        for o in objects:o.Shape,o.ViewObject.Visibility,o.ViewObject.Transparency=saved[o.Name]
        doc.recompute()
