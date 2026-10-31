#!/usr/bin/env python3
"""Exercise bounded negative-input admission through actual MCP callbacks; no IO."""
import argparse
import hashlib
import json
from pathlib import Path

from capture_lingxi import firmware_replay


def check(executable):
    def call(name, args=None, ms=10, rpc=1, **extra):
        return dict(name='self.tank.'+name,arguments=args or {},elapsed_ms=ms,rpc_id=rpc,**extra)
    def text(value, ms=0):return dict(input_text=value,elapsed_ms=ms)
    def receipt(wire):
        return dict(result='rpc_error',message=wire['error']['message']) if 'error' in wire else json.loads(wire['result']['content'][0]['text'])
    results=[]
    def run(name, commands, verify, profile='corpus_idle'):
        wire=firmware_replay(executable,profile,commands,await_stt=True)
        replies=[receipt(w) for w in wire[:-1]]
        results.append(dict(name=name,passed=bool(verify(replies,wire[-1])),profile=profile,commands=commands,receipts=replies,final_state=wire[-1]))
    off=lambda s:not any(s['logical_outputs'].values()) and not s['sequence_active']
    for phrase in ('不要前进','别喷水','不要开启狂暴模式','不许吹泡泡','不要放电','不要饭店','请先不要启动泡泡。'):
        run('idle_false_stop_'+phrase,[text(phrase),call('stop',defer=True)],
            lambda r,s:r[0]['result']=='input_negated' and s['starts_this_boot']==0 and off(s))
    for phrase in ('不要编排表演','这次先别编排新的表演','先不要创建节目，保留现在的草稿','别取消这份草稿','我没让你取消草稿'):
        run('preserve_draft_'+phrase,[text(phrase),call('stop',defer=True)],
            lambda r,s:r[0]['result']=='input_negated' and bool(r[0].get('negation_facts')) and s['show_draft']['revision']==7 and s['show_draft']['active'] and s['starts_this_boot']==0,'corpus_draft7')
    plan='[{"direction":"left","move_ms":880,"water_ms":0,"bubbles_ms":0,"ignition_ms":0}]'
    for tool,args in [('move',dict(direction='forward',duration_ms=1000)),('water',dict(duration_ms=1000)),('bubbles',dict(duration_ms=1000)),
                      ('ignition',dict(duration_ms=1000)),('frenzy',dict(duration_ms=1000)),('sequence',dict(steps_json=plan))]:
        run('no_substitute_'+tool,[text('不要放电'),call(tool,args)],lambda r,s:r[0]['result']=='input_negated' and s['starts_this_boot']==0 and off(s))
    edit=dict(edit='cancel',revision=7,step=0,steps_json='')
    run('no_cancel_substitute',[text('不要编排表演'),call('get_status'),call('compose',edit,20,2)],
        lambda r,s:r[0]['result']=='ok' and r[1]['result']=='input_negated' and s['show_draft']['revision']==7,'corpus_draft7')
    for tool,args in [('set_speed',dict(speed_percent=100)),('adjust_speed',dict(delta_percent=10))]:
        run('no_speed_'+tool,[text('不要前进'),call(tool,args)],lambda r,s:r[0]['result']=='input_negated' and s['move_speed_percent']==70,'corpus_forward70')
    for phrase in ('不要停止当前序列','不要停','别取消序列'):
        # No original-input ID exists on MCP stop. Keep the stop path even
        # when it may be a model mistake; do not disguise that semantic gap.
        run('active_stop_priority_'+phrase,[text(phrase),call('stop',defer=True)],lambda r,s:r[0]['result']=='ok' and off(s),'corpus_sequence')
    for phrase in ('停止','停下','停止行走','停止喷水','停止泡泡','停止狂暴模式','取消序列','所有动作都停下来',
                   '别动','不要再动了','别喷水了','先别编排了，马上停下','不要放电，停下','别再往前走了，马上停下','未知表达'):
        run('stop_not_blocked_'+phrase,[text(phrase),call('stop',defer=True),dict(inspect_ms=60000)],
            lambda r,s:r[0]['result']=='ok' and r[0]['uptime_ms']==1010 and off(s),'corpus_sequence')
    run('active_prohibition_keeps_stop',[text('别喷水'),call('stop',defer=True)],lambda r,s:r[0]['result']=='ok' and off(s),'corpus_sequence')
    run('new_input_restores_stop',[text('不要编排表演'),call('stop'),text('停下',20),call('stop',ms=30,rpc=2)],
        lambda r,s:r[0]['result']=='input_negated' and r[1]['result']=='ok' and s['show_draft']['revision']==0,'corpus_draft7')
    run('failure_latch_no_fallback',[text('不要放电'),call('ignition',dict(duration_ms=1000)),call('water',dict(duration_ms=1000),20,2)],
        lambda r,s:r[0]['result']=='input_negated' and r[1]['result']=='rpc_error' and s['starts_this_boot']==0)
    run('positive_clause_not_globally_blocked',[text('先不要编排，直接吹泡泡两秒'),call('bubbles',dict(duration_ms=2000))],
        lambda r,s:r[0]['result']=='accepted' and s['starts_this_boot']==1)
    run('old_callback_isolated',[text('前进一秒'),call('move',dict(direction='forward',duration_ms=1000),defer=True),text('不要前进',20),dict(flush=True,elapsed_ms=30)],
        lambda r,s:r[0]['result']=='voice_input_changed' and s['starts_this_boot']==0)
    run('late_valid_stop_after_new_negative_input',[text('停止'),text('不要编排表演',1),call('stop',ms=2,defer=True)],
        lambda r,s:r[0]['result']=='ok' and r[0]['uptime_ms']==1002 and off(s),'corpus_sequence')
    run('waiting_gap_stop_after_negative_input',[text('不要停止当前序列',30001),call('stop',ms=30010,defer=True),dict(inspect_ms=60000)],
        lambda r,s:r[0]['result']=='ok' and r[0]['uptime_ms']==31010 and off(s) and s['starts_this_boot']==1,'corpus_sequence')
    return dict(scope='Actual MCP with simulated recognized input/time, no model/ASR/board acceptance; active prohibitions preserve the stop path',
                host_sha256=hashlib.sha256(executable.read_bytes()).hexdigest(),scenarios=len(results),passed=all(r['passed'] for r in results),
                failed=[r['name'] for r in results if not r['passed']],results=results)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--executable',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    report=check(a.executable);a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='results'},ensure_ascii=False));raise SystemExit(0 if report['passed'] else 1)
