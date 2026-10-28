"""Patch current 3MFs in place, retaining user layout/settings and unrelated meshes.

Invalidates only affected plate caches. Does not slice or claim print readiness.
"""
import json
from pathlib import Path
import re
import xml.etree.ElementTree as E
import zipfile
from prepare_lean_print import NS, PN, tag, xml, meta, raw_mesh, archive_write, sha

ROOT=Path(__file__).resolve().parents[1]
MODEL=ROOT/'hardware/model'
REMOVED={'BubblePod','BubbleLidMark'}
E.register_namespace('',NS);E.register_namespace('p',PN)


def update(path):
    before=path.read_bytes()
    with zipfile.ZipFile(path) as z:files={n:z.read(n) for n in z.namelist()}
    original=dict(files)
    root=E.fromstring(files['3D/3dmodel.model'])
    settings=E.fromstring(files['Metadata/model_settings.config'])
    resources,build=root.find(tag('resources')),root.find(tag('build'))
    ids=set();removed=[];changed=[]
    for obj in list(settings.findall('object')):
        name=meta(obj)['name'];oid=obj.get('id')
        if name not in REMOVED and name!='PP03-base':continue
        parent=resources.find("%s[@id='%s']"%(tag('object'),oid));ids.add(oid)
        if name in REMOVED:
            removed.append(name);settings.remove(obj);resources.remove(parent)
            for item in list(build):
                if item.get('objectid')==oid:build.remove(item)
            assembly=settings.find('assemble')
            if assembly is not None:
                for item in list(assembly):
                    if item.get('object_id')==oid:assembly.remove(item)
            for component in parent.find(tag('components')):
                child_path=component.get('{'+PN+'}path').lstrip('/')
                # An unreferenced mesh is also excluded from the saved print archive.
                assert not any(c.get('{'+PN+'}path','').lstrip('/')==child_path for c in resources.iter(tag('component')))
                files.pop(child_path,None)
        else:
            component=parent.find(tag('components'))[0]
            child_path=component.get('{'+PN+'}path').lstrip('/')
            child=E.fromstring(files[child_path])
            child_obj=child.find(tag('resources')).find("%s[@id='%s']"%(tag('object'),component.get('objectid')))
            mesh,count=raw_mesh(MODEL/'remaining-print/PP03-base.stl')
            old_mesh=child_obj.find(tag('mesh'))
            # Bambu may recenter imported vertices around local Z=0 while
            # retaining bed placement in the instance transform. Preserve it.
            def centre(m):
                vertices=list(m.find(tag('vertices')))
                return [(min(float(v.get(k)) for v in vertices)+max(float(v.get(k)) for v in vertices))/2 for k in ('x','y','z')]
            delta=[a-b for a,b in zip(centre(old_mesh),centre(mesh))]
            for v in mesh.find(tag('vertices')):
                for k,offset in zip(('x','y','z'),delta):v.set(k,str(float(v.get(k))+offset))
            child_obj.remove(old_mesh);child_obj.append(mesh)
            files[child_path]=xml(child)
            obj.find('metadata[@face_count]').set('face_count',str(count))
            obj.find('part/mesh_stat').set('face_count',str(count));changed.append(name)
    assert changed==['PP03-base']
    plates=[]
    for index,plate in enumerate(settings.findall('plate'),1):
        instances=plate.findall('model_instance')
        if not any(meta(i)['object_id'] in ids for i in instances):continue
        plates.append(index)
        existing={o.get('id') for o in settings.findall('object')}
        for i in instances:
            if meta(i)['object_id'] not in existing:plate.remove(i)
        for m in list(plate.findall('metadata')):
            if m.get('key') in ('gcode_file','thumbnail_file','thumbnail_no_light_file','top_file','pick_file'):
                files.pop(m.get('value'),None);plate.remove(m)
        for n in list(files):
            if re.search(r'/(?:plate_(?:no_light_)?|top_|pick_)'+str(index)+r'\.',n):files.pop(n)
    if 'Metadata/slice_info.config' in files:
        info=E.fromstring(files['Metadata/slice_info.config'])
        for plate in list(info.findall('plate')):
            if int(meta(plate)['index']) in plates:info.remove(plate)
        files['Metadata/slice_info.config']=xml(info)
    # Package-level stale previews and relationships must not point at removed data.
    for n in list(files):
        if n.startswith('Metadata/') and ('thumbnail' in n or n.startswith('Metadata/plate_0')):files.pop(n)
    for n in list(files):
        if n.endswith('.rels'):
            rel=E.fromstring(files[n]);edited=False
            for node in list(rel):
                target=node.get('Target','').lstrip('/')
                if target in original and target not in files:rel.remove(node);edited=True
            if edited:
                namespace='http://schemas.openxmlformats.org/package/2006/relationships'
                clean=E.Element('Relationships',xmlns=namespace)
                for node in rel:E.SubElement(clean,'Relationship',node.attrib)
                files[n]=xml(clean)
    files['3D/3dmodel.model']=xml(root)
    files['Metadata/model_settings.config']=xml(settings)
    names=[meta(o)['name'] for o in settings.findall('object')]
    assert not REMOVED.intersection(names)
    unchanged=[n for n in original if n in files and original[n]==files[n]]
    # Unrelated source meshes and all project process settings remain byte-for-byte.
    touched=[n for n in original if n not in files or original[n]!=files[n]]
    assert original['Metadata/project_settings.config']==files['Metadata/project_settings.config']
    archive_write(path,files)
    with zipfile.ZipFile(path) as z:
        assert set(z.namelist())==set(files)
        assert all(z.read(n)==files[n] for n in files)
    return {'path':str(path.relative_to(ROOT)),'before_sha256':sha(before),'sha256':sha(path.read_bytes()),
            'removed':removed,'updated':changed,'part_names':names,'print_parts':len(names),
            'requires_reslice_plates':plates,'unchanged_archive_entries':len(unchanged),'changed_or_removed_entries':touched,
            'process_settings_unchanged':True,'mesh_local_translation_mm':delta,'sliced':False}


def main():
    previous=MODEL/'backpack-print-update.json'
    retired=json.loads(previous.read_text())['retired_exports'] if previous.exists() else []
    report={'date':'2026-10-27','projects':[],'retired_exports':retired,'sliced':False}
    for relative in ('lean-print/CyberTrack-Lean-6plates.3mf','print-ready/CyberTrack-Ready-6plates.3mf'):
        report['projects'].append(update(MODEL/relative))
    # Retire obsolete loose exports; historical baseline archives remain intact.
    for name in sorted(REMOVED):
        for ext in ('brep','step','stl'):
            p=MODEL/'completion-print'/(name+'.'+ext)
            if p.exists():
                report['retired_exports'].append({'path':str(p.relative_to(ROOT)),'sha256':sha(p.read_bytes())})
                p.unlink()
    (MODEL/'backpack-print-update.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
