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
subprocess.run(['c++', '-std=c++17', *flags, '-I', str(cjson), '-I', str(build),
                '-I', str(root/'firmware/esp32-audio'), '-I', str(root/'firmware/esp32-linx/main'),
                str(Path(__file__).with_name('receipt_adapter_test.cc')), str(build/'cJSON.o'),
                str(build/'receipt_water_policy.o'), '-o', str(build/'receipt_adapter_test')], check=True)
subprocess.run([str(build/'receipt_adapter_test')], check=True)
