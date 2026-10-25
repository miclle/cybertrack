"""0.43 candidate PCB edge carriers and low-voltage wiring allocations.

PCB thickness and component-free edges are assumptions to measure before use.
No real board holes, pin assignments, cable ratings or production fit are inferred.
"""
import FreeCAD as A
import Part
from breadboard_layout import box
from ultrasonic_integration import bounds
from refine_assembly import route
V=A.Vector
MOUNTS=[(x,y) for x in (-47,47) for y in (-49,-26.5)]
BOARDS={side+kind:(sign*x,y,w,d,h) for side,sign in [('L',1),('R',-1)]
        for kind,x,y,w,d,h in [('MOS',23,-40.75,33,17,12),('Buck',18.5,-55.25,20,11,5)]}


SIDE_WIRE_POINTS=[(43.5,-32.25,75),(40,-32.25,75),(40,-49.75,74.5),(32.5,-49.75,74.5)]


def zc(r,z0,z1,x,y):return Part.makeCylinder(r,z1-z0,V(x,y,z0))
def mirror(s,sign):
    if sign>0:return s
    m=A.Matrix();m.A11=-1
    return s.transformGeometry(m)


def vertical_sweep(shape,dz):
    """Cover vertical translation with the starting solid and face prisms.

    Preserve the fixture's holes and open pockets. Reject inclined geometry;
    the carrier consists only of horizontal planes and vertical side faces.
    """
    pieces=[shape]
    for face in shape.Faces:
        if face.BoundBox.ZLength<1e-6:
            pieces.append(face.extrude(V(0,0,dz)))
        else:
            u0,u1,v0,v1=face.ParameterRange
            for f in (.2,.5,.8):
                normal=face.normalAt(u0+f*(u1-u0),v0+f*(v1-v0))
                if abs(normal.z)>1e-6:
                    raise ValueError('Unsupported sloping face in fixture sweep')
    swept=pieces[0].multiFuse(pieces[1:]).removeSplitter()
    if not swept.isValid():raise ValueError("Invalid vertical sweep")
    return swept


