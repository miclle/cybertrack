"""Compare PP04 process settings while retaining geometry, three walls and shell layers."""
import argparse
import concurrent.futures
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'hardware/model/print-parts/PP04-slicing'
OUT = BASE / 'speed-study'
SLICER = '/Applications/BambuStudio.app/Contents/MacOS/BambuStudio'
COMMON = dict(layer_height='0.28', wall_loops='3', top_shell_layers='5',
              bottom_shell_layers='4', sparse_infill_density='10%')
CUBIC = dict(COMMON, sparse_infill_pattern='cubic')
WIDE = dict(CUBIC, sparse_infill_line_width='0.6', internal_solid_infill_line_width='0.6')
VARIANTS = {
    '028-layers': COMMON,
    '028-cubic-wide-infill': WIDE,
    '028-arachne': dict(WIDE, wall_generator='arachne'),
    '028-support4': dict(WIDE, support_base_pattern_spacing='4'),
    '028-snug': dict(WIDE, support_style='snug', support_base_pattern_spacing='4'),
    '028-wide-walls': dict(WIDE, outer_wall_line_width='0.5', inner_wall_line_width='0.5',
                           support_base_pattern_spacing='4'),
}
VARIANTS.update({
    '024-snug': dict(VARIANTS['028-snug'], layer_height='0.24'),
    '024-snug-critical': dict(VARIANTS['028-snug'], layer_height='0.24', support_critical_regions_only='1'),
    '028-snug-critical': dict(VARIANTS['028-snug'], support_critical_regions_only='1'),
    '028-tree-hybrid': dict(WIDE, support_type='tree(auto)', support_style='tree_hybrid', support_base_pattern_spacing='4'),
    '024-tree-hybrid': dict(WIDE, layer_height='0.24', support_type='tree(auto)', support_style='tree_hybrid', support_base_pattern_spacing='4'),
    '024-snug-arachne': dict(VARIANTS['028-snug'], layer_height='0.24', wall_generator='arachne'),
})
VARIANTS.update({
    '024-snug5': dict(VARIANTS['024-snug'], support_base_pattern_spacing='5'),
    '024-snug-aligned': dict(VARIANTS['024-snug'], independent_support_layer_height='0'),
    '024-snug-standard-infill': dict(VARIANTS['024-snug'], sparse_infill_line_width='0.45', internal_solid_infill_line_width='0.42'),
    '024-snug5-supportwide': dict(VARIANTS['024-snug'], support_base_pattern_spacing='5', support_line_width='0.6'),
})
KEEP = ('[Content_Types].xml', '_rels/.rels', '3D/3dmodel.model',
        '3D/_rels/3dmodel.model.rels', '3D/Objects/object_1.model',
        'Metadata/model_settings.config')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(name):
    target = OUT / name
    target.mkdir(parents=True, exist_ok=True)
    project = target / 'input.3mf'
    with zipfile.ZipFile(BASE / 'PP04-P2S-PLA-0.24.3mf') as src:
        config = json.loads(src.read('Metadata/project_settings.config'))
        config.update(VARIANTS[name])
        config['print_settings_id'] = 'PP04 speed study ' + name
        with zipfile.ZipFile(project, 'w', zipfile.ZIP_DEFLATED) as dst:
            for filename in KEEP:
                dst.writestr(filename, src.read(filename))
            dst.writestr('Metadata/project_settings.config', json.dumps(config))
    with (target / 'run.log').open('w') as log:
        proc = subprocess.run([SLICER, '--orient', '0', '--arrange', '0', '--slice', '0',
            '--export-3mf', name + '.3mf', '--outputdir', str(target), str(project)],
            stdout=log, stderr=subprocess.STDOUT, timeout=300)
    assert proc.returncode == 0, (name, proc.returncode)
    result = json.loads((target / 'result.json').read_text())
    assert result['return_code'] == 0, result
    plate = result['sliced_plates'][0]
    row = dict(name=name, overrides=VARIANTS[name], seconds=plate['total_predication'],
        grams=sum(f['total_used_g'] for f in plate['filaments']),
        warning=plate['warning_message'], feature_times=plate['feature_type_times'],
        project=str((target / (name + '.3mf')).relative_to(BASE)),
        project_sha256=digest(target / (name + '.3mf')))
    print(json.dumps({k:row[k] for k in ('name','seconds','grams','warning')}), flush=True)
    return row


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('variants', nargs='*')
    args = parser.parse_args()
    if any(name not in VARIANTS for name in args.variants):
        parser.error('Unknown candidate')
    stl = BASE.parent / 'PP04-LowerTub.stl'
    baseline = json.loads((BASE / 'report.json').read_text())
    export = json.loads((BASE / 'export-check.json').read_text())
    assert digest(stl) == export['stl_sha256'], 'STL changed; review baseline first'
    assert digest(BASE / 'PP04-P2S-PLA-0.24.3mf') == baseline['project_sha256']
    OUT.mkdir(exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        rows = list(pool.map(run, args.variants or list(VARIANTS)))
    previous = OUT / 'report.json'
    old = json.loads(previous.read_text()) if previous.exists() else {}
    if old:
        assert old['input_stl_sha256'] == digest(stl)
    merged = {row['name']: row for row in old.get('candidates', [])}
    merged.update({row['name']: row for row in rows})
    report = dict(input_stl_sha256=digest(stl), baseline=baseline,
        invariants='Exact embedded geometry and orientation; three walls, five top and four bottom layers; 10 percent infill; same Generic PLA 12 mm3/s cap and machine G-code',
        candidates=list(merged.values()), print_sent=False, physical_strength_verified=False)
    previous.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
