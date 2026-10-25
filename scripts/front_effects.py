"""Four passive front effect lead mockups; no electrical route or electrode design."""
import FreeCAD as App
import Part

V = App.Vector
PREFIX = 'FrontEffect'
ROOTS_XZ = ((44, 62), (54, 53))
WIRE_DIAMETER = 1.5
FORWARD_LENGTH = 28
RISE = FORWARD_LENGTH * 4 / 18  # Retain the 0.45 visual slope.
BASIS = ('用户2026-10-25指定底盘前方左右各两根线，并补充单线外径1.5 mm；位置、长度及护套仍为外观假设，'
         '不是高压线材、电极、放电间距、绝缘或安装规格；不含内部接线')


def bounds(shape):
    b = shape.optimalBoundingBox(False)
    return [b.XMin, b.YMin, b.ZMin, b.XMax, b.YMax, b.ZMax]


def apply(doc, add):
    for side, sign, label in [('L', 1, '左'), ('R', -1, '右')]:
        for index, (x, z) in enumerate(ROOTS_XZ, 1):
            root = V(sign*x, -109, z)
            tip = V(sign*x, -109-FORWARD_LENGTH, z+RISE)
            direction = tip-root
            add(f'{PREFIX}Sleeve{side}{index}', f'{label}前方效果线{index}／根部护套外观',
                Part.makeCylinder(3, 3, root, V(0, 1, 0)), 'exterior', 'dark', BASIS)
            # Trim the oblique cylinder against the sleeve's front plane so it
            # meets the sleeve without a modeled solid overlap or cutting the shell.
            rod = Part.makeCylinder(WIRE_DIAMETER/2, direction.Length+1, root-direction*(1/direction.Length), direction)
            rod = rod.common(Part.makeBox(140, FORWARD_LENGTH+4, 40, V(-70, -113-FORWARD_LENGTH, 45)))
            # Rounded closed tip is a visual wire end, not a stripped conductor.
            rod = rod.fuse(Part.makeSphere(WIRE_DIAMETER/2, tip)).removeSplitter()
            obj = add(f'{PREFIX}Lead{side}{index}', f'{label}前方效果线{index}／封闭端外观占位',
                      rod, 'exterior', 'accent', BASIS)
            obj.addProperty('App::PropertyBool', 'ElectricalDesign', 'Evidence')
            obj.ElectricalDesign = False
    return dict(quantity=4, groups=2, leads_per_group=2,
                basis=BASIS, appearance_only=True,
                root_centres_mm=[[s*x, -109, z] for s in (1, -1) for x, z in ROOTS_XZ],
                tip_centres_mm=[[s*x, -109-FORWARD_LENGTH, z+RISE] for s in (1, -1) for x, z in ROOTS_XZ],
                forward_projection_mm=FORWARD_LENGTH, rise_mm=RISE,
                visual_diameter_mm=WIRE_DIAMETER, sleeve_visual_diameter_mm=6,
                internal_wiring_designed=False, electrodes_designed=False,
                physical_fit_verified=False, electrical_verified=False)


def check(doc):
    selected = [o for o in doc.Objects if o.Name.startswith(PREFIX)]
    # Proposed route/lead interfaces are checked explicitly by ignition_routing.
    others = [o for o in doc.Objects if hasattr(o, 'Category') and not o.Name.startswith((PREFIX, 'IgnitionRoute'))]
    overlaps = []
    pairs = [(a, b) for a in selected for b in others]
    pairs += [(a, b) for i, a in enumerate(selected) for b in selected[i+1:]]
    tested = 0
    for a, b in pairs:
        if not a.Shape.BoundBox.intersect(b.Shape.BoundBox):
            continue
        tested += 1
        volume = a.Shape.common(b.Shape).Volume
        if volume > .01:
            overlaps.append(dict(a=a.Name, b=b.Name, volume_mm3=volume))
    rows = [dict(name=o.Name, valid=o.Shape.isValid(), solids=len(o.Shape.Solids),
                 bbox_mm=bounds(o.Shape)) for o in selected]
    contact = []
    for side in ('L', 'R'):
        for i in (1, 2):
            sleeve = doc.getObject(f'{PREFIX}Sleeve{side}{i}').Shape
            contact.append(dict(side=side, index=i,
                guard_distance_mm=sleeve.distToShape(doc.getObject('ChestGuard'+side).Shape)[0],
                lead_distance_mm=sleeve.distToShape(doc.getObject(f'{PREFIX}Lead{side}{i}').Shape)[0]))
    return dict(objects=rows, boolean_pairs_tested=tested, overlaps=overlaps,
                visual_root_contacts=contact,
                passed=len(rows)==8 and all(r['valid'] and r['solids']==1 for r in rows)
                    and not overlaps and all(r['guard_distance_mm']<1e-5 and r['lead_distance_mm']<.7 for r in contact),
                scope='Static visual solids; guard contact and lead within 2.6 mm exit bore budget; not electrical spacing or fixture validation',
                physical_fit_verified=False, electrical_verified=False)


def render(doc, output):
    import FreeCADGui as Gui
    from PySide import QtGui
    objects = [o for o in doc.Objects if hasattr(o, 'Category')]
    original = {o.Name:(o.ViewObject.Visibility, o.ViewObject.Transparency) for o in objects}
    view = Gui.activeDocument().activeView()
    orientation = view.getCameraOrientation()
    try:
        for o in objects:
            o.ViewObject.Visibility = o.Category not in ('envelope', 'clearance') or o.Name in ('WaterModule', 'BubbleModule', 'BackpackArcL', 'BackpackArcR')
            o.ViewObject.Transparency = 40 if o.Name in ('WaterModule', 'BubbleModule') else 0
        for filename, rotation in [
            ('front-effects.png', App.Rotation(V(1,1,0), V(-1,1,3), V(1,-1,.75), 'ZXY')),
            ('front-effects-front.png', App.Rotation(V(1,0,0),90)),
        ]:
            view.setCameraOrientation(rotation.Q)
            view.fitAll()
            for _ in range(10):
                QtGui.QApplication.processEvents()
            view.saveImage(str(output/filename),1600,1200,'White')
    finally:
        for o in objects:
            o.ViewObject.Visibility, o.ViewObject.Transparency = original[o.Name]
        view.setCameraOrientation(orientation.Q)
        view.fitAll()