def apply(doc,put):
    lid=doc.getObject('KeelLid').Shape.copy()
    tray=box(-43,-56,66.5,43,-22,68.5)
    for i,(x,y) in enumerate(MOUNTS):
        tray=tray.fuse(zc(3.7,66.5,70.5,x,y)).fuse(box(min(x,41 if x>0 else -41),y-2,66.5,max(x,41 if x>0 else -41),y+2,68.5))
        tray=tray.cut(zc(1.4,66.4,70.6,x,y)).cut(zc(2.6,66.4,68.1,x,y))
        # Stop inside the first original roof material; keep its outer skin.
        roof=zc(3.5,70.5,110,x,y).common(lid)
        top=bounds(roof)[2]+.4
        post=zc(3.5,70.5,top,x,y)
        for obstacle in ('LowerTub','ShoulderRailL','ShoulderRailR'):
            post=post.cut(doc.getObject(obstacle).Shape)
        lid=lid.fuse(post).cut(zc(2.1,70.4,75.6,x,y))
        put('EffectInsert'+str(i),'承板内柱M2.5级嵌件候选 '+str(i),zc(2,71,75.5,x,y).cut(zc(1.25,70.9,75.6,x,y)))
        screw=zc(1.2,68.1,75.1,x,y).fuse(zc(2.4,66.6,68.1,x,y))
        screw=screw.cut(box(x-1.4,y-.5,66.5,x+1.4,y+.5,67.4))
        put('EffectScrew'+str(i),'承板凹入式M2.5级螺钉候选 '+str(i),screw)
        put('EffectTool'+str(i),'取电源后承板底部Ø3工具杆 '+str(i),zc(1.5,-12,66.6,x,y),'clearance','accent')
    for suffix,(x,y,w,d,h) in BOARDS.items():
        kind='MOS' if suffix.endswith('MOS') else 'Buck';side=suffix[0];sign=1 if side=='L' else -1
        x0,x1=x-w/2,x+w/2
        pcb=box(x0,y,68,x1,y+d,69.6)
        components=box(x0+2.5,y+2.5,69.6,x1-2.5,y+d-2.5,68+h)
        put('Effect'+kind+side,kind+'板／PCB与元件区候选 '+side,pcb.fuse(components),'envelope','electronics' if kind=='MOS' else 'bubble',
            '外包络MOS33×17×12（高假设）／降压20×11×5（用户）；PCB厚1.6、四边2.5无元件区均为新增假设，必须实测。')
        # A 1 mm deep seat keeps the board low; remaining floor is 1 mm.
        tray=tray.cut(box(x0-.5,y-.5,67.5,x1+.5,y+d+.5,68.6))
        pads=box(x0+1,y+.2,67.5,x1-1,y+1.8,68).fuse(box(x0+1,y+d-1.8,67.5,x1-1,y+d-.2,68))
        put('EffectSupport'+suffix,'两条0.5 mm板边垫候选 '+suffix,pads,'structure','dark',
            '只在假设无焊脚的板边承托；板底中央留0.5，焊脚／材料／散热／压缩未验，不是绝缘等级。')
        # Low fixed walls locate the PCB; the open-centre retaining frame is
        # removable, so boards lift rather than sliding past adjacent fixtures.
        walls=box(x0-1.5,y-1.5,68.5,x1+1.5,y+d+1.5,69.5).cut(box(x0-.5,y-.5,68.4,x1+.5,y+d+.5,69.6))
        tray=tray.fuse(walls)
        frame=box(x0-1.5,y-1.5,70,x1+1.5,y+d+1.5,71.2).cut(box(x0+2,y+2,69.9,x1-2,y+d-2,71.3))
        yy=y+d/2
        for end,xx in [('Inner',x-sign*(w/2+4)),('Outer',x+sign*(w/2+4))]:
            tag=suffix+end
            tab=box(xx-3,yy-3,66.5,xx+3,yy+3,68.5).fuse(zc(2.5,68.5,70,xx,yy))
            tab=tab.cut(zc(1.5,66.9,70.1,xx,yy));tray=tray.fuse(tab)
            # Tab meets the frame's edge; no clamp loads are asserted.
            edge=x0 if xx<x else x1
            frame=frame.fuse(box(min(xx-2.3,edge-1.5),yy-3,70,max(xx+2.3,edge+1.5),yy+3,71.2))
            frame=frame.cut(zc(1.1,69.9,71.3,xx,yy))
            put('EffectRetainerInsert'+tag,'压框M2级短嵌件候选 '+tag,zc(1.4,67,69.9,xx,yy).cut(zc(1,66.9,70,xx,yy)))
            screw=zc(.95,67.1,71.2,xx,yy).fuse(zc(1.8,71.2,72.5,xx,yy))
            screw=screw.cut(box(xx-1.1,yy-.4,71.9,xx+1.1,yy+.4,72.6))
            put('EffectRetainerScrew'+tag,'压框M2级螺钉候选 '+tag,screw)
            put('EffectRetainerTool'+tag,'机外压框Ø3工具杆 '+tag,zc(1.5,72.5,112.5,xx,yy),'clearance','accent','仅整盘取出后的直工具杆预算，不表示底盘内可拆压框。')
        # Clear the adjacent fixed ear/post with a 0.5 mm radial budget.
        for mx,my in MOUNTS:
            frame=frame.cut(zc(4.2,69.9,71.3,mx,my))
        put('EffectRetainer'+suffix,'单板开窗防脱压框候选 '+suffix,frame,'structure','metal',
            '机外拆两颗M2级螺钉后上取压框，再提板；框只覆盖假设无元件的板边，PCB上方留0.4，不压紧元件。')
        inner=abs(x)-w/2;outer=abs(x)+w/2
        span=4 if kind=='MOS' else 2
        innerport=box(inner-4,yy-span,73,inner,yy+span,77.5 if kind=='MOS' else 75.5)
        outerport=box(outer,yy-2,73,outer+4,yy+2,77.5 if kind=='MOS' else 75.5)
        for end,shape in [('Inner',innerport),('Outer',outerport)]:
            put('EffectPort'+suffix+end,'板端接线空间候选 '+suffix+end,mirror(shape,sign),'clearance','signal',
                '接线空间位置、方向和4 mm外伸均假设；不是选定连接器，不替代真实端子、针序及工具核对。')
    put('EffectWireCentre','中央低压线束交接通道候选',box(-2.5,-51,72,2.5,-36,76),'clearance','power',
        '5×4共享通道，板端另留接线预算；实际供电／控制分配、线数、针序及设备端接待定。')
    for side,sign in [('L',1),('R',-1)]:
        wire=route([(sign*x,y,z) for x,y,z in SIDE_WIRE_POINTS],1.5)
        put('EffectWireSide'+side,'板间侧向Ø3线束预算 '+side,wire,'clearance','power',
            '仅侧廊连接预算；不是真实弯曲半径、线径、接头针序或完整外部线束。')
    for suffix,(x,y,w,d,h) in BOARDS.items():
        sign=1 if x>0 else -1
        for xx in (x-sign*(w/2+4),x+sign*(w/2+4)):
            tray=tray.cut(zc(1.5,66.9,70.1,xx,y+d/2))
    for x,y in MOUNTS:
        tray=tray.cut(zc(1.4,66.4,70.6,x,y)).cut(zc(2.6,66.4,68.1,x,y))
    tray=tray.cut(doc.getObject('LowerTub').Shape)
    doc.getObject('KeelLid').Shape=lid.removeSplitter()
    put('EffectTray','效果板低位承板／凹座、防脱压框与四点沉台',tray,'structure','metal',
        '底Z66.5，上Z68.5；板座下凹1、四耳厚4、螺钉头底66.6；下方至少2 mm候选，公差与强度待验。')
    return {'revision':'0.43','tray_floor_z_mm':[66.5,68.5],'tray_mount_xy_mm':MOUNTS,
            'power_top_z_mm':64.5,'minimum_undertray_gap_target_mm':2,'screw_head_bottom_z_mm':66.6,
            'screw_head_gap_mm':2.1,'board_bottom_z_mm':68,'pcb_thickness_assumed_mm':1.6,
            'component_free_edge_assumed_mm':2.5,'seat_depth_mm':1,'remaining_seat_floor_mm':1,
            'board_edge_pad_mm':.5,'board_side_allowance_mm':.5,'board_lip_vertical_allowance_mm':.4,
            'retainer_screws':8,'tray_ear_thickness_mm':4,'port_and_wire_positions_measured':False,
            'board_mounting_candidate_modeled':True,'board_contact_and_retention_verified':False,'physical_fit_verified':False}


