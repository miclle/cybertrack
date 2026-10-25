"""0.41 whole-breadboard tray; dimensions are layout candidates, not interfaces."""
import FreeCAD as A
import Part

V = A.Vector
SIZE = (100, 85, 36)
ORIGIN = (-50, -70, 174)
MOUNTS = [(x, y) for x in (-57, 57) for y in (-40, -5)]
TOL = .01


def box(x0, y0, z0, x1, y1, z1):
    return Part.makeBox(x1-x0, y1-y0, z1-z0, V(x0, y0, z0))


def cylinder(r, z0, z1, x, y):
    return Part.makeCylinder(r, z1-z0, V(x, y, z0))


def replaced(name):
    return (name.startswith(('Controller', 'ESP32', 'Tray', 'ArcModule'))
            or name in ('Electronics', 'AudioModule'))


def apply(doc, add):
    from refine_assembly import route
    for obj in list(doc.Objects):
        if hasattr(obj, 'Category') and replaced(obj.Name):
            doc.removeObject(obj.Name)
    shell = doc.getObject('HeadShell')
    shape = shell.Shape.copy()
    for x in (-49.5, 49.5):
        for y in (-30, 0):
            shape = shape.cut(cylinder(3.6, 164, 170, x, y))
    tray = box(-52.5, -72.5, 171.5, 52.5, 17.5, 174)
    rim = box(-52.5, -72.5, 174, 52.5, 17.5, 177).cut(
        box(-50.5, -70.5, 173, 50.5, 15.5, 178))
    tray = tray.fuse(rim)
    for index, (x, y) in enumerate(MOUNTS):
        x0, x1 = (-61, -52) if x < 0 else (52, 61)
        tray = tray.fuse(box(x0, y-4, 171.5, x1, y+4, 174))
        tray = tray.cut(cylinder(1.5, 171, 175, x, y))
        shape = shape.fuse(cylinder(3.5, 163, 171.5, x, y))
        shape = shape.cut(cylinder(2.1, 165, 171.6, x, y))
        insert = cylinder(2, 165.5, 171.3, x, y).cut(cylinder(1.35, 165, 172, x, y))
        add('BreadboardInsert'+str(index), '浅托盘嵌件候选 '+str(index+1), insert,
            'structure', 'metal', 'M2.5级候选；外径4、孔径2.7，材质、装配及承载未验')
        screw = cylinder(1.25, 166.5, 174, x, y).fuse(cylinder(2.2, 174, 175, x, y))
        screw = screw.cut(box(x-1.4, y-.4, 174.5, x+1.4, y+.4, 175.1))
        add('BreadboardScrew'+str(index), '浅托盘侧耳螺钉候选 '+str(index+1), screw,
            'structure', 'metal', 'M2.5级简化几何；不是已选定螺钉或螺纹模型')
        add('BreadboardTool'+str(index), '侧耳直工具杆审查 Ø8 '+str(index+1),
            cylinder(4, 175, 265, x, y), 'clearance', 'signal',
            '开冠盖后直杆上方入口；不含手柄、手指、拧紧力矩')
    # Rear edge opening routes the neck harness beside, not through, the board.
    tray = tray.cut(box(-5, 1, 171, 5, 18, 178)).removeSplitter()
    tray = tray.cut(box(-24.5,-73,171,24.5,-70.5,178)).removeSplitter()
    shell.Shape = shape.removeSplitter()
    shell.EvidenceBasis = '0.41仅改内部托盘支柱；外部曲面与0.39范围审计核对'
    obj = doc.getObject('ElectronicsTray')
    obj.Shape = tray
    obj.Label = '面包板浅托盘／105×90主体、122侧耳总宽'
    obj.EvidenceBasis = '内部101×86、底厚2.5、围边高3；100×85×36为用户规划包络；前缘中央49×2让位；公差、材料、保持力待验'
    board = add('BreadboardEnvelope', '面包板整组规划包络 100×85×36',
                Part.makeBox(*SIZE, V(*ORIGIN)), 'envelope', 'electronics',
                '用户指定规划包络；含面包板、ESP32、扬声器、麦克风、屏幕及线束；不是整组实测或逐元件几何')
    board.addProperty('App::PropertyString', 'ServiceGroup', 'Assembly')
    board.ServiceGroup = 'electronics'
    # Keep the established lower cable unchanged, extending only its head end.
    points = [(0,-14,50),(0,-14,84),(0,6,84),(0,6,170),(0,19,170),(0,19,190)]
    cable = doc.getObject('PowerCableRoute')
    cable.Shape = route(points, 3).fuse(box(-10,-23,42,10,-5,58)).removeSplitter()
    cable.EvidenceBasis = '0.41头端改经托盘后缘开口；Ø6及折线路线为假设，不证明真实接头、弯曲半径或可不断线提取'
    doc.recompute()
    return {'revision':'0.41', 'size_xyz_mm':list(SIZE), 'origin_mm':list(ORIGIN),
            'basis':'user-authorized planning envelope, not assembled measurement',
            'tray_inner_xy_mm':[101,86], 'tray_outer_xy_mm':[105,90],
            'tray_with_ears_width_mm':122, 'floor_thickness_mm':2.5,
            'rim_height_mm':3, 'mount_centres_xy_mm':MOUNTS,
            'front_relief_width_depth_mm':[49,2], 'cable_points_mm':points, 'cable_diameter_assumed_mm':6,
            'component_positions_known':False, 'board_anti_lift_retention_verified':False,
            'retention_note':'Side rims locate only. Edge clips require actual plastic-base height and free contact areas; no pressure on components is designed.',
            'arc_modules':'excluded from this layout; no lower-body relocation',
            'physical_fit_verified':False}


