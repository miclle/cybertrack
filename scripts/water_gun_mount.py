"""Reversible water-gun cradle and service space candidates; no release dimensions.

Bottom double-sided soft adhesive is user selected; its thickness, footprint,
fasteners, cable sizes and bend radii remain assumptions. Hose OD5 is user measured.
The measured gun is never drilled or cut to manufacture a passing fit.
"""
import math
import FreeCAD as App
import Part
from water_gun_layout import ORIGIN, WIDTH, THICKNESS
V = App.Vector

# Keep the gun pose fixed when reviewing another adhesive thickness.
ADHESIVE_THICKNESS = 1.0
BODY_BOTTOM = ORIGIN[2]-THICKNESS/2
CRADLE_TOP = BODY_BOTTOM-ADHESIVE_THICKNESS
CRADLE_BOTTOM = CRADLE_TOP-3.0
SIDE_GAP, SIDE_WALL_THICKNESS, SIDE_WALL_HEIGHT = 0.6, 2.0, 20.0
SIDE_X0, SIDE_X1 = ORIGIN[0]-WIDTH/2-SIDE_GAP, ORIGIN[0]+WIDTH/2+SIDE_GAP
BASE_X0, BASE_X1 = SIDE_X0-SIDE_WALL_THICKNESS, SIDE_X1+SIDE_WALL_THICKNESS


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
# Top-fed reservoir segment stays fixed; the final five points follow the gun tilt.
HOSE_FIXED_COUNT=5
HOSE_POINTS=[(-24,49,45),(-24,49,149),(-24,70,149),(99,70,149),(99,10,149),
             (78.2,6,117),(78.2,-75,117),(90,-90,117),(90,-105,117),(76.9,-105,117)]
LEAD_POINTS=[(55,9.5,117),(55,21.5,117),(83,21.5,117)]
ADHESIVE_CENTRES=(-62,-10)
BASE_CENTRES=(-60,-18)
HOSE_SUPPORTS=[('WaterGunHoseSupport',-64),('WaterGunHoseSupportRear',-12)]


def hose_shapes():
    return rounded_route(HOSE_POINTS,2.5,8), rounded_route(HOSE_POINTS,4,8)


def lead_guide_shape():
    guide=box(76,16.5,CRADLE_TOP,82,26.5,120.5)
    guide=guide.cut(cylinder(2.3,7,(75.5,21.5,117),(1,0,0)))
    guide=guide.cut(box(75.5,19.8,117,82.5,23.2,121))
    # Slots for a future removable tie, not a claim of certified strain relief.
    for y in (17.4,24.6):guide=guide.cut(box(75.5,y,106,82.5,y+.8,109))
    return guide.removeSplitter()


def cradle_primitives():
    parts=[box(BASE_X0,-72,CRADLE_BOTTOM,BASE_X1,2,CRADLE_TOP),
           box(70.6,-2,CRADLE_BOTTOM,82,26,CRADLE_TOP)]
    # Front/rear pairs locate the housing laterally; no overhanging lip or
    # screw holes. Adhesive remains the retention method.
    for y in ADHESIVE_CENTRES:
        parts += [box(BASE_X0,y-6,CRADLE_TOP,SIDE_X0,y+6,CRADLE_TOP+SIDE_WALL_HEIGHT),
                  box(SIDE_X1,y-6,CRADLE_TOP,BASE_X1,y+6,CRADLE_TOP+SIDE_WALL_HEIGHT)]
    for x0,x1 in ((39,47),(63,72)):
        parts += [box(x0,1,CRADLE_BOTTOM,x1,12,CRADLE_TOP),
                  box(x0,10,CRADLE_TOP,x1,12,CRADLE_TOP+8)]
    parts.append(lead_guide_shape())
    return parts


