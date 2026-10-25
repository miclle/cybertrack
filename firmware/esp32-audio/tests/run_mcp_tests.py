#!/usr/bin/env python3
"""Compile the actual overlaid MCP validation block against ESP-IDF's cJSON."""
import argparse
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
subprocess.run(['c++', '-std=c++17', *flags, '-I', str(cjson), '-I', str(build),
                str(Path(__file__).with_name('mcp_arguments_test.cc')), str(build/'cJSON.o'),
                '-o', str(build/'mcp_arguments_test')], check=True)
subprocess.run([str(build/'mcp_arguments_test')], check=True)
