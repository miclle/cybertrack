import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('maintenance',Path(__file__).resolve().parents[2]/'scripts/analyze_maintenance.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def trial(task,phase,repeat,seconds):
    return dict(sample_id=f'{task}-{phase}-{repeat}',condition_id='fixture',task=task,before_or_after=phase,
                revision=phase,repeat=repeat,duration_s=seconds,completed=True,observed_by='test',tools=[],faults=[])


class MaintenanceTests(unittest.TestCase):
    def test_median_and_conditions(self):
        rows=[trial(t,'before',i+1,d) for t,d0 in zip(m.TASKS,[10,50,20,100,30]) for i,d in enumerate([d0,d0,900])]
        rows.extend(trial(t,'after',i,d) for t,d in [('换电池',70),('清洁',35.01)] for i in (1,2,3))
        rows.append({**trial('换电池','after',1,1),'condition_id':'other'})
        report=m.analyze({'maintenance_trials':rows},'fixture','before','after')
        self.assertEqual(report['slowest_two'],['换电池','清洁'])
        self.assertTrue(report['comparisons']['换电池']['at_least_30_percent'])
        self.assertFalse(report['comparisons']['清洁']['at_least_30_percent'])
        rows.pop(0)
        self.assertEqual(m.analyze({'maintenance_trials':rows},'fixture','before','after')['slowest_two'],[])

    def test_distinct_complete_cycles_and_missing_records(self):
        cycles=[dict(sample_id=str(i),condition_id='fixture',revision='after',repeat=i,completed=True,observed_by='test',
                     checks=dict.fromkeys(m.CHECKS,'ok'),faults=[]) for i in range(1,11)]
        data=dict(maintenance_trials=[{'task':'取瓶'}, {**trial('取瓶','before',1,10),'completed':False}],maintenance_cycles=cycles)
        cycles[0]['checks']['磨线']='issue'
        report=m.analyze(data,'fixture','before','after')
        self.assertEqual(report['unassigned_observations'],1)
        self.assertEqual(report['complete_cycles'],9)
        self.assertEqual(len(report['incomplete_samples']),2)
        cycles[0]['faults']=['synthetic abrasion']
        report=m.analyze(data,'fixture','before','after')
        self.assertTrue(report['ten_cycles_recorded'])
        self.assertEqual(report['observations_with_faults'],['1'])
        cycles.append({**cycles[-1],'sample_id':'different'})
        with self.assertRaisesRegex(ValueError,'Duplicate'):m.analyze(data,'fixture','before','after')
