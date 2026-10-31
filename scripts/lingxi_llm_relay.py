#!/usr/bin/env python3
"""Local-only Chat Completions relay: isolate tool-round prose before TTS."""
import argparse
import copy
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import build_opener, HTTPRedirectHandler, ProxyHandler, Request

LIMIT = 2 * 1024 * 1024


class RelayError(Exception):
    """Public error codes contain no upstream response text or credentials."""


def prepare_request(body, config):
    if not isinstance(body, dict) or body.get('model') != config['public_model']:
        raise RelayError('unsupported_model')
    if not isinstance(body.get('messages'), list) or not body['messages']:
        raise RelayError('missing_messages')
    if type(body.get('stream', False)) is not bool or type(body.get('n', 1)) is not int or body.get('n', 1) != 1:
        raise RelayError('unsupported_generation_shape')
    options=body.get('stream_options')
    if options is not None and (not isinstance(options,dict) or type(options.get('include_usage',False)) is not bool):
        raise RelayError('invalid_stream_options')
    request = copy.deepcopy(body)
    request.update(model=config['upstream_model'], stream=False)
    request.pop('stream_options', None)
    # Preserve messages, tools, tool_choice and all tool-result history verbatim.
    if config.get('disable_thinking'):
        request['thinking'] = {'type': 'disabled'}
        request.pop('reasoning_effort', None)
    return request


def isolate_tool_round(response):
    """Decide after the complete response; never infer phase from prose keywords."""
    if not isinstance(response, dict) or not isinstance(response.get('choices'), list) or len(response['choices']) != 1:
        raise RelayError('invalid_completion')
    if (not isinstance(response.get('id'),str) or not response['id'] or response.get('object') != 'chat.completion'
        or type(response.get('created')) is not int or response['created'] < 0
        or not isinstance(response.get('model'),str) or not response['model']):
        raise RelayError('invalid_completion_identity')
    choice = response['choices'][0]
    if not isinstance(choice, dict) or type(choice.get('index')) is not int or choice['index'] != 0 or choice.get('finish_reason') not in ('stop', 'tool_calls'):
        raise RelayError('incomplete_completion')
    message = choice.get('message')
    if not isinstance(message, dict) or message.get('role') != 'assistant':
        raise RelayError('invalid_assistant_message')
    # Thinking tool calls may require reasoning history on the next request.
    # This prototype refuses that mode instead of silently breaking the history.
    if message.get('reasoning_content') not in (None, '') or message.get('reasoning') not in (None, ''):
        raise RelayError('reasoning_mode_unsupported')
    if message.get('content') is not None and not isinstance(message['content'], str):
        raise RelayError('unsupported_content')
    calls = message.get('tool_calls')
    if calls is not None and not isinstance(calls, list):
        raise RelayError('invalid_tool_calls')
    if bool(calls) != (choice['finish_reason'] == 'tool_calls'):
        raise RelayError('inconsistent_tool_finish')
    if calls and message.get('refusal'): raise RelayError('inconsistent_tool_refusal')
    seen = set()
    for call in calls or []:
        if not isinstance(call, dict) or set(call) != {'id','type','function'} or not isinstance(call.get('id'), str) or not call['id'] or call['id'] in seen:
            raise RelayError('invalid_tool_call_id')
        seen.add(call['id'])
        function = call.get('function')
        if call.get('type') != 'function' or not isinstance(function, dict) or set(function) != {'name','arguments'} or not isinstance(function.get('name'), str) or not function['name']:
            raise RelayError('invalid_tool_function')
        if not isinstance(function.get('arguments'), str):
            raise RelayError('invalid_tool_arguments')
        try:
            arguments = json.loads(function['arguments'])
        except (ValueError, TypeError):
            raise RelayError('invalid_tool_arguments') from None
        if not isinstance(arguments, dict): raise RelayError('invalid_tool_arguments')
    result = {key:copy.deepcopy(response[key]) for key in ('id','object','created','model','usage') if key in response}
    result['choices'] = [{'index':0, 'finish_reason':choice['finish_reason']}]
    result['choices'][0]['message'] = {'role':'assistant', 'content':None if calls else message.get('content')}
    if calls: result['choices'][0]['message']['tool_calls'] = copy.deepcopy(calls)
    if message.get('refusal') is not None:
        if not isinstance(message['refusal'], str): raise RelayError('invalid_refusal')
        result['choices'][0]['message']['refusal'] = message['refusal']
        if not calls and not message.get('content'): result['choices'][0]['message']['content'] = message['refusal']
    return result


