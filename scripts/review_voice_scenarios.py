#!/usr/bin/env python3
"""Score fixed single/multi-turn speech scenarios and reproduce their host state."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path

from evaluate_voice import canonical
from review_spoken_cases import normalized
from review_stt_host import review as replay_stt


def score_turn(case, calls, wires, events, completed, reply):
    """Keep model calls, actual receipts and recognized speech as separate results."""
    heard = [e['text'] for e in events if e['event'] == 'stt']
    if any(e['event'] == 'simulated_input' for e in events):
        raise ValueError('simulated input cannot be scored as speech')
    seen_stt = False
    early = False
    for event in events:
        if event['event'] == 'stt' and event['text'].strip():
            seen_stt = True
        if event['event'] == 'tool_call' and not seen_stt:
            early = True
    try:
        strict = completed and canonical(calls, step_format='legacy_string') == canonical(case['expected_calls'])
    except (ValueError, TypeError):
        strict = False
    receipts = [json.loads(w['result']['content'][0]['text']) if 'result' in w else dict(result='rpc_error') for w in wires]
    wanted = case.get('expected_result')
    expected_results = [wanted or ('ok' if c['name'] in ('self.tank.stop', 'self.tank.get_status') else 'accepted')
                        for c in case['expected_calls']]
    results = [r['result'] for r in receipts]
    return dict(text=case['text'], completed=completed, stt=heard,
                transcript_matches=len(heard) == 1 and normalized(heard[0]) == normalized(case['text']),
                strict_tool_match=strict, tools_before_stt=early, calls=calls,
                results=results, expected_results=expected_results,
                expected_receipts_match=completed and results == expected_results,
                rejected=any(r not in ('ok', 'accepted') for r in results),
                remote_reply=reply, remote_text_empty=not reply.strip())


def review(trace, corpus_path, executable):
    """Verify provenance, then score each utterance without hiding incomplete turns."""
    if hashlib.sha256(corpus_path.read_bytes()).hexdigest() != trace['corpus_sha256']:
        raise ValueError('corpus differs from capture')
    cases = json.loads(corpus_path.read_bytes())['cases']
    expected = {c['id']: c for c in cases}
    if len(expected) != len(cases):
        raise ValueError('duplicate corpus IDs')
    replay = replay_stt(trace, executable)
    rows = []
    seen = set()
    for row in trace['results']:
        cid = row['id']
        if cid in seen or cid not in expected:
            raise ValueError('unknown or duplicate capture ID')
        seen.add(cid)
        case = expected[cid]
        if row['input_text'] != case['text'] or row['context'] != case['context']:
            raise ValueError('capture inputs differ from corpus')
        inputs = [case, *case.get('followups', [])]
        timeline = row['timeline']
        boundaries = [i for i, e in enumerate(timeline) if e['event'] == 'input_sent']
        if not boundaries or len(boundaries) > len(inputs):
            raise ValueError('unexpected number of inputs')
        saved = row.get('turns', [dict(text=row['input_text'], completed=row['completed'],
            call_start=0, call_end=len(row['calls']), reply_start=0, reply_end=len(row['replies']), uplink=row['uplink'])])
        turns = []
        for i, item in enumerate(inputs):
            if i >= len(saved):
                turns.append(dict(text=item['text'], completed=False, not_sent=True,
                                  strict_tool_match=False, expected_receipts_match=False, transcript_matches=False))
                continue
            turn = saved[i]
            if turn['text'] != item['text']:
                raise ValueError('followup differs from corpus')
            up = turn['uplink']
            if ([up[k] for k in ('codec','sample_rate_hz','channels','frame_ms')] != ['opus',16000,1,60]
                    or up['frames'] <= 0 or up['encoded_bytes'] <= 0 or len(up['payload_sha256']) != 64):
                raise ValueError('missing synthesized audio provenance')
            end = boundaries[i+1] if i+1 < len(boundaries) else len(timeline)
            events = timeline[boundaries[i]+1:end]
            start_call = turn['call_start']
            end_call = turn.get('call_end', len(row['calls']))
            if [e['name'] for e in events if e['event']=='tool_call'] != [c['name'] for c in row['calls'][start_call:end_call]]:
                raise ValueError('turn call boundaries differ from events')
            turns.append(score_turn(item, row['calls'][start_call:end_call],
                row.get('host_rpc_replies', [])[start_call:end_call], events, turn['completed'],
                ''.join(row['replies'][turn['reply_start']:turn.get('reply_end', len(row['replies']))])))
        state = row['host_final_state']
        rows.append(dict(id=cid, category=case['category'], completed=row['completed'], turns=turns,
                         strict_tool_match=all(t['strict_tool_match'] for t in turns),
                         expected_receipts_match=all(t['expected_receipts_match'] for t in turns),
                         final_outputs=state['logical_outputs'], starts=state['starts_this_boot'],
                         sequence_result=state['sequence_result'],
                         remote_audio_bytes=row['received_audio_bytes_discarded']))
    turns = [turn for row in rows for turn in row['turns']]
    return dict(scope='Fixed ct78 scenarios, synthesized Mandarin and real platform STT/model; actual host MCP; no physical or human speech acceptance',
                run_id=trace['run_id'], expected_scenarios=len(cases), captured_scenarios=len(rows),
                expected_utterances=sum(1+len(c.get('followups', [])) for c in cases),
                completed_scenarios=sum(r['completed'] for r in rows), completed_utterances=sum(t['completed'] for t in turns),
                strict_scenario_matches=sum(r['strict_tool_match'] for r in rows),
                strict_utterance_matches=sum(t['strict_tool_match'] for t in turns),
                expected_receipt_scenarios=sum(r['expected_receipts_match'] for r in rows),
                transcript_matches=sum(t['transcript_matches'] for t in turns),
                tools_before_stt=sum(t.get('tools_before_stt',False) for t in turns),
                missing=sorted(set(expected)-seen), replay=replay, results=rows)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--corpus', type=Path, required=True)
    parser.add_argument('--executable', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    raw = args.capture.read_bytes()
    trace = json.loads(gzip.decompress(raw) if args.capture.suffix == '.gz' else raw)
    report = review(trace, args.corpus, args.executable)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('results','replay')}, ensure_ascii=False))
