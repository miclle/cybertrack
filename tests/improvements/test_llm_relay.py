import copy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import lingxi_llm_relay as relay


def completion(content='请问要改成几秒？',calls=None,finish=None):
    message=dict(role='assistant',content=content)
    if calls is not None: message['tool_calls']=calls
    return dict(id='fixture-completion',object='chat.completion',created=0,model='fixture-model',
        choices=[dict(index=0,message=message,finish_reason=finish or ('tool_calls' if calls else 'stop'))],
        usage=dict(prompt_tokens=10,completion_tokens=2,total_tokens=12))


def tool(call_id='call_fixture'):
    # Deliberate whitespace: arguments must survive byte-for-byte.
    return dict(id=call_id,type='function',function=dict(name='self_tank_water',arguments='{ "duration_ms": 30000 }'))


class RelayPolicyTests(unittest.TestCase):
    def test_tool_round_discards_prose_without_changing_any_calls(self):
        original=completion('我先查询规则，然后执行。',[tool('a'),tool('b')]); saved=copy.deepcopy(original)
        result=relay.isolate_tool_round(original)
        self.assertIsNone(result['choices'][0]['message']['content'])
        self.assertEqual(result['choices'][0]['message']['tool_calls'],original['choices'][0]['message']['tool_calls'])
        self.assertEqual(original,saved)
        self.assertNotIn('我先查询',json.dumps(result,ensure_ascii=False))

    def test_final_limits_refusals_queries_and_clarifications_are_not_keyword_filtered(self):
        for text in ['喷水单次最多三十秒。','设备还没连接。','第二步要改成几秒？','刚查询到剩余两秒。',
                     '根据规则，这是工具之后的最终文字，当前原型不会识别并删除它。','I need a duration in seconds.']:
            with self.subTest(text=text):
                self.assertEqual(relay.isolate_tool_round(completion(text))['choices'][0]['message']['content'],text)

    def test_reasoning_mode_is_rejected_before_tool_calls_can_escape(self):
        for calls in (None,[tool()]):
            original=completion('valid',calls); original['choices'][0]['message']['reasoning_content']='provider reasoning needing history'
            with self.assertRaisesRegex(relay.RelayError,'reasoning_mode_unsupported'):relay.isolate_tool_round(original)

    def test_incomplete_or_inconsistent_tool_round_is_never_forwarded(self):
        for response in [completion('partial',[tool()],finish='length'), completion('partial',finish='length'),
                         completion(None,[],finish='tool_calls'),completion(None,[tool()],finish='stop')]:
            with self.subTest(response=response),self.assertRaises(relay.RelayError):relay.isolate_tool_round(response)
        ambiguous=completion(None,[tool()]);ambiguous['choices'][0]['message']['refusal']='refused'
        with self.assertRaisesRegex(relay.RelayError,'inconsistent_tool_refusal'):relay.isolate_tool_round(ambiguous)

    def test_invalid_tool_ids_arguments_and_choice_shapes_fail_closed(self):
        bad=[]
        for field,value in [('id',''),('function',None),('index',7)]:
            t=tool();t[field]=value;bad.append(completion(None,[t]))
        for args in ('[1]','{','null',{}):
            t=tool();t['function']['arguments']=args;bad.append(completion(None,[t]))
        bad.extend([completion(None,[tool(),tool()]),dict(choices=[]),dict(choices=[{},{}])])
        for response in bad:
            with self.subTest(response=response),self.assertRaises(relay.RelayError):relay.isolate_tool_round(response)

    def test_stream_has_no_tool_prose_and_preserves_ids_order_arguments_usage(self):
        response=relay.isolate_tool_round(completion('forbidden tool narration',[tool('a'),tool('b')]))
        chunks=list(relay.sse_chunks(response,True));self.assertNotIn('forbidden tool narration',json.dumps(chunks))
        calls=chunks[1]['choices'][0]['delta']['tool_calls']
        self.assertEqual([(c['index'],c['id'],c['function']['arguments']) for c in calls],
                         [(i,t['id'],t['function']['arguments']) for i,t in enumerate(response['choices'][0]['message']['tool_calls'])])
        self.assertEqual(chunks[-1]['choices'][0]['finish_reason'],'tool_calls')
        self.assertEqual(chunks[-1]['usage'],response['usage'])
        self.assertNotIn('usage',list(relay.sse_chunks(response))[-1])

    def test_refusal_is_retained_and_unknown_provider_fields_are_not_emitted(self):
        response=completion(None); response['choices'][0]['message']['refusal']='这次不能执行。'
        response['choices'][0]['hidden_provider_data']='do not forward';response['provider_debug']='do not forward'
        result=relay.isolate_tool_round(response)
        self.assertEqual(result['choices'][0]['message']['content'],'这次不能执行。')
        self.assertNotIn('do not forward',json.dumps(result))

    def test_request_preserves_messages_tool_results_and_definitions(self):
        body=dict(model='local',messages=[dict(role='user',content='原话'),dict(role='tool',tool_call_id='a',content='{"result":"rejected"}')],
                  tools=[dict(type='function',function=dict(name='self_tank_stop'))],tool_choice='auto',stream=True,
                  stream_options=dict(include_usage=True),thinking=dict(type='enabled'),reasoning_effort='low')
        saved=copy.deepcopy(body)
        result=relay.prepare_request(body,dict(public_model='local',upstream_model='upstream',disable_thinking=True))
        for key in ('messages','tools','tool_choice'):self.assertEqual(result[key],body[key])
        self.assertEqual(result['thinking'],dict(type='disabled'));self.assertNotIn('reasoning_effort',result)
        self.assertFalse(result['stream']);self.assertNotIn('stream_options',result);self.assertEqual(body,saved)

    def test_bad_request_shapes_do_not_reach_upstream(self):
        config=dict(public_model='local',upstream_model='upstream')
        valid=dict(model='local',messages=[dict(role='user',content='hello')])
        for changed in [None,dict(valid,model='unknown'),dict(valid,messages=[]),dict(valid,stream='true'),dict(valid,n=2),
                        dict(valid,n=True),dict(valid,stream_options='invalid')]:
            with self.subTest(changed=changed),self.assertRaises(relay.RelayError):relay.prepare_request(changed,config)

    def test_config_requires_https_and_separate_environment_credential_inputs(self):
        base=dict(upstream_url='https://example.invalid/v1/chat/completions',upstream_model='fixture',public_model='local',
                  upstream_api_key_env='TEST_RELAY_UPSTREAM',client_api_key_env='TEST_RELAY_CLIENT')
        with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,{'TEST_RELAY_UPSTREAM':'upstream-fixture-key','TEST_RELAY_CLIENT':'client-fixture-key'}):
            path=Path(folder)/'config.json';path.write_text(json.dumps(base));self.assertEqual(relay.load_config(path)['client_api_key'],'client-fixture-key')
            for url in ['http://localhost:9000/v1/chat/completions','https://user:secret@example.invalid/v1/chat/completions',
                        'https://example.invalid/v1/chat/completions?secret=1']:
                path.write_text(json.dumps(dict(base,upstream_url=url)))
                with self.assertRaises(ValueError):relay.load_config(path)