def check(doc):
    physical = [o for o in doc.Objects if hasattr(o,'Category') and o.Category!='clearance']
    names = {o.Name for o in physical}
    moving = ['ElectronicsTray','BreadboardEnvelope']
    screws = sorted(n for n in names if n.startswith('BreadboardScrew'))
    crown = [o.Name for o in physical if getattr(o,'ServiceGroup','')=='crown']
    crown_screws = [n for n in names if n.startswith('CrownScrew')]
    removed = set(crown+crown_screws+screws+['PowerCableRoute','UltrasonicWireSpace'])
    def overlaps(shape, excluded):
        hits=[];tested=0;b=shape.optimalBoundingBox(False)
        for o in physical:
            if o.Name in excluded or not b.intersect(o.Shape.optimalBoundingBox(False)): continue
            tested+=1;volume=shape.common(o.Shape).Volume
            if volume>TOL: hits.append({'object':o.Name,'volume_mm3':volume})
        return {'boolean_pairs_tested':tested,'overlaps':hits,'passed':not hits}
    static = {n:overlaps(doc.getObject(n).Shape,{n}) for n in moving}
    # Conservative union of upright prisms contains every pose of tray and board.
    sweep = box(-52.5,-72.5,171.5,52.5,17.5,295)
    for x,y in MOUNTS:
        x0,x1=(-61,-52) if x<0 else (52,61)
        sweep=sweep.fuse(box(x0,y-4,171.5,x1,y+4,295))
    sweep = sweep.cut(box(-24.5,-73,171,24.5,-70.5,296))
    service = overlaps(sweep,removed|set(moving))
    service.update(method='continuous conservative vertical prism union',
                   translation_mm=[0,0,85], removed_first=sorted(removed),
                   moving=moving, excludes_flexible_harness_and_hands=True)
    tools=[];fasteners=[]
    for i,(x,y) in enumerate(MOUNTS):
        tool=doc.getObject('BreadboardTool'+str(i)).Shape
        result=overlaps(tool,set(crown+crown_screws+[screws[i]]))
        result.update(name='BreadboardTool'+str(i),diameter_mm=8,length_mm=90)
        tools.append(result)
        shaft=cylinder(1.25,166.5,194,x,y)
        head=cylinder(2.2,174,195,x,y)
        result=overlaps(shaft.fuse(head),set(crown+crown_screws+[screws[i]]))
        result.update(name=screws[i],translation_mm=[0,0,20],method='continuous shaft/head cylinder union')
        fasteners.append(result)
    board=doc.getObject('BreadboardEnvelope').Shape
    contacts=[]
    for x,y in MOUNTS:
        seat=cylinder(3.5,171.49,171.5,x,y).cut(cylinder(2.1,171,172,x,y))
        contacts.append({'xy':[x,y],'seat_area_mm2':3.141592653589793*(3.5**2-2.1**2),
                         'distance_to_tray_mm':seat.distToShape(doc.getObject('ElectronicsTray').Shape)[0]})
    negatives=[]
    for label, excluded, shape, expected in [
        ('closed crown blocks removal',set(moving+screws+['PowerCableRoute','UltrasonicWireSpace']),sweep,('HeadCrownShell','Crown')),
        ('retained tray screws block removal',set(crown+crown_screws+moving+['PowerCableRoute','UltrasonicWireSpace']),sweep,('BreadboardScrew',)),
        ('height increased by 5 mm hits crown',{'BreadboardEnvelope'},box(-50,-70,174,50,15,215),('HeadCrownShell','Crown'))]:
        result=overlaps(shape,excluded)
        negatives.append({'case':label,'detected':any(r['object'].startswith(expected) for r in result['overlaps']),
                          'expected_obstacle_prefixes':list(expected),'hits':result['overlaps']})
    return {'revision':'0.41','tolerance_mm3':TOL,'static':static,
            'board_to_crown_mm':board.distToShape(doc.getObject('HeadCrownShell').Shape)[0],
            'tray_to_harness_mm':doc.getObject('ElectronicsTray').Shape.distToShape(doc.getObject('PowerCableRoute').Shape)[0],
            'tray_removal':service,'tool_access':tools,'screw_removal':fasteners,
            'seats':contacts,'negative_controls':negatives,
            'passed':all(r['passed'] for r in list(static.values())+[service]+tools+fasteners)
                     and all(r['detected'] for r in negatives)
                     and all(r['distance_to_tray_mm']<1e-5 for r in contacts),
            'board_anti_lift_retention_verified':False,'physical_fit_verified':False,
            'limits':'Envelope and rigid tray only. No individual audio/display/USB/RF fit, hand access, flexible harness service, material strength or anti-lift retention acceptance.'}


