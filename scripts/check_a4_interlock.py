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


# Further board signals used by the dedicated ESP32-S3 image. The exporter
# may rename nets to NET_n; compare component-pad equivalence classes.
FIRMWARE_GROUPS = {
    'MOTOR_A_IN1': 'U12_4 U26_2', 'MOTOR_A_IN2': 'U12_5 U26_5',
    'MOTOR_B_IN1': 'U12_6 U26_10', 'MOTOR_B_IN2': 'U12_7 U26_13',
    'BOOT_STOP_N': 'U1_27 J6_1', 'AUX_EN': 'U1_22 R38_1',
    'WATER_EN': 'U1_11 R32_1', 'BUBBLE_EN': 'U1_10 R35_1',
    'TALK': 'U12_8 J4_2', 'VOL_DN': 'U12_9 J4_4', 'VOL_UP': 'U12_10 J4_3',
    'OLED_SCL': 'U1_35 U12_22 J2_3', 'OLED_SDA': 'U1_34 U12_23 J2_4',
    'MIC_SCK': 'U1_5 U18_2', 'MIC_DATA': 'U1_6 U18_3',
    'AMP_DATA': 'U1_7 U2_1', 'AMP_BCLK': 'U1_8 U2_16', 'AMP_LRCK': 'U1_9 U2_14',
    'US_TRIG': 'U1_39 J3_2', 'US_ECHO': 'U1_38 J3_3',
}


def check(archive):
    with ZipFile(archive) as gerber:
        rows = json.loads(gerber.read('FlyingProbeTesting.json'))['pins']['rows']
    pins = {}
    for row in rows:
        pins.setdefault(row[1], set()).add(row[6])
    occupied = {}
    for net, members in (GROUPS | FIRMWARE_GROUPS).items():
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
    print(f'PASS: {len(GROUPS)} interlock groups and {len(FIRMWARE_GROUPS)} additional firmware pin groups')
