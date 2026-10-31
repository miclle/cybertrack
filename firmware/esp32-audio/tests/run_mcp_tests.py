#!/usr/bin/env python3
"""Compile the actual overlaid MCP validation block against ESP-IDF's cJSON."""
import argparse
import json
import os
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parents[3]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source', type=Path, default=root / 'build/xiaozhi-ct6-src')
parser.add_argument('--idf', type=Path, default=Path(os.environ.get('IDF_PATH', Path.home() / 'esp/esp-idf')))
args = parser.parse_args()
build = root / 'build/audio-host'
build.mkdir(parents=True, exist_ok=True)
text = (args.source / 'main/mcp_server.cc').read_text()
start = text.index('    const bool cybertrack =')
end = text.index('    PropertyList arguments =', start)
(build / 'argument_checks.inc').write_text(text[start:end])
cjson = args.idf / 'components/json/cJSON'
flags = ['-g', '-fsanitize=address,undefined', '-Wall', '-Wextra', '-Werror']
subprocess.run(['cc', '-std=c11', *flags, '-Wno-deprecated-declarations', '-I', str(cjson), '-c', str(cjson/'cJSON.c'), '-o', str(build/'cJSON.o')], check=True)
subprocess.run(['c++', '-std=c++17', *flags, '-I', str(cjson), '-I', str(build), '-I', str(root/'firmware/esp32-audio'), '-I', str(root/'firmware/esp32-linx/main'),
                str(Path(__file__).with_name('mcp_arguments_test.cc')), str(build/'cJSON.o'),
                '-o', str(build/'mcp_arguments_test')], check=True)
subprocess.run([str(build/'mcp_arguments_test')], check=True)
subprocess.run(['c++', '-std=c++17', *flags, '-I', str(cjson),
                '-I', str(root/'firmware/esp32-audio'), '-I', str(root/'firmware/esp32-linx/main'),
                str(Path(__file__).with_name('web_request_test.cc')), str(build/'cJSON.o'),
                '-o', str(build/'web_request_test')], check=True)
subprocess.run([str(build/'web_request_test')], check=True)
stubs = build/'web-stubs'
stubs.mkdir(exist_ok=True)
for name in ('application.h', 'board.h', 'display/display.h', 'esp_http_server.h',
             'esp_event.h', 'esp_wifi.h', 'esp_netif.h', 'esp_timer.h', 'esp_random.h', 'esp_log.h', 'web_page.h'):
    path = stubs/name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('#include "web_server_stubs.h"\n')
subprocess.run(['c++', '-std=c++17', *flags, '-I', str(stubs), '-I', str(cjson),
                '-I', str(root/'firmware/esp32-audio'), '-I', str(root/'firmware/esp32-linx/main'),
                '-I', str(Path(__file__).parent), str(Path(__file__).with_name('web_server_test.cc')),
                str(build/'cJSON.o'), '-o', str(build/'web_server_test')], check=True)
subprocess.run([str(build/'web_server_test')], check=True)
# Actual receipt serialization and request-history behavior with real guards.
receipt_source = (root / 'firmware/esp32-audio/cybertrack_tools.cc').read_text()
start = receipt_source.index('std::string Reply(')
end = receipt_source.index('\n}\n}', start) + 2
(build / 'receipt_reply.inc').write_text(receipt_source[start:end])
subprocess.run(['cc', '-std=c11', *flags, '-I', str(root/'firmware/esp32-linx/main'), '-c',
                str(root/'firmware/esp32-linx/main/water_policy.c'), '-o', str(build/'receipt_water_policy.o')], check=True)
for executable in ('receipt_adapter_test','receipt_replay','admission_result_test'):
    subprocess.run(['c++', '-std=c++17', *flags, '-I', str(cjson), '-I', str(build),
                    '-I', str(root/'firmware/esp32-audio'), '-I', str(root/'firmware/esp32-linx/main'),
                    str(Path(__file__).with_name(executable+'.cc')), str(build/'cJSON.o'),
                    str(build/'receipt_water_policy.o'), '-o', str(build/executable)], check=True)
subprocess.run([str(build/'receipt_adapter_test')], check=True)
subprocess.run([str(build/'admission_result_test')], check=True)