def build_mount(doc,add):
    def cut(name,tool):
        obj=doc.getObject(name);obj.Shape=obj.Shape.cut(tool).removeSplitter()
    def feature(name,label,shape,category='structure',color='metal',group=None):
        obj=add(name,label,shape,category,color,
                '候选尺寸：胶厚、粘接面、M3级基座紧固、引线均未实测；水管外径5为用户实测；不在原水枪上钻孔')
        if group is None and name.startswith(('WaterGunCradle','WaterGunLowerPad','WaterGunHoseSupport')):
            group='water_gun_cradle'
        if group:
            obj.addProperty('App::PropertyString','ServiceGroup','Assembly');obj.ServiceGroup=group
        assert obj.Shape.isValid() and len(obj.Shape.Solids)==1,name
        return obj
    parts=cradle_primitives()
    base=parts[0]
    for part in parts[1:]:base=base.fuse(part)
    feature('WaterGunCradle','水枪一体底托／左右挡板／尾线导向鞍／前开口',base.removeSplitter())
    for index,y in enumerate(BASE_CENTRES):
        tag=str(index+1);x=42.5
        z0=84 if index==0 else 90
        boss=cylinder(5,CRADLE_BOTTOM-z0,(x,y,z0)).cut(doc.getObject('KeelLid').Shape).cut(doc.getObject('LowerTub').Shape)
        rail=doc.getObject('ShoulderRailL')
        rail.Shape=rail.Shape.fuse(boss).removeSplitter()
        cut('ShoulderRailL',cylinder(2.3,6,(x,y,CRADLE_BOTTOM-5.9)))
        cut('WaterGunCradle',cylinder(1.6,4,(x,y,CRADLE_BOTTOM-.2)))
        cut('WaterGunCradle',cylinder(2.8,2,(x,y,CRADLE_BOTTOM+1.3)))
        insert=cylinder(2.2,5.5,(x,y,CRADLE_BOTTOM-5.7)).cut(cylinder(1.6,5.5,(x,y,CRADLE_BOTTOM-5.7)))
        feature('WaterGunBaseInsert'+tag,'托架基座 M3 级嵌件候选 '+tag,insert,color='power')
        screw=cylinder(1.4,6,(x,y,CRADLE_BOTTOM-4.5)).fuse(cylinder(2.6,1.3,(x,y,CRADLE_BOTTOM+1.5)))
        feature('WaterGunBaseScrew'+tag,'托架沉入式紧固候选 '+tag,screw)
        # Short L-key: narrow tip through the pad, then a 6 mm shank corridor
        # opening toward the front after the gun has been detached and removed.
        tool=cylinder(1.5,3.5,(x,y,CRADLE_BOTTOM+2.8)).fuse(cylinder(3,8,(x,y,CRADLE_BOTTOM+6.3)))
        tool=tool.fuse(cylinder(3,40,(x,y,CRADLE_BOTTOM+14.3),(0,-1,0))).fuse(Part.makeSphere(3,V(x,y,CRADLE_BOTTOM+14.3))).removeSplitter()
        feature('WaterGunBaseTool'+tag,'空托架基座短臂内六角操作空间 '+tag,tool,category='clearance',color='power')
    for index,y in enumerate(ADHESIVE_CENTRES):
        tag=str(index+1)
        bottom=box(39.4,y-10,CRADLE_TOP,70.6,y+10,BODY_BOTTOM)
        # Leave the base screw accesses clear of tape. Adhesive release itself
        # is a prerequisite, not simulated as a rigid-body motion.
        for by in BASE_CENTRES:bottom=bottom.cut(cylinder(3,ADHESIVE_THICKNESS+.4,(42.5,by,CRADLE_TOP-.2)))
        feature('WaterGunLowerPad'+tag,'底部双面软胶候选／厚度未测 '+tag,bottom,color='dark')
    lead=rounded_route(LEAD_POINTS,1.5,8)
    feature('WaterGunLeadRoute','水枪尾线束候选 Ø3／中心弯曲半径8',lead,category='envelope',color='power')
    feature('WaterGunLeadClearance','尾线 Ø8 走线审查区／不含手部',
            rounded_route(LEAD_POINTS,4,8),category='clearance',color='power')
    connector=box(83,16.5,112,99,26.5,122)
    feature('WaterGunLeadConnector','水枪可分离插头包络 16×10×10／型号未定',connector,category='envelope',color='power')
    feature('WaterGunConnectorService','尾线插头外拔16及侧面操作余量',
            box(82.5,13.5,109,115,29.5,125),category='clearance',color='power')
    # Two open saddles sit flush against the outer locating walls.
    for name,y in HOSE_SUPPORTS:
        saddle=cylinder(4.3,6,(78.2,y-3,117),(0,1,0))
        saddle=saddle.cut(cylinder(2.8,8,(78.2,y-4,117),(0,1,0)))
        saddle=saddle.cut(box(75.4,y-4,117,81.0,y+4,123))
        saddle=saddle.cut(box(70,y-4,110,BASE_X1,y+4,124))
        feature(name,('外侧前' if y==-64 else '外侧后')+'挡板托管座／Ø5管／Ø5.6上开口',
                saddle.removeSplitter(),color='metal')
    _,hose_space=hose_shapes()
    feature('WaterGunHoseClearance','水管 Ø8 路线预留／中心弯曲半径8候选',hose_space,category='clearance',color='water')
    feature('WaterGunHoseService','侧接管沿 +X 拔出30／操作直径16候选',
            cylinder(8,30,(76.9,-105,117),(1,0,0)),category='clearance',color='water')
    return {'candidate_revision':'0.25','retention':'user-selected double-sided soft adhesive under gun; no mechanical top clamp',
            'fixed_to':'ShoulderRailL; two integral 10 mm bosses with M3 candidate inserts',
            'base_screws':2,'cap_screws':0,
            'base_screw_centres_xy_mm':[[42.5,y] for y in BASE_CENTRES],
            'adhesive':{'thickness_mm':ADHESIVE_THICKNESS,'thickness_measured':False,
                'patches':2,'patch_bbox_xy_mm':[31.2,20],'centres_y_mm':list(ADHESIVE_CENTRES),
                'base_screw_access_cutouts_diameter_mm':6,'grade_or_strength_selected':False},
            'base':{'main_width_mm':BASE_X1-BASE_X0,'main_length_mm':74,'thickness_mm':3,
                'side_margin_to_maximum_housing_mm':SIDE_GAP+SIDE_WALL_THICKNESS,'rear_stop_gap_mm':.5},
            'side_walls':{'pairs':2,'centres_y_mm':list(ADHESIVE_CENTRES),'length_mm':12,
                'height_above_base_mm':SIDE_WALL_HEIGHT,'thickness_mm':SIDE_WALL_THICKNESS,
                'channel_width_mm':SIDE_X1-SIDE_X0,'nominal_side_gap_mm':SIDE_GAP,'top_lips_or_fasteners':False},
            'hose':{'measured_od_mm':5,'measurement_source':'user 2026-10-24','routing':'top-inserted suction tube via side route and two saddles; no rear-armor passage','route_clearance_diameter_mm':8,'centreline_bend_radius_mm':8,'unplug_direction_mm':[30,0,0]},
            'hose_support':{'attached_to':'front and rear outer side walls','quantity':2,'integral_with_cradle':True,
                'centres_module_mm':[[78.2,y,117] for _,y in HOSE_SUPPORTS],'centre_spacing_mm':52,'flush_to_outer_wall':True,'support_arm':False,'axial_length_mm':6,'seat_diameter_mm':5.6,
                'nominal_radial_gap_mm':.3,'outer_diameter_mm':8.6,'opening':'module +Z',
                'retaining_clip_or_strain_relief_verified':False},
            'leads':{'guide_integral_with_cradle':True,'assumed_bundle_diameter_mm':3,'route_clearance_diameter_mm':8,'centreline_bend_radius_mm':8,
                     'connector_size_xyz_mm':[16,10,10],'connector_unplug_direction_mm':[16,0,0]},
            'sequence':['power off and drain','withdraw hose +X 30 and lift hose out of both open saddles, unplug tail connector +X 16, release guide tie and flexible lines',
                        'fully release adhesive bond; release method and access not verified',
                        'lift gun along module +Z 2 then pull forward -Y 150',
                        'optional: use short L-key from the front to remove 2 base screws, lift empty cradle +Z 2 then move +X 60'],
            'contact_surfaces_fasteners_bends_and_materials_assumed':True,
            'adhesive_retention_release_strain_relief_and_physical_fit_verified':False}


