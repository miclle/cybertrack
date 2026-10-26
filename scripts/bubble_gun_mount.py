"""One-piece front circular locator and rear stepped slot; conditional measured-datum fit.

Rear tab6x25x6.8 and resting-plane gap4.7 are user inputs. The10 mm front
slot is user requested; its19 mm length and the centred/flush placement are assumptions.
"""
import FreeCAD as App
import Part
from water_gun_mount import box, cylinder, rounded_route
from water_gun_layout import hits, bbox
V=App.Vector
BASE_Y=(-78,-62)
RING_Y=-125.5
HOSE_FIXED_COUNT=6
HOSE_POINTS=[(-28,65,154.5),(-28,65,174),(-99,65,174),(-99,10,174),(-99,10,94),
             (-99,-45,94),(-55,-45,101),(-55,-62,101)]
LEAD_POINTS=[(-44,-62,98),(-44,-44,98),(-58,-44,114),(-74,-44,114)]


def line_names(doc):
    return [o.Name for o in doc.Objects if o.Name in ('BubbleGunHoseRoute','BubbleGunLeadRoute',
        'BubbleGunLeadConnector','BubbleGunHoseClearance','BubbleGunLeadClearance',
        'BubbleGunHoseService','BubbleGunConnectorService')]


def cradle_primitives():
    return [box(-80,-82,85.95,-30,-59,88.95),box(-65,-127,85.95,-45,-81,88.95)]


def ring_shape():
    # One continuous ring, no parting line, ears or ring screws. Bore clearance
    # supports the tilted insertion path; glue is not included as a rigid CAD solid.
    ring=cylinder(19.5,3,(-55,-127,110),(0,1,0)).cut(cylinder(17,3,(-55,-127,110),(0,1,0)))
    return ring.fuse(box(-60,-127,88.95,-50,-124,92.5)).removeSplitter()


def body_service_poses():
    # Local module coordinates before the assembly elevation transform.
    poses=[]
    for i in range(31):poses.append((i*.5,(0,0,0)))
    for i in range(1,21):poses.append((15,(0,i*.5,0)))
    for i in range(1,7):poses.append((15,(0,10,i*.5)))
    for i in range(1,46):poses.append((15,(-i*2,10,3)))
    return poses


def body_service_shape(shape,angle,offset):
    s=shape.copy();s.rotate(V(-55,-125.5,110),V(1,0,0),angle);s.translate(V(*offset));return s


def slot_primitives():
    # Slots are open above. Step has0.3 longitudinal relief to the assumed shoulder.
    parts=[]
    for x0,x1 in [(-62.7,-60.2),(-49.8,-47.3)]:parts.append(box(x0,-105.7,88.95,x1,-86.7,96.05))
    for x0,x1 in [(-60.7,-58.2),(-51.8,-49.3)]:parts.append(box(x0,-86.7,88.95,x1,-61.7,96.05))
    parts.append(box(-60.7,-61.7,88.95,-49.3,-59.2,94.45))
    parts.append(box(-60,-108.8,88.95,-50,-106.3,94))
    # Bevel the open slot ends to clear the measured bottom section as the tail
    # rises; nominal6/10 widths remain at the seating plane.
    from build_tank import yz_prism
    for i,front in enumerate((-105.7,-105.7,-86.7,-86.7,-61.7)):
        relief=yz_prism([(-140,89.55),(front,89.55),(front+.7*(97-89.55),97),(-140,97)],-90,-20)
        parts[i]=parts[i].cut(relief).removeSplitter()
    return parts


