"""Measured water-gun bounds, photo-informed mockup, and conservative fit checks.

Only overall dimensions are measured. The stepped shell, nozzle and inlet are
illustrations; the complete rectangular bound is checked independently.
"""
import hashlib
import json
from pathlib import Path
import FreeCAD as App
import Part

V = App.Vector
ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / 'hardware/components/pulse-water-gun'
ORIGIN = (55.0, -129.0, 117.0)
LENGTH, WIDTH, THICKNESS, WET_WIDTH = 138.5, 33.2, 24.6, 38.5
TOLERANCE = 0.01


def bbox(shape):
    b = shape.optimalBoundingBox(False)
    return [getattr(b, k) for k in ('XMin', 'YMin', 'ZMin', 'XMax', 'YMax', 'ZMax')]


def conservative_shape(origin=ORIGIN, width_along_x=True):
    x, y, z = origin
    sx, sz = (WIDTH, THICKNESS) if width_along_x else (THICKNESS, WIDTH)
    dx, dz = (WET_WIDTH-WIDTH, 0) if width_along_x else (0, WET_WIDTH-WIDTH)
    return Part.makeBox(sx+dx, LENGTH, sz+dz, V(x-sx/2, y, z-sz/2))


def local_shapes():
    # All segment lengths, radii and corner shapes below are explicit assumptions.
    points = [(-13.6, 43), (13.6, 43), (16.6, 46),
              (16.6, 135.5), (13.6, 138.5), (-13.6, 138.5),
              (-16.6, 135.5), (-16.6, 46)]
    vertices = [V(x, y, -12.3) for x, y in points]
    body = Part.Face(Part.makePolygon(vertices+[vertices[0]])).extrude(V(0, 0, THICKNESS))
    barrel = Part.makeCylinder(10.5, 38, V(0, 7, 0), V(0, 1, 0))
    nozzle = Part.makeCone(2, 4, 8, V(), V(0, 1, 0))
    body = body.fuse(barrel).fuse(nozzle).removeSplitter()
    # Inlet and a short tube end occupy the reported extra 5.3 mm width.
    # This is not a measured tube diameter or a reconstruction of the flexible hose.
    inlet = Part.makeCylinder(2.5, 11.4, V(10.5, 24, 0), V(1, 0, 0))
    expected = [-WIDTH/2, 0, -THICKNESS/2, WIDTH/2, LENGTH, THICKNESS/2]
    assert all(abs(a-b) < 1e-6 for a, b in zip(bbox(body), expected))
    combined = Part.makeCompound([body, inlet])
    expected[3] = WET_WIDTH-WIDTH/2
    assert all(abs(a-b) < 1e-6 for a, b in zip(bbox(combined), expected))
    assert all(s.isValid() and len(s.Solids) == 1 for s in (body, inlet))
    return {'WaterGunBody': body, 'WaterGunInlet': inlet}


def hits(shape, objects):
    bounds = shape.optimalBoundingBox(False)
    overlaps = []
    for obj in objects:
        if not bounds.intersect(obj.Shape.optimalBoundingBox(False)):
            continue
        volume = shape.common(obj.Shape).Volume
        if volume > TOLERANCE:
            overlaps.append({'object': obj.Name, 'label': obj.Label,
                             'overlap_mm3': volume})
    return overlaps


