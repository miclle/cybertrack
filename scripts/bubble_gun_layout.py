"""Bubble body mockup with user-supplied overall and rear-bottom tab dimensions.

The width, internal features and segment positions are explicit design assumptions.
The inspection box is a reserved space, NOT a measured maximum envelope.
"""
import hashlib
import json
import math
from pathlib import Path
import FreeCAD as App
import Part
from water_gun_layout import bbox, hits

V = App.Vector
ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / 'hardware/components/bubble-gun'
REVISION = COMPONENT / 'revisions/tail-height-2026-10-26'
ORIGIN = (-55.0, -129.0, 110.0)  # Muzzle end centre in assembly; body extends toward +Y after Z rotation.
WIDTH = 35.8  # Reserved width, unmeasured.
NAMES = ('BubbleGunShell', 'BubbleGunWheel', 'BubbleGunMotor', 'BubbleGunGearcase', 'BubbleGunMountingTab', 'BubbleGunFrontFoot')


def dimensions():
    return json.loads((COMPONENT/'dimensions.json').read_text())['dimensions']


def mounting_height():
    """Support-to-muzzle-top datum; independent of the taller rear shell."""
    d=dimensions()
    tab=json.loads((COMPONENT/'mounting-tab-dimensions.json').read_text())
    return d['outermost_muzzle_circle_diameter']+tab['resting_plane_measurement']['muzzle_circle_bottom_above_plane_mm']


def tail_dimensions():
    return json.loads((REVISION/'dimensions.json').read_text())


def overall_height():
    tail=tail_dimensions()
    return max(mounting_height(),tail['tail_shell_height_mm']+tail['bottom_tab_height_mm'])


def inspection_box(origin=ORIGIN, extra_length=0, front_facing=True):
    d = dimensions()
    radius = d['outermost_muzzle_circle_diameter']/2
    height = overall_height()
    length = d['overall_body_length']
    x, y, z = origin
    return Part.makeBox(WIDTH, length+extra_length, height,
                        V(x-WIDTH/2, y-extra_length if front_facing else y-length, z+radius-mounting_height()))


def local_shapes():
    d = dimensions(); radius = d['outermost_muzzle_circle_diameter']/2
    length = d['overall_body_length']; height = overall_height()
    bottom = radius-mounting_height()
    # Cylinder shell and five bubble loops convey visible features only.
    shell = Part.makeCylinder(radius, 23, V(0,-23,0),V(0,1,0)).cut(
        Part.makeCylinder(radius-1.5, 24, V(0,-23.5,0),V(0,1,0)))
    # Three ventilation slots per side, entirely assumed geometry.
    for x in (-radius, radius-4):
        for y in (-21, -16, -11):
            shell = shell.cut(Part.makeBox(4,3,7,V(x,y,-3.5)))
    wheel = Part.makeCylinder(2.8,1.5,V(0,-2,0),V(0,1,0))
    for i in range(5):
        angle = math.radians(90+i*72)
        x,z = 9.1*math.cos(angle),9.1*math.sin(angle)
        loop = Part.makeCylinder(4.3,1.5,V(x,-2,z),V(0,1,0)).cut(
            Part.makeCylinder(3.3,2,V(x,-2.2,z),V(0,1,0)))
        # Radial support kept behind the loop; not a moving-gear reconstruction.
        endpoint = V(x,-1.25,z); start=V(0,-1.25,0); direction=endpoint-start
        spoke=Part.makeCylinder(.65,direction.Length,start,direction)
        wheel=wheel.fuse(loop).fuse(spoke)
    # Motor lies behind the front shell. Rear case reaches the reported total length/height.
    motor=Part.makeCylinder(7,25,V(-3,-48,-1),V(0,1,0))
    tail=tail_dimensions()
    case_height=tail['tail_shell_height_mm']+tail['bottom_tab_height_mm']
    case=Part.makeBox(23,length-23,case_height,V(-11.5,-length,bottom))
    case=case.fuse(Part.makeBox(6,22,case_height,V(11.5,-55,bottom)))
    case=case.cut(motor).cut(shell).removeSplitter()
    # Rear bottom narrows into the measured thin section; it is NOT added below the body.
    td=json.loads((COMPONENT/'mounting-tab-dimensions.json').read_text())['dimensions']
    assert td['height']==tail['bottom_tab_height_mm']==6.8
    tab=Part.makeBox(td['width'],td['length'],td['height'],V(-td['width']/2,-length,bottom))
    front_foot=Part.makeBox(10,length-23-td['length'],td['height'],V(-5,-length+td['length'],bottom))
    cut=Part.makeBox(WIDTH+2,length-23,td['height'],V(-WIDTH/2-1,-length,bottom))
    case=case.cut(cut).removeSplitter()
    shapes=dict(zip(NAMES,(shell,wheel.removeSplitter(),motor,case,tab,front_foot)))
    compound=Part.makeCompound(list(shapes.values()))
    b=bbox(compound)
    assert abs(b[4]-b[1]-length)<1e-6 and abs(b[5]-b[2]-height)<1e-6
    assert all(s.isValid() for s in shapes.values())
    for i,a in enumerate(shapes.values()):
        for bshape in list(shapes.values())[i+1:]:
            assert a.common(bshape).Volume < .01
    assert compound.cut(inspection_box((0,0,0), front_facing=False)).Volume<1e-5
    return shapes


