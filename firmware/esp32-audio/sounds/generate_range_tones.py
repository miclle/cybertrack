#!/usr/bin/env python3
"""Generate local radar tones; requires FFmpeg with libopus, no speech or recording."""
import math
from pathlib import Path
import struct
import subprocess
import tempfile
import wave

RATE = 16000
FREQUENCY = 1400
AMPLITUDE = 0.18
BEEP_MS = 80
FADE_MS = 5


def samples(starts_ms, duration_ms):
    for i in range(RATE * duration_ms // 1000):
        value = 0.0
        for start in starts_ms:
            offset = i - RATE * start // 1000
            length = RATE * BEEP_MS // 1000
            if 0 <= offset < length:
                fade = RATE * FADE_MS // 1000
                envelope = min(1.0, offset / fade, (length - 1 - offset) / fade)
                value = AMPLITUDE * envelope * math.sin(2 * math.pi * FREQUENCY * offset / RATE)
        yield round(32767 * value)


def main():
    root = Path(__file__).resolve().parent
    for name, starts, duration in [('beep', [0], 120), ('stop', [0, 140, 280], 420)]:
        with tempfile.TemporaryDirectory(prefix='range-tone-') as tmp:
            source = Path(tmp) / 'tone.wav'
            with wave.open(str(source), 'wb') as out:
                out.setparams((1, 2, RATE, 0, 'NONE', 'not compressed'))
                out.writeframes(b''.join(struct.pack('<h', n) for n in samples(starts, duration)))
            subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(source), '-map_metadata', '-1',
                            '-c:a', 'libopus', '-b:a', '20k', '-frame_duration', '60',
                            str(root / f'range-{name}.ogg')], check=True)


if __name__ == '__main__':
    main()
