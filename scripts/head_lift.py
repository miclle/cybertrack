"""0.37 rigid head lift and extended fixed neck; dimensions are CAD candidates."""
import FreeCAD as A
import Part
V = A.Vector
LIFT = 25.0
HEAD_PREFIXES = ('Head', 'Visor', 'BrowArmor', 'CheekArmor', 'Jaw', 'Audio',
                 'Ear', 'Crown', 'Temple', 'Occipital', 'Sensor', 'Ultrasonic',
                 'Electronics', 'ArcModule', 'Tray', 'ESP32', 'Controller', 'Breadboard')


def head_members(doc):
    return [o for o in doc.Objects if hasattr(o, 'Category') and o.Name.startswith(HEAD_PREFIXES)]


def add_neck(doc, add):
    from build_tank import box, footprint, yz_prism, strut, ring
    # Retain lower attachment points; extend the web between lower and upper bosses.
    def z(value):
        return value - 4 + LIFT * max(0, min(1, (value - 106) / 22))
    def profile(points):
        return [(y, z(h)) for y, h in points]
    def endpoints(sign):
        start = V(sign*12, 16, 97)
        end = V(sign*12, 2, 133 + LIFT)
        sleeve_end = start + (end-start)*.38
        return tuple(start), tuple(end), tuple(sleeve_end)
    pedestal = Part.Face(footprint(17,-17,20,6,93)).extrude(V(0,0,5))
    for sign in (-1,1):
        start,end,sleeve_end = endpoints(sign)
        pedestal = pedestal.cut(strut(4.8,start,sleeve_end))
    add('NeckPedestal','颈架八角基座／斜撑沉座',pedestal,'structure','dark')
    for side,sign in [('L',1),('R',-1)]:
        x0,x1 = (18,25) if sign>0 else (-25,-18)
        web = yz_prism(profile([(-9,97),(19,97),(22,105),(7,134),(-3,140),(-25,140),(-28,132),(-16,106)]),x0,x1)
        web = web.cut(Part.makeCylinder(8,60,V(-30,-11,z(128)),V(1,0,0)))
        web = web.cut(yz_prism(profile([(-9,107),(8,107),(-1,122),(-16,122)]),x0-1,x1+1))
        add('NeckYoke'+side,'加高25 mm开窗固定颈架 '+side,web,'structure','metal')
        ax0,ax1 = (26,29) if sign>0 else (-29,-26)
        plate = yz_prism(profile([(-7,100),(17,100),(17,105),(4,131),(-4,137),(-23,137),(-24,132),(-13,106)]),ax0,ax1)
        plate = plate.cut(Part.makeCylinder(9,70,V(-35,-11,z(128)),V(1,0,0)))
        plate = plate.cut(yz_prism(profile([(-8,109),(5,109),(-2,120),(-13,120)]),ax0-1,ax1+1))
        add('NeckOuterWeb'+side,'加高颈架外层加强板 '+side,plate,'structure','accent')
        add('NeckBearing'+side,'固定横梁阶梯套 '+side,ring(11,8,3,V(sign*29,-11,z(128)),V(sign,0,0)),'structure','dark')
        add('NeckCap'+side,'横梁端部锁片 '+side,Part.makeCylinder(6,2,V(sign*32,-11,z(128)),V(sign,0,0)),'structure','accent')
        for y,h in [(10,104),(-20,136)]:
            add('NeckSpacer'+side+str(h),'颈架层间连接柱 '+side+' '+str(h),Part.makeCylinder(2.5,1,V(sign*25,y,z(h)),V(sign,0,0)),'structure','dark')
        start,end,sleeve_end = endpoints(sign)
        add('NeckStay'+side,'加长后斜撑芯杆 '+side,strut(2.8,start,end),'structure','metal')
        sleeve = strut(4.8,start,sleeve_end).cut(strut(2.8,start,sleeve_end))
        add('NeckStaySleeve'+side,'同轴后斜撑固定套筒 '+side,sleeve,'structure','dark','固定候选支撑；不是液压或电动推杆；强度未验收')
    add('NeckCrossbar','加高固定横梁',Part.makeCylinder(7.5,64,V(-32,-11,z(128)),V(1,0,0)),'structure','metal')
    saddle = box(-18,-27,133+LIFT,18,6,136+LIFT)
    for sign in (-1,1):
        start,end,_ = endpoints(sign)
        saddle = saddle.cut(strut(2.8,start,end))
    add('NeckHeadSaddle','加高头舱承托鞍座',saddle,'structure','dark')


