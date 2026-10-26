"""30 mm tail-gap cassette candidate, with removable-cover mounting.

All pad contacts, screw envelopes and wire channels are design allocations.
No PCB holes, terminal coordinates or wire sizes are inferred from photos.
"""
import math
import FreeCAD as A
import Part
from check_l298n_measured_gap import box, bounds, union, collisions
V=A.Vector
REVISION='0.57'
BASIS='2026-10-26：两电机安装面至尾部均57 mm，直接净距30 mm；L298N插线总厚28.5 mm；按较小净距设计；紧固件、PCB接触、线束、散热与打印公差待试配'


def cylinder(r, length, origin, axis=(0,0,1)):
    return Part.makeCylinder(r,length,V(*origin),V(*axis))


def hex_z(af,z0,z1,x,y):
    radius=af/math.sqrt(3)
    pts=[V(x+radius*math.cos(i*math.pi/3),y+radius*math.sin(i*math.pi/3),z0) for i in range(6)]
    return Part.Face(Part.makePolygon(pts+[pts[0]])).extrude(V(0,0,z1-z0))


def hex_y(af,y0,y1,x,z):
    s=hex_z(af,0,y1-y0,0,0)
    s.rotate(V(),V(1,0,0),-90);s.translate(V(x,y0,z));return s


def shapes(with_primitives=False):
    board=box((-14.25,-21.25,36,14.25,22.25,82.2))
    base=box((-13.75,-22.7,28.8,13.75,24.5,32)).cut(box((-7,-19.5,28,7,20.5,33)))
    parts=[base]; hardware={}; pads=[]
    for side,x in [('R',-10.5),('L',10.5)]:
        parts.append(box((x-3.75,-4,28.8,x+3.75,4,34.2)))
        hardware['L298NBaseNut'+side]=hex_z(5,31.8,33.8,x,0).cut(cylinder(1.25,2.2,(x,0,31.7)))
        hardware['L298NBaseScrew'+side]=cylinder(1.2,8,(x,0,26)).fuse(cylinder(2.3,1.8,(x,0,24.2)))
    for side,x in [('R',-11),('L',11)]:
        x0,x1=x-2.5,x+2.5
        parts += [box((x0,-22.7,32,x1,-21.5,62)),box((x0,22.5,32,x1,24.5,86.7)),
                  box((x-3.5,22.5,81.2,x+3.5,24.8,87.8)),
                  box((x0,-21.5,32,x1,-19.5,35.2)),box((x0,20.5,32,x1,22.5,35.2))]
        hardware['L298NCapNut'+side]=hex_y(4,23.5,24.7,x,84.5).cut(cylinder(1,1.4,(x,23.4,84.5),(0,1,0)))
        hardware['L298NCapScrew'+side]=cylinder(.95,4,(x,20.7,84.5),(0,1,0)).fuse(cylinder(1.8,1.6,(x,19.1,84.5),(0,1,0)))
        pads += [('L298NBottomPad'+side+'F',box((x0,-21.25,35.2,x1,-19.5,36))),
                 ('L298NBottomPad'+side+'B',box((x0,20.5,35.2,x1,22.25,36))),
                 ('L298NFrontPad'+side,box((x-1.5,-21.5,56.5,x+1.5,-21.25,59.5))),
                 ('L298NRearPad'+side,box((x-1.5,22.25,56.5,x+1.5,22.5,59.5))),
                 ('L298NTopPad'+side+'F',box((x0,-21.25,82.2,x1,-19.5,82.7))),
                 ('L298NTopPad'+side+'B',box((x0,20.4,82.2,x1,22.25,82.5)))]
    for sign in (-1,1):
        x0,x1=(14.75,16.75) if sign>0 else (-16.75,-14.75)
        px0,px1=(14.25,14.75) if sign>0 else (-14.75,-14.25)
        fx0,fx1=(8.5,16.75) if sign>0 else (-16.75,-8.5)
        for end,y0,y1 in [('F',-21.25,-19.5),('B',20.5,22.25)]:
            parts += [box((fx0,y0,32,fx1,y1,35.2)),box((x0,y0,35.2,x1,y1,48))]
            pads.append(('L298NSidePad'+str(sign).replace('-','R')+end,box((px0,y0,40,px1,y1,44))))
    carrier=union(parts)
    for x in (-10.5,10.5):
        carrier=carrier.cut(cylinder(1.45,6,(x,0,28.7))).cut(hex_z(5.3,31.8,34.3,x,0))
    for x in (-11,11):
        carrier=carrier.cut(cylinder(1.15,2.6,(x,22.4,84.5),(0,1,0))).cut(hex_y(4.2,23.5,24.9,x,84.5))
    cap_parts=[box((-14.5,-21.25,84.7,14.5,-19.5,88))]
    for x in (-11,11):
        cap_parts += [box((x-3.5,-21.25,84.7,x+3.5,22.5,88)),
                      box((x-2.5,-21.25,82.7,x+2.5,-19.5,84.7)),
                      box((x-2.5,20.7,82.5,x+2.5,22.5,84.7))]
    cap=union(cap_parts)
    for x in (-11,11):
        cap=cap.cut(cylinder(1.15,2.0,(x,20.6,84.5),(0,1,0))).cut(cylinder(2.1,43,(x,-22.3,84.5),(0,1,0)))
    spaces={
        'L298NLowerConnectorSpace':box((-6,-23.6,32.9,6,24.8,35.5)),
        'L298NFrontWireSpace':box((-6,-23.6,35.5,6,-21.4,61)),
        'L298NRearWireSpace':box((-7,22.4,35.5,7,24.8,85)),
        'L298NTrunkJoinSpace':box((-7,6,84,7,24.8,88)),
        'L298NMotorExitSpace':box((-23,15,82.5,23,17.4,84.7)),
        'L298NMotorLeadLSpace':box((21.8,16,70.5,24.2,22.5,84.7)),
        'L298NMotorLeadRSpace':box((-24.2,16,70.5,-21.8,22.5,84.7)),
        'L298NAirSpace':box((-6,-19,82.2,6,-17,94.5)),
    }
    result={'L298NEnvelope':board,'L298NCarrier':carrier.removeSplitter(),'L298NTopRetainer':cap.removeSplitter()}
    result.update(hardware);result.update(dict(pads));result.update(spaces)
    return (result,parts,cap_parts) if with_primitives else result


