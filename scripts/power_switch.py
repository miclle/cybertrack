"""Measured slide switch and guarded centre deck seat; electrical selection remains open."""
import json
from pathlib import Path
import FreeCAD as App
import Part

V = App.Vector
CENTER = (0.0, -64.0, 81.1)  # +X left, +Y rear; flange contact plane Z
NAMES = ['PowerSwitchBody', 'PowerSwitchLever', 'PowerSwitchScrew0', 'PowerSwitchScrew1']
BASIS = ('用户2026-10-26实测：含耳宽19.5、耳下宽10.6、厚5.8、含脚深8.3、'
         '孔距14.8、孔径2.6、拨柄2.9方形／行程6／突出4 mm；'
         '安装面为挂耳下表面；挂耳厚0.5和居中对称、连续含脚包络为建模假设，电气与实物适配未验')


def box(x0, y0, z0, x1, y1, z1):
    return Part.makeBox(x1-x0, y1-y0, z1-z0, V(x0,y0,z0))


def hole(radius, z0, z1, x, y):
    return Part.makeCylinder(radius,z1-z0,V(x,y,z0))


def component_shapes():
    # The complete terminal depth is conservatively solid; no inferred pin spacing.
    body=box(-2.9,-5.3,-8.3,2.9,5.3,0)
    flange=box(-2.9,-9.75,0,2.9,9.75,.5)
    for y in (-7.4,7.4): flange=flange.cut(hole(1.3,-1,1,0,y))
    body=body.fuse(flange).removeSplitter()
    lever=box(-1.45,-1.45,.5,1.45,1.45,4)
    return body,lever


def placed(shape):
    result=shape.copy();result.rotate(V(),V(0,0,1),-90);result.translate(V(*CENTER));return result


def apply(doc,add):
    x,y,z=CENTER
    # Central foredeck, between the front MOS carrier and rear effects tray.
    base=box(-14,-76,73,14,-52,81.1)
    rails=box(-14,-76,81.1,14,-74.5,86.1).fuse(box(-14,-53.5,81.1,14,-52,86.1))
    opening=box(-5.6,-67.2,68,5.6,-60.8,90)
    lid=doc.KeelLid
    original_solids=len(lid.Shape.Solids)
    lid.Shape=lid.Shape.fuse(base).fuse(rails).cut(opening).removeSplitter()
    for xx in (-7.4,7.4): lid.Shape=lid.Shape.cut(hole(.8,75.1,90,xx,y)).removeSplitter()
    assert lid.Shape.isValid() and len(lid.Shape.Solids)==original_solids
    body,lever=component_shapes()
    specs=[('PowerSwitchBody','电源开关／实测包络与挂耳',body,'component','metal'),
           ('PowerSwitchLever','电源开关／拨柄／中间行程展示',lever,'component','dark')]
    for i,yy in enumerate((-7.4,7.4)):
        # Show only the core inside the pilot hole. Thread crests/engagement are
        # deliberately not represented as accepted interference geometry.
        screw=hole(.8,-5.5,.5,0,yy).fuse(hole(1.8,.5,2.1,0,yy))
        specs.append(('PowerSwitchScrew'+str(i),'电源开关／Ø2×6塑料用自攻螺钉候选 '+str(i+1),screw,'structure','metal'))
    for name,label,shape,category,color in specs:
        basis=BASIS if name in NAMES[:2] else 'Ø2×6塑料用自攻螺钉候选；仅画Ø1.6孔内芯径及头部，螺纹未建模；导孔与材料、夹紧和重复拆装待验'
        obj=add(name,label,placed(shape),category,color,basis)
        obj.addProperty('App::PropertyString','ServiceGroup','Assembly');obj.ServiceGroup='power_switch'
    doc.recompute()
    return dict(centre_xyz_mm=CENTER,flange_contact_plane_z_mm=81.1,lever_tip_z_mm=85.1,
                guard_top_z_mm=86.1,body_opening_xy_mm=[11.2,6.4],
                pilot_holes_diameter_mm=1.6,pilot_depth_mm=6,screw_hole_pitch_mm=14.8,
                nominal_engagement_depth_mm=5.5,pilot_to_body_opening_wall_mm=1.0,
                fasteners='2 candidate diameter-2 x 6 plastic self-tapping screws; core only, no threads modeled',
                flange_thickness_assumed_mm=.5,service='disconnect leads; unscrew from above; extract switch upwards without removing battery or bottom cover',
                physical_fit_verified=False,electrical_verified=False)


