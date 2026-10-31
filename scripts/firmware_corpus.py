"""Project generated intent fixtures onto a frozen host's declared wire format.

Never apply this to a captured trace. Wire replay must preserve actual arguments.
"""
import copy
import hashlib
import json


def expected_commands(executable, commands):
    manifest=json.loads((executable.parent/'manifest.json').read_bytes())
    if manifest['executable_sha256']!=hashlib.sha256(executable.read_bytes()).hexdigest():
        raise ValueError('host differs from its manifest')
    mode=manifest.get('step_argument_format','legacy_string')
    if mode not in ('legacy_string','native_array'):raise ValueError('unknown host step contract')
    result=copy.deepcopy(commands)
    if mode=='legacy_string':return result
    for command in result:
        if command.get('name','').replace('self_tank_','self.tank.',1) not in ('self.tank.compose','self.tank.sequence'):continue
        args=command.get('arguments')
        if not isinstance(args,dict) or 'steps_json' not in args:continue
        if 'steps' in args:raise ValueError('fixture contains both step representations')
        encoded=args['steps_json']
        if not isinstance(encoded,str):continue  # Retain a malformed fixture for rejection.
        try:steps=json.loads(encoded) if encoded else []
        except ValueError:continue
        args.pop('steps_json');args['steps']=steps
    return result
