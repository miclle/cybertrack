"""Reversible water-gun cradle and service space candidates; no release dimensions.

Clamp locations, padding, fasteners, hose/cable sizes and bend radii are assumptions.
The measured gun is never drilled or cut to manufacture a passing fit.
"""
import math
import FreeCAD as App
import Part
V = App.Vector


def box(x0, y0, z0, x1, y1, z1):
    return Part.makeBox(x1-x0, y1-y0, z1-z0, V(x0,y0,z0))


def cylinder(radius, length, start, axis=(0,0,1)):
    return Part.makeCylinder(radius,length,V(*start),V(*axis))


def rounded_route(points, radius, bend_radius):
    """Circular section on tangent lines and exact circular fillets in 3D."""
    p = [V(*q) for q in points]
    entry, exit_, mids, trims = {}, {}, {}, {}
    for i in range(1,len(p)-1):
        incoming=p[i]-p[i-1];incoming.normalize()
        outgoing=p[i+1]-p[i];outgoing.normalize()
        theta=math.acos(max(-1,min(1,incoming.dot(outgoing))))
        assert 1e-6 < theta < math.pi-1e-6
        trim=bend_radius*math.tan(theta/2)
        entry[i]=p[i]-incoming*trim;exit_[i]=p[i]+outgoing*trim
        bisector=outgoing-incoming;bisector.normalize()
        centre=p[i]+bisector*(bend_radius/math.cos(theta/2))
        radial=(entry[i]-centre)+(exit_[i]-centre);radial.normalize()
        mids[i]=centre+radial*bend_radius;trims[i]=trim
    for i in range(len(p)-1):
        assert trims.get(i,0)+trims.get(i+1,0) < (p[i+1]-p[i]).Length, (i,'Bends too close')
    edges=[];last=p[0]
    for i in range(1,len(p)-1):
        edges.append(Part.makeLine(last,entry[i]))
        edges.append(Part.Arc(entry[i],mids[i],exit_[i]).toShape());last=exit_[i]
    edges.append(Part.makeLine(last,p[-1]))
    path=Part.Wire(edges)
    profile=Part.Wire([Part.makeCircle(radius,p[0],p[1]-p[0])])
    shape=path.makePipeShell([profile],True,False)
    assert shape.isValid() and len(shape.Solids)==1
    return shape


# Radius is a packaging assumption, not a supplier minimum bend specification.
HOSE_POINTS=[(-24,39,118),(-24,22,118),(-39,15,119),(-45,5,119),
             (-45,-80,99.5),(90,-80,99.5),(90,-80,117),(90,-105,117),(76.9,-105,117)]
LEAD_POINTS=[(55,9.5,117),(55,21.5,117),(83,21.5,117)]
CAP_CENTRES=(-62,-10)
BASE_CENTRES=(-60,-18)


def hose_shapes():
    return rounded_route(HOSE_POINTS,2,8), rounded_route(HOSE_POINTS,4,8)