def apply(doc, add=None):
    """Upgrade an old saved model in memory; caller owns saving/exporting."""
    if doc.getObject('L298NTopRetainer'):
        raise ValueError('Compact mount already present; update from an explicit baseline')
    old_hangers=union([box((x0,-16,31.2,x1,-8,90.1)) for x0,x1 in [(-23,-17),(17,23)]]+
                       [box((x0,-16,79,x1,24.5,81.5)) for x0,x1 in [(-23,-17),(17,23)]])
    lid=doc.KeelLid
    lid.Shape=lid.Shape.cut(old_hangers).cut(box((-6,-19,82.2,6,-17,94.5))).removeSplitter()
    lid.EvidenceBasis=BASIS+'；取消旧驱动吊柱，中央前侧12×2排气开口候选'
    cover=doc.BottomServiceCover
    for x in (-10.5,10.5):cover.Shape=cover.Shape.cut(cylinder(1.45,3,(x,0,25.9)))
    cover.Shape=cover.Shape.removeSplitter();cover.EvidenceBasis=BASIS+'；底盖承载驱动托架，两M2.5级贯穿锁紧，整体下取'
    old=[o.Name for o in doc.Objects if o.Name.startswith('L298N')]
    parent=doc.L298NEnvelope.InList
    group=next((g for g in parent if g.isDerivedFrom('App::DocumentObjectGroup')),None)
    for n in old:doc.removeObject(n)
    for name,shape in shapes().items():
        category='clearance' if name.endswith('Space') else 'envelope' if name=='L298NEnvelope' else 'structure'
        if add:
            obj=add(name,name,shape,category,'power' if category=='clearance' else 'body',BASIS)
        else:
            obj=doc.addObject('Part::Feature',name);obj.Shape=shape
            obj.addProperty('App::PropertyString','Category');obj.Category=category
            obj.addProperty('App::PropertyString','EvidenceBasis');obj.EvidenceBasis=BASIS
            destination=doc.getObject({'structure':'Structure','envelope':'Envelope','clearance':'Clearance'}[category])
            if destination:destination.addObject(obj)
            elif group:group.addObject(obj)
        obj.Label={'L298NEnvelope':'L298N 90°转向／下沿抬高4 mm',
                   'L298NCarrier':'L298N 底盖承载托架／前后导向',
                   'L298NTopRetainer':'L298N 可拆上压框／机外两螺钉释放'}.get(name,name)
    doc.recompute()
    return dict(revision=REVISION,measured_motor_length_each_mm=57,reported_gap_mm=30,
                mounting='cassette carried by bottom service cover; 2 M2.5x8 base screws, 2 M2x4 cap screws with DIN439 M2 thin nuts (AF4, 1.2 thick); candidate envelopes',
                board_bbox_mm=bounds(doc.L298NEnvelope.Shape),physical_fit_verified=False)


