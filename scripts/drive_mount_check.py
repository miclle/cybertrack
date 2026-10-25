"""Independent saved-solid mounting, continuity and assembly-path checks."""
import hashlib,json,math
from pathlib import Path
import FreeCAD as App
import Part
from drive_mount import V,box,cx,cz,union,side_shape,HOLES,COVER_POINTS
ROOT=Path(__file__).resolve().parents[1]
TOL=1e-5


def capsule_drop(x0,x1,y,z,r,drop=80):
    return union([cx(r,x0,x1,y,z),cx(r,x0,x1,y,z-drop),
                  box(x0,y-r,z-drop,x1,y+r,z)])


def cover_sweep():
    return union([box(25.7,-19.1,-52,67.3,31.3,30.8),
                  box(22.5,-19,-52,27,19,30.8),box(61,-26,-52,67.3,23,30.8)]
                 +[cz(3,-52,38,x,y) for x,y in COVER_POINTS])


def check(doc,verbose=False):
    objects={o.Name:o for o in doc.Objects if hasattr(o,'Category') and o.Category!='clearance'}
    shapes={n:o.Shape for n,o in objects.items()}
    bounds={n:s.optimalBoundingBox(False) for n,s in shapes.items()}
    tub=shapes['LowerTub'];report={'tolerance_mm3':TOL,'interfaces':[], 'paths':[], 'tools':[], 'negative_controls':[]}
    def hits(moving,absent):
        rows=[];absent=set(absent)
        for label,q in moving.items():
            b=q.optimalBoundingBox(False)
            for n,s in shapes.items():
                if n in absent or not b.intersect(bounds[n]):continue
                overlap=q.common(s)
                v=sum(t.Volume for t in overlap.Solids)
                if not overlap.isValid() or v>TOL:rows.append({'moving':label,'fixed':n,'volume_mm3':v,'valid':overlap.isValid()})
        return rows
    def swept(name,parts,absent,description):
        h=hits(parts,absent);row={'name':name,'method':'continuous conservative solid sweep','description':description,
                                'absent':sorted(set(absent)),'collisions':h,'passed':not h}
        report['paths'].append(row)
        if verbose:print(name,row['passed'],h,flush=True)
    refdir=ROOT/'hardware/components/drive-interface'
    evidence=json.loads((refdir/'readback.json').read_text())
    for file,digest in evidence['files_sha256'].items():
        if hashlib.sha256((refdir/file).read_bytes()).hexdigest()!=digest:raise ValueError('Read-only interface reference changed: '+file)
    ref=Part.Shape();ref.read(str(refdir/'MotorInterfaceL.brep'));ref.translate(V(14,0,0))
    ref_screw=Part.Shape();ref_screw.read(str(refdir/'TrackMountScrewLFront.brep'));ref_screw.translate(V(14,0,0))
    drive=App.openDocument(str(ROOT/'hardware/components/drive-layout/DriveLayout.FCStd'))
    unchanged=[]
    try:
        for o in drive.Objects:
            sign=1 if o.Shape.optimalBoundingBox(False).XMin>0 else -1
            q=o.Shape.copy();q.translate(V(sign*14,0,0));actual=shapes[o.Name]
            # Tessellation-independent BRep equality; fall back to exact differences.
            same=q.copy().cleaned().exportBrepToString()==actual.copy().cleaned().exportBrepToString()
            delta=0 if same else q.cut(actual).Volume+actual.cut(q).Volume
            unchanged.append({'name':o.Name,'difference_mm3':delta,'passed':delta<=TOL})
    finally:App.closeDocument(drive.Name)
    report['drive_preservation']={'objects':unchanged,'translation_mm':{'L':[14,0,0],'R':[-14,0,0]},'passed':len(unchanged)==30 and all(r['passed'] for r in unchanged)}
    report['reference']={'source_sha256':evidence['source_sha256'],'curated_files_sha256':evidence['files_sha256'],
                         'mask_source_mm':evidence['clip_box_mm'],'coordinate_transform':'X +/-14 mm; no scale or rotation'}
    battery=['PowerBank','BatteryHatch','BatteryPullStrap','CableServiceCover','PowerCableRoute']+[n for n in shapes if n.startswith(('BatteryPad','BatteryScrew','AccessScrew'))]
    for side,sign in [('L',1),('R',-1)]:
        track=[n for n in shapes if n.startswith('Track'+('Left' if sign>0 else 'Right')) or n in ('TrackMount'+side,'DriveCoupler'+side)]
        cover=['MotorServiceCover'+side]
        cs=[n for n in shapes if n.startswith('MotorCoverScrew'+side)]
        ms=[n for n in shapes if n.startswith('MotorFaceScrew'+side)]
        ts=[n for n in shapes if n.startswith('TrackMountScrew'+side)]
        motor=['Motor'+side,'MotorShaft'+side]
        expected=side_shape(ref,sign)
        actual=tub.common(side_shape(box(73.3,-36,28,87.01,36,73),sign))
        delta=expected.cut(actual).Volume+actual.cut(expected).Volume
        report['interfaces'].append({'kind':'reference_local_face_and_posts','side':side,'difference_mm3':delta,'passed':delta<=TOL})
        for i,(y,z) in enumerate(HOLES):
            ring=cx(2.4,73.1,76.9,y,z).cut(cx(1.8,73.1,76.9,y,z))
            missing=side_shape(ring,sign).cut(tub).Volume
            report['interfaces'].append({'kind':'motor_bearing_seat','side':side,'hole_index':i,'missing_material_mm3':missing,
                'complete_required':i<4,'passed':missing<=TOL if i<4 else missing>1})
        channel=side_shape(box(73.01,-6.49,28,76.99,6.49,56.99),sign)
        blocked=channel.common(tub).Volume
        report['interfaces'].append({'kind':'13mm_face_channel','side':side,'blocked_mm3':blocked,'passed':blocked<=TOL})
        # Contact between fixed posts and purchased mount is measured face-to-face,
        # not by a solid common that discards zero-volume contact.
        for end,y in [('Front',-28.1),('Rear',28.1)]:
            screw=shapes['TrackMountScrew'+side+end]
            expected_screw=ref_screw.copy()
            if end=='Rear':expected_screw.translate(V(0,56.2,0))
            expected_screw=side_shape(expected_screw,sign)
            delta=screw.cut(expected_screw).Volume+expected_screw.cut(screw).Volume
            ring=cx(4,86.9,87,y,37.4).cut(cx(1.8,86.9,87,y,37.4))
            missing=side_shape(ring,sign).cut(tub).Volume
            face=Part.Face(Part.Wire(Part.makeCircle(4,V(sign*87,y,37.4),V(sign,0,0))))
            face=face.cut(Part.Face(Part.Wire(Part.makeCircle(1.8,V(sign*87,y,37.4),V(sign,0,0)))))
            contact=sum(face.common(f).Area for f in shapes['TrackMount'+side].Faces if face.distToShape(f)[0]<1e-6)
            report['interfaces'].append({'kind':'track_screw_and_contact','side':side,'end':end,'screw_difference_mm3':delta,
                'missing_post_seat_mm3':missing,'mount_contact_area_mm2':contact,'passed':delta<=TOL and missing<=TOL and contact>30})
        for i,(x,y) in enumerate(COVER_POINTS):
            ring=cz(2.8,38,38.1,sign*x,y).cut(cz(1.4,38,38.1,sign*x,y))
            lower=cz(2.8,37.9,38,sign*x,y).cut(cz(1.8,37.9,38,sign*x,y))
            missing=ring.cut(tub).Volume+lower.cut(shapes[cover[0]]).Volume
            report['interfaces'].append({'kind':'cover_clamping_land','side':side,'index':i,'missing_material_mm3':missing,'passed':missing<=TOL})
        # Covers retain a straight vertical route inside the complete tracks.
        swept('cover_'+side,{cover[0]:side_shape(cover_sweep(),sign)},cover+cs,'80 mm downward; both full tracks remain installed')
        for i,(x,y) in enumerate(COVER_POINTS):
            q=union([cz(2.7,-48.8,34,x,y),cz(1.2,-46,43.8,x,y)])
            swept('cover_screw_'+side+str(i),{'screw':side_shape(q,sign)},[cs[i]],'80 mm downward; cover and tracks remain')
            tool=side_shape(union([cz(1,30.8,32.6,x,y),cz(2,-15,30.8,x,y)]),sign)
            h=hits({'tool':tool},[])
            report['tools'].append({'name':'cover_bit_'+side+str(i),'scope':'2mm bit / 4mm vertical shaft only, not handle or hand','collisions':h,'passed':not h})
        m=union([capsule_drop(26.2,49,0,50,16),capsule_drop(49,73,0,50,18.5),
                 capsule_drop(73,79,0,57,6),capsule_drop(73,95,0,57,3)])
        swept('motor_'+side,{'complete_motor':side_shape(m,sign)},motor+cover+cs+ms+ts+track,
              '80 mm vertically at final XY; opposite motor and opposite track remain; full round shaft is conservative to the D-flat')
        blocker=side_shape(box(73,-6.5,28,77,6.5,57),sign)
        lowered=shapes['Motor'+side].copy();lowered.translate(V(0,0,-12))
        control=lowered.common(blocker).Volume
        report['negative_controls'].append({'name':'closed_channel_'+side,'collision_mm3':control,'passed':control>1})
        for i,(y,z) in enumerate(HOLES[:4]):
            q=union([cx(2.7,77,104.8,y,z),cx(1.4,71,102,y,z)])
            swept('motor_face_screw_'+side+str(i),{'screw':side_shape(q,sign)},[ms[i]]+track+ts,
                  '25 mm axially outward before the track module is installed')
            tool=side_shape(union([cx(1,78.4,82,y,z),cx(2,82,115,y,z)]),sign)
            h=hits({'tool':tool},track+ts)
            report['tools'].append({'name':'motor_bit_'+side+str(i),'scope':'2mm bit / 4mm shaft only, not handle or hand','collisions':h,'passed':not h})
        for end,y in [('Front',-28.1),('Rear',28.1)]:
            name='TrackMountScrew'+side+end
            lateral=union([cx(2.7,37.7,76,y,37.4),cx(1.5,40.5,102,y,37.4)])
            vertical=union([capsule_drop(37.7,40.5,y,37.4,2.7),capsule_drop(40.5,66.5,y,37.4,1.5)])
            absent=[name]+cover+cs+(battery if end=='Front' else [])
            swept('track_screw_'+side+end,{'axial':side_shape(lateral,sign),'vertical':side_shape(vertical,sign)},absent,
                  '35.5 mm inward then 80 mm down; assembly reverses this route; complete tracks stay installed')
            tool=side_shape(cx(2,10,73.2,y,37.4),sign)
            h=hits({'tool_shaft':tool},absent)
            report['tools'].append({'name':'track_tool_'+side+end,'scope':'4mm straight shaft from X10 to73.2; handle/hand not modeled','collisions':h,'passed':not h})
            bad=shapes[name].copy();bad.translate(V(-sign*31.5,0,-35))
            badhits=hits({'screw':bad},[name]+cover+cs+battery)
            report['negative_controls'].append({'name':'insufficient_inboard_shift_'+side+end,'collisions':badhits,
                'passed':any(r['fixed'].startswith('Track'+('Left' if sign>0 else 'Right')) for r in badhits)})
        # Full tread/receiver shapes, not a box around them: sample at 1 mm.
        poses=[]
        for offset in range(61):
            moving={}
            for n in track:
                q=shapes[n].copy();q.translate(V(sign*offset,0,0));moving[n]=q
            h=hits(moving,track+ts)
            poses.append({'offset_mm':offset,'collisions':h})
        row={'name':'track_module_'+side,'method':'1 mm discrete positions, 0..60 mm outward','moving_parts':track,
             'absent':ts,'poses':poses,'passed':len(track)==13 and not any(p['collisions'] for p in poses)}
        report['paths'].append(row)
        if verbose:print(row['name'],row['passed'],flush=True)
    report['single_chassis']={'valid':tub.isValid(),'solids':len(tub.Solids),'passed':tub.isValid() and len(tub.Solids)==1}
    widths=[]
    for y in (-50,50):
        edges=tub.common(Part.makeLine(V(-100,y,40),V(100,y,40))).Edges
        vals=[v.Point.x for e in edges for v in e.Vertexes]
        widths.append({'y':y,'z':40,'width_mm':max(vals)-min(vals)})
    report['lower_width']={'stations':widths,'passed':all(abs(r['width_mm']-132)<1e-6 for r in widths)}
    rear_rows=[]
    for side in (-1,1):
        for y in (71.5,73.5,73.99):
            for z in (40,60):
                probe=side_shape(box(43.9,y-.005,z-.005,45.1,y+.005,z+.005),side)
                missing=probe.cut(tub).Volume
                rear_rows.append({'side':side,'y':y,'z':z,'missing_mm3':missing,'passed':missing<=1e-7})
    report['rear_transition']={'probes':rear_rows,'passed':all(r['passed'] for r in rear_rows)}
    report['passed']=all(report[k]['passed'] for k in ('single_chassis','lower_width','drive_preservation','rear_transition')) and all(r['passed'] for key in ('interfaces','paths','tools','negative_controls') for r in report[key])
    report['limitations']=['Track module axial paths are sampled at 1 mm, not continuous proofs.',
        'Other paths use conservative continuous rigid sweeps; actual encoder/cables, tool handles/hands, flex and tolerances are not modeled.',
        'Motor screw engagement2mm and M3-like smooth fasteners are candidates. Four full seats retained; lower two holes are not accepted as seats.',
        'No physical assembly, strength, creep, thread pullout, liquid sealing or manufacturing release.']
    return report
