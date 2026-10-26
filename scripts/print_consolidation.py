"""0.51 printable unions; design features remain hidden, traceable check inputs.

Run via build_tank.py. Added material is confined to four crown ties and the
fixed crossbar clearance, two internal wet-bay seam ties and two neck bore webs.
No soft pads, purchased parts or service lids merge.
"""
import json
from pathlib import Path
import FreeCAD as App
import Part
import Mesh
import MeshPart

V = App.Vector
REVISION = '0.54'


def groups(doc):
    from bubble_gun_mount import SLOT_WALL_IDS
    crown = [o.Name for o in doc.Objects
             if o.Name.startswith(('Crown', 'BrowArmor', 'OccipitalBrow', 'HeadCrown', 'HeadService'))
             and not o.Name.startswith(('CrownScrew', 'CrownInsert'))]
    neck = [o.Name for o in doc.Objects if o.Name.startswith('Neck') and o.Name != 'NeckCableBridge']
    return [
        ('PrintWaterCradle', 'PP01 水枪一体底托', ['WaterGunCradle', 'WaterGunHoseSupport', 'WaterGunHoseSupportRear']),
        ('PrintBubbleCradle', 'PP02 泡泡枪一体圆环底座', ['BubbleGunCradle', 'BubbleGunRing'] + ['BubbleGunSlotWall'+str(i) for i in SLOT_WALL_IDS]),
        ('PrintBackpack', 'PP03 双瓶背包一体外壳及桶座', ['BackpackShell', 'RearBaseArmor', 'BackpackSpine']),
        ('PrintLowerTub', 'PP04 一体底盘及湿舱隔板', ['LowerTub', 'RearBulkhead', 'WetDivider']),
        ('PrintCrown', 'PP05 一体冠盖及装甲饰件', crown),
        ('PrintNeck', 'PP06 一体固定颈架', neck),
    ]


def connect_features(doc):
    """Add ties without overlapping feature material used by collision checks."""
    crown_names = groups(doc)[4][2]
    others = Part.makeCompound([doc.getObject(n).Shape for n in crown_names if n != 'HeadCrownShell'])
    ties = [Part.makeBox(6, 5.5, 2, V(x-3, -85.5, 207)) for x in (-48, 48)]
    ties += [Part.makeBox(6, 6.5, 2, V(x-3, 27, 207)) for x in (-44, 44)]
    crown = doc.HeadCrownShell
    original = crown.Shape.copy()
    crown.Shape = original.multiFuse(ties).cut(others).removeSplitter()
    # The transverse member is fixed, not a rotating shaft: fill its radial gap.
    crossbar = doc.NeckCrossbar
    old_crossbar = crossbar.Shape.copy()
    crossbar.Shape = Part.makeCylinder(8, 64, V(-32, -11, 149), V(1, 0, 0))
    crossbar.Label = '固定横梁／填平0.5 mm径向间隙并入颈架'
    crown.Label = '整体上取冠盖／四处内侧连接筋／0.25 mm装配分缝'
    bulkhead = doc.RearBulkhead
    old_bulkhead = bulkhead.Shape.copy()
    # Eliminate two knife-edge contacts at the wet-bay seam. Stay on its wet
    # side (Y>=25) so the L298N dry-side clearance is not reduced.
    seam_ties = [Part.makeBox(28.2, .4, .8, V(x,25,37)) for x in (-37.5,9.3)]
    other_base = doc.LowerTub.Shape.fuse(doc.WetDivider.Shape)
    bulkhead.Shape = old_bulkhead.multiFuse(seam_ties).cut(other_base).removeSplitter()
    bulkhead.Label = '后湿舱隔板／湿侧0.4 mm接缝连桥并入底盘'
    webs=[]
    for side,x in (('L',26),('R',-29)):
        obj=doc.getObject('NeckOuterWeb'+side)
        old=obj.Shape.copy()
        # The R9 bore was tangent to the plate's top edge. Keep the outside
        # contour and add a 0.4 mm web on the bore side to remove that knife edge.
        obj.Shape=old.fuse(Part.makeBox(3,6,.4,V(x,-14,157.6))).removeSplitter()
        webs.append((obj,old))
    added = {}
    all_features = [o for o in doc.Objects if hasattr(o, 'Category')]
    for obj, old in [(crown, original), (crossbar, old_crossbar), (bulkhead, old_bulkhead)]+webs:
        assert obj.Shape.isValid() and len(obj.Shape.Solids) == 1, obj.Name
        delta = obj.Shape.cut(old)
        removed = old.cut(obj.Shape).Volume
        hits = []
        for obstacle in all_features:
            if obstacle == obj or not delta.BoundBox.intersect(obstacle.Shape.BoundBox):
                continue
            volume = delta.common(obstacle.Shape).Volume
            if volume > .01:
                hits.append({'object': obstacle.Name, 'volume_mm3': volume})
        assert removed < 1e-5 and not hits, (obj.Name, removed, hits)
        added[obj.Name] = {'added_volume_mm3': delta.Volume, 'removed_volume_mm3': removed,
                          'added_material_collisions_including_reserved_spaces': hits}
    return {'revision': REVISION, 'changes': added,
            'crown_ties': {'quantity': 4, 'width_mm': 6, 'height_mm': 2, 'z_mm': [207, 209],
                          'front_centres_x_mm': [-48, 48], 'rear_centres_x_mm': [-44, 44]},
            'fixed_crossbar': {'old_radius_mm': 7.5, 'new_radius_mm': 8, 'length_mm': 64},
            'neck_bore_webs': {'quantity':2, 'thickness_mm':.4, 'y_mm':[-14,-8], 'z_mm':[157.6,158]},
            'wet_seam_ties': {'quantity':2, 'x_ranges_mm':[[-37.5,-9.3],[9.3,37.5]],
                              'y_mm':[25,25.4], 'z_mm':[37,37.8], 'dry_side_unchanged':True},
            'physical_fit_verified': False}


