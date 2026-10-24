"""Serviceable assembly candidate, keeping the approved exterior proportions.

All fasteners, insert fits, hoses and connector clearances are design allocations.
No thread, seal performance, supplier fit or physical assembly is certified here.
"""
import math
import FreeCAD as App
import Part
from controller_layout import build_controller, controller_members
V=App.Vector


def box(x0,y0,z0,x1,y1,z1):
    return Part.makeBox(x1-x0,y1-y0,z1-z0,V(x0,y0,z0))


def cylinder(r,z0,z1,x,y):
    return Part.makeCylinder(r,z1-z0,V(x,y,z0))


def tube(r,bore,z0,z1,x,y):
    return cylinder(r,z0,z1,x,y).cut(cylinder(bore,z0,z1,x,y))


def route(points,radius):
    pieces=[]
    for a,b in zip(points,points[1:]):
        a,b=V(*a),V(*b);pieces.append(Part.makeCylinder(radius,(b-a).Length,a,b-a))
    pieces += [Part.makeSphere(radius,V(*p)) for p in points[1:-1]]
    return pieces[0].multiFuse(pieces[1:]).removeSplitter()


def refine(doc,add):
    def cut(name,tool):
        obj=doc.getObject(name);obj.Shape=obj.Shape.cut(tool).removeSplitter()
    def fuse(name,shape):
        obj=doc.getObject(name);obj.Shape=obj.Shape.fuse(shape).removeSplitter()
    def fastener(name,x,y,bottom,head_bottom,head_top):
        bolt=cylinder(1.25,bottom,head_bottom,x,y).fuse(cylinder(2.2,head_bottom,head_top,x,y))
        bolt=bolt.cut(box(x-1.4,y-0.4,head_top-0.4,x+1.4,y+0.4,head_top+0.1))
        add(name,'M2.5 级紧固件候选 '+name,bolt,'structure','metal','简化非螺纹几何；长度、头型及采购规格未定')
    def insert(name,x,y,z0,z1):
        add(name,'嵌件候选 '+name,tube(2,1.35,z0,z1,x,y),'structure','power','设计占位 Ø4／孔 Ø2.7；材料、螺纹及压装参数待试验')

    # Battery carrier: four recessed fasteners outside the battery envelope.
    for side,sign in [('L',1),('R',-1)]:
        for end,y in [('Front',-85),('Rear',-34)]:
            x=sign*63.5;tag=side+end
            tab=box(60.5 if sign>0 else -65.8,y-4,28,65.8 if sign>0 else -60.5,y+4,31)
            fuse('BatteryHatch',tab)
            cut('LowerTub',box(x-2.5,y-4.2,27,x+2.5,y+4.2,31.3))
            boss=box(x-2.5,y-4,31.3,x+2.5,y+4,37)
            fuse('LowerTub',boss)
            cut('LowerTub',cylinder(2.1,31.2,35.9,x,y))
            cut('BatteryHatch',cylinder(1.4,27,32,x,y))
            cut('BatteryHatch',cylinder(2.4,27,29.4,x,y))
            insert('BatteryInsert'+tag,x,y,31.3,35.8)
            bolt=cylinder(1.25,29.2,35.7,x,y).fuse(cylinder(2.2,28.2,29.2,x,y))
            bolt=bolt.cut(box(x-1.4,y-0.4,28.1,x+1.4,y+0.4,28.6))
            add('BatteryScrew'+tag,'电源托盖下方沉头位紧固候选 '+tag,bolt,'structure','metal','M2.5 级候选；不是已选定沉头螺钉标准')
    strap=box(-60.6,-63,32.2,60.6,-57,32.8)
    for sign in (-1,1):
        x0,x1=(60,60.6) if sign>0 else (-60.6,-60)
        strap=strap.fuse(box(x0,-63,32.2,x1,-57,65.2))
        x0,x1=(45,60.6) if sign>0 else (-60.6,-45)
        strap=strap.fuse(box(x0,-63,64.6,x1,-57,65.2))
    add('BatteryPullStrap','随电源托盖下取的柔性拉带占位',strap.removeSplitter(),'structure','accent','柔性件占位；材料、强度及固定方式待试验')
    cut('FrontBulkhead',box(-20,-22,38,20,-18,61))

    # A separate underside opening makes the connector reachable before dropping the battery.
    cut('LowerTub',box(-15,-17,27,15,16,32))
    access=box(-14.8,-16.8,28,14.8,15.8,30.8)
    for side,sign in [('L',1),('R',-1)]:
        x=sign*18;y=0
        access=access.fuse(box(14.5 if sign>0 else -21,-4,28,21 if sign>0 else -14.5,4,30.8))
        cut('LowerTub',box(15 if sign>0 else -21.2,-4.2,27,21.2 if sign>0 else -15,4.2,31.3))
        fuse('LowerTub',box(15.2 if sign>0 else -23.5,-8,30.8,23.5 if sign>0 else -15.2,8,37))
        cut('LowerTub',cylinder(2.1,30.7,35.9,x,y))
        access=access.cut(cylinder(1.4,27,32,x,y)).cut(cylinder(2.4,27,29.4,x,y))
        insert('AccessInsert'+side,x,y,31.3,35.8)
        bolt=cylinder(1.25,29.2,35.7,x,y).fuse(cylinder(2.2,28.2,29.2,x,y))
        bolt=bolt.cut(box(x-1.4,y-0.4,28.1,x+1.4,y+0.4,28.6))
        add('AccessScrew'+side,'电源插头检修小盖紧固候选 '+side,bolt,'structure','metal','M2.5 级简化候选；实物长度和头型待核')
    add('CableServiceCover','底部独立电源插头检修小盖',access.removeSplitter(),'structure','dark','30×33 mm 开口；手指、实际插头及工具空间尚未实测')

    # The whole armored crown lifts, rather than expecting a board to pass the small hatch.
    original=doc.getObject('HeadShell').Shape.copy()
    doc.getObject('HeadShell').Shape=original.common(box(-100,-100,120,100,50,181))
    crown=original.common(box(-100,-100,181.25,100,50,210))
    add('HeadCrownShell','整体上取冠盖／0.25 mm 装配分缝',crown,'exterior','body')
    for side,sign in [('L',1),('R',-1)]:
        for end,y in [('Front',-52),('Rear',7)]:
            x=sign*64;tag=side+end
            x0,x1=(60,81) if sign>0 else (-81,-60)
            ledge=box(x0,y-4.5,174,x1,y+4.5,181).common(original.fuse(box(-79,-80,140,79,26,181)))
            fuse('HeadShell',ledge)
            cut('HeadShell',cylinder(2.1,176,181.1,x,y))
            insert('CrownInsert'+tag,x,y,176,180.5)
            for name in ('HeadCrownShell','CrownSideArmor'+side):
                cut(name,cylinder(1.5,181,201,x,y))
                cut(name,cylinder(2.5,193.6,201,x,y))
            fastener('CrownScrew'+tag,x,y,178,193.9,194.9)
    # Separate locating keys at the front rim avoid relying on screw shanks for alignment.
    for side,sign in [('L',1),('R',-1)]:
        key=box(sign*45-2,-80,179.5,sign*45+2,-77.5,183)
        cut('HeadCrownShell',box(sign*45-2.2,-80.2,181.1,sign*45+2.2,-77.3,183.2))
        fuse('HeadShell',key)

    # A removable tray carries both existing equipment allocations; no board hole pattern invented.
    tray=box(-52,-39,144.5,52,10,145.5).fuse(box(-39,-74,144.5,39,-39,145.5))
    add('ElectronicsTray','头舱电子及音频共用上取托板',tray.removeSplitter(),'structure','metal','托板轮廓候选；实际板卡安装孔、绝缘支柱及天线净空待整合')
    for sign in (-1,1):
        for i,y in enumerate((-30,0)):
            x=sign*49.5;tag=('L' if sign>0 else 'R')+str(i)
            fuse('HeadShell',cylinder(3.5,139,144.5,x,y))
            cut('HeadShell',cylinder(2.1,140,144.6,x,y))
            insert('TrayInsert'+tag,x,y,140,144.5)
            cut('ElectronicsTray',cylinder(1.5,144,148,x,y))
            fastener('TrayScrew'+tag,x,y,141,145.5,146.5)

    # Wet module service lids lift independently; a neck passes the inner pod cap.
    for name,cx in [('Water',-24),('Bubble',24)]:
        cut(name+'PodCap',cylinder(7,121,129,cx,49))
        fuse(name+'PodCap',tube(9,7,122,127.6,cx,49))
        add(name+'FillPlug',('喷水' if name=='Water' else '泡泡')+'补液盖导向塞',cylinder(6.8,124.3,128,cx,49),'structure','dark','Ø14 补液孔候选；整套商品模块能否接入或拆分尚未确认')
        add(name+'FillSeal',('喷水' if name=='Water' else '泡泡')+'补液口端面密封垫占位',tube(9,7,127.6,128,cx,49),'structure','accent','0.4 mm 占位；材质、压缩率及密封性能未验证')
        for sign in (-1,1):
            x=cx+sign*12;y=69;tag=name+('L' if sign>0 else 'R')
            fuse('BackpackShell',box(x-3.5,66,125,x+3.5,76,128))
            cut('BackpackShell',cylinder(2.1,125,128.1,x,y))
            insert('FillInsert'+tag,x,y,125,128)
            cut(name+'ServiceLid',cylinder(1.5,127,132,x,y))
            cut(name+'ServiceLid',cylinder(2.4,129.5,132,x,y))
            fastener('FillScrew'+tag,x,y,125.2,129.7,130.7)

    # The long-side port faces +Y. Exact lateral position remains an explicit assumption.
    wire_points=[(0,-14,50),(0,6,70),(0,6,142),(0,-5,142)]
    wire=route(wire_points,3).fuse(box(-10,-23,42,10,-5,58)).removeSplitter()
    wire_tool=route(wire_points,4.5)
    for name in ('KeelLid','NeckPedestal','NeckHeadSaddle','HeadShell','ElectronicsTray'):
        cut(name,wire_tool)
    add('PowerCableRoute','电源插头候选及中央干区线束 Ø6',wire,'envelope','power','长侧面有输出口为用户确认；端口 X/Z、插头 20×18×16 与线束 Ø6 为假设，不表示实物可插入')
    for name,z0,z1 in [('BaseCableGrommet',90,93),('HeadCableGrommet',133,139)]:
        add(name,'中央干区线束护口 '+name,tube(4.4,3.4,z0,z1,0,6),'structure','dark','护口尺寸候选；线束规格、弯曲半径与磨损待测')
    bridge=box(-18,-1,107,18,2,109).fuse(tube(4.5,3.5,107,109,0,6)).removeSplitter()
    add('NeckCableBridge','固定颈架线束限位桥',bridge,'structure','dark','固定夹持候选；没有增加活动关节')

    from water_gun_mount import hose_shapes
    hose,hose_space=hose_shapes()
    add('WaterHoseRoute','喷水顶部吸液管 Ø5 实测／R8／侧向接前枪',hose,'envelope','water','外径5为用户实测；中心弯曲半径8及接口位置为设计假设；不是供应商最小弯曲半径或已验收液路')
    controller_info=build_controller(doc,add,cut,fuse,fastener,insert)
    doc.getObject('HeadShell').Label='头舱固定下壳／托板及冠盖支座'
    doc.getObject('HeadServiceHatch').Label='中央隆起顶甲／随整体冠盖拆装'
    for group,names in service_groups(doc).items():
        for name in names:
            obj=doc.getObject(name)
            obj.addProperty('App::PropertyString','ServiceGroup','Assembly')
            obj.ServiceGroup=group
    doc.recompute()
    for o in doc.Objects:
        if hasattr(o,'Category') and (o.Shape.isNull() or not o.Shape.isValid() or (o.Category!='drive' and len(o.Shape.Solids)!=1)):
            raise ValueError('Assembly refinement invalid: '+o.Name)
    return controller_info


