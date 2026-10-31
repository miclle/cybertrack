"""Generate clean-room Mandarin speech for the v1 Lingxi 16 kHz Opus uplink."""
import hashlib
from pathlib import Path
import subprocess
import tempfile

FRAME_MS = 60
VOICE = 'Tingting'
RATE = 180


def split_packets(payload, frame_list):
    """FFmpeg's tee muxer writes identical packets to its data and framecrc outputs."""
    packets, offset = [], 0
    for row in frame_list.splitlines():
        if not row or row.startswith('#'):
            continue
        size = int(row.split(',')[4])
        packet = payload[offset:offset + size]
        if size <= 0 or len(packet) != size:
            raise ValueError('Truncated or empty Opus packet')
        packets.append(packet)
        offset += size
    if not packets or offset != len(payload):
        raise ValueError('Encoded audio and packet index differ')
    return packets


def synthesize(text):
    with tempfile.TemporaryDirectory(prefix='cybertrack-tts-') as tmp:
        subprocess.run(['say', '-v', VOICE, '-r', str(RATE), '-o', 'phrase.aiff', '--', text],
                       cwd=tmp, check=True, capture_output=True, timeout=20)
        subprocess.run(['ffmpeg', '-v', 'error', '-i', 'phrase.aiff', '-map', '0:a:0',
                        '-af', 'adelay=180,apad=pad_dur=0.24', '-ar', '16000', '-ac', '1',
                        '-c:a', 'libopus', '-application', 'voip', '-frame_duration', str(FRAME_MS),
                        '-b:a', '24k', '-f', 'tee', '[f=data]audio.bin|[f=framecrc]frames.csv'],
                       cwd=tmp, check=True, capture_output=True, timeout=20)
        payload = Path(tmp, 'audio.bin').read_bytes()
        packets = split_packets(payload, Path(tmp, 'frames.csv').read_text())
    metadata = dict(voice=VOICE, words_per_minute=RATE, codec='opus', sample_rate_hz=16000,
                    channels=1, frame_ms=FRAME_MS, frames=len(packets), encoded_bytes=len(payload),
                    payload_sha256=hashlib.sha256(payload).hexdigest())
    return packets, metadata
