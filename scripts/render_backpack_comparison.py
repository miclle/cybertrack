"""Render two saved assemblies side by side at the same orthographic scale.

Read-only: source geometry, placements and view settings are never saved back.
Run with FreeCAD's bundled Python; supply the archived pre-change FCStd.
"""
import argparse
import hashlib
import json
from pathlib import Path

import FreeCAD as A
import FreeCADGui as G
from PySide import QtCore, QtGui

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('before', type=Path)
parser.add_argument('--after', type=Path, default=Path('hardware/model/CyberTrack.FCStd'))
parser.add_argument('--output', type=Path, default=Path('hardware/model/comparisons/0.35-to-0.36'))
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
sources = [args.before.resolve(), args.after.resolve()]
hashes = [sha(p) for p in sources]
G.showMainWindow()
records = []
for path in sources:
    doc = A.openDocument(str(path))
    parts = []
    for obj in doc.Objects:
        if not hasattr(obj, 'Category'):
            continue
        if obj.Category in ('envelope', 'clearance') and obj.Name not in ('WaterModule', 'BubbleModule'):
            continue
        parts.append((obj.Name, obj.Shape.copy(), tuple(obj.ViewObject.ShapeColor)))
    records.append(parts)
    A.closeDocument(doc.Name)

V = A.Vector
views = {
    'rear': (A.Rotation(V(0, 0, 1), 180).multiply(A.Rotation(V(1, 0, 0), 90)),
             [V(160, 0, 0), V(-160, 0, 0)]),
    'side': (A.Rotation(V(0, 1, 0), V(0, 0, 1), V(1, 0, 0), 'ZXY'),
             [V(0, -160, 0), V(0, 160, 0)]),
}
report = {'before_sha256': hashes[0], 'after_sha256': hashes[1],
          'before_source': str(sources[0]), 'after_source': str(sources[1]),
          'left': '0.35 before', 'right': '0.36 after',
          'bottles': 'complete provisional capped cylinders, not actual shoulder/cap shapes',
          'hose_routes_hidden_in_both': True, 'geometry_scaled': False,
          'camera': 'orthographic', 'views': {}}
for name, (rotation, offsets) in views.items():
    doc = A.newDocument('BackpackComparison')
    for index, parts in enumerate(records):
        for original_name, original_shape, color in parts:
            obj = doc.addObject('PartDesign::Feature', ('Before' if index == 0 else 'After') + original_name)
            shape = original_shape.copy()
            shape.translate(offsets[index])
            obj.Shape = shape
            obj.ViewObject.ShapeColor = color
            obj.ViewObject.DisplayMode = 'Flat Lines'
            obj.ViewObject.LineColor = (0.08, 0.10, 0.12)
            obj.ViewObject.LineWidth = 1
            obj.ViewObject.Transparency = 40 if original_name in ('WaterModule', 'BubbleModule') else 0
    doc.recompute()
    view = G.activeDocument().activeView()
    view.setAnimationEnabled(False)
    view.setCameraType('Orthographic')
    view.setCameraOrientation(rotation.Q)
    view.fitAll()
    camera = view.getCameraOrientation()
    camera_node = view.getCameraNode()
    camera_node.height.setValue(250.0)
    for _ in range(10):
        QtGui.QApplication.processEvents()
    output = args.output / (name + '-before-after.png')
    view.saveImage(str(output.resolve()), 2400, 1000, 'White')
    report['views'][name] = {'camera_height_mm': float(camera_node.height.getValue()),
                              'camera_orientation': list(camera.Q),
                              'offsets_mm': [list(v) for v in offsets],
                              'output_sha256': sha(output)}
    A.closeDocument(doc.Name)

assert hashes == [sha(p) for p in sources], 'Source file changed during rendering'
report['source_files_unchanged'] = True
(args.output / 'render-audit.json').write_text(json.dumps(report, indent=2) + '\n')
QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
G.getMainWindow().close()
QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
QtGui.QApplication.processEvents()
print(json.dumps({'output': str(args.output), 'source_files_unchanged': True}))