def build_mount(doc,add):
    def cut(name,tool):
        obj=doc.getObject(name);obj.Shape=obj.Shape.cut(tool).removeSplitter()
    def feature(name,label,shape,category='structure',color='metal',group=None):
        obj=add(name,label,shape,category,color,
                '候选尺寸：夹持面、垫片、M3级紧固、管径与引线均未实测；不在原水枪上钻孔')
        if group is None and name.startswith(('WaterGunCradle','WaterGunLowerPad','WaterGunInnerPad','WaterGunCapInsert','WaterGunLeadGuide')):
            group='water_gun_cradle'
        if group:
            obj.addProperty('App::PropertyString','ServiceGroup','Assembly');obj.ServiceGroup=group
        assert obj.Shape.isValid() and len(obj.Shape.Solids)==1,name
        return obj
    base=box(35.8,-72,100.7,80.5,2,103.7)
    # Narrow rear outrigger supports an open cable guide, away from the backpack.
    base=base.fuse(box(76,-2,100.7,82,26,103.7))
    for y in CAP_CENTRES:
        inner=box(35.8,y-6,103.7,37.8,y+6,134)
        lip=box(37.8,y-6,132.5,40.5,y+6,134)
        outer=box(77.5,y-6,103.7,80.5,y+6,129.1)
        base=base.fuse(inner).fuse(lip).fuse(outer)
    # Rear stops leave the centre clear for the tail leads. Forward retention is
    # by the padded clamps; no unmeasured front shoulder is treated as a datum.
    for x0,x1 in ((39,47),(63,72)):
        base=base.fuse(box(x0,1,100.7,x1,12,103.7)).fuse(box(x0,10,103.7,x1,12,111.7))
    feature('WaterGunCradle','水枪固定托架／前开口／后端双止挡',base.removeSplitter())
    for index,y in enumerate(BASE_CENTRES):
        tag=str(index+1);x=42.5
        z0=84 if index==0 else 90
        boss=cylinder(5,100.7-z0,(x,y,z0)).cut(doc.getObject('KeelLid').Shape).cut(doc.getObject('LowerTub').Shape)
        rail=doc.getObject('ShoulderRailL')
        rail.Shape=rail.Shape.fuse(boss).removeSplitter()
        cut('ShoulderRailL',cylinder(2.3,6,(x,y,94.8)))
        cut('WaterGunCradle',cylinder(1.6,4,(x,y,100.5)))
        cut('WaterGunCradle',cylinder(2.8,2,(x,y,102)))
        insert=cylinder(2.2,5.5,(x,y,95)).cut(cylinder(1.6,5.5,(x,y,95)))
        feature('WaterGunBaseInsert'+tag,'托架基座 M3 级嵌件候选 '+tag,insert,color='power')
        screw=cylinder(1.4,6,(x,y,96.2)).fuse(cylinder(2.6,1.3,(x,y,102.2)))
        feature('WaterGunBaseScrew'+tag,'托架沉入式紧固候选 '+tag,screw)
        # Short L-key: narrow tip through the pad, then a 6 mm shank corridor
        # opening toward the front after the gun and caps have been removed.
        tool=cylinder(1.5,3.5,(x,y,103.5)).fuse(cylinder(3,8,(x,y,107)))
        tool=tool.fuse(cylinder(3,40,(x,y,115),(0,-1,0))).fuse(Part.makeSphere(3,V(x,y,115))).removeSplitter()
        feature('WaterGunBaseTool'+tag,'空托架基座短臂内六角操作空间 '+tag,tool,category='clearance',color='power')
    for index,y in enumerate(CAP_CENTRES):
        tag=str(index+1)
        bottom=box(39.4,y-5,103.7,70.6,y+5,104.7)
        # Access to the base screw after the gun has been withdrawn.
        for by in BASE_CENTRES:bottom=bottom.cut(cylinder(3,2,(42.5,by,103.5)))
        feature('WaterGunLowerPad'+tag,'水枪底部 1 mm 软垫候选 '+tag,bottom,color='dark')
        feature('WaterGunInnerPad'+tag,'内侧 0.6 mm 定位软垫候选 '+tag,
                box(37.8,y-5,110,38.4,y+5,124),color='dark')
        cap=box(38,y-5,130.3,83.5,y+5,132.3).fuse(box(80.5,y-5,122.5,83.5,y+5,130.3))
        cap=cap.cut(cylinder(1.6,8,(77,y,125.5),(1,0,0)))
        feature('WaterGunCap'+tag,'侧向抽出的水枪压盖 '+tag,cap.removeSplitter(),group='water_gun_caps')
        feature('WaterGunUpperPad'+tag,'随压盖拆出的 1 mm 上垫 '+tag,
                box(39.4,y-5,129.3,70.6,y+5,130.3),color='dark',group='water_gun_caps')
        cut('WaterGunCradle',cylinder(2.3,3.1,(77.45,y,125.5),(1,0,0)))
        insert=cylinder(2.2,2.8,(77.6,y,125.5),(1,0,0)).cut(cylinder(1.6,2.8,(77.6,y,125.5),(1,0,0)))
        feature('WaterGunCapInsert'+tag,'压盖横向 M3 级嵌件候选 '+tag,insert,color='power')
        screw=cylinder(1.4,5.8,(77.7,y,125.5),(1,0,0)).fuse(cylinder(2.5,2,(83.5,y,125.5),(1,0,0)))
        feature('WaterGunCapScrew'+tag,'压盖外侧操作紧固件 '+tag,screw,group='water_gun_cap_screws')
        feature('WaterGunCapTool'+tag,'压盖批头工具直线空间 Ø10×30 '+tag,
                cylinder(5,30,(85.5,y,125.5),(1,0,0)),category='clearance',color='power')
    lead=rounded_route(LEAD_POINTS,1.5,8)
    feature('WaterGunLeadRoute','水枪尾线束候选 Ø3／中心弯曲半径8',lead,category='envelope',color='power')
    feature('WaterGunLeadClearance','尾线 Ø8 走线审查区／不含手部',
            rounded_route(LEAD_POINTS,4,8),category='clearance',color='power')
    connector=box(83,16.5,112,99,26.5,122)
    feature('WaterGunLeadConnector','水枪可分离插头包络 16×10×10／型号未定',connector,category='envelope',color='power')
    feature('WaterGunConnectorService','尾线插头外拔16及侧面操作余量',
            box(82.5,13.5,109,115,29.5,125),category='clearance',color='power')
    guide=box(76,16.5,103.7,82,26.5,120.5)
    guide=guide.cut(cylinder(2.3,7,(75.5,21.5,117),(1,0,0)))
    guide=guide.cut(box(75.5,19.8,117,82.5,23.2,121))
    # Slots for a future removable tie, not a claim of certified strain relief.
    for y in (17.4,24.6):guide=guide.cut(box(75.5,y,106,82.5,y+.8,109))
    feature('WaterGunLeadGuide','尾线开放导向鞍／扎带槽候选',guide.removeSplitter(),color='dark')
    _,hose_space=hose_shapes()
    feature('WaterGunHoseClearance','水管 Ø8 路线预留／中心弯曲半径8候选',hose_space,category='clearance',color='water')
    feature('WaterGunHoseService','侧接管沿 +X 拔出30／操作直径16候选',
            cylinder(8,30,(76.9,-105,117),(1,0,0)),category='clearance',color='water')
    return {'candidate_revision':'0.13','fixed_to':'ShoulderRailL; two integral 10 mm bosses with M3 candidate inserts',
            'base_screws':2,'cap_screws':2,'cap_centres_y_mm':list(CAP_CENTRES),
            'base_screw_centres_xy_mm':[[42.5,y] for y in BASE_CENTRES],
            'padding_mm':{'top':1,'bottom':1,'inner_side':.6},
            'gun_play_nominal_mm':{'bare_inner_side':.6,'top_with_pad':0,'bottom_with_pad':0,'rear_stop':.5},
            'hose':{'assumed_od_mm':4,'route_clearance_diameter_mm':8,'centreline_bend_radius_mm':8,'unplug_direction_mm':[30,0,0]},
            'leads':{'assumed_bundle_diameter_mm':3,'route_clearance_diameter_mm':8,'centreline_bend_radius_mm':8,
                     'connector_size_xyz_mm':[16,10,10],'connector_unplug_direction_mm':[16,0,0]},
            'sequence':['power off and drain','withdraw hose +X 30, unplug tail connector +X 16, release guide tie and flexible lines',
                        'withdraw 2 cap screws +X 20','slide both caps and upper pads +X 50','pull gun forward -Y 150',
                        'optional: use short L-key from the front to remove 2 base screws, lift empty cradle +Z 2 then move +X 60'],
            'contact_surfaces_fasteners_bends_and_materials_assumed':True,
            'strength_clamp_load_strain_relief_and_physical_fit_verified':False}


