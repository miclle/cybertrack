"""Tessellate one saved FreeCAD assembly as a compressed glTF file for the docs."""

import argparse
from array import array
from collections import defaultdict
import gzip
import hashlib
import json
import math
from pathlib import Path
import struct
import sys
import tempfile
import xml.etree.ElementTree as ET
from zipfile import ZipFile


MAC_LIB = Path("/Applications/FreeCAD.app/Contents/Resources/lib")
if sys.platform == "darwin" and MAC_LIB.is_dir():
    sys.path.append(str(MAC_LIB))

import FreeCAD as App

from cad_gui_state import read_material_list


def saved_styles(source):
    """Read face colors and visibility from the saved GUI state without a GUI."""
    styles = {}
    with ZipFile(source) as archive:
        gui = ET.fromstring(archive.read("GuiDocument.xml"))
        for view in gui.iter("ViewProvider"):
            props = view.find("Properties")
            visible = props.find("Property[@name='Visibility']/Bool")
            material = props.find("Property[@name='ShapeAppearance']/MaterialList")
            colors = [0xAAB5BDFF]
            if material is not None and material.get("file"):
                data = archive.read(material.get("file"))
                if material.get("version") != "3":
                    raise ValueError(f"Unsupported saved material on {view.get('name')}")
                records = read_material_list(data)
                if records:
                    colors = [struct.unpack_from("<I", numeric, 4)[0] for numeric, _ in records]
            transparency = props.find("Property[@name='Transparency']/Integer")
            if transparency is not None:
                opacity = 1 - int(transparency.get("value")) / 100
                colors = [(color & 0xFFFFFF00) | round((color & 255) * opacity) for color in colors]
            rank = int(view.get("treeRank", "-1"))
            styles[view.get("name")] = (
                visible is None or visible.get("value") == "true", colors,
                rank if rank >= 0 else math.inf,
            )
    return styles


def linear_color(value):
    srgb = value / 255
    return srgb / 12.92 if srgb <= 0.04045 else ((srgb + 0.055) / 1.055) ** 2.4