def moving_names(doc):
    return [o.Name for o in doc.Objects if o.Name.startswith('L298N') and getattr(o,'Category','')!='clearance']


def physical(doc):
    consumed={p.Name for o in doc.Objects if hasattr(o,'PrintPartID') and hasattr(o,'Shapes') for p in o.Shapes}
    return {o.Name:o.Shape for o in doc.Objects if hasattr(o,'Shape') and not o.Shape.isNull()
            and not o.isDerivedFrom('App::DocumentObjectGroup') and o.Name not in consumed
            and (hasattr(o,'Category') or o.Name.startswith('Print')) and getattr(o,'Category','')!='clearance'}


def check(doc):
    all_shapes=physical(doc)
    tails=Part.makeCompound([box((15,-18.5,31.5,26.2,18.5,68.5)),box((-26.2,-18.5,31.5,-15,18.5,68.5))])
    all_shapes['MotorTailKeepout30mm']=tails
    moving=moving_names(doc)
    installed={n:s for n,s in all_shapes.items() if n not in moving}
    static={n:collisions(all_shapes[n],installed) for n in moving}
    internal=[]
    for i,n in enumerate(moving):
        for other in moving[i+1:]:
            hits=collisions(all_shapes[n],{other:all_shapes[other]})
            if hits:internal.append(dict(a=n,b=other,volume_mm3=hits[0]['volume_mm3']))
    spaces={}
    for obj in doc.Objects:
        if not obj.Name.startswith('L298N') or obj.Category!='clearance':continue
        obstacles={n:s for n,s in all_shapes.items() if n!='PowerCableRoute' or obj.Name!='L298NTrunkJoinSpace'}
        spaces[obj.Name]=collisions(obj.Shape,obstacles)
    return dict(revision=REVISION,static_overlaps=static,internal_overlaps=internal,wire_air_overlaps=spaces,
                valid={n:all_shapes[n].isValid() for n in moving},
                passed=not any(static.values()) and not internal and not any(spaces.values()),physical_fit_verified=False)


def drop_polyhedron(shape,distance=80):
    """Exact Z sweep for an orthogonal polyhedron (or vertical holes)."""
    pieces=[shape]
    end=shape.copy();end.translate(V(0,0,-distance));pieces.append(end)
    for face in shape.Faces:
        if abs(face.normalAt(0,0).z)>.99:pieces.append(face.extrude(V(0,0,-distance)))
    return union(pieces)


def bbox_drop(shape,distance=80):
    b=bounds(shape);return box((b[0],b[1],b[2]-distance,b[3],b[4],b[5]))