def removable_line_names(doc):
    return [o.Name for o in doc.Objects if o.Name in ('WaterHoseRoute','WaterGunLeadRoute','WaterGunLeadConnector',
            'WaterGunHoseClearance','WaterGunHoseService','WaterGunLeadClearance','WaterGunConnectorService')]


def check_mount(doc):
    from water_gun_layout import hits, bbox
    physical=[o for o in doc.Objects if hasattr(o,'Category') and o.Category!='clearance']
    spaces=[]
    exclusions={
        'WaterGunHoseClearance':['WaterHoseRoute'],
        'WaterGunLeadClearance':['WaterGunLeadRoute','WaterGunLeadGuide'],
        'WaterGunHoseService':['WaterHoseRoute'],
        'WaterGunConnectorService':['WaterGunLeadRoute','WaterGunLeadConnector'],
        'WaterGunCapTool1':[], 'WaterGunCapTool2':[],
    }
    removed_for_base=['WaterGunBody','WaterGunInlet','WaterHoseRoute','WaterGunLeadRoute','WaterGunLeadConnector']
    removed_for_base += [o.Name for o in physical if getattr(o,'ServiceGroup','') in ('water_gun_caps','water_gun_cap_screws')]
    exclusions['WaterGunBaseTool1']=removed_for_base
    exclusions['WaterGunBaseTool2']=removed_for_base
    for name,excluded in exclusions.items():
        overlaps=hits(doc.getObject(name).Shape,[o for o in physical if o.Name not in excluded])
        spaces.append({'name':name,'excluded':excluded,'overlaps':overlaps,'passed':not overlaps})
    results=[]
    caps=[o.Name for o in physical if getattr(o,'ServiceGroup','')=='water_gun_caps']
    screws=[o.Name for o in physical if getattr(o,'ServiceGroup','')=='water_gun_cap_screws']
    for index,y in enumerate(CAP_CENTRES):
        # Exact axial sweeps of the simplified screw (shaft and head separately).
        sweep=cylinder(1.4,25.8,(77.7,y,125.5),(1,0,0)).fuse(cylinder(2.5,22,(83.5,y,125.5),(1,0,0)))
        overlap=hits(sweep,[o for o in physical if o.Name!='WaterGunCapScrew'+str(index+1)])
        results.append({'operation':'cap_screw_'+str(index+1),'delta_mm':[20,0,0],
                        'method':'continuous axial shaft and head sweeps','moving':['WaterGunCapScrew'+str(index+1)],'removed_first':[],
                        'overlaps':overlap,'passed':not overlap})
        # Unbored cap primitives form a conservative continuous sweep; avoids
        # falsely filling the entire L-shaped cap with its rectangular bbox.
        top=box(38,y-5,130.3,133.5,y+5,132.3)
        leg=box(80.5,y-5,122.5,133.5,y+5,130.3)
        pad=box(39.4,y-5,129.3,120.6,y+5,130.3)
        overlap=hits(top.fuse(leg).fuse(pad),[o for o in physical if o.Name not in screws+caps])
        results.append({'operation':'cap_and_pad_'+str(index+1),'delta_mm':[50,0,0],
                        'method':'continuous union of unbored cap material primitives and upper pad',
                        'moving':caps,'removed_first':screws,'overlaps':overlap,'passed':not overlap})
    # Optional empty cradle removal: conservative bounds per material primitive.
    parts=[box(35.8,-72,100.7,80.5,2,103.7),box(76,-2,100.7,82,26,103.7)]
    for y in CAP_CENTRES:
        parts += [box(35.8,y-6,103.7,37.8,y+6,134),box(37.8,y-6,132.5,40.5,y+6,134),
                  box(77.5,y-6,103.7,80.5,y+6,129.1)]
    for x0,x1 in ((39,47),(63,72)):parts.append(box(x0,1,100.7,x1,12,111.7))
    cradle=[o for o in physical if getattr(o,'ServiceGroup','')=='water_gun_cradle']
    parts += [o.Shape for o in cradle if o.Name!='WaterGunCradle']
    removed=caps+screws+removable_line_names(doc)+['WaterGunBody','WaterGunInlet','WaterGunBaseScrew1','WaterGunBaseScrew2']
    excluded=removed+[o.Name for o in cradle]
    obstacles=[o for o in physical if o.Name not in excluded]
    overlaps=[]
    for start,end in [((0,0,0),(0,0,2)),((0,0,2),(60,0,2))]:
        for i,shape in enumerate(parts):
            b=bbox(shape)
            lo=[b[j]+min(start[j],end[j]) for j in range(3)]
            hi=[b[j+3]+max(start[j],end[j]) for j in range(3)]
            sweep=box(*lo,*hi)
            for hit in hits(sweep,obstacles):
                overlaps.append({'primitive':i,'start_mm':start,'end_mm':end,**hit})
    results.append({'operation':'empty_cradle','waypoints_mm':[[0,0,0],[0,0,2],[60,0,2]],
                    'method':'conservative continuous AABB sweeps of individual material primitives',
                    'removed_first':removed,'overlaps':overlaps,'passed':not overlaps})
    return {'service_spaces':spaces,'continuous_service_sweeps':results,
            'passed':all(x['passed'] for x in spaces+results),
            'intended_contacts':'upper/lower/inner pads contact nominal measured body faces; cap flange and saddle mounting faces contact without volume overlap',
            'tool_scope':'cap screwdriver shank diameter 10, length 30; base short L-key tip diameter 3, shank diameter 6, front arm 40; hands not covered',
            'hose_pressure_wire_flex_clamp_preload_strength_and_physical_fit_verified':False}
