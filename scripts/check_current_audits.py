#!/usr/bin/env python3
"""Recheck current L298N exports and schematic evidence without rewriting history."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import struct
import subprocess
from zoneinfo import ZoneInfo

from check_schematic_netlist import check as check_netlist

ROOT = Path(__file__).resolve().parents[1]
L298N = ROOT / 'hardware/model/l298n-compact'
SCHEMATIC = ROOT / 'hardware/schematic'
HISTORY = '9ab523c6c9aa3792cc21fb1710eae2b5ecd2258f'
A1 = '84c5f708d96ea7a6a3e3a6ce9b84647be7551886'
A1_RECHECK = '8206f328e6a72a31123cd3fdc8037c8d8b9320f4'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def historical_bytes(revision, path):
    return subprocess.check_output(
        ['git', 'show', f'{revision}:{path.relative_to(ROOT).as_posix()}'], cwd=ROOT)


def preserved_report(path):
    assert path.read_bytes() == historical_bytes(HISTORY, path), f'Historical report changed: {path}'
    return json.loads(path.read_text())


def check_parts(date):
    original = L298N / 'parts-readback.json'
    old = preserved_report(original)
    export = L298N / 'slicing/export-check.json'
    newer = {r['stem']: r for r in preserved_report(export)['parts']}
    rows = []
    for row in old:
        stem = row['stem']
        stl, step = [L298N / f'{stem}.{ext}' for ext in ('stl', 'step')]
        digest = sha(stl)
        expected = newer[stem]['sha256'] if stem in newer else row['files_sha256'][stl.name]
        assert digest == expected, stl
        assert sha(step) == row['files_sha256'][step.name], step
        data = stl.read_bytes()
        facets = struct.unpack_from('<I', data, 80)[0]
        assert len(data) == 84 + 50 * facets and facets == row['stl_facets'], stl
        vertices = []
        for offset in range(84, len(data), 50):
            values = struct.unpack_from('<12fH', data, offset)
            vertices.extend(values[start:start + 3] for start in (3, 6, 9))
        size = [max(v[i] for v in vertices) - min(v[i] for v in vertices) for i in range(3)]
        assert all(abs(a - b) < 0.0001 for a, b in zip(size, row['size_xyz_mm'])), stem
        rows.append({'stem': stem, 'stl_sha256': digest, 'step_sha256': sha(step),
                     'stl_facets': facets, 'size_xyz_mm': size,
                     'matches_original_stl_hash': digest == row['files_sha256'][stl.name],
                     'current_stl_evidence': 'slicing/export-check.json' if stem in newer else 'parts-readback.json',
                     'step_matches_original_hash': True})
    return {'date': date, 'passed': True,
            'scope': 'File identity, binary STL facet count and bounding size; not a new CAD readback',
            'historical_report_revision': HISTORY,
            'historical_reports_sha256': {'parts-readback.json': sha(original),
                                         'slicing/export-check.json': sha(export)},
            'historical_reports_byte_preserved': True, 'parts': rows,
            'cad_boolean_rechecked': False, 'mesh_closedness_rechecked': False,
            'physical_fit_verified': False, 'manufacturing_released': False}


def check_schematic(date):
    original = SCHEMATIC / 'verification.json'
    old = preserved_report(original)
    package = SCHEMATIC / 'CyberTrack-schematic-A1.zip'
    assert package.read_bytes() == historical_bytes(A1_RECHECK, package), 'A1 package changed'
    recheck = SCHEMATIC / 'checks/A1-source-recheck-20261030.json'
    assert recheck.read_bytes() == historical_bytes(A1_RECHECK, SCHEMATIC / 'verification-current.json'), 'A1 recheck changed'
    outputs, sources = {}, {}
    for name, expected in old['sha256'].items():
        path = SCHEMATIC / name
        assert hashlib.sha256(historical_bytes(A1, path)).hexdigest() == expected, name
        actual = sha(path)
        outputs[name] = {'sha256': actual, 'matches_A1': actual == expected}
    for name, expected in old['source_evidence_sha256'].items():
        path = ROOT / name
        assert hashlib.sha256(historical_bytes(A1, path)).hexdigest() == expected, name
        actual = sha(path)
        sources[name] = {'sha256': actual, 'matches_A1': actual == expected}
    connectivity = check_netlist(SCHEMATIC / 'checks/CyberTrack.net.xml')
    assert connectivity['passed'] and len(connectivity['checks']) == 112
    export_path = SCHEMATIC / 'checks/A2-export-check.json'
    export = json.loads(export_path.read_text())
    assert export['revision'] == 'A2' and export['passed']
    for name, expected in export['files_sha256'].items():
        assert sha(ROOT / name) == expected, name
    erc = json.loads((SCHEMATIC / 'checks/erc.json').read_text())
    assert len(erc['sheets']) == 6 and not any(s['violations'] for s in erc['sheets'])
    assert erc['ignored_checks'] == old['erc']['default_ignored_checks']
    assert export['pdf_review']['pages'] == 6 and export['pdf_review']['passed']
    outputs['ultrasonic.kicad_sch'] = {'sha256': sha(SCHEMATIC / 'ultrasonic.kicad_sch'), 'matches_A1': False}
    return {'date': date, 'passed': True,
            'revision': 'A2',
            'scope': 'A2 regenerated six-sheet schematic, ERC, PDF and current source assignments',
            'historical_A1_revision': A1, 'historical_report_sha256': sha(original),
            'historical_report_byte_preserved': True,
            'historical_package_sha256': sha(package),
            'historical_source_recheck_sha256': sha(recheck),
            'historical_package_and_source_recheck_byte_preserved': True,
            'historical_source_and_output_hashes_verified_at_A1_revision': True,
            'current_outputs': outputs, 'current_sources': sources,
            'additional_source_hashes': {
                'firmware/esp32-audio/apply_overlay.py': sha(ROOT / 'firmware/esp32-audio/apply_overlay.py'),
                'firmware/esp32-audio/ultrasonic.cc': sha(ROOT / 'firmware/esp32-audio/ultrasonic.cc')},
            'connectivity': connectivity,
            'export_check_sha256': sha(export_path),
            'erc_rerun': True, 'erc_violations': 0, 'pdf_render_review_rerun': True,
            'netlist_reexported': True, 'physical_test_performed': False,
            'manufacturing_ready': False,
            'limits': 'A1 package and original audit are retained. A2 adds controller 3V3/GND and GPIO1/GPIO2 ultrasonic wiring; all A1 terminal connectivity is preserved. New header positions, module electrical levels, 3V3 current margin and physical acceptance remain unverified.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true', help='Regenerate separate current reports')
    parser.add_argument('--date', help='Report date when writing, YYYY-MM-DD')
    args = parser.parse_args()
    if args.date and not args.write:
        parser.error('--date requires --write')
    reports = [(L298N / 'parts-current-check.json', check_parts),
               (SCHEMATIC / 'verification-current.json', check_schematic)]
    # Validate both scopes before writing either report.
    results = []
    for path, check in reports:
        previous = json.loads(path.read_text()) if path.exists() else None
        if args.write:
            date = args.date or datetime.now(ZoneInfo('Asia/Shanghai')).date().isoformat()
        else:
            date = previous['date'] if previous else None
        assert date, f'Missing report: run with --write first: {path}'
        result = check(date)
        if not args.write:
            assert result == previous, f'Current report drift: {path}'
        results.append((path, result))
    for path, result in results:
        if args.write:
            path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
        print(f'PASS: {path.relative_to(ROOT)}')


if __name__ == '__main__':
    main()
