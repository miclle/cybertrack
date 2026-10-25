"""Top-entry candidate for capped purchased bottles; no invented bottle-wall holes."""
import FreeCAD as A
import Part
from bottle_backpack import CENTRES, Y
V=A.Vector


def check_top_feed(doc):
    from water_gun_layout import hits
    rows=[]
    for name,x in CENTRES:
        route='WaterHoseRoute' if name=='Water' else 'BubbleGunHoseRoute'
        space='WaterGunHoseClearance' if name=='Water' else 'BubbleGunHoseClearance'
        corridor=doc.getObject(space).Shape
        parts=[doc.getObject(name+s) for s in ('Pod','RetentionBand','StrapClosure')]
        overlaps=hits(corridor,parts)
        gaps=[{'object':o.Name,'distance_mm':corridor.distToShape(o.Shape)[0]} for o in parts]
        actual=doc.getObject(route).Shape
        start=Part.makeCylinder(2.5 if name=='Water' else 2,6,V(x,Y,154.5))
        missing=start.cut(actual).Volume
        rows.append({'reservoir':name,'top_axis_xy_mm':[x,Y],'external_hose_start_z_mm':154.5,
            'internal_dip_space_z_mm':[45,154.5],'printed_lid_present':False,
            'top_part_clearance_overlaps':overlaps,'top_part_clearance_gaps':gaps,
            'vertical_entry_missing_volume_mm3':missing,
            'passed':not overlaps and missing<1e-5 and min(g['distance_mm'] for g in gaps)>=1-1e-5})
    return {'source':'user specified two capped 150 mL bottles OD48.8 x114; top hose entry retained',
            'self_priming_user_confirmed':{'water':True,'bubble':True},'top_insertion_only':True,'reservoirs':rows,
            'lid_service_prerequisite':'withdraw and park target hose, open and park target band, lift target bottle; opposite bottle and hose stay installed',
            'bottle_envelope_uncut':True,'bottle_cap_fitting_and_vent_not_designed':True,
            'internal_hose_is_clearance_only':True,'suction_lift_air_seal_priming_and_physical_fit_verified':False,
            'passed':all(r['passed'] for r in rows)}