def check_service(doc):
    all_shapes=physical(doc)
    all_shapes['MotorTailKeepout30mm']=Part.makeCompound([box((15,-18.5,31.5,26.2,18.5,68.5)),box((-26.2,-18.5,31.5,-15,18.5,68.5))])
    moving=moving_names(doc)+['BottomServiceCover']
    cover_screws=[n for n in all_shapes if n.startswith('BottomCoverScrew')]
    fixed={n:s for n,s in all_shapes.items() if n not in moving+cover_screws}
    _,carrier_parts,cap_parts=shapes(True)
    sweeps={n:bbox_drop(all_shapes[n]) for n in moving if n not in ('L298NCarrier','L298NTopRetainer','BottomServiceCover')}
    sweeps['L298NCarrier']=union([drop_polyhedron(p) for p in carrier_parts])
    sweeps['L298NTopRetainer']=union([drop_polyhedron(p) for p in cap_parts])
    sweeps['BottomServiceCover']=drop_polyhedron(doc.BottomServiceCover.Shape)
    hits={n:collisions(s,fixed) for n,s in sweeps.items()}
    negative=collisions(sweeps['BottomServiceCover'],{n:all_shapes[n] for n in cover_screws})
    tools=[]
    # Base screws are removed only on the bench when separating the carrier
    # from its cover. The installed tool shafts also remain unobstructed.
    for side,x in [('R',-10.5),('L',10.5)]:
        target='L298NBaseScrew'+side
        tool=cylinder(1.6,44.2,(x,0,-20))
        tools.append(dict(name=target,diameter_mm=3.2,overlaps=collisions(tool,{n:s for n,s in all_shapes.items() if n!=target})))
    # On the bench, remove the two top-cap screws along -Y, then lift the cap.
    bench={n:all_shapes[n] for n in moving if n!='BottomServiceCover'}
    cap_screws=[n for n in moving if n.startswith('L298NCapScrew')]
    cap_screw_checks=[]
    for name in cap_screws:
        s=all_shapes[name]; b=bounds(s)
        sweep=box((b[0],b[1]-20,b[2],b[3],b[4],b[5]))
        # The accurate cylindrical shank, rather than its full head bbox,
        # must pass through the close-fitting cap hole.
        x=-11 if name.endswith('R') else 11
        sweep=union([cylinder(1.8,21.6,(x,-.9,84.5),(0,1,0)),
                     cylinder(.95,24,(x,.7,84.5),(0,1,0))])
        # Head travel ends at the original bearing plane Y20.7.
        tool=cylinder(1.5,25,(x,-5.9,84.5),(0,1,0))
        obstacles={n:q for n,q in bench.items() if n!=name}
        cap_screw_checks.append(dict(name=name,sweep_overlaps=collisions(sweep,obstacles),tool_overlaps=collisions(tool,obstacles)))
    cap_moving=['L298NTopRetainer']+[n for n in bench if n.startswith('L298NTopPad')]
    cap_up=[]
    for name in cap_moving:
        b=bounds(bench[name]); sweep=box((b[0],b[1],b[2],b[3],b[4],b[5]+80))
        # Use primitive pieces for the U cap, preserving the open rear.
        if name=='L298NTopRetainer':
            pieces=[]
            for p in cap_parts:
                b=bounds(p);pieces.append(box((b[0],b[1],b[2],b[3],b[4],b[5]+80)))
            sweep=union(pieces)
        cap_up += collisions(sweep,{n:s for n,s in bench.items() if n not in cap_moving+cap_screws})
    b=bounds(bench['L298NEnvelope']);board_up=box((b[0],b[1],b[2],b[3],b[4],b[5]+80))
    board_hits=collisions(board_up,{n:s for n,s in bench.items() if n not in cap_moving+cap_screws+['L298NEnvelope']})
    contacts={n:contact_area(doc.getObject(n).Shape,doc.L298NEnvelope.Shape) for n in bench if 'Pad' in n}
    carrier_contact=contact_area(doc.L298NCarrier.Shape,doc.BottomServiceCover.Shape)
    source_spaces=[o for o in doc.Objects if hasattr(o,'Category') and o.Category=='clearance' and not o.Name.startswith('L298N')]
    static_reserved={n:collisions(all_shapes[n],{o.Name:o.Shape for o in source_spaces}) for n in moving if n!='BottomServiceCover'}
    return dict(cassette_removal=dict(distance_mm=80,moving=moving,remove_first=cover_screws,
                method='continuous conservative carrier/cap blank sweeps plus accurate cover projection and fastener bounding sweeps',
                overlaps=hits,retained_cover_screw_negative_control=negative,
                disconnect_first='power/control and motor connections or provide measured service slack; flexible wire withdrawal not certified'),
                base_screw_tools=tools,bench_cap_screws=cap_screw_checks,bench_cap_lift_overlaps=cap_up,
                bench_board_lift_overlaps=board_hits,pad_envelope_contact_areas_mm2=contacts,
                carrier_cover_contact_area_mm2=carrier_contact,other_reserved_space_overlaps=static_reserved,
                passed=not any(hits.values()) and bool(negative) and not any(t['overlaps'] for t in tools)
                and not any(t['sweep_overlaps'] or t['tool_overlaps'] for t in cap_screw_checks)
                and not cap_up and not board_hits and carrier_contact>50 and all(a>0 for a in contacts.values()),
                pcb_contact_verified=False,flexible_service_verified=False)


def contact_area(a,b):
    total=0.0
    for f in a.Faces:
        for g in b.Faces:
            if f.BoundBox.intersect(g.BoundBox) and f.distToShape(g)[0]<1e-7:
                total+=f.common(g).Area
    return total
