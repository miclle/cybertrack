"""0.50 integrated backpack body pockets and chassis effect-board carrier.

Contact, pads, M2.5-class hardware and actual boards remain candidates. This
module defines no HV wiring, electrode, drive, insulation or protective rating.
"""
import FreeCAD as A
import Part
from breadboard_layout import box
from ultrasonic_integration import inspect as inspect_exact,box_sweep
V=A.Vector
from effect_board_mount import MOUNTS, apply as add_board_mount, check as check_board_mount, vertical_sweep, SIDE_WIRE_POINTS
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
def ring(ro,ri,z0,z1):return zc(ro,z0,z1,74,85).cut(zc(ri,z0-.1,z1+.1,74,85))


def housing():
    """Right-handed master: closed lower cup and open upper guide, one solid.

    Keep the old band/ear silhouette, but bridge the split and remove fasteners
    and the overhanging axial stop. The module is inserted vertically.
    """
    body=box(57,81,51.5,60.5,89,118)
    body=body.fuse(zc(15.75,51.5,90,74,85).cut(zc(13.25,53,91,74,85)))
    for z in (86,114):
        band=ring(15.75,13.25,z-4,z+4)
        band=band.fuse(box(57,81,z-4,60.5,89,z+4))
        for y in (66.5,103.5):
            band=band.fuse(box(67,y-4,z-4,80.3,y+4,z+4))
        body=body.fuse(band)
    # Relief at the inner/front bottom corner keeps the chassis unchanged.
    body=body.cut(box(60.5,60,50,64.5,74.75,54))
    return body.removeSplitter()


def apply(doc,add):
    fixed=doc.getObject('BackpackShell').Shape.copy()
    def put(n,label,s,category='structure',color='metal',basis=None):
        return add(n,label,s.removeSplitter(),category,color,basis or '0.50机械候选；接触面、材料、标准件规格与实物配合待核，不是绝缘或安全外壳')
    for side,sign in [('L',1),('R',-1)]:
        put('BackpackArc'+side,'背包外侧本体候选 Ø25.5×70 '+side,zc(12.75,54,124,sign*74,85),'envelope','accent',
            '历史用户规划Ø25.5×70，非实测；不含端部、引线、电极、驱动、绝缘或屏蔽验收')
        put('ArcBottomPad'+side,'本体底托1 mm软垫候选 '+side,mirror(box(68,81,53,80,89,54),sign),'structure','dark')
        for i,z in enumerate((86,114)):
            lining=ring(13.25,12.75,z-3,z+3)
            for part,x0,x1 in [('Inner',50,73.7),('Outer',74.3,95)]:
                put('ArcLiner'+part+side+str(i),'环带0.5 mm软衬候选 '+part+side+str(i),
                    mirror(lining.common(box(x0,60,z-4,x1,110,z+4)),sign),'structure','dark',
                    '名义接触不建压缩；材料、摩擦保持力、灌封壳接触区域与温升均待实测')
        fixed=fixed.fuse(mirror(housing(),sign))
    shell=doc.getObject('BackpackShell')
    shell.Shape=fixed.removeSplitter()
    shell.Label='双瓶背包／一体点火模块桶座与上导环'
    shell.EvidenceBasis='0.50双侧桶座、完整上下环带及连接耳与双瓶护舱融合为一个实体；无顶部倒L压件及分体夹环紧固件；未验证防脱保持力、制造或绝缘'
    assert shell.Shape.isValid() and len(shell.Shape.Solids)==1
    board_info=add_board_mount(doc,put)
    doc.recompute()
    return {'revision':'0.50','arc_body_diameter_length_mm':[25.5,70],'arc_centres_xy_mm':[[74,85],[-74,85]],
        'arc_body_z_mm':[54,124],'band_z_centres_mm':[86,114],'liner_thickness_mm':.5,
        'integrated_object':'BackpackShell','cup_z_mm':[51.5,90],'cup_outer_inner_diameter_mm':[31.5,26.5],
        'cup_floor_thickness_mm':1.5,'upper_ring_z_mm':[110,118],'top_axial_stop':False,
        'arc_clamp_screw_quantity':0,'effect_tray_screw_quantity':4,'effect_mount_xy_mm':MOUNTS,
        'MOS_lwh_mm':[33,17,12],'MOS_height_assumed':True,'buck_lwh_mm':[20,11,5],
        'quantity_assumption':'one MOS and one buck per water/bubble effect; shared ignition MOS is separate',
        'board_mounting_complete':False,'board_mounting_candidate':board_info,
        'axial_retention_verified':False,'physical_fit_verified':False,'electrical_or_insulation_verified':False}


