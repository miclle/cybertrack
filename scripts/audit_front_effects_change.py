"""Check front effect additions or a four-lead length change against a saved baseline."""
import argparse
import hashlib
import json
from pathlib import Path
import FreeCAD as App

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('baseline', type=Path)
parser.add_argument('--length-update', action='store_true', help='Compare against 0.45; only four lead shapes may change')
args = parser.parse_args()
folder = Path(__file__).resolve().parents[1]/'hardware/model'
current = folder/'CyberTrack.FCStd'
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
old = App.openDocument(str(args.baseline.resolve()))
new = App.openDocument(str(current))
before = {o.Name:o for o in old.Objects if hasattr(o, 'Category')}
after = {o.Name:o for o in new.Objects if hasattr(o, 'Category')}
rows = []
expected_changed = {f'FrontEffectLead{side}{i}' for side in ('L', 'R') for i in (1, 2)}
for name, obj in before.items():
    other = after.get(name)
    if other is None:
        rows.append(dict(name=name, passed=False, missing=True))
        continue
    same = obj.Shape.exportBrepToString() == other.Shape.exportBrepToString()
    delta = 0 if same else obj.Shape.cut(other.Shape).Volume + other.Shape.cut(obj.Shape).Volume
    changed = delta >= 1e-5
    allowed = changed if args.length_update and name in expected_changed else not changed
    rows.append(dict(name=name, difference_mm3=delta, changed=changed,
                     passed=allowed and obj.Label==other.Label and obj.Category==other.Category))
expected = sorted(f'FrontEffect{kind}{side}{i}'
                  for kind in ('Lead', 'Sleeve') for side in ('L', 'R') for i in (1, 2))
added = sorted(after.keys()-before.keys())
removed = sorted(before.keys()-after.keys())
report = dict(revision='0.46', baseline_revision='0.45' if args.length_update else '0.44',
              baseline_sha256=sha(args.baseline), source_sha256=sha(current),
              added=added, removed=removed, objects=rows,
              unchanged_objects=sum(not row.get('changed', True) for row in rows),
              changed=[row['name'] for row in rows if row.get('changed')],
              passed=added==([] if args.length_update else expected) and not removed and all(row['passed'] for row in rows))
filename = 'front-effects-length-change-audit.json' if args.length_update else 'front-effects-change-audit.json'
(folder/filename).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k!='objects'},indent=2))
assert report['passed'], 'Unexpected assembly change; inspect front-effects-change-audit.json'