def removable_line_names(doc):
    return [o.Name for o in doc.Objects if o.Name in ('WaterHoseRoute','WaterGunLeadRoute','WaterGunLeadConnector',
            'WaterGunHoseClearance','WaterGunHoseService','WaterGunLeadClearance','WaterGunConnectorService')]


def check_mount(doc):
    from water_gun_layout import hits, bbox
    fit=[]
    body=doc.getObject('WaterGunBody').Shape
    for tag in ('1','2'):
        pad=doc.getObject('WaterGunLowerPad'+tag).Shape
        pb=bbox(pad)
        thickness=pb[5]-pb[2]
        top=pad.common(Part.makePlane(100,150,V(20,-100,BODY_BOTTOM)))
        area=top.Area
        contact=top.common(body).Area
        fit.append({'patch':int(tag),'thickness_mm':thickness,'nominal_top_area_mm2':area,
                    'nominal_body_contact_area_mm2':contact,
                    'passed':abs(thickness-ADHESIVE_THICKNESS)<1e-6 and area>0 and abs(area-contact)<1e-5})
    physical=[o for o in doc.Objects if hasattr(o,'Category') and o.Category!='clearance']
    spaces=[]
    exclusions={
        'WaterGunHoseClearance':['WaterHoseRoute']+[name for name,_ in HOSE_SUPPORTS],
        'WaterGunLeadClearance':['WaterGunLeadRoute'],
        'WaterGunHoseService':['WaterHoseRoute'],
        'WaterGunConnectorService':['WaterGunLeadRoute','WaterGunLeadConnector'],
    }
    removed_for_base=['WaterGunBody','WaterGunInlet','WaterHoseRoute','WaterGunLeadRoute','WaterGunLeadConnector']
    exclusions['WaterGunBaseTool1']=removed_for_base
    exclusions['WaterGunBaseTool2']=removed_for_base
    for name,excluded in exclusions.items():
        space=doc.getObject(name).Shape
        # Permit only the known guide material, not the rest of the now-integral cradle.
        intentional=lead_guide_shape() if name=='WaterGunLeadClearance' else None
        if intentional is not None:space=space.cut(intentional)
        overlaps=hits(space,[o for o in physical if o.Name not in excluded])
        spaces.append({'name':name,'excluded':excluded,
                       'excluded_material':'integrated tail guide only' if intentional is not None else None,
                       'overlaps':overlaps,'passed':not overlaps})
    # Exact capsule sweeps through each open saddle. The remaining flexible
    # hose is not treated as a rigid part or certified by these local checks.
    results=[]
    tube=doc.getObject('WaterHoseRoute').Shape
    for name,y in HOSE_SUPPORTS:
        lift=cylinder(2.5,6,(78.2,y-3,117),(0,1,0)).fuse(cylinder(2.5,6,(78.2,y-3,127),(0,1,0)))
        lift=lift.fuse(box(75.7,y-3,117,80.7,y+3,127)).removeSplitter()
        overlaps=hits(lift,[o for o in physical if o.Name!='WaterHoseRoute'])
        gap=tube.distToShape(doc.getObject(name).Shape)[0]
        results.append({'operation':'hose_local_lift_from_saddle','support':name,'translation_module_mm':[0,0,10],
              'method':'exact continuous capsule sweep of 6 mm straight hose section only',
              'measured_hose_od_mm':5,'seat_diameter_mm':5.6,'minimum_tube_support_gap_mm':gap,
              'overlaps':overlaps,'passed':not overlaps and gap>=.3-1e-5})
    # Empty support after the gun is detached and removed.
    parts=cradle_primitives()
    cradle=[o for o in physical if getattr(o,'ServiceGroup','')=='water_gun_cradle']
    parts += [o.Shape for o in cradle if o.Name!='WaterGunCradle']
    removed=removable_line_names(doc)+['WaterGunBody','WaterGunInlet','WaterGunBaseScrew1','WaterGunBaseScrew2']
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
    return {'adhesive_contact_checks':fit,'service_spaces':spaces,'continuous_service_sweeps':results,
            'passed':all(x['passed'] for x in fit+spaces+results),
            'intended_contacts':'adhesive nominally bridges gun bottom and support top; side walls and rear stops locate only and do not prove adhesive retention',
            'tool_scope':'base short L-key tip diameter 3, shank diameter 6, front arm 40; hands not covered',
            'adhesive_retention_release_hose_pressure_wire_flex_and_physical_fit_verified':False}