def check(doc):
    objects=[o for o in doc.Objects if hasattr(o,'Category')]
    def overlaps(shape,exclude=()):
        hits=[];count=0
        for o in objects:
            if o.Name in exclude or not shape.BoundBox.intersect(o.Shape.BoundBox):continue
            count+=1;v=shape.common(o.Shape).Volume
            if v>.01:hits.append(dict(object=o.Name,volume_mm3=v))
        return dict(passed=not hits,overlaps=hits,boolean_pairs=count)
    static={n:overlaps(doc.getObject(n).Shape,[n]) for n in NAMES}
    # Full continuous 6 mm travel, not merely the midpoint shown in the assembly.
    travel=box(-4.45,-65.45,81.6,4.45,-62.55,85.1)
    slider=overlaps(travel,['PowerSwitchLever'])
    # Flat-ended 20 mm finger envelope swept 6 mm along X, approaching from above.
    finger=box(-13,-74,85.1,13,-54,115.1)
    # Tool reservations describe maintenance operations, not physical obstacles during use.
    reservations=[o.Name for o in objects if o.Category=='clearance']
    operation=overlaps(finger,NAMES+reservations)
    # Unspecified terminal/pin geometry is not inferred; reserve an adjacent wire exit.
    wire=box(-6,-67.5,66.8,6,-60.5,72.8)
    wiring=overlaps(wire,NAMES)
    # Complete continuous extraction through the top opening, with battery retained.
    removal=box(-5.3,-66.9,72.8,5.3,-61.1,125).fuse(box(-9.75,-66.9,81.1,9.75,-61.1,125.5)).fuse(box(-1.45,-65.45,81.6,1.45,-62.55,129))
    extraction=overlaps(removal,NAMES+reservations)
    tools=[overlaps(hole(2,83.2,120,xx,-64),NAMES+reservations) for xx in (-7.4,7.4)]
    screws=[]
    for xx in (-7.4,7.4):
        swept=hole(.8,75.6,112,xx,-64).fuse(hole(1.8,81.6,113.2,xx,-64))
        screws.append(overlaps(swept,NAMES[2:]+reservations))
    blocked=slider['passed'] and travel.common(box(-1,-66,82,1,-62,84)).Volume>.01
    oversized=box(-13,-75,85.1,13,-53,115.1)
    negative_finger=not overlaps(oversized,NAMES+reservations)['passed']
    retained_screws=not overlaps(removal,NAMES[:2]+reservations)['passed']
    report=dict(static=static,continuous_slider_travel=slider,finger_approach=operation,
                local_wire_budget=wiring,tools=tools,
                upward_switch_removal={**extraction,'removed_first':NAMES[2:],'battery_retained':True,'method':'continuous conservative envelope'},
                upward_screw_removal=screws,
                negative_controls=dict(slider_obstruction_detected=blocked,oversized_finger_hits_guards=negative_finger,retained_screws_block_extraction=retained_screws),
                finger_envelope_xyz_mm=[26,20,30],wire_budget_xyz_mm=[12,7,6],
                physical_fit_verified=False,electrical_verified=False,
                limits='Nominal solid geometry only; finger envelope is an assumption, not ergonomic acceptance. Harness route/connectors and actual terminals are unverified.')
    report['passed']=all(r['passed'] for r in list(static.values())+[slider,operation,wiring]+tools+screws) and extraction['passed'] and blocked and negative_finger and retained_screws
    return report


def export_component(root):
    directory=Path(root)/'hardware/components/power-switch'
    path=directory/'PowerSwitch-envelope.FCStd'
    doc=App.newDocument('PowerSwitchMeasured')
    for name,shape in zip(('Body','Lever'),component_shapes()):
        o=doc.addObject('Part::Feature',name);o.Shape=shape
        o.addProperty('App::PropertyString','EvidenceBasis');o.EvidenceBasis=BASIS
    doc.recompute();doc.saveAs(str(path))
    expected=Part.makeCompound([o.Shape for o in doc.Objects])
    Part.export(doc.Objects,str(directory/'PowerSwitch-envelope.step'))
    App.closeDocument(doc.Name)
    doc=App.openDocument(str(path));native=Part.makeCompound([o.Shape for o in doc.Objects])
    step=Part.Shape();step.read(str(directory/'PowerSwitch-envelope.step'))
    checks=[]
    for kind,s in [('FCStd',native),('STEP',step)]:
        delta=expected.cut(s).Volume+s.cut(expected).Volume
        checks.append(dict(format=kind,valid=s.isValid(),difference_mm3=delta,passed=s.isValid() and delta<1e-5))
    App.closeDocument(doc.Name)
    result=dict(checks=checks,saved_and_reopened=True,passed=all(c['passed'] for c in checks),
                local_axes='X thickness; Y overall width and travel; Z outward from flange plane',
                flange_plane_z_mm=0,physical_fit_verified=False)
    (directory/'readback.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    assert result['passed']


def render(doc,out):
    import FreeCADGui as Gui
    from PySide import QtGui
    old={o.Name:o.ViewObject.Visibility for o in doc.Objects}
    try:
        for o in doc.Objects:
            if hasattr(o,'Shape'):
                o.ViewObject.Visibility=o.Name in ('KeelLid','ChestAudioPanel','ChestGuardL','ChestGuardR') or o.Name in NAMES
        doc.PowerSwitchBody.ViewObject.Visibility=True
        view=Gui.activeDocument().activeView()
        for name,orientation in [('power-switch-top.png','viewTop'),('power-switch-layout.png','viewAxonometric')]:
            getattr(view,orientation)();view.fitAll()
            for _ in range(5):QtGui.QApplication.processEvents()
            view.saveImage(str(Path(out)/name),1600,1100,'White')
    finally:
        for o in doc.Objects:o.ViewObject.Visibility=old[o.Name]