def export_component(shapes, render=False):
    active=App.ActiveDocument
    REVISION.mkdir(parents=True,exist_ok=True)
    report_path=REVISION/'readback.json'
    cad=REVISION/'BubbleGun.FCStd'; step=REVISION/'BubbleGun.step'
    if report_path.exists():
        previous=json.loads(report_path.read_text())
        for name,digest in previous['input_sha256'].items():
            assert hashlib.sha256((REVISION/name).read_bytes()).hexdigest()==digest,name
        for name,digest in previous['files_sha256'].items():
            assert hashlib.sha256((REVISION/name).read_bytes()).hexdigest()==digest,name
        saved=App.openDocument(str(cad))
        for name,shape in shapes.items():
            old=saved.getObject(name).Shape
            assert old.cut(shape).Volume+shape.cut(old).Volume<1e-5,name
        App.closeDocument(saved.Name); App.setActiveDocument(active.Name)
        return
    doc=App.newDocument('BubbleGun')
    doc.Label='泡泡枪主体 · 尾壳35.9／底部薄片6.8保持'
    labels=['前端通风圆筒／枪口外径31.5','五环出泡盘示意','电机外形示意','后部机构壳高35.9／不含薄片6.8','后端底部薄片6×25×6.8／保持原位','前段底部10×19×6.8／配合轮廓假设']
    for (name,shape),label in zip(shapes.items(),labels):
        obj=doc.addObject('Part::Feature',name);obj.Label=label;obj.Shape=shape
        obj.addProperty('App::PropertyString','EvidenceBasis')
        obj.EvidenceBasis='2026-10-26用户确认尾壳35.9不含薄片6.8；承托至尾顶42.7为推导；枪口、薄片、长度保持，宽度和分段轮廓仍是假设'
        if render:obj.ViewObject.ShapeColor=(.88,.87,.78) if name!='BubbleGunMotor' else (.55,.58,.6)
    doc.recompute();doc.saveAs(str(cad));Part.export(doc.Objects,str(step))
    expected={o.Name:o.Shape.copy() for o in doc.Objects}
    App.closeDocument(doc.Name);saved=App.openDocument(str(cad))
    rows=[]
    for obj in saved.Objects:
        delta=expected[obj.Name].cut(obj.Shape).Volume+obj.Shape.cut(expected[obj.Name]).Volume
        assert obj.Shape.isValid() and delta<1e-5
        rows.append({'name':obj.Name,'bbox_mm':bbox(obj.Shape),'valid':True,'symmetric_difference_mm3':delta})
    neutral=Part.Shape();neutral.read(str(step));combined=Part.makeCompound(list(shapes.values()))
    delta=abs(neutral.Volume-combined.Volume)
    assert neutral.isValid() and len(neutral.Solids)==len(combined.Solids) and delta<.01
    report={'historical_user_dimensions_mm':dimensions(),'tail_height_revision':tail_dimensions(),'rear_bottom_tab':json.loads((COMPONENT/'mounting-tab-dimensions.json').read_text()),'local_coordinates':'muzzle end centre at origin; +Y faces outward; body extends to -Y; +Z up',
            'assumptions':{'reserved_width_mm':WIDTH,'shell_length_mm':23,'shell_wall_mm':1.5,
                'wheel_ring_count':5,'wheel_ring_outer_radius_mm':4.3,'wheel_ring_inner_radius_mm':3.3,
                'wheel_ring_centres_radius_mm':9.1,'motor_radius_mm':7,'motor_length_mm':25,
                'motor_origin_mm':[-3,-48,-1],'case_width_mm':23,'case_shell_height_mm':35.9,
                'side_case_shell_size_xyz_mm':[6,22,35.9],'side_case_shell_origin_mm':[11.5,-55,-13.65],
                'vent_slot_size_xyz_mm':[4,3,7],'vent_y_mm':[-21,-16,-11],
                'all_internal_dimensions_and_positions':'Except the user-confirmed tail height, widths, lengths and internal geometry remain illustrative, not inferred measurements.'},
            'objects':rows,'actual_model_bbox_mm':bbox(combined),'inspection_bbox_mm':bbox(inspection_box((0,0,0), front_facing=False)),
            'step_readback':{'valid':True,'volume_difference_mm3':delta,'solid_count':len(neutral.Solids)},
            'input_sha256':{**{'../../'+p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (COMPONENT/'dimensions.json',COMPONENT/'sources.json',COMPONENT/'mounting-tab-dimensions.json')},'dimensions.json':hashlib.sha256((REVISION/'dimensions.json').read_bytes()).hexdigest()},
            'files_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (cad,step)},
            'maximum_width_measured':False,'mounts_designed':False,'physical_fit_verified':False}
    report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    App.closeDocument(saved.Name);App.setActiveDocument(active.Name)