# Replay both admission outcomes against the same dispatch contract as the board.
speed_call = dict(name='self.tank.set_speed', arguments={'speed_percent':100}, elapsed_ms=1800)
for profile in ('thirty_second_forward70', 'idle', 'voice_offline', 'wifi_offline'):
    lines = subprocess.check_output([str(build/'receipt_replay'), profile],
                                    input=json.dumps([speed_call]), text=True).splitlines()
    reply, final = map(json.loads, lines)
    if profile != 'thirty_second_forward70':
        assert 'auto result = CyberTrackAdmissionResult(tool_name.c_str()+10, admission_error);' in text
        assert 'else ReplyResult(id, result);' in text
        assert reply['result']=='rejected' and reply['physical_feedback'] is False
        assert 'CyberTrackActionClaim(id, tool_name.c_str(), &admission_error)' in text
        expected = {'idle':'not_moving', 'voice_offline':'voice_offline', 'wifi_offline':'wifi_offline'}
        assert reply['rejection_reason'].startswith('speed_rejected_' + expected[profile] + ':')
        assert final['starts_this_boot'] == 0 and not any(final['logical_outputs'].values())
    else:
        assert reply['result'] == 'accepted' and reply['move_speed_percent'] == 100
        assert final['starts_this_boot'] == 1 and final['move_direction'] == 'forward'
        assert final['move_remaining_ms'] == 30000 - speed_call['elapsed_ms']


# A status read of an empty draft is not a successful creation.
compose_corpus = json.loads((root/'docs/validation/compose-cases.json').read_text())['cases']
create = next(case for case in compose_corpus if case['id']=='C001')['expected_calls']
for prefix in (create[:1], create):
    lines = subprocess.check_output([str(build/'receipt_replay'), 'empty_web_draft'],
                                    input=json.dumps(prefix), text=True).splitlines()
    first, final = json.loads(lines[0]), json.loads(lines[-1])
    assert not first['show_draft']['active'] and first['show_draft']['revision']==0
    assert '没有已保存草稿' in first['draft_status_facts']
    assert final['starts_this_boot']==0 and not any(final['logical_outputs'].values())
    if len(prefix)==1:
        assert not final['show_draft']['active'] and final['show_draft']['revision']==0
    else:
        saved = json.loads(lines[-2])
        assert saved['result']=='draft_saved' and final['show_draft']['revision']==1
        assert 'draft_status_facts' not in saved
        assert '当前有已保存草稿' in final['draft_status_facts']
        assert final['show_draft']['steps'][0]['move_ms']==880
        assert final['show_draft']['steps'][1]['bubbles_ms']==1000


# C002 uses a real web-owned draft. A matching revision alone cannot authorize
# a voice edit. Exercise the fresh-read boundary and verify both steps on readback.
compose_cases = json.loads((root/'docs/validation/compose-cases.json').read_text())['cases']
c002 = next(case for case in compose_cases if case['id'] == 'C002')
read, edit = c002['expected_calls']
for offset, expected in ((None, 'draft_changed'), (29999, 'draft_saved'), (30000, 'draft_changed')):
    calls = [] if offset is None else [dict(read, elapsed_ms=0)]
    calls.append(dict(edit, elapsed_ms=1000 if offset is None else offset))
    lines = subprocess.check_output([str(build/'receipt_replay'), 'two_step_web_draft'],
                                    input=json.dumps(calls), text=True).splitlines()
    reply, final = map(json.loads, lines[-2:])
    assert reply['result'] == expected
    draft = final['show_draft']
    saved = expected == 'draft_saved'
    assert draft['active'] and draft['revision'] == (8 if saved else 7)
    assert len(draft['steps']) == 2 and draft['steps'][0]['direction'] == 'left'
    assert draft['steps'][0]['move_ms'] == 880 and draft['steps'][1]['bubbles_ms'] == (2000 if saved else 1000)
    assert final['starts_this_boot'] == 0 and not any(final['logical_outputs'].values())
print('PASS: web draft stays active, only a fresh voice read permits C002, no output starts')


subprocess.run(['c++', '-std=c++17', *flags, '-I', str(cjson), '-I', str(root/'firmware/esp32-audio'),
                str(Path(__file__).with_name('voice_feedback_test.cc')), str(build/'cJSON.o'),
                '-o', str(build/'voice_feedback_test')], check=True)
subprocess.run([str(build/'voice_feedback_test')], check=True)
