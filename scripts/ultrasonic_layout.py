"""Measured twin probes with an explicitly provisional front-panel datum."""
import json
from pathlib import Path

import FreeCAD as App
import Part

SOURCE = Path(__file__).resolve().parents[1] / 'hardware/components/ultrasonic/dimensions.json'
DIMENSIONS = json.loads(SOURCE.read_text())['dimensions']
DIAMETER = DIMENSIONS['cylinder_diameter']
SPAN = DIMENSIONS['two_cylinders_overall_width']
HEIGHT = DIMENSIONS['height_from_panel']
PITCH = SPAN - DIAMETER
PANEL_Y = -81.0
CENTER_Z = 163.0
RADIAL_GAP = 0.3
NAMES = ('SensorMask', 'SensorStatusStrip', 'UltrasonicRingL', 'UltrasonicFaceL',
         'UltrasonicRingR', 'UltrasonicFaceR')
V = App.Vector
BASIS = ('用户尺寸：圆柱Ø16、双圆柱总宽42、离面板高10.3 mm；中心距26为推导；'
         '临时将面板解释为前脸外表面Y=-81，中心Z=163；不含PCB、背面元件和接头')


def probe_shape(sign):
    return Part.makeCylinder(DIAMETER / 2, HEIGHT,
                             V(sign * PITCH / 2, PANEL_Y, CENTER_Z), V(0, -1, 0))


def add_ultrasonic(add, panel):
    """Panel arrives in final world coordinates; neither it nor probes shift again."""
    for sign in (-1, 1):
        panel = panel.cut(Part.makeCylinder(DIAMETER / 2 + RADIAL_GAP, 5,
                          V(sign * PITCH / 2, PANEL_Y - 1, CENTER_Z), V(0, 1, 0)))
    add('SensorMask', '前脸传感器面板／双Ø16.6候选孔', panel, 'exterior', 'visor',
        BASIS + '；孔单边0.3 mm为装配假设，未定制造公差')
    for side, sign in [('L', 1), ('R', -1)]:
        full = probe_shape(sign)
        # Face division is only a colour detail; the union is the complete cylinder.
        face = Part.makeCylinder(7.25, 0.5,
                                V(sign * PITCH / 2, PANEL_Y - HEIGHT, CENTER_Z), V(0, 1, 0))
        add('UltrasonicRing' + side, '超声波圆柱主体 Ø16×10.3 ' + side,
            full.cut(face), 'component', 'metal', BASIS + '；端面分色为外观假设')
        add('UltrasonicFace' + side, '超声波探头端面 ' + side,
            face, 'component', 'dark', BASIS + '；端面Ø14.5及0.5深度仅为分色')
    add('SensorStatusStrip', '双探头上方窄状态色条',
        Part.makeBox(16, 0.5, 1, V(-8, PANEL_Y - 0.5, 172.5)),
        'exterior', 'signal', '布局选择：移至双探头上方；色块示意，不是已选定灯具')


def check_ultrasonic(doc):
    objects = [o for o in doc.Objects if hasattr(o, 'Category')]
    probes, overlaps, reserved, nearby = [], [], [], []
    tested = 0
    for side, sign in [('L', 1), ('R', -1)]:
        names = ('UltrasonicRing' + side, 'UltrasonicFace' + side)
        parts = [doc.getObject(n).Shape for n in names]
        full = probe_shape(sign)
        actual = parts[0].fuse(parts[1]).removeSplitter()
        difference = actual.cut(full).Volume + full.cut(actual).Volume
        b = actual.optimalBoundingBox(False)
        probes.append({'side': side, 'bbox_mm': [b.XMin, b.YMin, b.ZMin, b.XMax, b.YMax, b.ZMax],
                       'valid': actual.isValid(), 'solids': len(actual.Solids),
                       'cylinder_difference_mm3': difference,
                       'visual_parts_overlap_mm3': parts[0].common(parts[1]).Volume})
        # Test filled cylinders, so hollow display details cannot hide interferences.
        for obj in objects:
            if obj.Name in names:
                continue
            other = obj.Shape
            if b.intersect(other.optimalBoundingBox(False)):
                tested += 1
                volume = full.common(other).Volume
                if volume > 0.01:
                    row = {'probe': side, 'object': obj.Name, 'volume_mm3': volume}
                    (reserved if obj.Category == 'clearance' else overlaps).append(row)
            distance = full.distToShape(other)[0]
            if distance < 15:
                nearby.append({'probe': side, 'object': obj.Name, 'category': obj.Category,
                               'distance_mm': distance})
    nearby.sort(key=lambda row: row['distance_mm'])
    panel = doc.getObject('SensorMask').Shape
    valid = all(doc.getObject(n).Shape.isValid() for n in NAMES)
    return {'source': str(SOURCE.relative_to(SOURCE.parents[3])),
            'diameter_mm': DIAMETER, 'outer_span_mm': SPAN, 'height_from_panel_mm': HEIGHT,
            'derived_center_spacing_mm': PITCH, 'derived_gap_mm': SPAN - 2 * DIAMETER,
            'center_x_mm': [-PITCH / 2, PITCH / 2], 'center_z_mm': CENTER_Z,
            'panel_datum_y_mm': PANEL_Y, 'probe_front_y_mm': PANEL_Y - HEIGHT,
            'datum_is_assumption': True, 'datum_description': 'robot front-panel outer face; user panel datum not confirmed',
            'candidate_hole_diameter_mm': DIAMETER + 2 * RADIAL_GAP,
            'nominal_radial_gap_mm': RADIAL_GAP,
            'panel_valid': panel.isValid(), 'panel_solids': len(panel.Solids),
            'probes': probes, 'overlap_tolerance_mm3': 0.01, 'static_boolean_pairs': tested,
            'overlaps': overlaps, 'reserved_space_overlaps': reserved, 'nearby_distances': nearby,
            'passed': valid and len(panel.Solids) == 1 and not overlaps and not reserved
                      and all(p['valid'] and p['solids'] == 1 and p['cylinder_difference_mm3'] < 1e-5
                              and p['visual_parts_overlap_mm3'] < 1e-5 for p in probes),
            'pcb_and_rear_components_modeled': False, 'mounting_verified': False,
            'physical_fit_verified': False, 'acoustic_verified': False}


def render_ultrasonic(doc, output):
    import FreeCADGui as Gui
    from PySide import QtGui
    objects = [o for o in doc.Objects if hasattr(o, 'Category')]
    saved = {o.Name: o.ViewObject.Visibility for o in objects}
    view = Gui.activeDocument().activeView()
    camera = view.getCameraOrientation()
    try:
        for obj in objects:
            obj.ViewObject.Visibility = obj.Name in NAMES or obj.Name.startswith(
                ('VisorRim', 'BrowArmor', 'CheekArmor', 'Jaw'))
        for name, rotation in [('ultrasonic-front', App.Rotation(V(1, 0, 0), 90)),
                               ('ultrasonic-layout', App.Rotation(V(1, 1, 0), V(-1, 1, 3), V(1, -1, 0.75), 'ZXY'))]:
            view.setCameraOrientation(rotation.Q)
            view.fitAll()
            for _ in range(10):
                QtGui.QApplication.processEvents()
            view.saveImage(str(output / (name + '.png')), 1600, 1200, 'White')
    finally:
        for obj in objects:
            obj.ViewObject.Visibility = saved[obj.Name]
        view.setCameraOrientation(camera.Q)
        view.fitAll()
