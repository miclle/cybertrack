"""User-sized L298N box, rigid placement and scoped dry-bay clearance checks.

No PCB, hole, heat sink or terminal geometry is inferred from the overall size.
"""
import hashlib
import json
from pathlib import Path
import FreeCAD as App
import Part

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / 'hardware/components/L298N'
SIZE = (46.2, 43.5, 27.5)
ORIGIN = (21.75, 23.5, 32.0)
TOL = 0.01
BASIS = '用户于2026-10-25提供长46.2×宽43.5×高27.5 mm；完整矩形包络，孔位、尺寸包含范围和固定方式待确认'
CABLE_POINTS = [(0,-14,50), (0,-14,84), (0,6,84), (0,6,142), (0,-5,142)]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bounds(shape):
    b = shape.optimalBoundingBox(False)
    return [b.XMin, b.YMin, b.ZMin, b.XMax, b.YMax, b.ZMax]


def placement():
    # Local length +X -> world +Z, width +Y -> -X, height +Z -> -Y.
    rotation = App.Rotation(App.Vector(0,0,1), App.Vector(-1,0,0),
                            App.Vector(0,-1,0), 'ZXY')
    return App.Placement(App.Vector(*ORIGIN), rotation)


def component():
    """Create once; verify rather than overwrite an existing component asset."""
    COMPONENT.mkdir(exist_ok=True)
    cad = COMPONENT / 'L298N-envelope.FCStd'
    step = COMPONENT / 'L298N-envelope.step'
    expected = Part.makeBox(*SIZE)
    if not cad.exists():
        doc = App.newDocument('L298NEnvelope')
        doc.Label = '何健弓 L298N · 用户尺寸独立包络'
        obj = doc.addObject('Part::Box', 'L298NEnvelope')
        obj.Length, obj.Width, obj.Height = SIZE
        obj.Label = 'L298N 46.2 × 43.5 × 27.5 mm／整体包络'
        obj.addProperty('App::PropertyString', 'EvidenceBasis', 'Evidence')
        obj.EvidenceBasis = BASIS
        doc.recompute()
        doc.saveAs(str(cad))
        Part.export([obj], str(step))
        App.closeDocument(doc.Name)
    assert step.exists(), 'Existing L298N native asset has no STEP; inspect before replacing'
    saved = App.openDocument(str(cad))
    shape = saved.getObject('L298NEnvelope').Shape.copy()
    App.closeDocument(saved.Name)
    imported = Part.Shape()
    imported.read(str(step))
    checks = []
    for name, candidate in [('FCStd', shape), ('STEP', imported)]:
        delta = expected.cut(candidate).Volume + candidate.cut(expected).Volume
        checks.append({'format':name, 'valid':candidate.isValid(),
                       'solid_count':len(candidate.Solids), 'bbox_mm':bounds(candidate),
                       'symmetric_difference_mm3':delta,
                       'passed':candidate.isValid() and len(candidate.Solids)==1 and delta<1e-5})
    report = {'source':'user-provided dimensions, 2026-10-25',
              'product_url':'https://item.jd.com/10231029535273.html',
              'size_lwh_mm':list(SIZE), 'local_axes':'length X, width Y, height Z; origin at minimum corner',
              'geometry':'single full rectangular envelope; no inferred holes or internal details',
              'saved_and_reopened':True, 'checks':checks,
              'files_sha256':{p.name:sha(p) for p in (cad,step)},
              'passed':all(r['passed'] for r in checks), 'physical_fit_verified':False}
    (COMPONENT / 'readback.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    assert report['passed'], report
    return shape, report


def add_l298n(doc, add):
    shape, source = component()
    transform = placement()
    shape.Placement = transform
    obj = add('L298NEnvelope', 'L298N 驱动板竖装包络／46.2×43.5×27.5',
              shape, 'envelope', 'accent', BASIS+'；下部干舱竖装，0.34增加可拆托框；PCB接触点待验')
    obj.addProperty('App::PropertyString', 'SourceFile', 'Evidence')
    obj.SourceFile = 'hardware/components/L298N/L298N-envelope.FCStd'
    obj.addProperty('App::PropertyString', 'AxisMapping', 'Evidence')
    obj.AxisMapping = 'local X -> +Z; local Y -> -X; local Z -> -Y; scale 1'
    # Preserve the existing assumed battery plug and the complete neck/head route.
    from refine_assembly import route, box
    cable = doc.getObject('PowerCableRoute')
    cable.Shape = route(CABLE_POINTS,3).fuse(box(-10,-23,42,10,-5,58)).removeSplitter()
    cable.EvidenceBasis = ('Ø6示意线束；电源插头包络保持，干舱内先沿Y=-14上升至Z84，'
                           '再向后接原颈架通道，避让竖装L298N；弯曲半径及真实接线待核')
    return {'component_readback':source, 'origin_world_mm':list(ORIGIN),
            'local_to_world_axes':['+Z','-X','-Y'], 'scale':1,
            'placement_rotation_xyzw':list(transform.Rotation.Q),
            'bbox_mm':bounds(shape), 'cable_route_points_mm':CABLE_POINTS,
            'mounting':'vertical candidate between motors; removable cassette added by l298n_mount; PCB contact still unverified',
            'hole_pattern_assumed':False, 'thermal_verified':False, 'physical_fit_verified':False}


def check_l298n(doc):
    if doc.getObject('L298NTopRetainer'):
        from l298n_compact_mount import check
        return check(doc)
    board = doc.getObject('L298NEnvelope').Shape
    expected = Part.makeBox(*SIZE)
    expected.Placement = placement()
    delta = expected.cut(board).Volume + board.cut(expected).Volume
    b = bounds(board)
    assert max(abs(a-c) for a,c in zip(b,[-21.75,-4,32,21.75,23.5,78.2]))<1e-6
    # Established central dry-bay interior: inside walls, ahead of wet bulkhead,
    # above floor datum and below the flat roof underside (not a thermal volume).
    dry_bay = Part.makeBox(90,46,59,App.Vector(-45,-21,31))
    outside_dry_bay = board.cut(dry_bay).Volume
    objects = [o for o in doc.Objects if hasattr(o,'Category') and o.Name!='L298NEnvelope']
    overlaps, reserved, nearby = [], [], []
    for obj in objects:
        other = obj.Shape
        if board.BoundBox.intersect(other.BoundBox):
            common = board.common(other)
            volume = common.Volume
            assert common.isValid(), obj.Name
            if volume>TOL:
                (reserved if obj.Category=='clearance' else overlaps).append({'object':obj.Name,'volume_mm3':volume})
        distance = board.distToShape(other)[0]
        nearby.append({'object':obj.Name,'category':obj.Category,'distance_mm':distance})
    nearby.sort(key=lambda row:row['distance_mm'])
    removed = ['BottomServiceCover']+[o.Name for o in objects if o.Name.startswith('BottomCoverScrew')]
    co_moving = []
    if doc.getObject('L298NCarrier'):
        from l298n_mount import moving_names
        co_moving = [n for n in moving_names(doc) if n!='L298NEnvelope']
        removed += [o.Name for o in doc.Objects if o.Name.startswith('L298NMountScrew')]
    # A rectangular prism swept vertically is exactly its extended rectangular box.
    sweep = Part.makeBox(b[3]-b[0],b[4]-b[1],b[5]-b[2]+80,App.Vector(b[0],b[1],b[2]-80))
    hits = []
    for obj in objects:
        if obj.Name in removed+co_moving or not sweep.BoundBox.intersect(obj.Shape.BoundBox):
            continue
        common = sweep.common(obj.Shape)
        assert common.isValid(), obj.Name
        if common.Volume>TOL:hits.append({'object':obj.Name,'volume_mm3':common.Volume})
    closed_volume = sweep.common(doc.getObject('BottomServiceCover').Shape).Volume
    return {'size_lwh_mm':list(SIZE), 'bbox_mm':b, 'shape_valid':board.isValid(),
            'solid_count':len(board.Solids), 'placement_difference_mm3':delta,
            'outside_central_dry_bay_mm3':outside_dry_bay,
            'overlap_tolerance_mm3':TOL, 'objects_checked':len(objects),
            'overlaps':overlaps, 'reserved_space_overlaps':reserved,
            'nearby_distances':nearby[:20],
            'removal':{'method':'exact rectangular continuous sweep, 80 mm down',
                       'removed_first':removed,'co_moving_excluded_from_obstacles':co_moving,
                       'disconnect_first':'actual driver leads; release modeled cassette mounting screws when present',
                       'existing_power_route_retained_as_obstacle':True,
                       'sweep_bbox_mm':bounds(sweep),'overlaps':hits,'passed':not hits,
                       'closed_cover_negative_control_mm3':closed_volume,
                       'closed_cover_blocks':closed_volume>TOL},
            'passed':board.isValid() and len(board.Solids)==1 and delta<1e-5 and outside_dry_bay<TOL and not overlaps and not reserved and not hits and closed_volume>TOL,
            'limits':['Dimensions inclusion, PCB corner contacts and exact terminal positions remain unverified.',
                      'Minimum nominal gaps are not thermal, insulation, tolerance or physical acceptance.',
                      'Bare envelope checked with co-moving cassette removed from obstacles; see mount check for complete cassette, screws and tool shafts; real wires/fingers remain unverified.'],
            'physical_fit_verified':False,'manufacturing_released':False,'thermal_verified':False}


def render_l298n(doc, output):
    import FreeCADGui as Gui
    from PySide import QtGui
    objects = [o for o in doc.Objects if hasattr(o,'Category')]
    saved = {o.Name:(o.ViewObject.Visibility,o.ViewObject.Transparency,o.ViewObject.ShapeColor) for o in objects}
    view = Gui.activeDocument().activeView()
    camera = view.getCameraOrientation()
    selected = {'L298NEnvelope','PowerBank','BatteryHatch','LowerTub','RearBulkhead',
                'MotorL','MotorR','PowerCableRoute','BottomServiceCover','KeelLid'}
    try:
        for obj in objects:
            obj.ViewObject.Visibility = obj.Name in selected or (obj.Name.startswith('L298N') and obj.Category!='clearance')
            obj.ViewObject.Transparency = 88 if obj.Name in ('LowerTub','KeelLid') else 65 if obj.Name=='BottomServiceCover' else 0
        doc.getObject('L298NEnvelope').ViewObject.ShapeColor = (0.98,0.32,0.07)
        for name,rotation in [('l298n-layout',App.Rotation(App.Vector(1,1,0),App.Vector(-1,1,3),App.Vector(1,-1,0.75),'ZXY')),
                              ('l298n-side',App.Rotation(App.Vector(0,1,0),App.Vector(0,0,1),App.Vector(1,0,0),'ZXY')),
                              ('l298n-top',App.Rotation())]:
            view.setCameraOrientation(rotation.Q)
            view.fitAll()
            for _ in range(10):QtGui.QApplication.processEvents()
            view.saveImage(str(output/(name+'.png')),1600,1200,'White')
    finally:
        for obj in objects:
            obj.ViewObject.Visibility,obj.ViewObject.Transparency,obj.ViewObject.ShapeColor = saved[obj.Name]
        view.setCameraOrientation(camera.Q)
        view.fitAll()
