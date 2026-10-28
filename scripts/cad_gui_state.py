"""Retain FreeCAD view providers and their assets across headless saves."""
import copy
from pathlib import Path
import xml.etree.ElementTree as E
import zipfile


def capture(path):
    with zipfile.ZipFile(path) as z:
        if 'GuiDocument.xml' not in z.namelist():return None
        root=E.fromstring(z.read('GuiDocument.xml'))
        assets={n.get('file') for n in root.iter() if n.get('file')}
        return root,{n:z.read(n) for n in assets}


def restore(path, snapshot):
    """Copy surviving views; keep extra source features hidden and groups open.

    Geometry, object properties and every pre-existing archive entry stay intact.
    A delivery snapshot may initialize a source document missing all GUI state.
    """
    assert snapshot is not None,'A GUI snapshot is required before saving CAD'
    root=copy.deepcopy(snapshot[0]);assets=snapshot[1]
    with zipfile.ZipFile(path) as z:files={n:z.read(n) for n in z.namelist()}
    document=E.fromstring(files['Document.xml'])
    objects={o.get('name'):o.get('type') for o in document.findall('./Objects/Object')}
    providers=root.find('ViewProviderData')
    lookup={v.get('name'):v for v in providers}
    shape_template=lookup['PrintBackpack'];group_template=lookup['Drive']
    for v in list(providers):
        if v.get('name') not in objects:providers.remove(v)
    for name,kind in objects.items():
        if name in lookup:continue
        is_group='DocumentObjectGroup' in kind
        v=copy.deepcopy(group_template if is_group else shape_template)
        v.set('name',name);v.set('treeRank','-1');v.set('expanded','0')
        v.find("./Properties/Property[@name='Visibility']/Bool").set('value','true' if is_group else 'false')
        providers.append(v)
    providers.set('Count',str(len(providers)))
    files['GuiDocument.xml']=E.tostring(root,encoding='utf-8',xml_declaration=True)
    for node in root.iter():
        name=node.get('file')
        if name:files[name]=assets[name]
    path=Path(path);temporary=path.with_suffix('.gui-tmp')
    with zipfile.ZipFile(temporary,'w',zipfile.ZIP_DEFLATED) as z:
        for n,b in files.items():z.writestr(n,b)
    with zipfile.ZipFile(temporary) as z:
        assert z.read('Document.xml')==files['Document.xml']
        assert all(z.read(n)==b for n,b in files.items())
    temporary.replace(path)
    views=list(providers)
    return {'view_providers':len(views),'visible':sum(v.find("./Properties/Property[@name='Visibility']/Bool").get('value')=='true' for v in views)}