def export_component(shapes, render=False):
    active = App.ActiveDocument
    doc = App.newDocument('PulseWaterGun')
    doc.Label = '脉冲水枪 · 实测总尺寸／分段轮廓假设'
    for name, shape in shapes.items():
        obj = doc.addObject('Part::Feature', name)
        obj.Label = '发射枪轮廓示意' if name.endswith('Body') else '侧接头示意／尺寸未测'
        obj.Shape = shape
        obj.addProperty('App::PropertyString', 'EvidenceBasis')
        obj.EvidenceBasis = '总长138.5／最大宽33.2／厚24.6／带管宽38.5为用户实测；分段、喷嘴、接头为假设'
        if render:
            obj.ViewObject.ShapeColor = (0.98, 0.38, 0.04) if name.endswith('Body') else (0.96, 0.73, 0.10)
    envelope = doc.addObject('Part::Feature', 'MeasuredMaximumEnvelope')
    envelope.Label = '最大外包络／含管宽38.5／不是实物等截面'
    envelope.Shape = conservative_shape((0, 0, 0))
    if render:
        envelope.ViewObject.Visibility = False
    doc.recompute()
    cad = COMPONENT/'PulseWaterGun.FCStd'
    step = COMPONENT/'PulseWaterGun.step'
    doc.saveAs(str(cad))
    Part.export([doc.getObject(n) for n in shapes], str(step))
    expected = {o.Name: o.Shape.copy() for o in doc.Objects}
    App.closeDocument(doc.Name)
    saved = App.openDocument(str(cad))
    rows = []
    for obj in saved.Objects:
        difference = expected[obj.Name].cut(obj.Shape).Volume + obj.Shape.cut(expected[obj.Name]).Volume
        assert obj.Shape.isValid() and difference < 1e-5, obj.Name
        rows.append({'name': obj.Name, 'bbox_mm': bbox(obj.Shape),
                     'valid': True, 'symmetric_difference_mm3': difference})
    neutral = Part.Shape()
    neutral.read(str(step))
    compound = Part.makeCompound(list(shapes.values()))
    delta = abs(neutral.Volume-compound.Volume)
    assert neutral.isValid() and len(neutral.Solids) == len(compound.Solids) and delta < .01
    App.closeDocument(saved.Name)
    App.setActiveDocument(active.Name)
    report = {'measured_dimensions_mm': {'length': LENGTH, 'width': WIDTH,
              'thickness': THICKNESS, 'width_with_hose': WET_WIDTH},
              'coordinates': '+Y from nozzle tip to rear; +X across width toward inlet; +Z thickness',
              'shape_assumptions': {'nozzle_length': 8, 'nozzle_radii': [2, 4],
                  'barrel_radius': 10.5, 'barrel_y_range': [7, 45],
                  'body_y_range': [43, 138.5], 'body_corner_chamfer': 3,
                  'inlet_axis_yz': [24, 0], 'inlet_radius': 2.5,
                  'inlet_x_range': [10.5, 21.9]},
              'objects': rows, 'step_readback': {'valid': True, 'volume_difference_mm3': delta},
              'source_photo_sha256': hashlib.sha256((COMPONENT/'images/disassembled-2026-10-24.jpg').read_bytes()).hexdigest(),
              'files_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (cad, step)},
              'interfaces_measured': False, 'physical_fit_verified': False}
    (COMPONENT/'readback.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')


def add_water_gun(doc, add, render=False):
    shapes = local_shapes()
    verify_component(shapes)
    # Original port position is assessed without its own decorative sleeve.
    fixed = [o for o in doc.Objects if hasattr(o, 'Category') and
             o.Name not in ('WaterPort', 'WaterHoseRoute')]
    original = []
    for width_x in (False, True):
        original.append({'width_along_x': width_x, 'origin_mm': [44, -89, 145],
                         'overlaps': hits(conservative_shape((44, -89, 145), width_x), fixed)})
    for name, shape in shapes.items():
        shape = shape.copy()
        shape.translate(V(*ORIGIN))
        obj = add(name, '拆出发射枪／前细后粗示意' if name.endswith('Body') else '水枪侧接头／未测形状',
                  shape, 'component', 'accent' if name.endswith('Body') else 'power',
                  '实测总长138.5／宽33.2／厚24.6／带管宽38.5；分段轮廓与接口为假设；底部双面软胶固定；胶厚和线管为候选')
        obj.addProperty('App::PropertyString', 'ServiceGroup', 'Assembly')
        obj.ServiceGroup = 'water_gun'
    add('WaterGunMaximumEnvelope', '水枪最大尺寸审查包络／含管宽38.5',
        conservative_shape(), 'clearance', 'water',
        '最大尺寸沿全长保守检查；不按照片缩小检查包络；不含管线余量、固定件及测量公差')
    from water_gun_mount import build_mount
    mount_info=build_mount(doc,add)
    return {'source': 'hardware/components/pulse-water-gun/README.md',
            'local_model': 'hardware/components/pulse-water-gun/PulseWaterGun.FCStd',
            'origin_mm': list(ORIGIN), 'rotation_degrees': [0, 0, 0],
            'orientation': 'length +Y toward rear, nozzle faces -Y; width X, thickness Z; inlet +X',
            'maximum_bbox_mm': bbox(conservative_shape()),'mount':mount_info,
            'original_face_position_checks': original,
            'mounts_leads_tube_bend_and_physical_fit_verified': False}


