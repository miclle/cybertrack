"""Restore the two-bottle liquid layout in staged copies of the v2 assembly.

Run in FreeCAD Python with the scratch directory as the argument. Place the
368d5d8 delivery and design-source FCStd files under baseline/ in that directory
as two-bottles.FCStd and two-bottles-design.FCStd.
"""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

import FreeCAD as App
import Part

from cad_gui_state import capture, restore
from check_water_bottle_service import review
from update_backpack import BOTTLE, SPACES

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "hardware/model"
HOSES = ("WaterHoseRoute", "BubbleGunHoseRoute")
RETIRED = ("IgnitionMOS", "IgnitionRoute", "FrontEffect", "BackpackArc", "ArcBottomPad", "CrownEffect")


def set_visuals(current_state, bottle_state):
    providers, assets = current_state
    old_providers, old_assets = bottle_state
    views = providers.find("ViewProviderData")
    for name in BOTTLE:
        provider = deepcopy(old_providers.find(f"./ViewProviderData/ViewProvider[@name='{name}']"))
        provider.set("treeRank", "-1")
        for node in provider.iter():
            asset = node.get("file")
            if asset:
                new_key = f"Liquid-{name}-{asset}"
                assets[new_key] = old_assets[asset]
                node.set("file", new_key)
        views.append(provider)
    for name in HOSES:
        node = views.find(f"./ViewProvider[@name='{name}']/Properties/Property[@name='Visibility']/Bool")
        node.set("value", "true")


def restore_doc(path, baseline, out, bottle_state, design_source):
    state = capture(path)
    saved = App.openDocument(str(path))
    old = App.openDocument(str(baseline))
    names = [*BOTTLE, *SPACES] if design_source else BOTTLE
    for name in names:
        original = old.getObject(name)
        assert original and not saved.getObject(name), name
        restored = saved.copyObject(original, False)
        assert restored.Name == name and restored.Shape.isValid(), name
        for group in original.InList:
            if group.isDerivedFrom("App::DocumentObjectGroup"):
                saved.getObject(group.Name).addObject(restored)
    for name in HOSES:
        hose = saved.getObject(name).Shape
        original = old.getObject(name).Shape
        assert hose.isValid() and len(hose.Solids) == 1
        assert hose.cut(original).Volume + original.cut(hose).Volume < .01, name
    saved.PrintBackpack.Label = "PP03 背包及双瓶护舱"
    saved.PrintBackpack.EvidenceBasis = "v2 双瓶供液，护舱沿用无侧桶的现行几何。"
    if design_source:
        saved.BackpackShell.Label = "背包 · 开放式双瓶护舱"
        saved.BackpackShell.EvidenceBasis = saved.PrintBackpack.EvidenceBasis
    saved.recompute()
    dest = out / path.name
    saved.saveAs(str(dest))
    App.closeDocument(saved.Name)
    App.closeDocument(old.Name)
    set_visuals(state, bottle_state)
    restore(dest, state)
    reopened = App.openDocument(str(dest))
    assert all(reopened.getObject(name).Shape.isValid() for name in names)
    assert not any(obj.Name.startswith(RETIRED) for obj in reopened.Objects)
    report = {"added": names, "both_supply_routes_visible": True,
              "sha256": hashlib.sha256(dest.read_bytes()).hexdigest()}
    return reopened, report


def main(out):
    baseline_dir = out / "baseline"
    bottle_state = capture(baseline_dir / "two-bottles.FCStd")
    source, source_report = restore_doc(MODEL / "source/CyberTrack-design.FCStd",
                                       baseline_dir / "two-bottles-design.FCStd", out, bottle_state, True)
    delivery, delivery_report = restore_doc(MODEL / "CyberTrack.FCStd",
                                           baseline_dir / "two-bottles.FCStd", out, bottle_state, False)

    services = {name: review(delivery, name) for name in ("Water", "Bubble")}
    assert all(report["pass"] for report in services.values()), services
    bottle_fits = {}
    for name in ("Water", "Bubble"):
        pod = delivery.getObject(name + "Pod").Shape
        tub = delivery.PrintLowerTub.Shape
        bottle = delivery.getObject(name + "Module").Shape
        support = delivery.getObject(name + "BottomPad").Shape
        assert pod.distToShape(tub)[0] < 1e-5
        assert bottle.distToShape(support)[0] < 1e-5
        assert pod.common(tub).Volume < .01 and pod.common(bottle).Volume < .01
        bottle_fits[name] = {"pod_contacts_tub": True, "bottle_contacts_pad": True}
    assert delivery.WaterHoseRoute.Shape.common(delivery.BubbleGunHoseRoute.Shape).Volume < .01
    assembly = [obj for obj in delivery.Objects
                if hasattr(obj, "Shape") and not obj.isDerivedFrom("App::DocumentObjectGroup")
                and (obj.Name in (*HOSES, "WaterModule", "BubbleModule")
                         or getattr(obj, "Category", "") not in ("clearance", "envelope"))]
    exchange = out / "CyberTrack.step"
    Part.export(assembly, str(exchange))
    (out / "liquid-supply-readback.json").write_text(json.dumps({
        "source": source_report, "delivery": delivery_report,
        "supply_route_solids": HOSES, "bottle_support": bottle_fits,
        "bottle_service": services, "step_sha256": hashlib.sha256(exchange.read_bytes()).hexdigest(),
        "physical_fit_verified": False,
    }, ensure_ascii=False, indent=2) + "\n")
    App.closeDocument(delivery.Name)
    App.closeDocument(source.Name)


if __name__ == "__main__":
    main(Path(sys.argv[1]).resolve())
