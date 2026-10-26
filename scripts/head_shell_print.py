"""PP07 head shell union and measured Ø2.5 / 8.6 total / Ø3.9 / 1 head screw.

Applied locally after the existing six-part consolidation. All coordinates are
assembly millimetres. Pilot diameter is a print-fit candidate, not thread data.
"""
import FreeCAD as App
import Part

V = App.Vector
MEMBERS = ['HeadShell', 'VisorRim', 'JawArmor', 'JawAccent', 'OccipitalFrame',
           'OccipitalInset', 'OccipitalSpine', 'OccipitalMark', 'SensorMask', 'SensorStatusStrip']
for prefix in ('CheekArmor', 'AudioSideGuard', 'AudioEarRing', 'AudioEarGrille',
               'EarHub', 'TempleGuard', 'TempleCrest', 'TempleLowerBlade', 'EarOuterArc'):
    MEMBERS.extend(prefix + side for side in ('L', 'R'))
MEMBERS.extend('OccipitalLouver' + side + str(i) for side in ('L', 'R') for i in range(3))
CROWN_MOUNTS = [(side + end, sign * 64, y) for side, sign in (('L', 1), ('R', -1))
                for end, y in (('Front', -52), ('Rear', 7))]
TRAY_MOUNTS = [(-57, -40), (-57, -5), (57, -40), (57, -5)]
PILOT_DIAMETER = 2.1
SCREW = dict(outer_diameter_mm=2.5, total_length_mm=8.6, head_diameter_mm=3.9,
             head_height_mm=1.0, under_head_length_mm=7.6,
             thread_type='coarse/self-tapping appearance; pitch and root diameter unmeasured')


def box(a, b):
    return Part.makeBox(b[0]-a[0], b[1]-a[1], b[2]-a[2], V(*a))


def cylinder(radius, bottom, top, x, y):
    return Part.makeCylinder(radius, top-bottom, V(x, y, bottom))


def screw(x, y, seat):
    # Smooth envelope, not a modeled/verified thread or driver recess.
    return cylinder(1.25, seat-7.6, seat, x, y).fuse(cylinder(1.95, seat, seat+1, x, y))


def connectors(doc):
    rows = []
    for x in (-22, 14):
        rows.append(('JawTie' + ('R' if x < 0 else 'L'), box((x, -84.5, 169), (x+6, -76, 172))))
    for side, sign in (('L', 1), ('R', -1)):
        x = sign*62
        rows.append(('SensorTie'+side, box((x-3,-82,185),(x+3,-79,189))))
        x = sign*72
        rows.append(('CheekTie'+side, box((x-3, -85, 173), (x+3, -82, 177))))
        x0, x1 = (84.5, 87) if sign > 0 else (-87, -84.5)
        for z in (172, 200):
            rows.append(('EarTie'+side+str(z), box((x0, -11, z), (x1, -7, z+4))))
        rows.append(('EarHubTie'+side, Part.makeCylinder(3.5, 3.5, V(sign*85.5, -9, 188), V(sign, 0, 0))))
    # These original panels touched their frames only along an edge. Bridge each
    # full seam with a 1.2 mm wide/deep band, rather than relying on mesh repair.
    for name, y in [('SensorMask', -81), ('OccipitalInset', 27)]:
        faces=[f for f in doc.getObject(name).Shape.Faces
               if isinstance(f.Surface, Part.Plane) and abs(f.normalAt(0,0).y)>.99]
        face=max(faces,key=lambda f:f.Area)
        outer=face.OuterWire.makeOffset2D(.6)
        inner=face.OuterWire.makeOffset2D(-.6)
        band=Part.Face(outer).cut(Part.Face(inner))
        band.translate(V(0,y-.6-face.CenterOfMass.y,0))
        rows.append((name+'Seam',band.extrude(V(0,1.2,0))))
    return rows


def geometry(doc):
    shell = doc.HeadShell.Shape.copy()
    for _, x, y in CROWN_MOUNTS:
        shell = shell.fuse(cylinder(2.1, 201, 206, x, y))
        shell = shell.fuse(cylinder(3.5, 205, 216.1, x, y))
        shell = shell.cut(cylinder(PILOT_DIAMETER/2, 210, 216.2, x, y))
    for x, y in TRAY_MOUNTS:
        shell = shell.fuse(cylinder(2.1, 165, 171.5, x, y))
        shell = shell.cut(cylinder(PILOT_DIAMETER/2, 164.5, 171.6, x, y))
    shell = shell.removeSplitter()
    pockets = Part.makeCompound([cylinder(3.75, 205.9, 216.35, x, y) for _, x, y in CROWN_MOUNTS])
    crown = doc.PrintCrown.Shape.cut(pockets).removeSplitter()
    parts = [shell if n == 'HeadShell' else doc.getObject(n).Shape for n in MEMBERS]
    ties = connectors(doc)
    merged = parts[0].multiFuse(parts[1:]+[s for _, s in ties]).removeSplitter()
    assert merged.isValid() and len(merged.Solids) == 1
    assert crown.isValid() and len(crown.Solids) == 1
    return dict(head=shell, merged=merged, crown=crown, pockets=pockets, connectors=ties)


def print_shape(shape):
    """Upright/open top up: no rotation, X/Y centred, native lowest plane on bed."""
    result = shape.copy()
    b = result.optimalBoundingBox(False)
    translation = V(-(b.XMin+b.XMax)/2, -(b.YMin+b.YMax)/2, -b.ZMin)
    result.translate(translation)
    return result, list(translation)


def coupon():
    """Three separated Ø2.0/2.1/2.2 pilot bosses on a common labelled strip.

One, two, three edge notches identify increasing diameters from left to right.
Matching removable 2.5 mm cover plates reproduce the axial screw stack.
"""
    base = box((0, 0, 0), (42, 12, 2))
    covers = []
    for i, diameter in enumerate((2.0, 2.1, 2.2)):
        x = 7+14*i
        boss = cylinder(3.5, 2, 9, x, 6).cut(cylinder(diameter/2, 2.9, 9.1, x, 6))
        base = base.fuse(boss)
        cover = box((x-5, 17, 0), (x+5, 27, 2.5)).cut(cylinder(1.5, -1, 4, x, 22))
        for j in range(i+1):
            base = base.cut(box((x-3+j*2, -1, -1), (x-2+j*2, 1, 3)))
            cover = cover.cut(box((x-3+j*2, 16, -1), (x-2+j*2, 18, 4)))
        covers.append(cover)
    return Part.makeCompound([base.removeSplitter()]+covers)
