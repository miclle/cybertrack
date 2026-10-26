"""Slice PP07 speed candidates from its verified P2S project, without changing CAD."""
import concurrent.futures
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'hardware/model/print-parts/PP07-slicing'
OUT = BASE / 'speed-study'
SLICER = '/Applications/BambuStudio.app/Contents/MacOS/BambuStudio'
VARIANTS = {
    '024-3walls': dict(layer_height='0.24', wall_loops='3', sparse_infill_density='10%',
                       top_shell_layers='5', bottom_shell_layers='4'),
    '028-4walls': dict(layer_height='0.28', wall_loops='4', sparse_infill_density='15%',
                       top_shell_layers='4', bottom_shell_layers='3'),
    '028-3walls': dict(layer_height='0.28', wall_loops='3', sparse_infill_density='10%',
                       top_shell_layers='4', bottom_shell_layers='3'),
    '028-3walls-normal': dict(layer_height='0.28', wall_loops='3', sparse_infill_density='8%',
                       sparse_infill_pattern='cubic', top_shell_layers='3', top_shell_thickness='0.84',
                       bottom_shell_layers='3', support_type='normal(auto)'),
    '028-2walls-normal': dict(layer_height='0.28', wall_loops='2', sparse_infill_density='8%',
                       sparse_infill_pattern='cubic', top_shell_layers='3', top_shell_thickness='0.84',
                       bottom_shell_layers='3', support_type='normal(auto)'),
    '028-3walls-tree1': dict(layer_height='0.28', wall_loops='3', sparse_infill_density='8%',
                       sparse_infill_pattern='cubic', top_shell_layers='3', top_shell_thickness='0.84',
                       bottom_shell_layers='3', tree_support_wall_count='1'),
}
VARIANTS['basic-020-4walls'] = dict(filament_profile='Bambu PLA Basic @BBL P2S')
VARIANTS['basic-028-3walls'] = dict(VARIANTS['028-3walls-tree1'], filament_profile='Bambu PLA Basic @BBL P2S')
VARIANTS['basic-028-2walls'] = dict(VARIANTS['basic-028-3walls'], wall_loops='2')
VARIANTS['basic-028-3walls-slim'] = dict(VARIANTS['basic-028-3walls'], support_style='tree_slim')
VARIANTS['basic-028-3walls-hybrid'] = dict(VARIANTS['basic-028-3walls'], support_style='tree_hybrid')
VARIANTS['basic-028-3walls-sparse'] = dict(VARIANTS['basic-028-3walls'],
    support_base_pattern_spacing='4', support_top_z_distance='0.28', support_object_xy_distance='0.4')
WIDE_INFILL=dict(sparse_infill_line_width='0.6', internal_solid_infill_line_width='0.6',
    top_surface_line_width='0.6', support_line_width='0.5')
VARIANTS['basic-028-3walls-wide'] = dict(VARIANTS['basic-028-3walls'], **WIDE_INFILL,
    line_width='0.5', outer_wall_line_width='0.5', inner_wall_line_width='0.5')
VARIANTS['basic-028-2walls-wide'] = dict(VARIANTS['basic-028-3walls'], **WIDE_INFILL,
    wall_loops='2', line_width='0.6', outer_wall_line_width='0.6', inner_wall_line_width='0.6')
VARIANTS['basic-028-3walls-critical'] = dict(VARIANTS['basic-028-3walls'], support_critical_regions_only='1')
VARIANTS['basic-028-wide-support06'] = dict(VARIANTS['basic-028-2walls-wide'], support_line_width='0.6')
VARIANTS['basic-028-wide-normal06'] = dict(VARIANTS['basic-028-wide-support06'], support_type='normal(auto)')
VARIANTS['basic-028-wide-rectilinear'] = dict(VARIANTS['basic-028-wide-support06'], sparse_infill_pattern='rectilinear')
VARIANTS['basic-028-wide-arachne'] = dict(VARIANTS['basic-028-2walls-wide'], wall_generator='arachne')


def filament_profile(name):
    directory=Path('/Applications/BambuStudio.app/Contents/Resources/profiles/BBL/filament')
    data=json.loads((directory/(name+'.json')).read_text())
    resolved=filament_profile(data['inherits']) if data.get('inherits') else {}
    for include in data.get('include', []):
        resolved.update(filament_profile(include))
    resolved.update(data)
    return resolved


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(name, overrides):
    target = OUT / name
    target.mkdir(parents=True, exist_ok=True)
    project = target / 'input.3mf'
    # Drop old G-code and slice metadata. Retain the exact embedded mesh/placement.
    with zipfile.ZipFile(BASE / 'PP07-P2S-PLA-0.20.3mf') as src:
        config = json.loads(src.read('Metadata/project_settings.config'))
        process={k:v for k,v in overrides.items() if k!='filament_profile'}
        if 'filament_profile' in overrides:
            profile=filament_profile(overrides['filament_profile'])
            metadata={'name','type','inherits','include','from','setting_id','instantiation',
                      'compatible_printers','compatible_printers_condition','description'}
            config.update({k:v for k,v in profile.items() if k not in metadata and k in config})
            config['filament_settings_id']=[overrides['filament_profile']]
            config['filament_ids']=[profile['filament_id']]
            (target/'resolved-filament.json').write_text(json.dumps(profile,indent=2)+'\n')
        config.update(process)
        config['print_settings_id'] = 'PP07 speed candidate ' + name
        with zipfile.ZipFile(project, 'w', zipfile.ZIP_DEFLATED) as dst:
            for filename in ('[Content_Types].xml', '_rels/.rels', '3D/3dmodel.model',
                             '3D/_rels/3dmodel.model.rels', '3D/Objects/object_1.model',
                             'Metadata/model_settings.config'):
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
    row = dict(name=name, overrides=overrides, seconds=plate['total_predication'],
        grams=sum(f['total_used_g'] for f in plate['filaments']),
        warning=plate['warning_message'], feature_times=plate['feature_type_times'],
        project=str((target / (name + '.3mf')).relative_to(BASE)),
        project_sha256=digest(target / (name + '.3mf')))
    print(json.dumps({k:row[k] for k in ('name','seconds','grams','warning')}), flush=True)
    return row


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('variants', nargs='*', help='Candidate names; omit to run all')
    args=parser.parse_args()
    if any(name not in VARIANTS for name in args.variants):
        parser.error('Unknown candidate. Available: '+', '.join(VARIANTS))
    stl = BASE.parent / 'PP07-HeadShell.stl'
    baseline = json.loads((BASE / 'report.json').read_text())
    assert digest(stl) == baseline['input_stl_sha256'], 'STL changed; recheck baseline first'
    OUT.mkdir(exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(run, name, VARIANTS[name]) for name in (args.variants or list(VARIANTS))]
        rows = [future.result() for future in futures]
    previous_path=OUT/'report.json'
    old={}
    if previous_path.exists():
        old=json.loads(previous_path.read_text())
        assert old['input_stl_sha256']==digest(stl)
        updated={row['name']:row for row in old['candidates']}
        updated.update({row['name']:row for row in rows})
        rows=list(updated.values())
    report = dict(old, input_stl_sha256=digest(stl), baseline=baseline['comparison'][0],
        unchanged='Embedded mesh, upright orientation, machine settings, process speeds, first layer; process and filament overrides listed per candidate',
        candidates=rows, print_sent=False, physical_fit_or_strength_verified=False)
    (OUT / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
