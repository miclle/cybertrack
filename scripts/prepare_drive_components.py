"""Curate only drive components from a local, non-publishable reference document."""
import argparse
import hashlib
import json
from pathlib import Path
import FreeCAD as App

TRACK_SUFFIXES = ('RubberBand', 'TreadPads', 'ChevronTreads', 'ShoulderLugs',
                  'WheelTires', 'WheelRims', 'WheelFaces', 'WheelHubs',
                  'SuspensionArms', 'RockerPlates', 'Fasteners')
ALLOWED = [f'Track{side}{suffix}' for side in ('Left', 'Right') for suffix in TRACK_SUFFIXES]
ALLOWED += [f'{prefix}{side}' for side in ('L', 'R')
            for prefix in ('Motor', 'MotorShaft', 'DriveCoupler', 'TrackMount')]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output = args.output_dir / 'DriveLayout.FCStd'
    if output.exists():
        raise SystemExit('Refusing to overwrite a curated component asset.')
    before = digest(args.input)
    src = App.openDocument(str(args.input.resolve()))
    dst = App.newDocument('DriveLayout')
    dst.Label = '双履带动力布局参考'
    dst.Comment = 'Drive geometry only. No chassis, covers, or inherited assembly links.'
    expected = {}
    for name in ALLOWED:
        source = src.getObject(name)
        if source is None or source.Shape.isNull() or not source.Shape.isValid():
            raise ValueError(name)
        obj = dst.addObject('Part::Feature', name)
        obj.Label = source.Label.replace('实测支架', '安装件参考')
        obj.Shape = source.Shape.copy()
        expected[name] = obj.Shape.copy()
    dst.recompute()
    dst.saveAs(str(output.resolve()))
    App.closeDocument(dst.Name)
    saved = App.openDocument(str(output.resolve()))
    rows = []
    for obj in saved.Objects:
        original = expected[obj.Name]
        matches = obj.Shape.exportBrepToString() == original.exportBrepToString()
        difference = 0.0 if matches else original.cut(obj.Shape).Volume + obj.Shape.cut(original).Volume
        if difference > 1e-5 or not obj.Shape.isValid():
            raise ValueError(f'Native readback failed: {obj.Name}')
        rows.append({'name': obj.Name, 'native_brep_matches': matches,
                     'symmetric_difference_mm3': difference, 'solids': len(obj.Shape.Solids)})
    assert len(rows) == 30
    assert digest(args.input) == before
    report = {'source_sha256': before, 'source_unchanged': True,
              'output_sha256': digest(output), 'objects': rows,
              'excluded': ['ReferenceChassis', 'ReferenceServiceCover', 'TrackMountScrew*'],
              'transform': 'identity; X left, Y rear, Z up; mm',
              'physical_fit_verified': False, 'manufacturing_released': False}
    (args.output_dir / 'readback.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(f'Curated and verified {len(rows)} objects')


if __name__ == '__main__':
    main()
