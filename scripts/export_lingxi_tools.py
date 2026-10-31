#!/usr/bin/env python3
"""Export robot schemas with the prepared firmware's actual MCP serializer.

Callbacks are replaced by an inert return before compilation. No device is opened.
"""
import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def export(source, idf, output):
    source = source.resolve()
    header = source / 'main/mcp_server.h'
    registration = ROOT / 'firmware/esp32-audio/cybertrack_tools.cc'
    prepared = source / 'main/boards/bread-compact-wifi/cybertrack_tools.cc'
    if prepared.read_bytes() != registration.read_bytes():
        raise ValueError('prepared tool registrations differ from repository source')
    text = registration.read_text()
    declarations = re.findall(r'server\.AddTool\((.*?)\s*,\s*\[\]\(const PropertyList&', text, re.S)
    if len(declarations) != 12:
        raise ValueError('expected exactly 12 robot registrations; inspect source changes')
    build = ROOT / 'build/lingxi-schema-export'
    (build / 'mbedtls').mkdir(parents=True, exist_ok=True)
    # Image encoding is not used by robot schema serialization.
    (build / 'mbedtls/base64.h').write_text('#include <stddef.h>\nint mbedtls_base64_encode(unsigned char*, size_t, size_t*, const unsigned char*, size_t);\n')
    rows = []
    for declaration in declarations:
        if not declaration.lstrip().startswith('"self.tank.'):
            raise ValueError('unexpected registration')
        rows.append('emit(McpTool(' + declaration + ', [](const PropertyList&) -> ReturnValue { return std::string("capture only"); }));')
    cpp = '#include <climits>\n#include <iostream>\n#include "mcp_server.h"\nint main(){bool first=true; std::cout<<"["; auto emit=[&](const McpTool& t){if(!first)std::cout<<",";first=false;std::cout<<t.to_json();};\n'
    cpp += '\n'.join(rows) + '\nstd::cout<<"]\\n";}\n'
    (build / 'export.cc').write_text(cpp)
    cjson = idf / 'components/json/cJSON'
    subprocess.run(['cc', '-c', '-I', str(cjson), str(cjson/'cJSON.c'), '-o', str(build/'cJSON.o')], check=True, capture_output=True)
    subprocess.run(['c++', '-std=c++17', '-I', str(build), '-I', str(header.parent), '-I', str(cjson), str(build/'export.cc'), str(build/'cJSON.o'), '-o', str(build/'export')], check=True, capture_output=True)
    schemas = json.loads(subprocess.check_output([str(build/'export')], text=True))
    if len({s['name'] for s in schemas}) != 12:
        raise ValueError('duplicate tool schemas')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({'scope':'host export, inert callbacks; not remote discovery', 'source_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [header,registration]}, 'tools':schemas}, ensure_ascii=False, indent=2)+'\n')
    return schemas


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--idf', type=Path, default=Path.home()/'esp/esp-idf')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print('Exported',len(export(args.source,args.idf,args.output)),'robot schemas without callbacks')
