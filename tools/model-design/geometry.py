"""Exact OCCT solids and preview meshes; no natural-language execution."""
import json
import math
from pathlib import Path
import sys
import cadquery as cq
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepBndLib import BRepBndLib
from OCP.Bnd import Bnd_Box


def plate_dimensions(part):
    length, width, thickness = part['size']
    diameter, spacing = part['holeDiameter'], part['holeSpacing']
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0
           for v in [length, width, thickness, diameter, spacing]):
        raise ValueError('Plate dimensions must be finite and positive')
    if spacing <= diameter or spacing + diameter >= length or diameter >= width:
        raise ValueError('Plate holes must not touch each other or the plate edges')
    if part['position'] != [0, 0, thickness/2]:
        raise ValueError('Plate bottom must be at the origin')
    return length, width, thickness, diameter, spacing


def check_plate(shape, part, world=False):
    """Check actual cylindrical surfaces as well as volume and material probes."""
    length, width, thickness, diameter, spacing = plate_dimensions(part)
    bottom = 0 if world else -thickness/2
    check_bounds(bounds(shape), [-length/2, -width/2, bottom, length/2, width/2, bottom+thickness])
    cylinders = [BRepAdaptor_Surface(face.wrapped).Cylinder()
                 for face in shape.Faces() if face.geomType() == 'CYLINDER']
    cylinders.sort(key=lambda cylinder: cylinder.Location().X())
    if len(cylinders) != 2:
        raise ValueError('Plate must contain exactly two cylindrical holes')
    centers = [[-spacing/2, 0], [spacing/2, 0]]
    for cylinder, (x, y) in zip(cylinders, centers):
        location, direction = cylinder.Location(), cylinder.Axis().Direction()
        if any(abs(value) > 1e-6 for value in [
            location.X()-x, location.Y()-y, cylinder.Radius()-diameter/2,
            direction.X(), direction.Y(), abs(direction.Z())-1,
        ]):
            raise ValueError('Plate hole center, radius or axis validation failed')
        for z in [bottom+thickness/4, bottom+thickness/2, bottom+3*thickness/4]:
            if any(shape.isInside(cq.Vector(x+offset, y, z), 1e-6) for offset in [0, diameter*0.45]):
                raise ValueError('Plate hole is blocked')
        # Probe material outside each hole toward the long side of the plate.
        if not shape.isInside(cq.Vector(x, (diameter+width)/4, bottom+thickness/2), 1e-6):
            raise ValueError('Plate wall is missing')
    if not shape.isInside(cq.Vector(0, 0, bottom+thickness/2), 1e-6):
        raise ValueError('Material between plate holes is missing')
    removed = 2*math.pi*(diameter/2)**2*thickness
    if abs(shape.Volume()-(length*width*thickness-removed)) > 1e-5:
        raise ValueError('Plate volume validation failed')
    return {'holeDiameterMm': diameter, 'holeSpacingMm': spacing, 'holeDepthMm': thickness,
            'holeCentersMm': centers, 'axis': 'Z', 'holeGeometryVerified': True,
            'axisVoidVerified': True, 'wallSolidVerified': True, 'removedVolumeMm3': removed}


def make_part(part):
    if part['kind'] == 'box':
        x, y, z = part['size']
        if part.get('profile') == 'mounting-plate':
            plate_dimensions(part)
        shape = cq.Solid.makeBox(x, y, z, cq.Vector(-x / 2, -y / 2, -z / 2))
        if part.get('profile') == 'mounting-plate':
            for center in [-part['holeSpacing']/2, part['holeSpacing']/2]:
                cutter = cq.Solid.makeCylinder(part['holeDiameter']/2, z+2, cq.Vector(center, 0, -z/2-1))
                shape = shape.cut(cutter).clean()
    elif part['kind'] == 'cylinder':
        if any(not isinstance(part[key], (int, float)) or not math.isfinite(part[key]) or part[key] <= 0 for key in ['radius', 'height']):
            raise ValueError('Cylinder dimensions must be finite and positive')
        shape = cq.Solid.makeCylinder(part['radius'], part['height'], cq.Vector(0, 0, -part['height'] / 2))
        diameter = part.get('centerHoleDiameter', 0)
        if diameter:
            if not 0 < diameter < 2 * part['radius']:
                raise ValueError('Hole diameter must be smaller than the cylinder diameter')
            cutter = cq.Solid.makeCylinder(diameter / 2, part['height'] + 2, cq.Vector(0, 0, -part['height'] / 2 - 1))
            shape = shape.cut(cutter).clean()
    else:
        raise ValueError('Unsupported primitive')
    if not shape.isValid() or len(shape.Solids()) != 1:
        raise ValueError('Kernel did not produce a valid single solid')
    return shape