def sse_chunks(response, include_usage=False):
    """Generate a stream only after isolation; no speculative content is sent."""
    base = {key:response[key] for key in ('id','created','model') if key in response}
    base['object'] = 'chat.completion.chunk'
    def chunk(delta, finish=None):
        return {**base, 'choices':[{'index':0, 'delta':delta, 'finish_reason':finish}]}
    yield chunk({'role':'assistant'})
    message = response['choices'][0]['message']
    if message.get('tool_calls'):
        yield chunk({'tool_calls':[{'index':i, **call} for i,call in enumerate(message['tool_calls'])]})
    elif message.get('content') is not None:
        yield chunk({'content':message['content']})
    final = chunk({}, response['choices'][0]['finish_reason'])
    if include_usage and 'usage' in response: final['usage'] = response['usage']
    yield final


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise RelayError('upstream_redirect_rejected')


def upstream(body, config):
    data = json.dumps(body, ensure_ascii=False).encode()
    request = Request(config['upstream_url'], data=data,
        headers={'Authorization':'Bearer '+config['upstream_api_key'], 'Content-Type':'application/json'})
    try:
        # Fixed destination, no environment proxy or redirect credential forwarding.
        with build_opener(ProxyHandler({}), NoRedirects()).open(request, timeout=config.get('timeout_seconds',45)) as response:
            raw = response.read(LIMIT+1)
        if len(raw) > LIMIT: raise RelayError('upstream_response_too_large')
        return json.loads(raw)
    except HTTPError as error:
        error.close()
        raise RelayError('upstream_failure') from None
    except (URLError, TimeoutError, OSError, ValueError):
        raise RelayError('upstream_failure') from None


def make_server(config, port=0):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass # No requests, prompts, headers or errors on disk.
        def send_json(self, status, data):
            raw=json.dumps(data, ensure_ascii=False).encode()
            self.send_response(status); self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(raw))); self.end_headers(); self.wfile.write(raw)
        def do_POST(self):
            if self.path != '/v1/chat/completions':
                self.send_json(404, {'error':{'code':'unknown_path'}}); return
            auth=self.headers.get('Authorization','')
            if not hmac.compare_digest(auth.encode(), ('Bearer '+config['client_api_key']).encode()):
                self.send_json(401, {'error':{'code':'unauthorized'}}); return
            try:
                self.connection.settimeout(10)
                size=int(self.headers.get('Content-Length','0'))
                if not 0 < size <= LIMIT or self.headers.get('Transfer-Encoding'):
                    raise RelayError('invalid_request_length')
                raw=self.rfile.read(size)
                if len(raw) != size: raise RelayError('incomplete_request')
                body=json.loads(raw)
                request=prepare_request(body, config)
            except (ValueError, RelayError, TimeoutError, OSError):
                self.send_json(400, {'error':{'code':'invalid_request'}}); return
            try:
                result=isolate_tool_round(upstream(request,config))
                if not body.get('stream'):
                    self.send_json(200,result); return
                options=body.get('stream_options') or {}
                if not isinstance(options,dict): raise RelayError('invalid_stream_options')
                self.send_response(200); self.send_header('Content-Type','text/event-stream')
                self.send_header('Cache-Control','no-cache'); self.end_headers()
                for chunk in sse_chunks(result, options.get('include_usage') is True):
                    self.wfile.write(('data: '+json.dumps(chunk,ensure_ascii=False)+'\n\n').encode())
                self.wfile.write(b'data: [DONE]\n\n'); self.wfile.flush()
            except RelayError as error:
                self.send_json(502, {'error':{'type':'relay_error','code':str(error)}})
            except (BrokenPipeError, ConnectionResetError): pass # Never retry an abandoned generation.
    return ThreadingHTTPServer(('127.0.0.1',port),Handler)


def load_config(path):
    data=json.loads(path.read_text())
    url=urlsplit(data['upstream_url'])
    if url.scheme != 'https' or not url.hostname or url.username or url.password or url.query or url.fragment:
        raise ValueError('upstream_url must be a fixed HTTPS endpoint without credentials/query/fragment')
    if not all(isinstance(data.get(k),str) and data[k] for k in ('upstream_model','public_model')):
        raise ValueError('model names required')
    for key in ('upstream_api_key','client_api_key'):
        value=os.environ.get(data[key+'_env'],'')
        if len(value)<16 or '\r' in value or '\n' in value: raise ValueError('credential environment variable missing or invalid')
        data[key]=value
    timeout=data.get('timeout_seconds',45)
    if type(timeout) not in (int,float) or not 0 < timeout <= 60: raise ValueError('timeout must be within 60 seconds')
    if type(data.get('disable_thinking',False)) is not bool: raise ValueError('disable_thinking must be boolean')
    return data


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--port',type=int,default=9474)
    args=parser.parse_args()
    try:
        server=make_server(load_config(args.config),args.port)
        print(f'CyberTrack local relay on 127.0.0.1:{server.server_port}; no platform binding',flush=True)
        server.serve_forever()
    except (ValueError, KeyError, OSError):
        raise SystemExit('Relay configuration/start failed; check local configuration without sharing credentials') from None
    except KeyboardInterrupt:
        server.server_close()
