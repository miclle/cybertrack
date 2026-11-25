#!/usr/bin/env python3
"""Check the dual-track inhibit against the A4 manufacturing pin groups."""
import json
from pathlib import Path
from zipfile import ZipFile


GERBER = Path(__file__).resolve().parents[1] / 'hardware/pcb/CyberTrack-A4-Gerber.zip'
# Each group must be connected internally and isolated from every other group.
GROUPS = {
    'ARM_CLK': 'U1_26 U10_1 U27_1',
    'ACT_CLR_N': 'U10_6 U25_1 J16_2',
    'ACT_ARMED': 'U10_5 Q6_1 U6_3 U24_3 U27_2 U28_10',
    '12V_MOTOR': 'L5_2 U6_11 U24_11 R82_1',
    'VM_SENSE': 'R82_2 R83_1 U25_4',
    'VM_GOOD_N': 'U25_6 R81_2 U21_11',
    'VM_GOOD': 'U21_10 U28_9',
    'TRACK_READY': 'U28_8 R78_2 R80_2',
    'TRACK_CLR_N': 'U6_4 U24_4 R78_1 R80_1 U27_6',
    'DRIVE_ARMED': 'U27_5 U1_31 U28_2 U28_5',
    'MOTOR_A_EN': 'U1_12 U28_1',
    'MOTOR_B_EN': 'U1_19 U28_4',
    'PWM_A_SAFE': 'U28_3 U26_1 U26_4',
    'PWM_B_SAFE': 'U28_6 U26_9 U26_12',
    'MA_IN1': 'U26_3 U6_1',
    'MA_IN2': 'U26_6 U6_2',
    'MB_IN1': 'U26_8 U24_1',
    'MB_IN2': 'U26_11 U24_2',
    '3V3_CTRL': 'U27_7 U27_8 U28_14 R81_1 C113_1 C114_1',
    'GND_SYS': 'U27_4 U28_7 U28_12 U28_13 R83_2 C113_2 C114_2',
}


def check(archive):
    with ZipFile(archive) as gerber:
        rows = json.loads(gerber.read('FlyingProbeTesting.json'))['pins']['rows']
    pins = {}
    for row in rows:
        pins.setdefault(row[1], set()).add(row[6])
    occupied = {}
    for net, members in GROUPS.items():
        groups = set()
        for pin in members.split():
            if len(pins.get(pin, ())) != 1:
                raise ValueError(f'{net}: missing or ambiguous pin {pin}')
            groups.update(pins[pin])
        if len(groups) != 1:
            raise ValueError(f'{net}: split across probe groups {groups}')
        group = groups.pop()
        if not group or group in occupied:
            raise ValueError(f'{net}: empty or shared group with {occupied.get(group)}')
        occupied[group] = net


if __name__ == '__main__':
    check(GERBER)
    print(f'PASS: {len(GROUPS)} distinct A4 interlock and drive pin groups')