def service_groups(doc):
    names=[o.Name for o in doc.Objects if hasattr(o,'Category')]
    crown=[n for n in names if n.startswith(('Crown','BrowArmor','OccipitalBrow')) and not n.startswith(('CrownScrew','CrownInsert'))]
    crown+=['HeadCrownShell','HeadServiceHatch']
    battery=['PowerBank','BatteryHatch','BatteryPullStrap']+[n for n in names if n.startswith('BatteryPad')]
    wet={name:[name+suffix for suffix in ('ServiceLid','CapGrip','LidMark','FillPlug','FillSeal')] for name in ('Water','Bubble')}
    return {'cable_access':['CableServiceCover'],'battery':battery,'crown':crown,'electronics':['ElectronicsTray','Electronics','AudioModule']+controller_members(doc)+[n for n in names if n.startswith(('ControllerMountScrew','ControllerMountInsert'))],**wet,
            'arc_left':['ArcModuleL'],'arc_right':['ArcModuleR'],
            **({key:[o.Name for o in doc.Objects if getattr(o,'ServiceGroup','')==key] for key in ('bubble_gun','bubble_gun_cradle')} if doc.getObject('BubbleGunShell') else {}),
            **({'water_gun':['WaterGunBody','WaterGunInlet']} if doc.getObject('WaterGunBody') else {}),
            **({key:[o.Name for o in doc.Objects if getattr(o,'ServiceGroup','')==key] for key in ('water_gun_cradle',)} if doc.getObject('WaterGunCradle') else {})}