def check(doc,inspect):
    physical={o.Name:o.Shape for o in doc.Objects if hasattr(o,'Category') and o.Category!='clearance'}
    moving={n:s for n,s in physical.items() if n.startswith('Effect') and not n.startswith(('EffectInsert','EffectScrew'))}
    wires={o.Name:o.Shape for o in doc.Objects if o.Name.startswith(('EffectPort','EffectWire'))}
    wire_checks={n:inspect(s,physical) for n,s in wires.items()}
    paths={};negative={};tools={};screws={}
    for suffix,(x,y,w,d,h) in BOARDS.items():
        sign=1 if x>0 else -1;yy=y+d/2
        bolts=['EffectRetainerScrew'+suffix+e for e in ('Inner','Outer')]
        frame='EffectRetainer'+suffix
        for end,xx in [('Inner',x-sign*(w/2+4)),('Outer',x+sign*(w/2+4))]:
            bolt='EffectRetainerScrew'+suffix+end
            swept=zc(.95,67.1,91.2,xx,yy).fuse(zc(1.8,71.2,92.5,xx,yy))
            screws[bolt]=inspect(swept,{n:s for n,s in moving.items() if n!=bolt})
            tools[bolt]=inspect(doc.getObject('EffectRetainerTool'+suffix+end).Shape,{n:s for n,s in moving.items() if n!=bolt})
        frame_sweep=vertical_sweep(physical[frame],20)
        paths['frame_'+suffix]=inspect(frame_sweep,{n:s for n,s in moving.items() if n not in bolts+[frame]})
        negative['frame_screws_'+suffix]=inspect(frame_sweep,{n:physical[n] for n in bolts})
        board='Effect'+('MOS' if suffix.endswith('MOS') else 'Buck')+suffix[0]
        swept=vertical_sweep(physical[board],20)
        paths['board_'+suffix]=inspect(swept,{n:s for n,s in moving.items() if n not in bolts+[frame,board]})
        negative['frame_retained_'+suffix]=inspect(swept,{frame:physical[frame]})
        negative['no_free_component_edge_'+suffix]=inspect(box(x-w/2,y,68,x+w/2,y+d,68+h),{frame:physical[frame]})
    gap=physical['EffectTray'].distToShape(physical['PowerBank'])[0]
    head_gap=min(physical['EffectScrew'+str(i)].distToShape(physical['PowerBank'])[0] for i in range(4))
    roof={n:s.distToShape(physical['KeelLid'])[0] for n,s in moving.items() if n!='EffectTray'}
    return {'revision':'0.43','wire_spaces':wire_checks,'bench_removal':paths,'bench_screw_sweeps':screws,'bench_tools':tools,
            'negative_controls':negative,'tray_to_power_mm':gap,'screw_head_to_power_mm':head_gap,'roof_distances_mm':roof,
            'passed':all(r['passed'] for section in (wire_checks,paths,screws,tools) for r in section.values()) and
                all(not r['passed'] for r in negative.values()) and gap>=2-1e-6 and head_gap>=2-1e-6,
            'limits':'Local candidate wiring only; PCB edges, components, compression, tolerance stack, complete harness and hand access unverified. Frame/board removal is off-machine after tray extraction.'}