class RelayHTTPTests(unittest.TestCase):
    def setUp(self):
        self.requests=[];self.answers=[]
        self.received=threading.Event()
        owner=self
        class Upstream(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                owner.requests.append((self.headers.get('Authorization'),json.loads(self.rfile.read(int(self.headers['Content-Length'])))))
                owner.received.set()
                answer=owner.answers.pop(0)
                if isinstance(answer,tuple):
                    gate,answer=answer
                    if not gate.wait(5): raise RuntimeError('fixture gate timed out')
                if isinstance(answer,int):
                    self.send_response(answer)
                    if answer==302:self.send_header('Location',f'http://127.0.0.1:{owner.upstream.server_port}/redirected')
                    self.end_headers();self.wfile.write(b'PRIVATE UPSTREAM ERROR');return
                raw=json.dumps(answer).encode();self.send_response(200);self.end_headers();self.wfile.write(raw)
            def do_GET(self):
                owner.requests.append(('UNEXPECTED_REDIRECT',{}));self.send_response(500);self.end_headers()
        self.upstream=ThreadingHTTPServer(('127.0.0.1',0),Upstream)
        config=dict(upstream_url=f'http://127.0.0.1:{self.upstream.server_port}/v1/chat/completions',upstream_model='fixture',public_model='local',
                    upstream_api_key='upstream-fixture-key',client_api_key='client-fixture-key')
        self.server=relay.make_server(config)
        self.config=config
        self.threads=[]
        for server in (self.upstream,self.server):
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();self.threads.append(thread)

    def tearDown(self):
        for server in (self.server,self.upstream):server.shutdown();server.server_close()
        for thread in self.threads:thread.join()

    def post(self,body,key='client-fixture-key'):
        request=Request(f'http://127.0.0.1:{self.server.server_port}/v1/chat/completions',data=json.dumps(body).encode(),
                        headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
        return urlopen(request,timeout=5)

    def test_two_round_http_tool_loop_preserves_result_and_final_limit(self):
        self.answers=[completion('I will first check rules.',[tool()]),completion('喷水单次最多三十秒。')]
        messages=[dict(role='user',content='喷水六十秒')]
        body=dict(model='local',messages=messages)
        with self.post(body) as response:first=json.load(response)
        self.assertIsNone(first['choices'][0]['message']['content'])
        messages.extend([first['choices'][0]['message'],dict(role='tool',tool_call_id='call_fixture',content='{"result":"accepted"}')])
        with self.post(body) as response:second=json.load(response)
        self.assertEqual(second['choices'][0]['message']['content'],'喷水单次最多三十秒。')
        self.assertEqual(self.requests[1][1]['messages'],messages)
        self.assertTrue(all(key=='Bearer upstream-fixture-key' for key,_ in self.requests))
        self.assertEqual(len(self.requests),2)

    def test_http_sse_ends_normally_and_no_tool_prose_is_sent(self):
        self.answers=[completion('forbidden narration',[tool()])]
        with self.post(dict(model='local',messages=[dict(role='user',content='hello')],stream=True,stream_options=dict(include_usage=True))) as response:
            raw=response.read().decode();self.assertIn('text/event-stream',response.headers['Content-Type'])
        self.assertNotIn('forbidden narration',raw);self.assertTrue(raw.endswith('data: [DONE]\n\n'))
        chunks=[json.loads(line[6:]) for line in raw.splitlines() if line.startswith('data: {')]
        self.assertEqual(chunks[-1]['choices'][0]['finish_reason'],'tool_calls')
        self.assertEqual(chunks[1]['choices'][0]['delta']['tool_calls'][0]['id'],'call_fixture')

    def test_unauthorized_and_invalid_requests_make_zero_upstream_calls(self):
        for body,key,code in [(dict(model='local'),'wrong',401),({},'client-fixture-key',400)]:
            with self.assertRaises(HTTPError) as raised:self.post(body,key)
            self.assertEqual(raised.exception.code,code)
            raised.exception.close()
        self.assertEqual(self.requests,[])

    def test_upstream_errors_never_retry_or_leak_response_text(self):
        self.answers=[429]
        with self.assertRaises(HTTPError) as raised:self.post(dict(model='local',messages=[dict(role='user',content='hello')]))
        self.assertEqual(raised.exception.code,502)
        self.assertNotIn('PRIVATE',raised.exception.read().decode());raised.exception.close();self.assertEqual(len(self.requests),1)

    def test_no_sse_headers_or_prose_escape_before_upstream_completion(self):
        gate=threading.Event();opened=threading.Event();finished=threading.Event();results=[]
        self.answers=[(gate,completion('forbidden early prose',[tool()]))]
        def consume():
            try:
                with self.post(dict(model='local',messages=[dict(role='user',content='hello')],stream=True)) as response:
                    opened.set();results.append(response.read().decode())
            finally:finished.set()
        thread=threading.Thread(target=consume);thread.start()
        try:
            self.assertTrue(self.received.wait(2));self.assertFalse(opened.wait(.05));self.assertFalse(finished.is_set())
        finally:gate.set();thread.join(5)
        self.assertFalse(thread.is_alive());self.assertEqual(len(results),1)
        self.assertNotIn('forbidden early prose',results[0]);self.assertIn('tool_calls',results[0])

    def test_redirect_does_not_send_credentials_to_another_request(self):
        self.answers=[302]
        with self.assertRaises(HTTPError) as raised:self.post(dict(model='local',messages=[dict(role='user',content='hello')]))
        self.assertEqual(raised.exception.code,502);raised.exception.close()
        self.assertEqual(len(self.requests),1)

    def test_truncated_response_does_not_return_partial_tool_calls(self):
        self.answers=[completion('partial prose',[tool()],finish='length')]
        with self.assertRaises(HTTPError) as raised:self.post(dict(model='local',messages=[dict(role='user',content='hello')],stream=True))
        self.assertEqual(raised.exception.code,502)
        body=raised.exception.read().decode();raised.exception.close()
        self.assertNotIn('call_fixture',body);self.assertNotIn('partial prose',body);self.assertEqual(len(self.requests),1)


if __name__=='__main__':unittest.main()