def arc_translation_sweep(shape, delta):
    """Exact straight sweep of a Y-axis cylinder; not a general part sweep."""
    b=shape.optimalBoundingBox(False)
    radius=b.XLength/2;length=b.YLength
    assert abs(b.ZLength-2*radius)<1e-6 and abs(delta.y)<1e-9
    assert abs(shape.Volume-math.pi*radius*radius*length)<1e-5
    start=V((b.XMin+b.XMax)/2,b.YMin,(b.ZMin+b.ZMax)/2)
    end=start+delta
    normal=V(-delta.z,0,delta.x);normal.normalize();normal.multiply(radius)
    corners=[start+normal,end+normal,end-normal,start-normal]
    bridge=Part.Face(Part.makePolygon(corners+[corners[0]])).extrude(V(0,length,0))
    moved=shape.copy();moved.translate(delta)
    sweep=shape.fuse(moved).fuse(bridge).removeSplitter()
    assert sweep.isValid() and len(sweep.Solids)==1
    return sweep


def check_service_paths(doc):
    """Check discrete service poses plus continuous sweeps of the two bare arc cylinders."""
    groups=service_groups(doc);all_shapes=[o for o in doc.Objects if hasattr(o,'Category') and o.Category!='clearance']
    bounds={o.Name:o.Shape.optimalBoundingBox(False) for o in all_shapes}
    results=[]
    scenarios=[('cable_access',(0,0,-25),['AccessScrewL','AccessScrewR']),
               ('battery',(0,0,-60),[n.Name for n in all_shapes if n.Name.startswith('BatteryScrew')]+['PowerCableRoute','CableServiceCover','AccessScrewL','AccessScrewR']),
               ('crown',(0,0,65),[n.Name for n in all_shapes if n.Name.startswith('CrownScrew')]),
               ('electronics',(0,0,85),groups['crown']+[n.Name for n in all_shapes if n.Name.startswith(('CrownScrew','TrayScrew'))]+['PowerCableRoute','WaterHoseRoute','ControllerWireRoute']),
               ('Water',(0,0,40),[n.Name for n in all_shapes if n.Name.startswith('FillScrewWater')]+['WaterHoseRoute','BubbleGunHoseRoute']),
               ('Bubble',(0,0,40),[n.Name for n in all_shapes if n.Name.startswith('FillScrewBubble')]+['WaterHoseRoute','BubbleGunHoseRoute'])]
    if 'bubble_gun' in groups:
        from bubble_gun_mount import line_names
        blines=line_names(doc)
        scenarios += [('bubble_gun_cradle',(-90,0,6),blines+groups['bubble_gun']+['BubbleGunBaseScrew1','BubbleGunBaseScrew2'])]
    if 'water_gun' in groups:
        lines=['WaterHoseRoute','WaterGunLeadRoute','WaterGunLeadConnector']
        scenarios.append(('water_gun',(0,-150,2),lines))
        scenarios.append(('water_gun_cradle',(60,0,2),lines+groups['water_gun']+['WaterGunBaseScrew1','WaterGunBaseScrew2']))
    prerequisites=groups['crown']+groups['electronics']+[o.Name for o in all_shapes if o.Name.startswith(('CrownScrew','TrayScrew'))]+['PowerCableRoute','WaterHoseRoute','ControllerWireRoute']
    scenarios += [('arc_left',(-24.5,0,85),prerequisites),('arc_right',(24.5,0,85),prerequisites)]
    crown_removed=groups['crown']+[o.Name for o in all_shapes if o.Name.startswith('CrownScrew')]+['ControllerWireRoute']
    scenarios += [('controller',(0,0,65),crown_removed+[o.Name for o in all_shapes if o.Name.startswith('ControllerMountScrew')]),
                  ('controller_retainer',(0,0,40),crown_removed+['ControllerRetainerScrewFront','ControllerRetainerScrewRear']),
                  ('controller_board',(0,0,65),crown_removed+['ControllerRetainer','ControllerRetainerScrewFront','ControllerRetainerScrewRear']),
                  ('usb_com',(-12,0,35),crown_removed),('usb_native',(-12,0,35),crown_removed)]
    special={'controller':controller_members(doc),'controller_retainer':['ControllerRetainer'],
             'controller_board':['ESP32Board'],'usb_com':['ControllerUSBCOM'],'usb_native':['ControllerUSBUSB']}
    for group,delta,removed in scenarios:
        moving=special[group] if group in special else groups[group];fixed=[o for o in all_shapes if o.Name not in moving+removed]
        collisions=[];tested=0
        waypoints=[V(),V(*delta)]
        if group in ('bubble_gun','bubble_gun_cradle'):
            waypoints=[V(),V(0,0,delta[2]),V(*delta)]
        if group=='water_gun':
            waypoints=[V(),V(0,0,2),V(0,-150,2)]
        if group=='water_gun_cradle':
            waypoints=[V(),V(0,0,2),V(60,0,2)]
        if group in ('Water','Bubble'):
            waypoints=[V(),V(0,0,6),V(0,12,6),V(0,12,40)]
        if group.startswith('arc_'):
            # Lift clear of the fixed tray supports before moving toward the centre.
            waypoints=[V(),V(0,0,2),V(delta[0],0,2),V(*delta)]
        elif group.startswith('usb_'):
            waypoints=[V(),V(delta[0],0,0),V(*delta)]
        if group.startswith(('water_gun','bubble_gun')):
            from gun_pitch import vector
            waypoints=[vector(tuple(p)) for p in waypoints]
        poses=[a+(b-a)*fraction for a,b in zip(waypoints,waypoints[1:]) for fraction in (0,0.05,0.1,0.2,0.4,0.6,0.8,1)]
        for pose_index,offset in enumerate(poses):
            for name in moving:
                shape=doc.getObject(name).Shape.copy();shape.translate(offset)
                moving_bounds=shape.optimalBoundingBox(False)
                for other in fixed:
                    if not moving_bounds.intersect(bounds[other.Name]):continue
                    tested+=1;vol=shape.common(other.Shape).Volume
                    if vol>0.01:collisions.append({'moving':name,'fixed':other.Name,'pose_index':pose_index,'overlap_mm3':vol})
        swept_check=None
        if group.startswith('arc_'):
            swept_hits=[];swept_tested=0
            for segment,(start,end) in enumerate(zip(waypoints,waypoints[1:])):
                shape=doc.getObject(moving[0]).Shape.copy();shape.translate(start)
                sweep=arc_translation_sweep(shape,end-start)
                sweep_bounds=sweep.optimalBoundingBox(False)
                for other in fixed:
                    if not sweep_bounds.intersect(bounds[other.Name]):continue
                    swept_tested+=1;vol=sweep.common(other.Shape).Volume
                    if vol>0.01:swept_hits.append({'fixed':other.Name,'segment':segment,'overlap_mm3':vol})
            swept_check={'method':'exact capsule cross-section extruded along Y for each straight translation of the cylindrical envelope',
                         'segment_count':len(waypoints)-1,'boolean_pairs_tested':swept_tested,
                         'overlaps':swept_hits,'passed':not swept_hits,
                         'scope':'bare cylindrical envelope after listed prerequisites; excludes mounts, leads and tools'}
        results.append({'group':group,'waypoints_mm':[[p.x,p.y,p.z] for p in waypoints],'pose_count':len(poses),'removed_first':removed,'boolean_pairs_tested':tested,'overlaps':collisions,'continuous_translation_sweep':swept_check,
                        'passed':not collisions and (swept_check is None or swept_check['passed'])})
    return {'method':'8 discrete poses per straight segment; wet caps use lift-back-lift; arc envelopes lift 2 mm, move inward then up after tray removal, with continuous translation sweeps; USB plugs withdraw then lift with crown removed; other groups remain discrete; no tool/hand access certification','scenarios':results,'passed':all(r['passed'] for r in results),'physical_assembly_verified':False}
