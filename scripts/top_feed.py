"""Top-inserted suction hoses; self-priming is user-confirmed, fit remains a candidate."""
import FreeCAD as App
import Part

V = App.Vector
PORT_DIAMETER = 9.0
DIP_END_Z = 45.0
TOP_PARTS = ('PodCap', 'FillPlug', 'ServiceLid', 'CapGrip')
ROUTES = ('WaterHoseRoute', 'BubbleGunHoseRoute')


def finish_top_feed(doc):
    """Cut only the top passage and remove tube clearance from fluid allocations."""
    for name, x in (('Water', -24), ('Bubble', 24)):
        passage = Part.makeCylinder(PORT_DIAMETER/2, 20, V(x, 49, 120))
        for suffix in TOP_PARTS:
            obj = doc.getObject(name+suffix)
            obj.Shape = obj.Shape.cut(passage).removeSplitter()
        # These are liquid-space reservations, not solid equipment or tank walls.
        allocation = doc.getObject(name+'Module')
        allocation.Shape = allocation.Shape.cut(Part.makeCylinder(4, 90, V(x, 49, 40)))
        allocation.Label = ('喷水' if name == 'Water' else '泡泡')+'液体区占位／扣除顶部吸管预留'
        allocation.EvidenceBasis = '原Ø32×70液体空间分配减去Ø8吸管审查通道；非实测容量或设备外包络'


def check_top_feed(doc):
    from water_gun_layout import hits
    results = []
    for name, x, route, space in (('Water', -24, 'WaterHoseRoute', 'WaterGunHoseClearance'),
                                 ('Bubble', 24, 'BubbleGunHoseRoute', 'BubbleGunHoseClearance')):
        tube = doc.getObject(route).Shape
        corridor = doc.getObject(space).Shape
        full_pod = Part.makeCylinder(20, 82, V(x, 49, 40)).cut(Part.makeCylinder(17, 82, V(x, 49, 40)))
        pod = doc.getObject(name+'Pod').Shape
        pod_delta = full_pod.cut(pod).Volume + pod.cut(full_pod).Volume
        straight = Part.makeCylinder(2.5 if name == 'Water' else 2, 85, V(x, 49, DIP_END_Z))
        missing_straight = straight.cut(tube).Volume
        parts = [doc.getObject(name+suffix) for suffix in TOP_PARTS]
        overlaps = hits(corridor, parts)
        gaps = [{'object': o.Name, 'distance_mm': corridor.distToShape(o.Shape)[0]} for o in parts]
        bb = tube.optimalBoundingBox(False)
        passed = (pod_delta <= 1e-5 and missing_straight <= 1e-5 and not overlaps
                  and min(g['distance_mm'] for g in gaps) >= .5-1e-5
                  and abs(bb.ZMin-DIP_END_Z) <= 1e-5 and bb.YMax < 74)
        results.append({'reservoir': name, 'top_axis_xy_mm': [x,49], 'dip_end_z_mm': DIP_END_Z,
                        'nominal_bottom_reference_z_mm':40,'nominal_bottom_gap_mm':5,
                        'top_passage_candidate_diameter_mm':PORT_DIAMETER,
                        'pod_side_wall_symmetric_difference_mm3':pod_delta,
                        'vertical_dip_segment_missing_volume_mm3':missing_straight,
                        'top_part_clearance_overlaps':overlaps,'top_part_clearance_gaps':gaps,
                        'hose_maximum_y_mm':bb.YMax,'passed':passed})
    rear = doc.getObject('RearBaseArmor').Shape
    former_hole = Part.makeCylinder(4.5,8,V(24,74,76),V(0,1,0))
    missing_rear = former_hole.cut(rear).Volume
    return {'source':'user confirmed both guns are self-priming and all liquid hoses enter from the top',
            'self_priming_user_confirmed':{'water':True,'bubble':True},
            'top_insertion_only':True,'reservoirs':results,
            'former_rear_hole_missing_volume_mm3':missing_rear,
            'lid_service_prerequisite':'withdraw both suction hoses before opening either reservoir lid; flexible hose handling not validated',
            'liquid_allocations':'original cylindrical fluid reservations minus the dip-tube review corridor; not measured capacity',
            'suction_lift_air_seal_priming_and_physical_fit_verified':False,
            'passed':all(r['passed'] for r in results) and missing_rear<=1e-5}