def finalize(doc, out, report, connection_check, render=False):
    """Add actual fused objects, export each, and verify the saved representation."""
    from build_tank import sha
    root = Path(out)
    directory = root / 'print-parts'
    directory.mkdir(exist_ok=True)
    # Re-exporting a verified source model replaces only these derived unions.
    for name, _, _ in groups(doc):
        if doc.getObject(name): doc.removeObject(name)
    if doc.getObject('PrintParts'): doc.removeObject('PrintParts')
    doc.recompute()
    group = doc.addObject('App::DocumentObjectGroup', 'PrintParts')
    group.Label = '08 合并打印件／六件候选'
    rows = []
    consumed = set()
    for index, (name, label, members) in enumerate(groups(doc), 1):
        assert not consumed.intersection(members)
        consumed.update(members)
        obj = doc.addObject('Part::MultiFuse', name)
        obj.Label = label
        obj.Shapes = [doc.getObject(n) for n in members]
        obj.Refine = True
        obj.addProperty('App::PropertyString', 'PrintPartID', 'Manufacturing')
        obj.PrintPartID = f'PP{index:02d}'
        obj.addProperty('App::PropertyString', 'EvidenceBasis', 'Manufacturing')
        obj.EvidenceBasis = '0.51合并打印候选；单实体检查，不代表材料、层向、公差或实物验收'
        group.addObject(obj)
        doc.recompute()
        assert obj.Shape.isValid() and len(obj.Shape.Solids) == 1, name
        originals = [doc.getObject(n).Shape for n in members]
        missing = sum(s.cut(obj.Shape).Volume for s in originals)
        extra = obj.Shape.cut(Part.makeCompound(originals)).Volume
        assert missing < 1e-5 and extra < 1e-5, (name, missing, extra)
        b = obj.Shape.optimalBoundingBox(False)
        # Keep axes, centre XY and put the lowest point on Z=0; no print orientation claim.
        translation = V(-(b.XMin+b.XMax)/2, -(b.YMin+b.YMax)/2, -b.ZMin)
        local = obj.Shape.copy()
        local.translate(translation)
        stem = f'PP{index:02d}-{name[5:]}'
        step_path = directory / (stem+'.step')
        local.exportStep(str(step_path))
        step = Part.Shape()
        step.read(str(step_path))
        step_delta = abs(step.Volume-local.Volume)
        assert step.isValid() and len(step.Solids) == 1
        mesh = MeshPart.meshFromShape(Shape=local, LinearDeflection=.08, AngularDeflection=.15, Relative=False)
        stl_path = directory / (stem+'.stl')
        mesh.write(str(stl_path))
        back = Mesh.Mesh(str(stl_path))
        # A connected CAD solid can have separate closed boundary meshes for
        # enclosed cavities. Require manifold closure and matching shell count.
        assert back.isSolid() and not back.hasNonManifolds(), stem
        assert back.countComponents() == len(obj.Shape.Shells), stem
        rows.append({'id': obj.PrintPartID, 'name': name, 'label': label,
                     'members': members, 'feature_count': len(members), 'solids': 1, 'valid': True,
                     'volume_mm3': obj.Shape.Volume, 'size_xyz_mm': [b.XLength,b.YLength,b.ZLength],
                     'stl_translation_xyz_mm': list(translation), 'stl_closed': back.isSolid(),
                     'stl_connected_components': back.countComponents(), 'cad_boundary_shells': len(obj.Shape.Shells),
                     'stl_nonmanifold': back.hasNonManifolds(), 'stl_facets': back.CountFacets,
                     'step_geometry_equivalence_verified': False, 'step_usage': 'layout_exchange_only; use native FCStd for geometry',
                     'step_volume_difference_mm3': step_delta, 'step_volume_comparison_passed': step_delta <= .01,
                     'missing_source_volume_mm3': missing, 'extra_volume_mm3': extra,
                     'files': {p.name: sha(p) for p in (step_path,stl_path)}})
        if render:
            obj.ViewObject.ShapeColor = obj.Shapes[0].ViewObject.ShapeColor
            colours=[]
            for face in obj.Shape.Faces:
                matches=[(face.common(source.Shape).Area, source.ViewObject.ShapeColor)
                         for source in obj.Shapes if face.BoundBox.intersect(source.Shape.BoundBox)]
                colours.append(max(matches,key=lambda item:item[0])[1] if matches else obj.ViewObject.ShapeColor)
            obj.ViewObject.DiffuseColor = colours
            obj.ViewObject.LineColor = (.08,.1,.12)
            obj.ViewObject.DisplayMode = 'Flat Lines'
            for source in obj.Shapes:
                source.ViewObject.Visibility = False
    doc.Label = 'CyberTrack 双履带交互机器人 · 装配候选 0.53'
    if render:
        group.ViewObject.Visibility = True
        for row in rows:
            doc.getObject(row['name']).ViewObject.Visibility = True
    doc.recompute()
    cad = root/'CyberTrack.FCStd'
    doc.save()
    # Exchange assembly includes each physical region exactly once.
    originals = [o for o in doc.Objects if hasattr(o,'Category') and o.Category not in ('envelope','clearance') and o.Name not in consumed]
    merged = [doc.getObject(r['name']) for r in rows]
    Part.export(originals+merged, str(root/'CyberTrack.step'))
    shape = Part.Shape()
    shape.read(str(root/'CyberTrack.step'))
    assembly = Part.makeCompound([o.Shape for o in originals+merged])
    bb, sb = assembly.optimalBoundingBox(False), shape.optimalBoundingBox(False)
    diff = abs(shape.Volume-assembly.Volume)
    bbox_diff = max(abs(getattr(bb,k)-getattr(sb,k)) for k in ('XMin','YMin','ZMin','XMax','YMax','ZMax'))
    assert shape.isValid() and len(shape.Solids)==len(assembly.Solids) and bbox_diff < 1e-5
    report['step_readback'].update(solids=len(shape.Solids),expected_solids=len(assembly.Solids),
                                  volume_difference_mm3=diff,bbox_difference_mm=bbox_diff,
                                  volume_comparison_passed=diff<=.01)
    report['design_revision'] = REVISION
    report['head_lift_check']['assembly_revision'] = REVISION
    report['print_consolidation'] = {'feature_count': len(consumed), 'print_part_count':len(rows),
                                     'design_features_are_hidden_sources':True, 'parts': rows}
    report['final_saved_audit']['gui_visibility_verified'] = False
    doc_name = doc.Name
    App.closeDocument(doc_name)
    saved = App.openDocument(str(cad))
    for row in rows:
        obj = saved.getObject(row['name'])
        assert obj.Shape.isValid() and len(obj.Shape.Solids)==1
        assert abs(obj.Shape.Volume-row['volume_mm3'])<1e-5
        assert [o.Name for o in obj.Shapes] == row['members']
    for row in report['objects']:
        obj=saved.getObject(row['name'])
        assert obj.Shape.isValid() and abs(obj.Shape.Volume-row['volume_mm3'])<1e-5
    visibility_verified = False
    if render:
        assert all(not saved.getObject(n).ViewObject.Visibility for n in consumed)
        assert all(saved.getObject(r['name']).ViewObject.Visibility for r in rows)
        visibility_verified = True
        render_parts(saved, root, rows)
    report['final_saved_audit'].update(gui_visibility_verified=visibility_verified,
                                      print_parts_saved_and_reopened=len(rows))
    App.closeDocument(saved.Name)
    # All geometric checks ran on the same source shapes before adding derived unions.
    # Refresh only exact pre-union file hashes, never historical baseline references.
    previous_hash = report['files_sha256']['CyberTrack.FCStd']
    current_hash = sha(cad)
    def refresh(value):
        if isinstance(value,dict):
            return {k:refresh(v) for k,v in value.items()}
        if isinstance(value,list):
            return [refresh(v) for v in value]
        return current_hash if value == previous_hash else value
    report = refresh(report)
    for filename in ('effects-mount-audit.json','effect-board-fit-audit.json','top-feed-audit.json',
                     'rear-armor-symmetry-audit.json','ultrasonic-fit-audit.json','ultrasonic-integration-audit.json',
                     'breadboard-fit-audit.json','drive-mount-audit.json','l298n-mount-audit.json','l298n-fit-audit.json',
                     'bottle-backpack-audit.json','head-lift-audit.json','mt3608-fit-audit.json','front-effects-fit-audit.json',
                     'ignition-mos-audit.json','ignition-routing-audit.json'):
        path=root/filename
        data=refresh(json.loads(path.read_text()))
        if filename == 'head-lift-audit.json': data['assembly_revision'] = REVISION
        path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    report['files_sha256']['CyberTrack.step'] = sha(root/'CyberTrack.step')
    for path in sorted(directory.glob('*.png')):
        report['files_sha256']['print-parts/'+path.name] = sha(path)
    audit = {**connection_check, 'source_sha256':current_hash,'parts':rows,
             'source_feature_count':len(consumed),'merged_print_part_count':len(rows),
             'saved_and_reopened':True,'passed':True,'manufacturing_released':False,
             'checks_on_design_features_equivalent_to_union':True,
             'limits':'CAD solid connectivity, nominal interference and existing service checks; no slicing, strength, material, tolerance or physical acceptance.'}
    (root/'print-consolidation-audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n')
    (root/'readback.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    return audit


def render_parts(doc, out, rows):
    import FreeCADGui as Gui
    from PySide import QtGui
    objects=[o for o in doc.Objects if hasattr(o,'Shape')]
    old={o.Name:o.ViewObject.Visibility for o in objects}
    view=Gui.activeDocument().activeView()
    view.viewAxonometric()
    try:
        for row in rows:
            for o in objects:o.ViewObject.Visibility=o.Name==row['name']
            view.fitAll()
            for _ in range(5):QtGui.QApplication.processEvents()
            view.saveImage(str(Path(out)/'print-parts'/(row['id']+'.png')),1200,900,'White')
    finally:
        for o in objects:o.ViewObject.Visibility=old[o.Name]
        view.fitAll()