def check_water_gun(doc):
    wet=doc.getObject('WaterGunMaximumEnvelope').Shape
    excluded={'WaterGunBody','WaterGunInlet','WaterGunMaximumEnvelope','WaterGunBaseTool1','WaterGunBaseTool2'}
    # These rods are used on the bench only after extracting the effect tray.
    # Keep all physical objects and every other in-machine clearance in scope.
    bench_tools={o.Name for o in doc.Objects if o.Name.startswith('EffectRetainerTool')
                 and getattr(o,'Category','')=='clearance'}
    obstacles=[o for o in doc.Objects if hasattr(o,'Category') and o.Name not in excluded|bench_tools]
    # The gun's own flexible hose is included in the wet size input, not an
    # external assembly obstacle. Its actual solid is still checked against
    # the complete bare housing here and every physical part globally.
    external=[o for o in obstacles if not o.Name.startswith('WaterGun') and o.Name!='WaterHoseRoute']
    origin=V(ORIGIN[0]-WIDTH/2,ORIGIN[1],ORIGIN[2]-THICKNESS/2)
    body=Part.makeBox(WIDTH,LENGTH,THICKNESS,origin)
    body_hits=hits(body,obstacles)
    wet_hits=hits(wet,external)
    inlet_hits=hits(doc.getObject('WaterGunInlet').Shape,obstacles)
    overlaps=body_hits+wet_hits+inlet_hits
    clearances=sorted([{'object':o.Name,'distance_mm':body.distToShape(o.Shape)[0]}
                      for o in obstacles if o.Name not in ('WaterHoseRoute','WaterGunLeadRoute') and 'Pad' not in o.Name and o.Category!='clearance'],key=lambda r:r['distance_mm'])
    from water_gun_mount import removable_line_names,check_mount
    removed=removable_line_names(doc)
    fixed=[o for o in obstacles if o.Name not in removed]
    def lift_and_forward(width,length,height,start):
        lift=Part.makeBox(width,length,height+2,start)
        forward=Part.makeBox(width,length+150,height,start+V(0,-150,2))
        return lift.fuse(forward)
    # Fit the measured bare housing between the side walls. Keep the full wet
    # rectangle for external obstacles, and check the front inlet separately.
    body_sweep=lift_and_forward(WIDTH,LENGTH,THICKNESS,origin)
    ib=bbox(doc.getObject('WaterGunInlet').Shape)
    inlet_sweep=lift_and_forward(ib[3]-ib[0],ib[4]-ib[1],ib[5]-ib[2],V(*ib[:3]))
    wet_sweep=lift_and_forward(WET_WIDTH,LENGTH,THICKNESS,origin)
    removal_hits=hits(body_sweep,fixed)+hits(inlet_sweep,fixed)+hits(wet_sweep,[o for o in external if o.Name not in removed])
    mount_check=check_mount(doc)
    return {'mount_check':mount_check,
            'excluded_off_machine_tools':sorted(bench_tools),
            'off_machine_tool_basis':'Effect retainer tools are checked against the extracted tray in effect_board_mount.check; not available in the assembled chassis.',
            'method':'full 33.2 x 24.6 housing rectangle against mount and assembly; full 38.5 wet rectangle against external assembly; assumed front inlet checked separately',
            'housing_bound':{'overlaps':body_hits,'passed':not body_hits},
            'external_wet_bound':{'excluded_own_hose':'WaterHoseRoute; actual tube checked separately','overlaps':wet_hits,'passed':not wet_hits},
            'inlet_candidate':{'overlaps':inlet_hits,'passed':not inlet_hits,'axial_location_measured':False},
            'tolerance_mm3':TOLERANCE,'overlaps':overlaps,'passed':not overlaps and mount_check['passed'],
            'nearest_clearances':clearances[:12],
            'removal':{'waypoints_mm':[[0,0,0],[0,0,2],[0,-150,2]],
                'method':'continuous housing box and inlet AABB lift/forward sweeps; full wet box sweep against external obstacles',
                'removed_first':removed,'adhesive_bond_released_first':True,
                'overlaps':removal_hits,'passed':not removal_hits,
                'scope':'after adhesive release; inlet location unmeasured, no peel-force, debonding-tool or hand-access verification'},
            'physical_fit_verified':False}


