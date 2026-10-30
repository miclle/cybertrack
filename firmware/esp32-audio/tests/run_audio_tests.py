#!/usr/bin/env python3
"""Test the actual overlaid audio methods with controlled decoder/output scheduling."""
from pathlib import Path
import argparse
import subprocess
p = argparse.ArgumentParser()
p.add_argument('--source', required=True, type=Path)
a = p.parse_args()
root = Path(__file__).resolve().parents[3]
build = root / 'build/audio-host'
s = (a.source/'main/audio/audio_service.cc').read_text()
parts=[]
for signature in ('bool AudioService::PushPacketToDecodeQueue(', 'void AudioService::PlaySound(', 'void AudioService::ResetDecoder('):
    start=s.index(signature); end=s.index('\n}',start)+2
    parts.append(s[start:end])
(build/'priority_audio_methods.inc').write_text('\n'.join(parts))
subprocess.run(['c++','-std=c++17','-g','-fsanitize=address,undefined','-pthread','-I',str(build),str(Path(__file__).with_name('priority_audio_test.cc')),'-o',str(build/'priority_audio_test')],check=True)
for name in ('beep','stop'):
    subprocess.run([str(build/'priority_audio_test'),str(root/f'firmware/esp32-audio/sounds/range-{name}.ogg')],check=True,timeout=15)

stubs = build / 'tone-stubs'
for name in ('application.h', 'proximity_sounds.h', 'freertos/FreeRTOS.h',
             'freertos/queue.h', 'freertos/task.h', 'esp_timer.h', 'esp_log.h'):
    path = stubs / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('#include "proximity_audio_stub.h"\n')
subprocess.run(['c++', '-std=c++17', '-g', '-fsanitize=address,undefined', '-Wall', '-Wextra', '-Werror',
                '-I', str(stubs), '-I', str(Path(__file__).parent),
                str(Path(__file__).with_name('proximity_audio_test.cc')),
                '-o', str(build/'proximity_audio_test')], check=True)
subprocess.run([str(build/'proximity_audio_test')], check=True, timeout=15)