def bounds(shape):
    # Preview tessellation must not change exact-solid dimension validation.
    box = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape.wrapped, box, False, False)
    return list(box.Get())


def check_bounds(actual, expected):
    if any(abs(a-b) > 1e-6 for a, b in zip(actual, expected)):
        raise ValueError('Bounding box validation failed')


def tessellate_faces(shape):
    # Face IDs belong only to this exact shape/revision, never to future topology.
    positions, indices, faces = [], [], []
    for index, face in enumerate(shape.Faces()):
        vertices, triangles = face.tessellate(0.05, 0.1)
        start, offset = len(indices)//3, len(positions)//3
        positions.extend(round(c, 8) for v in vertices for c in v.toTuple())
        indices.extend(offset+i for t in triangles for i in t)
        faces.append({'id': f'Face{index+1}', 'type': face.geomType(),
                      'start': start, 'count': len(triangles)})
    return {'positions': positions, 'indices': indices, 'faces': faces}


def generate(model, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    meshes, summaries, placed = {}, {}, []
    for part in model['parts']:
        shape = make_part(part)
        meshes[part['id']] = tessellate_faces(shape)
        diameter = part.get('centerHoleDiameter', 0)
        summary = {'valid': shape.isValid(), 'solids': len(shape.Solids()), 'volumeMm3': shape.Volume(), 'faces': len(shape.Faces())}
        if part.get('profile') == 'mounting-plate':
            summary.update(check_plate(shape, part))
            summary['bottomAnchoredVerified'] = True
        if diameter:
            h, radius = part['height'], part['radius']
            expected = math.pi * (radius ** 2 - (diameter / 2) ** 2) * h
            void = all(not shape.isInside(cq.Vector(0, 0, z), 1e-6) for z in [-h/2 + 0.01, 0, h/2 - 0.01])
            wall = shape.isInside(cq.Vector((radius + diameter/2)/2, 0, 0), 1e-6)
            if not void or not wall or abs(shape.Volume() - expected) > 1e-5:
                raise ValueError('Through-hole validation failed')
            summary.update({'holeDiameterMm': diameter, 'holeDepthMm': h, 'axis': 'Z', 'localCenter': [0, 0], 'axisVoidVerified': void, 'wallSolidVerified': wall, 'removedVolumeMm3': math.pi*(diameter/2)**2*h})
        world = shape.translate(tuple(part['position']))
        summary['boundsMm'] = bounds(world)
        if part.get('profile') == 'spacer':
            if not diameter or part['position'] != [0, 0, part['height']/2]:
                raise ValueError('Spacer must have a through-hole and its bottom at the origin')
            radius = part['radius']
            check_bounds(bounds(world), [-radius, -radius, 0, radius, radius, part['height']])
            summary['bottomAnchoredVerified'] = True
        path = output / f"{part['id']}.step"
        cq.exporters.export(world, str(path))
        reloaded = cq.importers.importStep(str(path)).val()
        if not reloaded.isValid() or len(reloaded.Solids()) != 1 or abs(reloaded.Volume() - shape.Volume()) > 1e-5:
            raise ValueError('STEP round-trip validation failed')
        check_bounds(bounds(reloaded), bounds(world))
        summary['stepRoundTripValid'] = True
        summary['stepBoundsVerified'] = True
        if part.get('profile') == 'mounting-plate':
            check_plate(reloaded, part, world=True)
            summary.update({'stepHoleGeometryVerified': True, 'stepHoleVoidVerified': True,
                            'stepWallSolidVerified': True})
        if diameter:
            p=part['position']
            if any(reloaded.isInside(cq.Vector(p[0],p[1],p[2]+z),1e-6) for z in [-h/2+0.01,0,h/2-0.01]):
                raise ValueError('STEP round-trip hole is blocked')
            summary['stepHoleVoidVerified'] = True
            if not reloaded.isInside(cq.Vector(p[0]+(radius+diameter/2)/2,p[1],p[2]),1e-6):
                raise ValueError('STEP round-trip wall is missing')
            summary['stepWallSolidVerified'] = True
        summaries[part['id']] = summary
        placed.append(world)
    if placed:
        cq.exporters.export(cq.Compound.makeCompound(placed), str(output/'assembly.step'))
    result = {'revision': model['revision'], 'engine': f'CadQuery {cq.__version__} / OpenCascade', 'meshes': meshes, 'parts': summaries}
    (output/'preview.json').write_text(json.dumps(result),encoding='utf8')
    return result

if __name__ == '__main__':
    request=json.load(sys.stdin)
    result=generate(request['model'],request['output'])
    print(json.dumps({'revision':result['revision'],'engine':result['engine'],'parts':result['parts']}))