def build_mount(doc,add):
    def cut(name,tool):
        obj=doc.getObject(name);obj.Shape=obj.Shape.cut(tool).removeSplitter()
    def feature(name,label,shape,category='structure',color='metal',group=None):
        obj=add(name,label,shape,category,color,'0.18：新支承面间距4.7；薄片不额外凸出；前环+两段槽，位置与配合公差为候选')
        if group:
            obj.addProperty('App::PropertyString','ServiceGroup','Assembly');obj.ServiceGroup=group
        assert shape.isValid() and len(shape.Solids)==1,name
        return obj
    parts=cradle_primitives();base=parts[0].fuse(parts[1])
    feature('BubbleGunCradle','泡泡枪底座／前圆环与阶梯槽',base.removeSplitter(),group='bubble_gun_cradle')
    for i,y in enumerate(BASE_Y,1):
        tag=str(i);x=-40
        boss=cylinder(5,9.95,(x,y,76)).cut(doc.getObject('KeelLid').Shape).cut(doc.getObject('LowerTub').Shape)
        rail=doc.getObject('ShoulderRailR');rail.Shape=rail.Shape.fuse(boss).removeSplitter()
        cut('ShoulderRailR',cylinder(2.3,6,(x,y,80)))
        cut('BubbleGunCradle',cylinder(1.6,4,(x,y,85.5)))
        cut('BubbleGunCradle',cylinder(2.8,1.6,(x,y,87.35)))
        insert=cylinder(2.2,5.5,(x,y,80.25)).cut(cylinder(1.6,5.5,(x,y,80.25)))
        feature('BubbleGunBaseInsert'+tag,'泡泡托架 M3 级嵌件 '+tag,insert,color='power')
        screw=cylinder(1.4,6,(x,y,81.5)).fuse(cylinder(2.6,1.2,(x,y,87.5)))
        feature('BubbleGunBaseScrew'+tag,'泡泡托架沉头位紧固候选 '+tag,screw)
        feature('BubbleGunBaseTool'+tag,'空托架基座批头空间 '+tag,cylinder(2.5,1.25,(x,y,88.7)).fuse(cylinder(4,38.75,(x,y,89.95))),category='clearance',color='power')
    feature('BubbleGunRing','前圆环整体／无分缝无紧固耳',ring_shape(),group='bubble_gun_cradle')
    for i,part in enumerate(slot_primitives(),1):
        feature('BubbleGunSlotWall'+str(i),'两段槽壁／后止挡 '+str(i),part,group='bubble_gun_cradle')
    floor=box(-59.8,-105.7,88.95,-50.2,-87,89.55).fuse(box(-57.8,-87,88.95,-52.2,-62,89.55)).removeSplitter()
    feature('BubbleGunLowerPadRear','阶梯槽底0.6垫／承托平面Z89.55',floor,color='dark',group='bubble_gun_cradle')
    hose=rounded_route(HOSE_POINTS,2,8);hose_space=rounded_route(HOSE_POINTS,4,8)
    feature('BubbleGunHoseRoute','泡泡顶部吸液管候选 Ø4／R8／侧向接前枪',hose,category='envelope',color='water')
    feature('BubbleGunHoseClearance','泡泡液管 Ø8 路线预留',hose_space,category='clearance',color='water')
    feature('BubbleGunHoseService','泡泡后端接管向后拔出25／Ø12空间',cylinder(6,25,(-55,-62,101),(0,1,0)),category='clearance',color='water')
    feature('BubbleGunLeadRoute','泡泡尾线束候选 Ø3／R8',rounded_route(LEAD_POINTS,1.5,8),category='envelope',color='power')
    feature('BubbleGunLeadClearance','泡泡尾线 Ø8 路线预留',rounded_route(LEAD_POINTS,4,8),category='clearance',color='power')
    feature('BubbleGunLeadConnector','泡泡插头候选16×10×10',box(-90,-49,109,-74,-39,119),category='envelope',color='power')
    feature('BubbleGunConnectorService','泡泡插头向外拔16／操作余量',box(-109,-52,106,-73.5,-36,122),category='clearance',color='power')
    approach=cylinder(6,30,(-35,-52,111),(0,1,0)).fuse(Part.makeSphere(6,V(-35,-22,111)))
    feature('BubbleGunStopAccess','原停止按钮前方 Ø12 指端接近候选／不含整手',approach,category='clearance',color='accent')
    return {'revision':'0.18','fixed_to':'ShoulderRailR; two integral diameter10 bosses',
        'mount_scheme':'one-piece full front ring plus stepped slot; adhesive-assisted locating candidate',
        'mounting_plane_z_mm':89.55,'muzzle_circle_bottom_above_plane_mm':4.7,
        'height_conflict_mm':0.4,'candidate_plane_to_muzzle_top_mm':36.2,
        'ring':{'bore_mm':34,'outer_diameter_mm':39,'axial_width_mm':3,'radial_clearance_mm':1.25,'one_piece':True,'ring_fasteners':0},
        'slot':{'rear_user_length_mm':25,'rear_user_width_mm':6,'front_user_nominal_width_mm':10,
                'rear_clear_width_mm':6.4,'front_clear_width_mm':10.4,'front_length_candidate_mm':19,
                'tab_height_mm':6.8,'lateral_clearance_each_side_mm':0.2,'floor_padding_mm':0.6,
                'centred_and_tail_flush':'assumed, not confirmed','front_foot_profile':'10x19x6.8 candidate; not measured'},
        'base_screw_centres_xy_mm':[[-40,y] for y in BASE_Y],
        'base_screws':2,'cap_screws':0,'fastener_grade':'M3 size candidates; threads, insert retention and lengths not specified',
        'hose':{'od_mm':4,'clearance_diameter_mm':8,'bend_centreline_radius_mm':8,'points_mm':HOSE_POINTS,'unplug_delta_mm':[0,25,0]},
        'lead':{'diameter_mm':3,'clearance_diameter_mm':8,'bend_centreline_radius_mm':8,'points_mm':LEAD_POINTS,'connector_size_mm':[16,10,10],'unplug_delta_mm':[-16,0,0]},
        'adhesive':{'user_authorized_auxiliary':True,'material_or_strength_specified':False,
                    'areas':'accessible annular gap and rear slot outer edges; avoid internal moving parts',
                    'must_be_removed_before_service':True,'physical_retention_verified':False},
        'sequence':['power off/drain; remove auxiliary adhesive; unplug lead then hose',
                    'raise tail by rotating15 degrees about ring centre in module frame',
                    'slide10 rearward out of ring; lift3 clear of slot; withdraw90 outboard',
                    'optional base screws +Z12; empty cradle +Z6 then -X90'],
        'clamp_load_materials_strain_relief_and_physical_fit_verified':False}