def check_other_service_sweeps(doc, service_check):
    """Exact axial bottle sweeps; conservative AABBs for other maintenance groups."""
    from refine_assembly import service_groups
    from controller_layout import controller_members
    from bottle_backpack import RADIUS, HEIGHT, BOTTOM, CENTRES, cyl
    from gun_pitch import moved, vector
    groups = service_groups(doc)
    special = {'controller': controller_members(doc), 'controller_retainer': ['ControllerRetainer'],
               'controller_board': ['ESP32Board'], 'usb_com': ['ControllerUSBCOM'],
               'usb_native': ['ControllerUSBUSB']}
    bound = doc.getObject('WaterGunMaximumEnvelope').Shape
    results = []
    for scenario in service_check['scenarios']:
        group = scenario['group']
        if group.startswith('water_gun'):
            continue
        names = special[group] if group in special else groups[group]
        overlaps = []
        method = 'axis-aligned bounding box of each complete translation segment'
        for start, end in zip(scenario['waypoints_mm'], scenario['waypoints_mm'][1:]):
            for name in names:
                if group in dict(CENTRES) and name == group+'Module':
                    # An AABB in the tilted gun frame falsely widens a vertical
                    # bottle path toward the gun. Verify the full cylinder, then
                    # sweep it analytically along its world Z axis instead.
                    x = dict(CENTRES)[group]
                    expected = moved(cyl(RADIUS,BOTTOM,BOTTOM+HEIGHT,x),'water',True)
                    actual = doc.getObject(name).Shape
                    assert expected.cut(actual).Volume+actual.cut(expected).Volume < 1e-5
                    a,b = vector(start),vector(end)
                    assert max(abs(a.x),abs(a.y),abs(b.x),abs(b.y)) < 1e-5
                    sweep = moved(cyl(RADIUS,BOTTOM+min(a.z,b.z),BOTTOM+HEIGHT+max(a.z,b.z),x),'water',True)
                    method = 'exact continuous full-cylinder axial sweep in world Z, transformed to gun frame'
                else:
                    b = bbox(doc.getObject(name).Shape)
                    low = [b[i]+min(start[i], end[i]) for i in range(3)]
                    high = [b[i+3]+max(start[i], end[i]) for i in range(3)]
                    sweep = Part.makeBox(*(high[i]-low[i] for i in range(3)), V(*low))
                volume = sweep.common(bound).Volume
                if volume > TOLERANCE:
                    overlaps.append({'moving': name, 'overlap_mm3': volume})
        results.append({'group': group, 'method': method, 'overlaps': overlaps, 'passed': not overlaps})
    return {'method': 'exact axial bottle cylinders; other complete translation segments use conservative AABBs; against maximum water gun box',
            'scenarios': results, 'passed': all(r['passed'] for r in results),
            'scope': 'conservative screening of modelled maintenance groups; not hands, tools or flexible leads'}


def verify_component(shapes):
    active=App.ActiveDocument
    report=json.loads((COMPONENT/'readback.json').read_text())
    for name,digest in report['files_sha256'].items():
        assert hashlib.sha256((COMPONENT/name).read_bytes()).hexdigest()==digest,name
    assert hashlib.sha256((COMPONENT/'images/disassembled-2026-10-24.jpg').read_bytes()).hexdigest()==report['source_photo_sha256']
    doc=App.openDocument(str(COMPONENT/'PulseWaterGun.FCStd'))
    for name,shape in shapes.items():
        stored=doc.getObject(name).Shape
        assert shape.cut(stored).Volume+stored.cut(shape).Volume<1e-5,name
    App.closeDocument(doc.Name)
    App.setActiveDocument(active.Name)