def check(doc):
    physical={o.Name:o.Shape for o in doc.Objects if hasattr(o,'Category') and o.Category!='clearance'}
    selected={n:s for n,s in physical.items() if n.startswith(PREFIXES)}
    reserved={o.Name:o.Shape for o in doc.Objects if getattr(o,'Category','')=='clearance' and not o.Name.startswith(PREFIXES)}
    changed={**selected,**{n:physical[n] for n in ('KeelLid','BackpackShell')}}
    static={n:inspect(s,{m:t for m,t in physical.items() if m!=n}) for n,s in changed.items()}
    spaces={n:inspect(s,reserved) for n,s in selected.items()}
    arc_checks={};screw_checks={};tool_checks={};negative={}
    for side,sign in [('L',1),('R',-1)]:
        sweep=zc(12.75,54,214,sign*74,85)
        arc_checks[side]=inspect(sweep,{n:s for n,s in physical.items() if n!='BackpackArc'+side})
        # The integrated floor must block downward motion, while the top stays open.
        negative['floor_blocks_down_'+side]=inspect(zc(12.75,50,124,sign*74,85),
                                                  {'BackpackShell':physical['BackpackShell']})
    removed={'PowerBank','BatteryHatch','BatteryPullStrap','BottomServiceCover','PowerCableRoute'}
    removed|={o.Name for o in doc.Objects if o.Name.startswith(('BatteryPad','BatterySupportWasher','BatteryScrew','BottomCoverScrew'))}
    names=[n for n in physical if n.startswith('Effect') and not n.startswith(('EffectScrew','EffectInsert'))]
    bolts=[n for n in selected if n.startswith('EffectScrew')]
    tray_sweep=Part.makeCompound([vertical_sweep(physical[n],-100) for n in names])
    tray_sweep=tray_sweep.Solids[0].multiFuse(tray_sweep.Solids[1:]).removeSplitter()
    tray=inspect(tray_sweep,{n:s for n,s in physical.items() if n not in removed and n not in names+bolts})
    wire_parts=[o.Shape for o in doc.Objects if o.Name.startswith(('EffectPort','EffectWireCentre'))]
    for sign in (-1,1):
        points=[(sign*x,y,z) for x,y,z in SIDE_WIRE_POINTS]
        for a,b in zip(points,points[1:]):
            wire_parts.append(box(*[min(a[i],b[i])-1.5 for i in range(3)],*[max(a[i],b[i])+1.5 for i in range(3)]))
    wire_sweep=Part.makeCompound([box_sweep(s,(0,0,-100)) for s in wire_parts])
    wire_sweep=wire_sweep.Solids[0].multiFuse(wire_sweep.Solids[1:]).removeSplitter()
    wire_service=inspect(wire_sweep,{n:s for n,s in physical.items() if n not in removed and n not in names+bolts})
    negative['battery_retained']=inspect(tray_sweep,{'PowerBank':physical['PowerBank']})
    negative['tray_screws_retained']=inspect(tray_sweep,{n:physical[n] for n in bolts})
    for i,(x,y) in enumerate(MOUNTS):
        n='EffectScrew'+str(i)
        swept=zc(1.2,43.1,75.1,x,y).fuse(zc(2.4,41.6,68.1,x,y))
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
    contacts['tray_to_posts']=face_contact(physical['EffectTray'],physical['KeelLid'])
    boards=check_board_mount(doc,inspect)
    return {'revision':'0.50','board_mount':boards,'static':static,'reserved_spaces':spaces,'arc_up_90':arc_checks,
        'housing_single_solid':len(physical['BackpackShell'].Solids)==1,'top_axial_stop':False,'axial_retention_verified':False,
        'tray_down_100':tray,'disconnected_local_wires_down_100':wire_service,'tray_removed_first':sorted(removed)+bolts,'screw_continuous_sweeps':screw_checks,'tool_rods':tool_checks,
        'negative_controls':negative,'nominal_contact_areas_mm2':contacts,'passed':all(r['passed'] for section in (static,spaces,arc_checks,screw_checks,tool_checks) for r in section.values())
            and len(physical['BackpackShell'].Solids)==1 and boards['passed'] and tray['passed'] and wire_service['passed'] and all(not r['passed'] for r in negative.values()) and all(area>10 for area in contacts.values()),
        'physical_fit_verified':False,'limits':'Module slides up 90 mm after releasing and parking its leads; integrated rings stay fixed. No upward hard stop; friction retention unverified. Bare body/tray/screws swept continuously. No hand, real wire, pad deformation, screw torque, thermal, HV or liquid acceptance.'}