def render(doc, output):
    import FreeCADGui as Gui
    from PySide import QtGui
    objects=[o for o in doc.Objects if hasattr(o,'Category')]
    saved={o.Name:(o.ViewObject.Visibility,o.ViewObject.Transparency) for o in objects}
    view=Gui.activeDocument().activeView();camera=view.getCameraOrientation()
    cable=doc.getObject('PowerCableRoute');full_cable=cable.Shape.copy()
    iso=A.Rotation(V(1,1,0),V(-1,1,3),V(1,-1,.75),'ZXY')
    try:
        cable.Shape=full_cable.common(box(-100,-100,160,100,50,220))
        for filename,rotation,kind in [('breadboard-layout.png',iso,'layout'),
                ('breadboard-top.png',A.Rotation(),'layout'),
                ('breadboard-tray.png',iso,'tray'),
                ('breadboard-access.png',iso,'access'),
                ('breadboard-service.png',iso,'service')]:
            for o in objects:
                o.ViewObject.Visibility=(o.Name.startswith('Breadboard') or o.Name=='ElectronicsTray'
                    or (o.Name in ('HeadShell','PowerCableRoute','SensorMask','UltrasonicPCBEnvelope','UltrasonicRearEnvelope','UltrasonicTopConnector','UltrasonicWireSpace','UltrasonicRingL','UltrasonicRingR','UltrasonicFaceL','UltrasonicFaceR') and kind in ('layout','access','service')))
                if kind=='tray':o.ViewObject.Visibility=o.Name=='ElectronicsTray'
                if o.Category=='clearance':
                    o.ViewObject.Visibility=kind=='access' and o.Name.startswith('BreadboardTool')
                if kind=='service' and o.Name.startswith('BreadboardScrew'):o.ViewObject.Visibility=False
                o.ViewObject.Transparency=85 if o.Name=='HeadShell' or o.Category=='clearance' else 45 if o.Name=='BreadboardEnvelope' else 0
            shifted={}
            if kind=='service':
                for name in ('ElectronicsTray','BreadboardEnvelope'):
                    o=doc.getObject(name);shifted[name]=o.Shape.copy()
                    s=o.Shape.copy();s.translate(V(0,0,85));o.Shape=s
                doc.getObject('PowerCableRoute').ViewObject.Visibility=False
                doc.getObject('UltrasonicWireSpace').ViewObject.Visibility=False
            view.setCameraOrientation(rotation.Q);view.fitAll()
            for _ in range(10):QtGui.QApplication.processEvents()
            view.saveImage(str(output/filename),1600,1200,'White')
            for name,s in shifted.items():doc.getObject(name).Shape=s
    finally:
        cable.Shape=full_cable
        for o in objects:o.ViewObject.Visibility,o.ViewObject.Transparency=saved[o.Name]
        view.setCameraOrientation(camera.Q)