def apply(doc, controller_info, l298n_info):
    from refine_assembly import route
    for obj in head_members(doc):
        shape = obj.Shape.copy()
        shape.translate(V(0,0,LIFT))
        obj.Shape = shape
        obj.addProperty('App::PropertyLength','HeadLift','Assembly')
        obj.HeadLift = LIFT
    from l298n_layout import CABLE_POINTS
    from build_tank import box
    points = [(x,y,z+LIFT if i>=3 else z) for i,(x,y,z) in enumerate(CABLE_POINTS)]
    doc.getObject('PowerCableRoute').Shape = route(points,3).fuse(box(-10,-23,42,10,-5,58)).removeSplitter()
    doc.getObject('PowerCableRoute').EvidenceBasis += '；0.37上端随头舱延长25 mm，底部接头原位'
    # The rebuilt saddle needs its cable channel at the raised world height.
    saddle = doc.getObject('NeckHeadSaddle')
    saddle.Shape = saddle.Shape.cut(route(points,4.5)).removeSplitter()
    controller_info['board_bbox_mm'][2] += LIFT
    controller_info['board_bbox_mm'][5] += LIFT
    controller_info['assumed_pcb_z_mm'] = [v+LIFT for v in controller_info['assumed_pcb_z_mm']]
    for yz in controller_info['assumed_usb_centers_yz_mm'].values(): yz[1] += LIFT
    controller_info['head_lift_mm'] = LIFT
    l298n_info['cable_route_points_mm'] = points
    doc.recompute()


def check(doc):
    head = Part.makeCompound([o.Shape for o in head_members(doc) if o.Category!='clearance'])
    rows = []
    for name in ('WaterModule','BubbleModule','WaterHoseRoute','BubbleGunHoseRoute',
                 'WaterGunHoseClearance','BubbleGunHoseClearance',
                 'WaterBottleRemovalSpace','BubbleBottleRemovalSpace',
                 'WaterFingerSpace','BubbleFingerSpace','WaterStrapAccessSpace','BubbleStrapAccessSpace'):
        other = doc.getObject(name).Shape
        rows.append({'object':name,'distance_to_head_mm':head.distToShape(other)[0],
                     'overlap_mm3':head.common(other).Volume})
    hb = doc.getObject('HeadShell').Shape.optimalBoundingBox(False)
    bottle_top = doc.getObject('WaterModule').Shape.optimalBoundingBox(False).ZMax
    support = []
    for a,b in [('NeckHeadSaddle','HeadShell'),('NeckYokeL','NeckHeadSaddle'),
                ('NeckYokeR','NeckHeadSaddle'),('NeckStayL','NeckHeadSaddle'),('NeckStayR','NeckHeadSaddle'),('NeckStaySleeveL','NeckPedestal'),('NeckStaySleeveR','NeckPedestal')]:
        support.append({'a':a,'b':b,'distance_mm':doc.getObject(a).Shape.distToShape(doc.getObject(b).Shape)[0]})
    return {'revision':'0.37','head_lift_mm':LIFT,'head_members':[o.Name for o in head_members(doc)],
            'head_shell_bottom_z_mm':hb.ZMin,'bottle_top_z_mm':bottle_top,
            'vertical_datum_difference_mm':hb.ZMin-bottle_top,
            'clearances':rows,'support_contacts':support,
            'passed':all(r['overlap_mm3']<.01 and r['distance_to_head_mm']>0 for r in rows)
                     and all(r['distance_mm']<1e-5 for r in support),
            'limits':'CAD nominal clearances and prescribed rigid service envelopes only; actual cap diameter, flexible hose withdrawal/parking, hand access, stiffness and stability unverified',
            'physical_fit_verified':False,'manufacturing_released':False}