class Model:
    def __init__(self, source):
        self.data = bytearray()
        self.colors = {}
        self.gltf = {
            "asset": {"version": "2.0", "generator": "CyberTrack FreeCAD export", "extras": {
                "sourceSha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                "exporterSha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "materialReaderSha256": hashlib.sha256(Path(__file__).with_name("cad_gui_state.py").read_bytes()).hexdigest(),
            }},
            "scene": 0, "scenes": [{"nodes": [0]}],
            "nodes": [{
                "name": source.stem,
                # FreeCAD is Z-up in mm. glTF is Y-up in metres.
                "rotation": [-math.sqrt(0.5), 0, 0, math.sqrt(0.5)],
                "scale": [0.001] * 3,
            }],
            "meshes": [], "materials": [], "bufferViews": [], "accessors": [],
        }

    def add(self, collection, item):
        items = self.gltf[collection]
        items.append(item)
        return len(items) - 1

    def accessor(self, values, array_type, component_type, kind, count, **limits):
        buf = array(array_type, values)
        if sys.byteorder == "big":
            buf.byteswap()
        self.data.extend(bytes(-len(self.data) % 4))
        view = self.add("bufferViews", {
            "buffer": 0, "byteOffset": len(self.data), "byteLength": len(buf) * buf.itemsize,
        })
        self.data.extend(buf.tobytes())
        return self.add("accessors", {
            "bufferView": view, "componentType": component_type, "type": kind,
            "count": count, **limits,
        })

    def material(self, rgba):
        if rgba not in self.colors:
            self.colors[rgba] = self.add("materials", {
                "doubleSided": True,
                "alphaMode": "BLEND" if (rgba & 255) < 255 else "OPAQUE",
                "pbrMetallicRoughness": {
                    "baseColorFactor": [linear_color(rgba >> shift & 255) for shift in (24, 16, 8)]
                    + [(rgba & 255) / 255],
                    "metallicFactor": 0.04,
                    "roughnessFactor": 0.7,
                },
            })
        return self.colors[rgba]

    def mesh(self, shape, colors, name):
        faces = shape.Faces
        if len(colors) not in (1, len(faces)):
            raise ValueError(f"{name}: {len(colors)} materials for {len(faces)} faces")
        by_color = defaultdict(lambda: ([], []))
        for i, face in enumerate(faces):
            # Keep CAD face boundaries unwelded so the viewer shades bevels and edges separately.
            points, triangles = face.tessellate(0.18)
            positions, indices = by_color[colors[0] if len(colors) == 1 else colors[i]]
            offset = len(positions)
            positions.extend(tuple(round(coord, 4) for coord in point) for point in points)
            indices.extend(offset + index for tri in triangles for index in tri)
        primitives = []
        for color, (positions, indices) in by_color.items():
            if not indices:
                continue
            axes = list(zip(*positions))
            position = self.accessor(
                (value for point in positions for value in point), "f", 5126, "VEC3", len(positions),
                min=[min(axis) for axis in axes], max=[max(axis) for axis in axes],
            )
            small = len(positions) <= 65536
            index = self.accessor(
                indices, "H" if small else "I", 5123 if small else 5125, "SCALAR", len(indices),
            )
            primitives.append({
                "attributes": {"POSITION": position}, "indices": index,
                "material": self.material(color),
            })
        if not primitives:
            raise ValueError(f"{name}: no triangles to export")
        return self.add("meshes", {"primitives": primitives})

    def read_assembly(self, source):
        styles = saved_styles(source)
        doc = App.openDocument(str(source))
        default_style = (True, [0xAAB5BDFF], math.inf)

        def tree_order(objects):
            return sorted(objects, key=lambda obj: styles.get(obj.Name, default_style)[2])

        def visit(obj, parent):
            visible, colors, _ = styles.get(obj.Name, default_style)
            node = {"name": obj.Name, "extras": {"label": obj.Label, "visible": visible}}
            if obj.TypeId == "App::Part":
                pose = obj.Placement
                node.update(translation=list(pose.Base), rotation=list(pose.Rotation.Q))
            elif obj.TypeId != "App::DocumentObjectGroup":
                if not obj.isDerivedFrom("Part::Feature") or obj.Shape.isNull():
                    return
                shape = obj.Shape.copy()
                pose = shape.Placement
                shape.Placement = App.Placement()
                node.update(
                    mesh=self.mesh(shape, colors, obj.Name),
                    translation=list(pose.Base), rotation=list(pose.Rotation.Q),
                    extras={**node["extras"], "part": True},
                )
            index = self.add("nodes", node)
            self.gltf["nodes"][parent].setdefault("children", []).append(index)
            if "mesh" not in node:
                for child in tree_order(obj.Group):
                    visit(child, index)

        try:
            for obj in tree_order(doc.RootObjects):
                visit(obj, 0)
        finally:
            App.closeDocument(doc.Name)
        if not self.gltf["meshes"]:
            raise ValueError(f"{source.name}: no parts to export")

    def save(self, target):
        self.data.extend(bytes(-len(self.data) % 4))
        self.gltf["buffers"] = [{"byteLength": len(self.data)}]
        header = json.dumps(self.gltf, ensure_ascii=False, separators=(",", ":")).encode()
        header += b" " * (-len(header) % 4)
        length = 28 + len(header) + len(self.data)

        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as temporary:
            temp_path = Path(temporary.name)
            try:
                with gzip.GzipFile(filename="", fileobj=temporary, mode="wb", mtime=0) as stream:
                    stream.write(struct.pack("<4sIIII", b"glTF", 2, length, len(header), 0x4E4F534A))
                    stream.write(header)
                    stream.write(struct.pack("<II", len(self.data), 0x004E4942))
                    stream.write(self.data)
                temporary.close()
                temp_path.replace(target)
            finally:
                temp_path.unlink(missing_ok=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("target", type=Path)
    args = parser.parse_args()
    model = Model(args.source)
    model.read_assembly(args.source)
    model.save(args.target)
    print(f"{args.source.name}: {len(model.gltf['meshes'])} parts → {args.target}", flush=True)
