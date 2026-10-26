"""Render current CAD face colours and transparency for the assembly PDF.

Run after export_drawing_geometry.py, with FreeCAD's bundled Python and a
desktop display. Only this process's in-memory document/view state is changed.
"""
import hashlib
import json
import math
from pathlib import Path

PROJECTION_MATRICES = {
    'iso': ((2**-.5,2**-.5,0),(-6**-.5,6**-.5,(2/3)**.5),(3**-.5,-3**-.5,3**-.5)),
    'front': ((1,0,0),(0,0,1),(0,-1,0)),
    'rear': ((-1,0,0),(0,0,1),(0,1,0)),
    'side': ((0,1,0),(0,0,1),(1,0,0)),
    'right': ((0,-1,0),(0,0,1),(-1,0,0)),
    'top': ((1,0,0),(0,1,0),(0,0,1)),
    'bottom': ((-1,0,0),(0,1,0),(0,0,-1)),
}


def main():
    import FreeCAD as App
    import FreeCADGui as Gui
    from gun_pitch import moved

    root = Path(__file__).resolve().parents[1]
    data = root / 'tmp/pdfs'
    out = data / 'colors'
    out.mkdir(exist_ok=True)
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    meta = json.loads((data / 'dimensions.json').read_text())
    source = root / 'hardware/model' / meta['source_document']
    assert sha(source) == meta['source_sha256'], 'Regenerate geometry first'
    projections = []
    for path in sorted(data.glob('*.json')):
        projection = json.loads(path.read_text())
        if projection.get('projection_revision') == 3 and projection.get('source_sha256') == meta['source_sha256']:
            assert not projection['clip'], 'Clipped colour views are not implemented'
            projections.append((path, projection))
    assert projections

    Gui.showMainWindow()
    doc = App.openDocument(str(source))
    Gui.updateGui()
    # Import after GUI/document initialization: Coin's SWIG wrapper is required
    # by getCameraNode(), but early initialization can crash this macOS build.
    from pivy import coin  # noqa: F401
    from PySide.QtGui import QImage
    for obj in doc.Objects:
        if obj.ViewObject:
            obj.ViewObject.Visibility = False
            if hasattr(obj.ViewObject, 'Deviation'):
                obj.ViewObject.Deviation = 0.08
                obj.ViewObject.AngularDeflection = 12
                obj.ViewObject.LineWidth = 1
    Gui.updateGui()
    view = Gui.activeDocument().activeView()
    view.setCameraType('Orthographic')
    camera = view.getCameraNode()
    visible = set()
    results = {}
    for path, projection in projections:
        key = path.stem
        image_path = out / (key + '.png')
        record_path = out / (key + '.json')
        projection_hash = sha(path)
        if record_path.exists() and image_path.exists():
            previous = json.loads(record_path.read_text())
            if (previous.get('render_revision') == 2 and
                    previous.get('projection_sha256') == projection_hash and
                    previous.get('image_sha256') == sha(image_path)):
                results[key] = previous
                continue
        names = set(projection['names'])
        for name in visible - names:
            doc.getObject(name).ViewObject.Visibility = False
        for name in names - visible:
            doc.getObject(name).ViewObject.Visibility = True
        visible = names
        ring_before = None
        if key == 'pp02_ring_local':
            ring_before = doc.BubbleGunRing.Shape.copy()
            doc.BubbleGunRing.Shape = moved(ring_before, 'bubble', inverse=True)
        try:
            Gui.updateGui()
            matrix = App.Matrix()
            for i, row in enumerate(PROJECTION_MATRICES[projection['view']]):
                for j, value in enumerate(row):
                    setattr(matrix, f'A{i+1}{j+1}', value)
            rotation = App.Rotation(matrix).inverted()
            x0,y0,x1,y1 = projection['bounds']
            span_x,span_y = max(x1-x0,.01),max(y1-y0,.01)
            longest = 1000 if key.startswith('part_') else 2200
            density = longest / max(span_x, span_y)
            width = max(128, math.ceil(span_x*density))
            height = max(128, math.ceil(span_y*density))
            world_height = max(span_y, span_x*height/width)*1.04
            mx,my = (x0+x1)/2,(y0+y1)/2
            # Camera looks along local -Z; all CAD vertices must remain between
            # its near/far planes, including long almost edge-on assemblies.
            zs = [matrix.multVec(v.Point).z for n in names for v in doc.getObject(n).Shape.Vertexes]
            distance = max(max(zs)-min(zs),span_x,span_y,1)*3
            position = rotation.multVec(App.Vector(mx,my,max(zs)+distance))
            # Direct Coin assignment avoids animated camera transitions.
            camera.orientation.setValue(*rotation.Q)
            camera.position.setValue(position.x,position.y,position.z)
            # FreeCAD's portrait saveImage changes the effective camera scale.
            # Render square, then crop pixels without rescaling so dimensions
            # and model coordinates remain aligned in every aspect ratio.
            side = max(width, height)
            square_span = world_height*side/height
            camera.height.setValue(square_span)
            camera.nearDistance.setValue(.01)
            camera.farDistance.setValue(distance+max(zs)-min(zs)+1)
            camera.focalDistance.setValue(distance+(max(zs)-min(zs))/2)
            Gui.updateGui()
            view.saveImage(str(image_path),side,side,'White')
            left,top = (side-width)//2,(side-height)//2
            cropped = QImage(str(image_path)).copy(left,top,width,height)
            assert cropped.save(str(image_path)), 'Failed to save colour view'
            unit = square_span/side
            bx0,by1 = mx-square_span/2+left*unit,my+square_span/2-top*unit
            result = dict(source_sha256=meta['source_sha256'],render_revision=2,
                          projection_sha256=projection_hash,image_sha256=sha(image_path),
                          image=str(image_path.relative_to(data)),pixels=[width,height],
                          bounds=[bx0,by1-height*unit,bx0+width*unit,by1],
                          colors_from='native CAD face materials',transparency_from='native CAD')
            record_path.write_text(json.dumps(result,indent=2)+'\n')
            results[key] = result
            print(key, width, height, flush=True)
        finally:
            if ring_before is not None:
                doc.BubbleGunRing.Shape = ring_before
    assert sha(source) == meta['source_sha256'], 'Source CAD changed during rendering'
    (out/'manifest.json').write_text(json.dumps(dict(source_sha256=meta['source_sha256'],views=results),indent=2)+'\n')
    print('Colour views:', len(results), flush=True)


if __name__ == '__main__':
    main()
    # FreeCAD's embedded Python GUI can crash during interpreter teardown on
    # macOS. All files above are explicitly closed; never save the CAD document.
    import os
    os._exit(0)
