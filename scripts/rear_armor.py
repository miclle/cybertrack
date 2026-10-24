"""Mirror-defined rear armor sections and saved-solid symmetry verification."""
import FreeCAD as App
import Part

V = App.Vector


def mirrored_profile(right):
    """Walk the right half bottom-to-top, then its mirror, retaining wire order."""
    left = [(-x, z) for x, z in reversed(right)]
    return left[-1:] + right + left[:-1]


def check_rear_armor(doc):
    """Verify the complete closed armor; no hole masking or geometry exceptions."""
    armor = doc.getObject('RearBaseArmor').Shape
    filled = armor
    reflection = App.Matrix()
    reflection.A11 = -1
    mirrored = filled.transformGeometry(reflection)
    volume_delta = filled.cut(mirrored).Volume + mirrored.cut(filled).Volume
    vertex_delta = max(min((v.Point-w.Point).Length for w in mirrored.Vertexes)
                       for v in filled.Vertexes)
    # Match whole faces, including bevels and the central spine seat, one-to-one.
    available = set(range(len(mirrored.Faces)))
    faces = []
    for i, face in enumerate(filled.Faces):
        delta, j = min((face.cut(mirrored.Faces[j]).Area + mirrored.Faces[j].cut(face).Area, j)
                       for j in available)
        available.remove(j)
        faces.append({'face': i+1, 'mirrored_face': j+1, 'area_mm2': face.Area,
                      'symmetric_difference_mm2': delta})
    tolerance = 1e-5
    passed = (armor.isValid() and len(armor.Solids) == 1 and filled.isValid()
              and volume_delta <= tolerance
              and vertex_delta <= tolerance
              and all(f['symmetric_difference_mm2'] <= tolerance for f in faces))
    return {'object': 'RearBaseArmor', 'mirror_plane': 'X=0',
            'method': 'mirror complete closed armor, vertices and whole faces; no exclusions',
            'excluded_feature': None, 'model_modified_by_check': False,
            'solid_symmetric_difference_mm3': volume_delta,
            'maximum_mirrored_vertex_distance_mm': vertex_delta,
            'face_pairs': faces, 'tolerance_mm': tolerance, 'tolerance_mm2': tolerance,
            'tolerance_mm3': tolerance, 'passed': passed,
            'physical_or_manufacturing_verified': False}
