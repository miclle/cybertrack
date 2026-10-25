"""User-supplied speaker envelope and scoped head-compartment geometry checks."""
import FreeCAD as App
import Part

SIZE = (69.5, 31.5, 16.5)
ORIGIN = (-34.75, -72.75, 146.0)
LABEL = '扬声器占位 69.5×31.5×16.5／用户提供尺寸'
BASIS = ('用户于 2026-10-24 提供长69.5×宽31.5×高16.5 mm；'
         '长沿X、宽沿Y、高沿Z为布局选择；安装孔、接口、线缆及声学空间未验证')


def speaker_shape():
    return Part.makeBox(*SIZE, App.Vector(*ORIGIN))


def render_speaker(doc, output):
    import FreeCADGui as Gui
    from PySide import QtGui
    objects = [o for o in doc.Objects if hasattr(o, 'Category')]
    saved = {o.Name:(o.ViewObject.Visibility, o.ViewObject.Transparency,
                     o.ViewObject.ShapeColor) for o in objects}
    view = Gui.activeDocument().activeView()
    camera = view.getCameraOrientation()
    try:
        for obj in objects:
            obj.ViewObject.Visibility = (obj.Name in ('HeadShell','ElectronicsTray','AudioModule',
                'Electronics','ESP32Board','ArcModuleL','ArcModuleR') or
                obj.Name.startswith('Controller') and obj.Category != 'clearance')
            obj.ViewObject.Transparency = 85 if obj.Name=='HeadShell' else 0
        doc.getObject('AudioModule').ViewObject.ShapeColor = (0.1,0.8,0.9)
        for name,rotation in [('speaker-layout',App.Rotation(App.Vector(1,1,0),
                              App.Vector(-1,1,3),App.Vector(1,-1,0.75),'ZXY')),
                              ('speaker-top',App.Rotation())]:
            view.setCameraOrientation(rotation.Q)
            view.fitAll()
            for _ in range(10): QtGui.QApplication.processEvents()
            view.saveImage(str(output/(name+'.png')),1600,1200,'White')
    finally:
        for obj in objects:
            visible,transparency,color = saved[obj.Name]
            obj.ViewObject.Visibility = visible
            obj.ViewObject.Transparency = transparency
            obj.ViewObject.ShapeColor = color
        view.setCameraOrientation(camera.Q)
        view.fitAll()


def check_speaker(doc):
    from build_tank import box, faceted_shell_volume
    speaker = doc.getObject('AudioModule').Shape
    b = speaker.optimalBoundingBox(False)
    assert max(abs(a-c) for a,c in zip((b.XLength,b.YLength,b.ZLength),SIZE)) < 1e-6
    # Original helmet cavity from build_tank, including its -4 mm Z translation.
    cavity = faceted_shell_volume([(65,-67,20,10,143),(79,-80,26,10,152),
                                  (79,-80,26,10,183),(72,-73,22,10,193)])
    lift = float(doc.getObject('AudioModule').HeadLift)
    cavity.translate(App.Vector(0,0,-4+lift))
    outside = speaker.cut(cavity).Volume
    overlaps, reserved_overlaps, nearby = [], [], []
    tested = 0
    for obj in doc.Objects:
        if obj.Name == 'AudioModule' or not hasattr(obj, 'Category'):
            continue
        other = obj.Shape
        bounds = other.optimalBoundingBox(False)
        if b.intersect(bounds):
            tested += 1
            volume = speaker.common(other).Volume
            if volume > 0.01:
                row = {'object':obj.Name, 'volume_mm3':volume}
                (reserved_overlaps if obj.Category == 'clearance' else overlaps).append(row)
        if bounds.ZMax >= 140 and bounds.YMin < 0:
            nearby.append({'object':obj.Name, 'category':obj.Category,
                           'distance_mm':speaker.distToShape(other)[0]})
    nearby.sort(key=lambda row: row['distance_mm'])
    old = box(-36,-75,146+lift,36,-39,167+lift)
    return {'source':'user-provided dimensions, 2026-10-24',
            'size_xyz_mm':list(SIZE), 'bbox_mm':[b.XMin,b.YMin,b.ZMin,b.XMax,b.YMax,b.ZMax],
            'orientation':'length X, width Y, height Z; original allocation shifted with head by 25 mm',
            'shape_valid':speaker.isValid(), 'solid_count':len(speaker.Solids),
            'outside_original_allocation_mm3':speaker.cut(old).Volume,
            'outside_head_cavity_mm3':outside, 'overlap_tolerance_mm3':0.01,
            'static_boolean_pairs':tested, 'overlaps':overlaps,
            'reserved_space_overlaps':reserved_overlaps, 'nearby_distances':nearby,
            'passed':speaker.isValid() and outside <= 0.01 and not overlaps and not reserved_overlaps,
            'mounts_leads_acoustics_verified':False, 'physical_fit_verified':False}