def add_bubble_gun(doc, add, render=False):
    shapes=local_shapes();export_component(shapes,render)
    for name,shape in shapes.items():
        moved=shape.copy();moved.rotate(V(),V(0,0,1),180);moved.translate(V(*ORIGIN))
        obj=add(name,'泡泡枪主体／'+name.removeprefix('BubbleGun'),moved,'component',
                'metal' if name=='BubbleGunMotor' else 'light',
                '2026-10-26尾壳高35.9不含薄片6.8，承托至尾顶42.7；枪口与承托基准保持；宽度及分段为假设')
        obj.addProperty('App::PropertyString','ServiceGroup','Assembly');obj.ServiceGroup='bubble_gun'
    add('BubbleGunInspectionEnvelope','泡泡枪安装审查空间／宽35.8为假设',inspection_box(),'clearance','bubble',
                '长67用户提供；高度按尾壳35.9+薄片6.8=42.7推导，承托基准保持；宽35.8为预留；不是实测等截面外形')
    from bubble_gun_mount import build_mount
    mount=build_mount(doc,add)
    return {'source':'hardware/components/bubble-gun/README.md','origin_mm':list(ORIGIN),
            'tail_shell_height_mm':tail_dimensions()['tail_shell_height_mm'],
            'bottom_tab_height_mm':tail_dimensions()['bottom_tab_height_mm'],
            'support_to_tail_top_mm':overall_height(),
            'component_revision':str(REVISION.relative_to(ROOT/'hardware')),
            'rotation_degrees':[0,0,180],'orientation':'muzzle -Y; body toward +Y; front-view left / vehicle right',
            'inspection_bbox_mm':bbox(inspection_box()),'reserved_width_mm':WIDTH,
            'mount':mount,'mounts_and_hose_routes_designed':True}


def check_bubble_gun(doc, service_check):
    from refine_assembly import service_groups
    from controller_layout import controller_members
    bound=doc.getObject('BubbleGunInspectionEnvelope').Shape
    obstacles=[o for o in doc.Objects if hasattr(o,'Category') and o.Name not in (*NAMES,'BubbleGunInspectionEnvelope')]
    from bubble_gun_mount import check_mount
    mount_check=check_mount(doc)
    contacts=[o.Name for o in obstacles if o.Name.startswith(('BubbleGunLowerPad','BubbleGunUpperPad','BubbleGunCap','BubbleGunRing','BubbleGunSlot')) and o.Category!='clearance']
    intrusions=hits(bound,[o for o in obstacles if o.Name in contacts])
    overlaps=hits(bound,[o for o in obstacles if o.Name not in contacts and not (o.Category=='clearance' and o.Name.startswith('BubbleGun'))])
    nearest=sorted([{'object':o.Name,'distance_mm':bound.distToShape(o.Shape)[0]} for o in obstacles if o.Name not in contacts and o.Category!='clearance'],key=lambda r:r['distance_mm'])[:12]
    removal=next(r for r in mount_check['continuous_service_sweeps'] if r['operation']=='body_install_remove')['overlaps']
    groups=service_groups(doc)
    special={'controller':controller_members(doc),'controller_retainer':['ControllerRetainer'],
             'controller_board':['ESP32Board'],'usb_com':['ControllerUSBCOM'],'usb_native':['ControllerUSBUSB']}
    others=[]
    for scenario in service_check['scenarios']:
        group=scenario['group']
        if group.startswith('bubble_gun'):continue
        names=special[group] if group in special else groups[group]
        clashes=[]
        for start,end in zip(scenario['waypoints_mm'],scenario['waypoints_mm'][1:]):
            for name in names:
                b=bbox(doc.getObject(name).Shape)
                low=[b[i]+min(start[i],end[i]) for i in range(3)]
                high=[b[i+3]+max(start[i],end[i]) for i in range(3)]
                sweep=Part.makeBox(*(high[i]-low[i] for i in range(3)),V(*low))
                volume=sweep.common(bound).Volume
                if volume>.01:clashes.append({'moving':name,'volume_mm3':volume})
        others.append({'group':group,'overlaps':clashes,'passed':not clashes})
    return {'mount_check':mount_check,'nominal_mount_intrusions':intrusions,
            'method':'reserved box vs external obstacles; contact pads/caps use actual mockup geometry and assumed contact profiles, not measured surfaces',
            'tolerance_mm3':.01,'overlaps':overlaps,'nearest_clearances':nearest,
            'removal':{'method':'tail-up15deg, rear10, lift3, outboard90 in tilted module frame; sampled CAD path',
                       'preconditions':'remove adhesive; disconnect connector then hose and move flexible routes',
                       'overlaps':removal,'passed':not removal},
            'other_service_sweeps':{'method':'conservative per-object AABB of every straight path segment vs bubble reserved box',
                                    'scenarios':others,'passed':all(r['passed'] for r in others)},
            'passed':mount_check['passed'] and not overlaps and not removal and all(r['passed'] for r in others),
            'width_and_interfaces_measured':False,'physical_fit_verified':False}