def box_sweep(shape,start,end):
    b=bbox(shape);lo=[b[i]+min(start[i],end[i]) for i in range(3)];hi=[b[i+3]+max(start[i],end[i]) for i in range(3)]
    return box(*lo,*hi)


def check_mount(doc):
    from bubble_gun_layout import NAMES
    physical=[o for o in doc.Objects if hasattr(o,'Category') and o.Category!='clearance']
    cradle=[o.Name for o in physical if getattr(o,'ServiceGroup','')=='bubble_gun_cradle']
    lines=line_names(doc);spaces=[]
    exclusions={'BubbleGunStopAccess':['StopControl'],'BubbleGunHoseClearance':['BubbleGunHoseRoute'],
        'BubbleGunLeadClearance':['BubbleGunLeadRoute'],'BubbleGunHoseService':['BubbleGunHoseRoute','BubbleGunLeadRoute'],
        'BubbleGunConnectorService':['BubbleGunLeadRoute','BubbleGunLeadConnector']}
    for i in (1,2):exclusions['BubbleGunBaseTool'+str(i)]=list(NAMES)+lines
    for name,excluded in exclusions.items():
        h=hits(doc.getObject(name).Shape,[o for o in physical if o.Name not in excluded])
        spaces.append({'name':name,'excluded':excluded,'overlaps':h,'passed':not h})
    results=[]
    def check(operation,sweeps,removed,method):
        obstacles=[o for o in physical if o.Name not in removed];clashes=[]
        for i,s in enumerate(sweeps):clashes += [{'segment_or_primitive':i,**h} for h in hits(s,obstacles)]
        results.append({'operation':operation,'method':method,'removed_or_moving':removed,'overlaps':clashes,'passed':not clashes})
    obstacles=[o for o in physical if o.Name not in list(NAMES)+lines]
    collisions=[];poses=body_service_poses()
    for index,(angle,offset) in enumerate(poses):
        for n in NAMES:
            shape=body_service_shape(doc.getObject(n).Shape,angle,offset)
            collisions += [{'pose_index':index,'moving':n,'rotation_x_deg':angle,'offset_mm':offset,**h} for h in hits(shape,obstacles)]
    results.append({'operation':'body_install_remove','method':'sampled actual schematic solids;0.5-degree rotation,0.5 mm rear/lift,2 mm lateral steps; not a continuous rotation proof',
        'removed_or_moving':list(NAMES)+lines,'pose_count':len(poses),'continuous':False,
        'overlaps':collisions,'passed':not collisions})
    for i,y in enumerate(BASE_Y,1):
        sweep=cylinder(1.4,18,(-40,y,81.5)).fuse(cylinder(2.6,13.2,(-40,y,87.5)))
        check('base_screw_'+str(i),[sweep],list(NAMES)+lines+['BubbleGunBaseScrew'+str(i)],'+Z12 after body removal')
    parts=cradle_primitives()+[doc.getObject(n).Shape for n in cradle if n!='BubbleGunCradle']
    sweeps=[box_sweep(p,a,b) for a,b in [((0,0,0),(0,0,6)),((0,0,6),(-90,0,6))] for p in parts]
    check('empty_cradle',sweeps,list(NAMES)+lines+cradle+['BubbleGunBaseScrew1','BubbleGunBaseScrew2'],'per-material conservative boxes +Z6 then -X90')
    check('front_outlet_clearance',[cylinder(18,50,(-55,-129,110),(0,-1,0))],list(NAMES),'diameter36 x50 forward corridor; not flow validation')
    return {'service_spaces':spaces,'continuous_service_sweeps':results,'passed':all(x['passed'] for x in spaces+results),
        'tool_scope':'no front-ring tools; base tip5x1.25 then8x38.75 after body removal; no complete hands/handles',
        'stop_access_scope':'diameter12 fingertip from front; current BOOT seat also checks 1.5 mm press; not whole-hand acceptance',
        'contact_and_removal_profiles_assumed':True,'physical_fit_verified':False}
