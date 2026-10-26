"""Flatten the delivery model without changing geometry or its checked design source."""
import hashlib
import json
import shutil
from pathlib import Path
import FreeCAD as App


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def physical_objects(doc):
    return [o for o in doc.Objects if hasattr(o,'Shape') and not o.isDerivedFrom('App::DocumentObjectGroup')]


def organize(out, render=False):
    root=Path(out)
    cad=root/'CyberTrack.FCStd'
    source=root/'source/CyberTrack-design.FCStd'
    doc=App.openDocument(str(cad))
    unions=[o for o in doc.Objects if hasattr(o,'PrintPartID')]
    assert len(unions)==6
    drive=doc.getObject('Drive')
    assert drive and drive.Label=='01 双履带与动力参考'
    flattened=all(o.TypeId=='Part::Feature' for o in unions)
    # Visible ignition routing is an explicit review overlay, not part of the
    # 59 hidden tool/service spaces the user asked to move out of the main file.
    spaces={o.Name for o in doc.Objects
            if getattr(o,'Category','')=='clearance' and not o.Name.startswith(('IgnitionRoute','StopSignalRoute'))}
    prior=None
    if flattened:
        assert [o.Name for o in doc.Objects if o.isDerivedFrom('App::DocumentObjectGroup')]==['Drive']
        prior=json.loads((root/'model-tree-audit.json').read_text())
        assert prior['delivery_sha256']==sha(cad), 'Flattened model changed since the last audit'
        assert prior['source_sha256']==sha(source), 'Design source changed since the last audit'
        if not spaces:
            App.closeDocument(doc.Name)
            return prior
        consumed=set()
    else:
        assert all(o.TypeId=='Part::MultiFuse' for o in unions)
        consumed={s.Name for o in unions for s in o.Shapes}
        from print_consolidation import groups
        assert consumed=={n for _,_,members in groups(doc) for n in members}
    assert len(spaces)==59, 'Review changed clearance inventory before removing it'
    if render:
        assert all(not doc.getObject(n).ViewObject.Visibility for n in spaces)
    removed=consumed|spaces
    drive_members=[o.Name for o in drive.Group]
    union_names={o.Name for o in unions}
    for name in removed:
        assert all(p.Name in union_names or p.isDerivedFrom('App::DocumentObjectGroup') for p in doc.getObject(name).InList),name
    assert all(not getattr(o,'ExpressionEngine',[]) for o in doc.Objects), 'Inspect expressions before removing inputs'
    retained=[o for o in physical_objects(doc) if o.Name not in removed]
    before={o.Name:o.Shape.copy() for o in retained}
    # Tessellation can change on save or display without changing the exact BRep.
    # Capture serialization before copy(), which may also change topology flags.
    before_brep={o.Name:o.Shape.exportBrepToString() for o in retained}
    before_cleaned={o.Name:o.Shape.cleaned().exportBrepToString() for o in retained}
    labels={o.Name:o.Label for o in physical_objects(doc) if o.Name not in removed}
    visual={}
    if render:
        for name in before:
            view=doc.getObject(name).ViewObject
            visual[name]={p:getattr(view,p) for p in ('ShapeColor','DiffuseColor','LineColor','DisplayMode','Transparency','LineWidth','Visibility')}
    # Preserve the exact previously checked file, including its editable fusion inputs.
    source.parent.mkdir(exist_ok=True)
    if not flattened:
        shutil.copy2(cad,source)
    source_hash=sha(source)
    inputs={o.Name:[s.Name for s in o.Shapes] for o in unions} if not flattened else {}
    ids={o.Name:o.PrintPartID for o in unions}
    evidence={o.Name:o.EvidenceBasis for o in unions}
    groups=[o for o in doc.Objects if o.isDerivedFrom('App::DocumentObjectGroup') and o.Name!='Drive']
    removed_groups=[{'name':o.Name,'label':o.Label} for o in groups]
    for group in groups:
        group.Group=[]
        doc.removeObject(group.Name)
    if not flattened:
        for name in sorted(union_names):doc.removeObject(name)
    for name in sorted(removed):doc.removeObject(name)
    for name in sorted(union_names) if not flattened else []:
        obj=doc.addObject('Part::Feature',name)
        obj.Label=labels[name]
        obj.Shape=before[name]
        obj.addProperty('App::PropertyString','PrintPartID','Manufacturing')
        obj.PrintPartID=ids[name]
        obj.addProperty('App::PropertyString','EvidenceBasis','Manufacturing')
        obj.EvidenceBasis=evidence[name]
        obj.addProperty('App::PropertyStringList','SourceFeatures','Evidence')
        obj.SourceFeatures=inputs[name]
        obj.addProperty('App::PropertyString','DesignSource','Evidence')
        obj.DesignSource='source/CyberTrack-design.FCStd'
    doc.recompute()
    if render:
        for name,properties in visual.items():
            view=doc.getObject(name).ViewObject
            for prop,value in properties.items():setattr(view,prop,value)
    assert [o.Name for o in drive.Group]==drive_members
    assert all([p.Name for p in doc.getObject(n).InList]==(['Drive'] if n in drive_members else []) for n in before)
    doc.save()
    App.closeDocument(doc.Name)
    saved=App.openDocument(str(cad))
    objects=physical_objects(saved)
    assert {o.Name for o in objects}==set(before)
    assert [o.Name for o in saved.Objects if o.isDerivedFrom('App::DocumentObjectGroup')]==['Drive']
    assert [o.Name for o in saved.Drive.Group]==drive_members
    rows=[]
    for obj in objects:
        name=obj.Name;old=before[name];shape=obj.Shape
        same=before_brep[name]==shape.exportBrepToString()
        cleaned_same=before_cleaned[name]==shape.cleaned().exportBrepToString()
        delta=0.0 if same or cleaned_same else old.cut(shape).Volume+shape.cut(old).Volume
        assert shape.isValid() and delta<1e-5 and len(shape.Solids)==len(old.Solids),name
        assert obj.Label==labels[name]
        assert [o.Name for o in obj.InList]==(['Drive'] if name in drive_members else []),name
        if render:
            assert all(getattr(obj.ViewObject,p)==v for p,v in visual[name].items()),name
        rows.append({'name':name,'symmetric_difference_mm3':delta,'native_brep_matches':same,
                     'brep_without_display_mesh_matches':cleaned_same})
    assert not any(saved.getObject(n) for n in removed)
    actual=[]
    report=json.loads((root/'readback.json').read_text())
    source_rows=report.get('source_feature_objects',report['objects'])
    indexed={r['name']:r for r in source_rows}
    for obj in objects:
        if obj.Name in indexed:
            actual.append(indexed[obj.Name])
        else:
            b=obj.Shape.optimalBoundingBox(False)
            actual.append({'name':obj.Name,'label':obj.Label,'category':'merged_print_part','valid':True,
                           'solids':len(obj.Shape.Solids),'volume_mm3':obj.Shape.Volume,
                           'bbox_mm':[b.XMin,b.YMin,b.ZMin,b.XMax,b.YMax,b.ZMax]})
    current_hash=sha(cad)
    audit={'source_document':'source/CyberTrack-design.FCStd','source_sha256':source_hash,
           'delivery_document':'CyberTrack.FCStd','delivery_sha256':current_hash,
           'kept_group':'01 双履带与动力参考','drive_members':drive_members,
           'removed_groups':prior['removed_groups'] if prior else removed_groups,
           'removed_duplicate_inputs':prior['removed_duplicate_inputs'] if prior else sorted(consumed),
           'removed_check_spaces':sorted(spaces),
           'retained_hidden_envelope_count':sum(getattr(o,'Category','')=='envelope' and not o.ViewObject.Visibility for o in objects) if render else None,
           'root_part_count':len(objects)-len(drive_members),'part_count':len(objects),
           'geometry_scope':'Retained objects; removed only duplicate inputs and hidden nonphysical check spaces',
           'shape_checks':rows,'geometry_unchanged':True,'appearance_properties_unchanged':render,
           'saved_and_reopened':True,'passed':True}
    report['source_feature_objects']=source_rows
    report['objects']=actual
    report['check_source_document']='source/CyberTrack-design.FCStd'
    report['model_tree']={k:v for k,v in audit.items() if k!='shape_checks'}
    report['print_consolidation']['design_features_are_hidden_sources']=False
    report['print_consolidation']['design_features_in_separate_source']=True
    report['print_consolidation']['source_document']='source/CyberTrack-design.FCStd'
    report['files_sha256']['CyberTrack.FCStd']=current_hash
    report['files_sha256']['source/CyberTrack-design.FCStd']=source_hash
    report['final_saved_audit']['delivery_objects_verified']=len(objects)
    report['final_saved_audit']['model_tree_verified']=True
    # Existing geometric proofs continue to identify the byte-identical design
    # file. This audit is the explicit equivalence link to the flattened model.
    for path in root.glob('*audit.json'):
        data=json.loads(path.read_text())
        if data.get('source_sha256')==source_hash or data.get('source_after_sha256')==source_hash:
            data['source_document']='source/CyberTrack-design.FCStd'
            data['equivalent_delivery_audit']='model-tree-audit.json'
            path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    (root/'model-tree-audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n')
    (root/'readback.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    App.closeDocument(saved.Name)
    return audit
