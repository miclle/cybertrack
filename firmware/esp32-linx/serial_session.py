#!/usr/bin/env python3
"""Hold one non-resetting serial connection; never log Wi-Fi or activation secrets."""
import argparse
import datetime
import json
import os
from pathlib import Path
import re
import select
import socket

ROOT = Path(__file__).resolve().parents[2]
PRIVATE = ROOT / 'build/linx-private'
SOCKET = PRIVATE / 'control.sock'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port')
    parser.add_argument('--wifi', type=Path)
    parser.add_argument('--command', choices=['s', 'status', 'stop', 'water'])
    args = parser.parse_args()
    if args.command:
        with socket.socket(socket.AF_UNIX) as client:
            client.connect(str(SOCKET))
            client.sendall(args.command.encode())
            print(client.recv(100).decode())
        return
    import serial
    os.umask(0o077)
    PRIVATE.mkdir(parents=True, exist_ok=True)
    if SOCKET.exists():
        raise SystemExit('Existing control socket; check its owner before removing it.')
    if not args.port or not args.wifi:
        parser.error('--port and --wifi required')
    cfg = json.loads(args.wifi.read_text())
    if not isinstance(cfg.get('ssid'), str) or not 0 < len(cfg['ssid'].encode()) <= 32:
        raise SystemExit('Invalid Wi-Fi SSID length')
    if not isinstance(cfg.get('password'), str) or len(cfg['password'].encode()) > 63:
        raise SystemExit('Invalid Wi-Fi password length')
    encoded = json.dumps({k: cfg[k] for k in ('ssid', 'password')}, ensure_ascii=False).encode() + b'\n'
    if len(encoded) >= 512:
        raise SystemExit('Configuration exceeds serial frame size')
    device = serial.Serial(port=None, baudrate=115200, timeout=0, exclusive=True)
    device.dtr = False
    device.rts = False
    device.port = args.port
    device.open()
    server = socket.socket(socket.AF_UNIX)
    server.bind(str(SOCKET))
    server.listen(1)
    pending = bytearray()
    configured = False
    activation = ROOT / 'secrets/linx-activation.txt'
    with (PRIVATE / 'session.log').open('a', buffering=1) as log:
        def report(text):
            stamp = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat()
            line = stamp + ' ' + text
            print(line, flush=True)
            log.write(line + '\n')
        report('SESSION_OPEN no DTR/RTS reset')
        try:
            while True:
                ready, _, _ = select.select([device.fileno(), server], [], [], 1)
                if server in ready:
                    with server.accept()[0] as client:
                        cmd = client.recv(32).decode(errors='replace')
                        if cmd in ('s', 'status', 'stop', 'water'):
                            device.write(cmd.encode() + b'\n')
                            client.sendall(b'command sent; verify device reply')
                            report('HOST_COMMAND ' + cmd)
                if device.fileno() in ready:
                    pending.extend(device.read(device.in_waiting or 1))
                    while b'\n' in pending:
                        raw, _, pending = pending.partition(b'\n')
                        text = raw.decode(errors='replace').strip()
                        code = re.fullmatch(r'LINX ACTIVATION_CODE (\d{6})', text)
                        if code:
                            activation.write_text(code[1] + '\n')
                            activation.chmod(0o600)
                            report('LINX ACTIVATION_REQUIRED code saved privately')
                        elif text.startswith('LINX '):
                            report(text)
                            if text == 'LINX BOUND' and activation.exists():
                                activation.unlink()
                            if 'WIFI_CONFIG_REQUIRED' in text and not configured:
                                device.write(encoded)
                                configured = True
                                report('WIFI_CONFIG_SENT values withheld')
                    if len(pending) > 16384:
                        pending.clear()
        finally:
            device.write(b's\n')
            device.close()
            server.close()
            SOCKET.unlink(missing_ok=True)

if __name__ == '__main__':
    main()
