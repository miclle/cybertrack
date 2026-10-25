"""Saved-geometry checks for the integral chassis and track-first motor service."""
from pathlib import Path
import FreeCAD as A
import Part
from drive_mount import V,box,cx,cz,union,side_shape,HOLES
from drive_service import COVER_POINTS,translated
from drive_mount_check import capsule_drop
ROOT=Path(__file__).resolve().parents[1]
TOL=1e-5


def check(doc,verbose=False):
    objects={o.Name:o for o in doc.Objects if hasattr(o,'Category') and o.Category!='clearance'}
    shapes={n:o.Shape for n,o in objects.items()};bounds={n:s.optimalBoundingBox(False) for n,s in shapes.items()}
    r={'tolerance_mm3':TOL,'interfaces':[],'paths':[],'tools':[],'negative_controls':[],
       'motor_service_prerequisites':['Remove unified cover','Disconnect power and motor leads','Remove power bank with its independent tray for front track screw access','Release actual coupling lock','Remove serviced track assembly and its two screws','Remove four motor face screws'],
       'retained_for_motor_service':['opposite complete track assembly','opposite motor','rear wet bulkhead'],
       'coupling_release':'Actual coupling locking details and encoder tail are not modeled; release and cable disconnection require physical confirmation.'}
    def hits(parts,absent):
        rows=[]
        for label,q in parts.items():
            b=q.optimalBoundingBox(False)
            for n,s in shapes.items():
                if n in absent or not b.intersect(bounds[n]):continue
                overlap=q.common(s);v=sum(t.Volume for t in overlap.Solids)
                if not overlap.isValid() or v>TOL:rows.append({'moving':label,'fixed':n,'volume_mm3':v})
        return rows
    def swept(name,parts,absent,description):
        h=hits(parts,set(absent));row={'name':name,'method':'continuous conservative solid sweep','description':description,'absent':sorted(set(absent)),'collisions':h,'passed':not h}
        r['paths'].append(row)
        if verbose:print(name,row['passed'],h,flush=True)
    src=A.openDocument(str(ROOT/'hardware/components/drive-layout/DriveLayout.FCStd'));rows=[]
    for o in src.Objects:
        sign=1 if o.Shape.optimalBoundingBox(False).XMin>0 else -1
        q=translated(o.Shape,(sign*14,0,0));s=shapes[o.Name]
        eq=q.cleaned().exportBrepToString()==s.cleaned().exportBrepToString()
        diff=0 if eq else q.cut(s).Volume+s.cut(q).Volume
        if verbose:print('drive preserved',o.Name,diff,flush=True)
        rows.append({'name':o.Name,'difference_mm3':diff,'passed':diff<=TOL})
    A.closeDocument(src.Name)
    r['drive_preservation']={'objects':rows,'translation_mm':{'L':[14,0,0],'R':[-14,0,0]},'passed':len(rows)==30 and all(q['passed'] for q in rows)}
    tub=shapes['LowerTub'];cover=['BottomServiceCover'];cs=[n for n in shapes if n.startswith('BottomCoverScrew')]
    battery=[n for n in shapes if n.startswith(('BatteryPad','BatteryScrew','BatterySupportWasher'))]+['PowerBank','BatteryHatch','BatteryPullStrap','PowerCableRoute']
    cover_sweep=box(-65.8,-96.8,-54,65.8,40,28.8)
    for sign in (-1,1):
        for y in (-85,-40):cover_sweep=cover_sweep.cut(cz(2.5,28.8,30,sign*63.5,y))
    if doc.getObject('L298NCarrier'):
        # The carrier fastener heads remain in place while the independent cover
        # is removed. Its actual new head-clearance holes continue through the sweep.
        for x in (-20,20):cover_sweep=cover_sweep.cut(cz(2.8,-54.1,28.9,x,-12))
    swept('unified_cover',{'cover':cover_sweep},cover+cs,'80mm down; power bank and both drives still installed')
    for i,(x,y) in enumerate(COVER_POINTS):
        swept('bottom_screw_'+str(i),{'screw':union([cz(2.2,-53.5,28,x,y),cz(1.2,-52,35.8,x,y)])},[cs[i]],'80mm downward')
        top=cz(2.6,28.8,28.9,x,y).cut(cz(1.6,28.8,28.9,x,y))
        lower=cz(2.6,28.7,28.8,x,y).cut(cz(1.6,28.7,28.8,x,y))
        missing=top.cut(tub).Volume+lower.cut(shapes['BottomServiceCover']).Volume
        r['interfaces'].append({'kind':'cover_clamping_land','index':i,'missing_mm3':missing,'passed':missing<=TOL})
        tool=union([cz(.8,26.2,27,x,y),cz(2,-20,26.2,x,y)])
        h=hits({'tool':tool},[]);r['tools'].append({'name':'bottom_bit_'+str(i),'collisions':h,'passed':not h})
    for side,sign in [('L',1),('R',-1)]:
        track=[n for n in shapes if n.startswith('TrackLeft' if sign>0 else 'TrackRight')]+['TrackMount'+side,'DriveCoupler'+side]
        ts=[n for n in shapes if n.startswith('TrackMountScrew'+side)]
        ms=[n for n in shapes if n.startswith('MotorFaceScrew'+side)]
        motor=['Motor'+side,'MotorShaft'+side]
        for i,(y,z) in enumerate(HOLES[:4]):
            ring=side_shape(cx(2.4,73.1,76.9,y,z).cut(cx(1.8,73.1,76.9,y,z)),sign)
            missing=ring.cut(tub).Volume
            r['interfaces'].append({'kind':'integral_motor_seat','side':side,'hole':i,'missing_mm3':missing,'passed':missing<=TOL})
            screw=union([cx(2.7,77,104.8,y,z),cx(1.4,71,102,y,z)])
            swept('motor_face_screw_'+side+str(i),{'screw':side_shape(screw,sign)},[ms[i]]+track+ts+cover+cs+battery,'25mm axially outward after track removal; reverse for installation')
            tool=side_shape(union([cx(1,78.4,82,y,z),cx(2,82,115,y,z)]),sign)
            h=hits({'tool':tool},track+ts+cover+cs+battery)
            r['tools'].append({'name':'motor_face_bit_'+side+str(i),'collisions':h,'passed':not h})
            blocked=hits({'tool':tool},cover+cs+battery)
            r['negative_controls'].append({'name':'track_retained_blocks_face_tool_'+side+str(i),'collisions':blocked,
                                          'passed':any(v['fixed']=='TrackMount'+side for v in blocked)})
        for end,y in [('Front',-28.1),('Rear',28.1)]:
            ring=side_shape(cx(4,86.9,87,y,37.4).cut(cx(1.8,86.9,87,y,37.4)),sign)
            missing=ring.cut(tub).Volume
            r['interfaces'].append({'kind':'track_post','side':side,'y':y,'missing_mm3':missing,'passed':missing<=TOL})
            name='TrackMountScrew'+side+end
            lateral=union([cx(2.7,37.7,76,y,37.4),cx(1.5,40.5,102,y,37.4)])
            vertical=union([capsule_drop(37.7,40.5,y,37.4,2.7),capsule_drop(40.5,66.5,y,37.4,1.5)])
            absent=[name]+cover+cs+(battery if end=='Front' else [])
            swept('track_screw_'+side+end,{'axial':side_shape(lateral,sign),'vertical':side_shape(vertical,sign)},absent,
                  '35.5mm inward then80mm down; front requires prior removal of power bank and tray; opposite track screw remains')
            tool=side_shape(cx(2,10,73.2,y,37.4),sign)
            h=hits({'tool':tool},absent);r['tools'].append({'name':'track_tool_'+side+end,'collisions':h,'passed':not h})
            bad=translated(shapes[name],(-sign*31.5,0,-35));h=hits({'screw':bad},[name]+cover+cs+battery)
            r['negative_controls'].append({'name':'short_track_screw_withdrawal_'+side+end,'collisions':h,
                                          'passed':any(v['fixed'].startswith('TrackLeft' if sign>0 else 'TrackRight') for v in h)})
        poses=[]
        for offset in range(61):
            h=hits({n:translated(shapes[n],(sign*offset,0,0)) for n in track},track+ts+cover+cs+battery)
            poses.append({'offset_mm':offset,'collisions':h})
        r['paths'].append({'name':'track_module_'+side,'method':'1mm discrete positions,0..60mm outward','moving_parts':track,
                           'absent':track+ts+cover+cs+battery,'poses':poses,'passed':len(track)==13 and not any(v['collisions'] for v in poses)})
        if verbose:print('track_module_'+side,r['paths'][-1]['passed'],flush=True)
        down=union([capsule_drop(26.2,49,0,50,16),capsule_drop(49,73,0,50,18.5),capsule_drop(73,79,0,57,6),capsule_drop(73,95,0,57,3)])
        swept('motor_down_'+side,{'motor_and_shaft':side_shape(down,sign)},motor+ms+track+ts+cover+cs+battery,
              '80mm vertically down at original XY; no inward move; serviced track and motor face screws removed; opposite drive retained')
        blocker=side_shape(box(73,-6.5,28,77,6.5,57),sign)
        bad=translated(shapes['Motor'+side],(0,0,-12));v=bad.common(blocker).Volume
        r['negative_controls'].append({'name':'closed_motor_slot_'+side,'collision_mm3':v,'passed':v>1})
    def contact_at(a,b,z):
        fa=[f for f in a.Faces if abs(f.BoundBox.ZMin-z)<1e-6 and abs(f.BoundBox.ZMax-z)<1e-6]
        fb=[f for f in b.Faces if abs(f.BoundBox.ZMin-z)<1e-6 and abs(f.BoundBox.ZMax-z)<1e-6]
        return sum(f.common(g).Area for f in fa for g in fb)
    for side in ('L','R'):
        for end in ('Front','Rear'):
            washer=shapes['BatterySupportWasher'+side+end]
            top=contact_at(washer,shapes['BatteryHatch'],31);bottom=contact_at(washer,shapes['BatteryScrew'+side+end],30.5)
            r['interfaces'].append({'kind':'battery_washer_bearing','side':side,'end':end,'tray_contact_mm2':top,'screw_head_contact_mm2':bottom,'passed':top>5 and bottom>5})
    r['single_chassis']={'valid':tub.isValid(),'solids':len(tub.Solids),'passed':tub.isValid() and len(tub.Solids)==1}
    widths=[]
    for y in (-50,50):
        e=tub.common(Part.makeLine(V(-100,y,40),V(100,y,40))).Edges;v=[p.Point.x for q in e for p in q.Vertexes]
        widths.append({'y':y,'z':40,'width_mm':max(v)-min(v)})
    r['lower_width']={'stations':widths,'passed':all(abs(v['width_mm']-132)<1e-6 for v in widths)}
    forbidden=[n for n in shapes if n in ('FrontBulkhead','BatteryRoof') or n.startswith(('MotorEndPlate','MotorCarrier'))]
    beams=[]
    for y0,y1 in [(-22.7,-19.2),(19.2,23.9)]:
        v=tub.common(box(-40,y0,37.1,40,y1,42.9)).Volume
        beams.append({'y_range_mm':[y0,y1],'remaining_volume_mm3':v,'passed':v<TOL})
    wet=shapes['RearBulkhead'];b=wet.optimalBoundingBox(False)
    r['simplified_interior']={'forbidden_objects':forbidden,'removed_crossbeams':beams,
        'rear_wet_bulkhead':{'valid':wet.isValid(),'solids':len(wet.Solids),'bbox_mm':[b.XMin,b.YMin,b.ZMin,b.XMax,b.YMax,b.ZMax]},
        'passed':not forbidden and all(v['passed'] for v in beams) and wet.isValid() and len(wet.Solids)==1}
    r['limits']=['Complete track withdrawal is sampled at1mm, not continuously proved.','Coupling locking hardware, encoder tail, flexible cables and tool handles/hands require physical verification.','No material, strength, fatigue, thread, tolerance, sealing or manufacturing acceptance.']
    r['passed']=all(q['passed'] for k in ('interfaces','paths','tools','negative_controls') for q in r[k]) and all(r[k]['passed'] for k in ('drive_preservation','single_chassis','lower_width','simplified_interior'))
    return r