def render(doc,output):
    import FreeCADGui as G
    from PySide import QtGui
    from pivy import coin  # Register the camera-node SWIG wrappers.
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
    views=[('effects-backpack',rear,arc|packs),('effects-housing',rear,{'BackpackShell'}),
           ('effects-clamp',rear,left|{'BackpackShell'}),
           ('effects-service',rear,arc|packs),('effects-tray',front,effect|{'KeelLid','LowerTub','PowerBank'}),
           ('effects-tray-bottom',bottom,effect),('effects-tray-service',front,effect|{'KeelLid','LowerTub'}),
           ('effects-board-mount',front,effect),('effects-board-wiring',front,effect|{o.Name for o in objects if o.Name.startswith(('EffectPort','EffectWire'))}),
           ('effects-board-service',front,effect)]
    try:
        for name,rotation,visible in views:
            for o in objects:
                o.Shape=saved[o.Name][0];o.ViewObject.Visibility=o.Name in visible
                o.ViewObject.Transparency=85 if name.startswith('effects-tray') and o.Name in ('KeelLid','LowerTub') else 40 if o.Name in ('PowerBank','WaterModule','BubbleModule') else 0
            if name=='effects-clamp':
                doc.getObject('BackpackShell').Shape=saved['BackpackShell'][0].common(box(56,60,50,91,109,127))
            if name=='effects-service':
                for n in arc:
                    o=doc.getObject(n);s=o.Shape.copy()
                    if n.startswith('BackpackArc'):s.translate(V(0,0,90));o.Shape=s
            if name=='effects-tray-bottom':
                for n in effect:
                    if n.startswith('EffectScrew'):
                        s=doc.getObject(n).Shape.copy();s.translate(V(0,0,-15));doc.getObject(n).Shape=s
            if name=='effects-tray-service':
                for n in effect:
                    if n.startswith(('EffectScrew','EffectInsert')):doc.getObject(n).ViewObject.Visibility=False
                    else:
                        s=doc.getObject(n).Shape.copy();s.translate(V(0,0,-100));doc.getObject(n).Shape=s
            if name.startswith('effects-board'):
                for n in effect:
                    if n.startswith(('EffectInsert','EffectScrew')):doc.getObject(n).ViewObject.Visibility=False
            if name=='effects-board-service':
                for n in effect:
                    o=doc.getObject(n)
                    if n.startswith('EffectRetainerScrew'):o.ViewObject.Visibility=False
                    elif n in ('EffectRetainerLMOS','EffectRetainerRMOS','EffectRetainerLBuck','EffectRetainerRBuck'):
                        s=o.Shape.copy();s.translate(V(0,0,42));o.Shape=s
                    elif n in ('EffectMOSL','EffectMOSR','EffectBuckL','EffectBuckR'):
                        s=o.Shape.copy();s.translate(V(0,0,20));o.Shape=s
            if name=='effects-board-wiring':
                for o in objects:
                    if o.Name.startswith(('EffectPort','EffectWire')):o.ViewObject.Transparency=45
            doc.recompute();view.setCameraOrientation(rotation.Q);view.fitAll()
            if name=='effects-board-service':
                camera=view.getCameraNode();camera.height.setValue(camera.height.getValue()*1.18)
            for _ in range(10):QtGui.QApplication.processEvents()
            view.saveImage(str(output/(name+'.png')),1600,1200,'White')
    finally:
        for o in objects:o.Shape,o.ViewObject.Visibility,o.ViewObject.Transparency=saved[o.Name]
        doc.recompute()
