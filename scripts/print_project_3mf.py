"""Shared 3MF archive, metadata and mesh helpers for print project updates."""
import hashlib
import struct
import xml.etree.ElementTree as E
import zipfile

NS = 'http://schemas.microsoft.com/3dmanufacturing/core/2015/02'
PN = 'http://schemas.microsoft.com/3dmanufacturing/production/2015/06'
E.register_namespace('', NS); E.register_namespace('p', PN)
tag = lambda n: '{'+NS+'}'+n
xml = lambda n: E.tostring(n, encoding='utf-8', xml_declaration=True)
meta = lambda n: {m.get('key'): m.get('value') for m in n.findall('metadata')}
sha = lambda b: hashlib.sha256(b).hexdigest()


def archive_write(path, files):
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, value in files.items(): z.writestr(name, value)


def setmeta(node, key, value):
    m = node.find("metadata[@key='%s']" % key)
    if m is None: m = E.SubElement(node, 'metadata', key=key)
    m.set('value', str(value))


def relxml(node):
    # Bambu's relationship parser expects an unprefixed default namespace.
    root = E.Element('Relationships', xmlns='http://schemas.openxmlformats.org/package/2006/relationships')
    for child in node: E.SubElement(root, 'Relationship', child.attrib)
    return xml(root)


def raw_mesh(path):
    data = path.read_bytes(); count = struct.unpack_from('<I', data, 80)[0]
    vertices, faces, ids = [], [], {}
    for i in range(count):
        coords = struct.unpack_from('<12fH', data, 84+50*i)[3:12]; face = []
        for j in (0, 3, 6):
            v = tuple(coords[j:j+3])
            if v not in ids: ids[v] = len(vertices); vertices.append(v)
            face.append(ids[v])
        faces.append(face)
    mesh = E.Element(tag('mesh')); vs = E.SubElement(mesh, tag('vertices')); ts = E.SubElement(mesh, tag('triangles'))
    for v in vertices: E.SubElement(vs, tag('vertex'), dict(zip(('x','y','z'), map(str, v))))
    for t in faces: E.SubElement(ts, tag('triangle'), dict(zip(('v1','v2','v3'), map(str, t))))
    return mesh, count
