#!/usr/bin/env python3
"""Generate the review-only, module-level KiCad schematic. No footprints or PCB.

The .kicad_sch files are editable deliverables. Regeneration overwrites them;
merge intentional edits here before using this script again.
"""

import json
from pathlib import Path
import uuid

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'hardware' / 'schematic'
PROJECT = 'CyberTrack'
INPUTS = json.loads((OUT / 'design-inputs.json').read_text())
REVISION = INPUTS['revision']
NS = uuid.UUID('38a02f73-5144-42b8-bdb6-ae67a5c4d045')


def uid(key):
    return str(uuid.uuid5(NS, key))


def q(value):
    return json.dumps(str(value), ensure_ascii=False)


def mm(value):
    return f'{value * 2.54:.4f}'.rstrip('0').rstrip('.')


def effects(size=0.5, justify='', hide=False):
    return (f'(effects (font (size {mm(size)} {mm(size)}))'
            + (f' (justify {justify})' if justify else '')
            + (' (hide yes)' if hide else '') + ')')


# Pin IDs are logical identities / module silkscreen, never connector pad numbers.
def pin(number, name, side, offset, kind='passive'):
    return dict(number=number, name=name, side=side, offset=offset, kind=kind)


LIB = {}


def module(name, width, height, pins, drawing='box', units=None):
    LIB[name] = dict(width=width, height=height, pins=pins, drawing=drawing,
                     units=units)


motor_nets = ['MOTOR_A_EN', 'MOTOR_A_IN1', 'MOTOR_A_IN2',
              'MOTOR_B_EN', 'MOTOR_B_IN1', 'MOTOR_B_IN2']
action_nets = motor_nets + ['WATER_EN', 'BUBBLE_EN', 'IGNITION_EN']
action_gpios = [8, 9, 10, 11, 12, 13, 18, 17, 21]
peripherals = [('4', 'MIC_WS', 'output'), ('5', 'MIC_SCK', 'output'),
               ('6', 'MIC_DATA', 'input'), ('7', 'AMP_DATA', 'output'),
               ('15', 'AMP_BCLK', 'output'), ('16', 'AMP_LRCK', 'output'),
               ('41', 'OLED_SDA', 'bidirectional'), ('42', 'OLED_SCL', 'output'),
               ('47', 'TALK_INPUT', 'input'), ('40', 'VOLUME_UP', 'input'),
               ('39', 'VOLUME_DOWN', 'input')]
unit1 = [pin('5Vin', '5Vin', 'L', -10, 'power_in'),
         pin('GND', 'GND', 'L', -6, 'passive'),
         pin('IO0', 'BOOT / IO0', 'L', 6, 'input')]
unit1 += [pin(f'IO{g}', n, 'R', -16 + i * 4, 'output')
          for i, (g, n) in enumerate(zip(action_gpios, action_nets))]
unit2 = [pin(f'IO{g}', n, 'R', -20 + i * 4, kind)
         for i, (g, n, kind) in enumerate(peripherals)]
for p in unit1 + unit2:
    p['name'] += ' [' + INPUTS['controller_header']['positions'][p['number']] + ']'
module('Existing_ESP32S3', 11, 24, [], units={1: unit1, 2: unit2})
module('Retained_Peripherals', 8, 24,
       [pin(n, n, 'L', -20 + i * 4,
            {'input': 'output', 'output': 'input', 'bidirectional': 'bidirectional'}[kind])
        for i, (_, n, kind) in enumerate(peripherals)])
module('Battery5V', 7, 7,
       [pin('OUT+', 'OUT+', 'R', -3, 'power_out'), pin('OUT-', 'OUT-', 'R', 3)])
module('InputProtection_TBD', 8, 7,
       [pin('IN+', 'IN+', 'L', -3, 'power_in'), pin('RET', 'RETURN', 'L', 3),
        pin('OUT+', 'OUT+', 'R', -3, 'power_out')])
module('MasterPower_TBD', 9, 7,
       [pin('IN+', 'IN+', 'L', -3, 'power_in'), pin('GND', 'GND', 'L', 3),
        pin('OUT+', 'OUT+', 'R', -3, 'power_out'),
        pin('REQ_A', 'REQ_A', 'B', -3), pin('REQ_B', 'REQ_B', 'B', 3)])
module('Fuse', 2, 1, [pin('1', '1', 'L', 0), pin('2', '2', 'R', 0)], 'fuse')
module('Disconnect', 2, 1, [pin('A', 'A', 'L', 0), pin('B', 'B', 'R', 0)], 'switch')
module('ButtonNO', 2, 1, [pin('A', 'A', 'L', 0), pin('B', 'B', 'R', 0)], 'button')
module('Pulldown', 1, 2, [pin('1', '1', 'T', 0), pin('2', '2', 'B', 0)], 'resistor')
module('SupplyFlag', 0, 0, [pin('1', '', 'B', 0, 'power_out')], 'flag')
module('MT3608', 9, 9,
       [pin('IN+', 'IN+', 'L', -4, 'power_in'), pin('IN-', 'IN-', 'L', 4),
        pin('OUT+', 'OUT+', 'R', -4, 'power_out'), pin('OUT-', 'OUT-', 'R', 4)])
l298pins = [pin('+12V', '+12V / VS', 'L', -15, 'power_in'),
            pin('GND', 'GND', 'L', -11)]
l298pins += [pin(n, n, 'L', -5 + i * 4, 'input')
             for i, n in enumerate(['ENA', 'IN1', 'IN2', 'ENB', 'IN3', 'IN4'])]
l298pins += [pin(n, n, 'R', dy, 'output')
             for n, dy in [('OUT1', -12), ('OUT2', -8), ('OUT3', 0), ('OUT4', 4)]]
l298pins += [pin('+5V', '+5V - DO NOT CONNECT', 'R', 12, 'power_out')]
module('L298N_Module', 13, 19, l298pins)
module('DCMotor', 3, 5, [pin('A', 'A', 'L', -2), pin('B', 'B', 'L', 2)], 'motor')
module('JZ_MOS', 9, 11,
       [pin('VIN+', 'VIN+', 'L', -6, 'power_in'), pin('VIN-', 'VIN-', 'L', -2),
        pin('TRIG', 'TRIG/PWM', 'L', 2, 'input'), pin('GND', 'CTRL GND', 'L', 6),
        pin('VOUT+', 'VOUT+', 'R', -4, 'power_out'), pin('VOUT-', 'VOUT-', 'R', 4)])
module('P12_Buck', 8, 8,
       [pin('IN+', 'IN+', 'L', -4, 'power_in'), pin('GND', 'GND', 'L', 4),
        pin('VO+', 'VO+', 'R', -4, 'power_out')])
module('Load3V7', 7, 8, [pin('+', '+', 'L', -4, 'power_in'), pin('-', '-', 'L', 4)])
module('LV_Reserved', 10, 8,
       [pin('+', 'LV+ ONLY', 'L', -4), pin('-', 'LV- ONLY', 'L', 4)])


def pin_xy(spec, p):
    w, h, d = spec['width'], spec['height'], p['offset']
    return {'L': (-w - 3, d), 'R': (w + 3, d),
            'T': (d, -h - 3), 'B': (d, h + 3)}[p['side']]


def lib_symbol(name, qualified=True):
    spec = LIB[name]
    w, h = spec['width'], spec['height']
    result = [f'(symbol {q("CyberTrack:" + name if qualified else name)}',
              '(pin_names (offset 1.016)) (in_bom yes) (on_board yes)',
              f'(property "Reference" "U" (at 0 {mm(h + 3)} 0) {effects()})',
              f'(property "Value" {q(name)} (at 0 {mm(h + 1)} 0) {effects()})']
    for unit, pins in (spec['units'] or {1: spec['pins']}).items():
        result.append(f'(symbol {q(name + "_" + str(unit) + "_1")}')
        drawing = spec['drawing']
        if drawing in ('box', 'fuse', 'resistor'):
            result.append(f'(rectangle (start {mm(-w)} {mm(h)}) (end {mm(w)} {mm(-h)})'
                          ' (stroke (width 0.254) (type default)) (fill (type background)))')
        elif drawing == 'motor':
            result += ['(circle (center 0 0) (radius 7.62) (stroke (width 0.254)'
                       ' (type default)) (fill (type background)))',
                       f'(text "M" (at 0 0 0) {effects(0.8)})']
        elif drawing in ('switch', 'button'):
            result += ['(polyline (pts (xy -5.08 0) (xy 4.064 3.048))'
                       ' (stroke (width 0.254) (type default)) (fill (type none)))']
            if drawing == 'button':
                result += ['(polyline (pts (xy 0 3.048) (xy 0 5.08)'
                           ' (xy -2.54 5.08) (xy 2.54 5.08))'
                           ' (stroke (width 0.254) (type default)) (fill (type none)))']
        elif drawing == 'flag':
            result += ['(polyline (pts (xy 0 0) (xy -1.27 1.27) (xy 0 2.54)'
                       ' (xy 1.27 1.27) (xy 0 0))'
                       ' (stroke (width 0.254) (type default)) (fill (type none)))']
        for p in pins:
            x, y = pin_xy(spec, p)
            angle = {'L': 0, 'R': 180, 'T': 270, 'B': 90}[p['side']]
            result.append(f'(pin {p["kind"]} line (at {mm(x)} {mm(-y)} {angle})'
                          f' (length 7.62) (name {q(p["name"])} {effects(0.45)})'
                          f' (number {q(p["number"])} {effects(0.4)}))')
        result.append(')')
    return '\n'.join(result + [')'])


class Sheet:
    def __init__(self, filename, title, page):
        self.filename, self.title, self.page = filename, title, page
        self.id = uid(filename)
        self.items, self.used, self.parts = [], set(), []
        self.sequence = 0

    def new_id(self):
        self.sequence += 1
        return uid(f'{self.filename}/{self.sequence}')

    def text(self, text, x, y, size=0.55):
        size = max(size, 0.65)
        self.items.append(f'(text {q(text)} (at {mm(x)} {mm(y)} 0)'
                          f' {effects(size, "left top")} (uuid {self.new_id()}))')

    def wire(self, a, b):
        assert a != b
        assert a[0] == b[0] or a[1] == b[1], (a, b)
        self.items.append(f'(wire (pts (xy {mm(a[0])} {mm(a[1])})'
                          f' (xy {mm(b[0])} {mm(b[1])}))'
                          f' (stroke (width 0) (type default)) (uuid {self.new_id()}))')

    def net(self, name, at, end=None, angle=0):
        if end is not None:
            self.wire(at, end)
            at = end
        self.items.append(f'(global_label {q(name)} (shape passive)'
                          f' (at {mm(at[0])} {mm(at[1])} {angle})'
                          f' {effects(0.55, "left" if angle == 0 else "right")} (uuid {self.new_id()})'
                          f' (property "Intersheetrefs" "${{INTERSHEET_REFS}}"'
                          f' (at {mm(at[0])} {mm(at[1])} 0) {effects(hide=True)}))')

    def local(self, name, at):
        self.items.append(f'(label {q(name)} (at {mm(at[0])} {mm(at[1])} 0)'
                          f' {effects(0.5, "left bottom")} (uuid {self.new_id()}))')

    def nc(self, at):
        self.items.append(f'(no_connect (at {mm(at[0])} {mm(at[1])})'
                          f' (uuid {self.new_id()}))')

    def part(self, kind, ref, value, x, y, unit=1, dnp=False, title_offset=None):
        spec = LIB[kind]
        self.used.add(kind)
        instance = self.new_id()
        dy = title_offset if title_offset is not None else spec['height'] + 5
        flag = kind == 'SupplyFlag'
        tx, ty, align = x, y - dy, ''
        if kind == 'Pulldown':
            tx, ty, align = x + 3, y - 1, 'left'
        elif kind == 'DCMotor':
            tx, ty, align = x + 7, y - 1, 'left'
        props = [f'(property "Reference" {q(ref)} (at {mm(tx)} {mm(ty)} 0)'
                 f' {effects(0.65, align, hide=flag)})',
                 f'(property "Value" {q(value)} (at {mm(tx)} {mm(ty + 2.5)} 0)'
                 f' {effects(0.6, align, hide=flag)})',
                 f'(property "Footprint" "" (at {mm(x)} {mm(y)} 0) {effects(hide=True)})',
                 f'(property "Description" "Logical module interface; no pad mapping frozen"'
                 f' (at {mm(x)} {mm(y)} 0) {effects(hide=True)})']
        # Modules and hypothetical parts are deliberately not transferable to a PCB.
        self.items.append(f'(symbol (lib_id {q("CyberTrack:" + kind)})'
                          f' (at {mm(x)} {mm(y)} 0) (unit {unit})'
                          ' (in_bom no) (on_board no)'
                          f' (dnp {"yes" if dnp else "no"}) (uuid {instance})'
                          + '\n'.join(props)
                          + f'(instances (project "{PROJECT}" (path "{self.path()}"'
                          f' (reference {q(ref)}) (unit {unit}))))' + ')')
        pins = (spec['units'] or {1: spec['pins']})[unit]
        self.parts.append(dict(ref=ref, unit=unit, kind=kind, value=value, dnp=dnp))
        return {p['number']: (x + pin_xy(spec, p)[0], y + pin_xy(spec, p)[1]) for p in pins}

    def path(self):
        return '/' + uid('CyberTrack.kicad_sch') + ('' if self.page == 1 else '/' + uid('sheet/' + self.filename))

    def save(self):
        header = (f'(kicad_sch (version 20250114) (generator "cybertrack_schematic")'
                  f' (uuid {self.id}) (paper "A3")'
                  f' (title_block (title {q(self.title)}) (date "2026-10-26")'
                  f' (rev {q(REVISION)}) (company "CyberTrack")'
                  ' (comment 1 "MODULE INTERCONNECTION SCHEMATIC - NOT FOR FABRICATION")'
                  ' (comment 2 "Retain existing ESP32-S3 board; TBD items are unresolved")'
                  ' (comment 3 "Pin IDs identify signals, NOT physical header positions"))')
        library = '(lib_symbols\n' + '\n'.join(lib_symbol(n) for n in sorted(self.used)) + ')'
        root_instance = '(sheet_instances (path "/" (page "1")))' if self.page == 1 else ''
        (OUT / self.filename).write_text(header + '\n' + library + '\n' + '\n'.join(self.items)
                                        + root_instance + '\n)\n')

    def child(self, other, x, y):
        self.items.append(f'(sheet (at {mm(x)} {mm(y)}) (size 63.5 12.7)'
                          ' (stroke (width 0.254) (type default)) (fill (color 0 0 0 0))'
                          f' (uuid {uid("sheet/" + other.filename)})'
                          f' (property "Sheetname" {q(other.title.split(" / ")[1])}'
                          f' (at {mm(x)} {mm(y-1)} 0) {effects(0.5, "left bottom")})'
                          f' (property "Sheetfile" {q(other.filename)}'
                          f' (at {mm(x)} {mm(y+6)} 0) {effects(0.45, "left top")})'
                          f' (instances (project "{PROJECT}" (path "/{self.id}"'
                          f' (page "{other.page}")))))')


def stub(sheet, pins, number, name, side='L', length=4):
    x, y = pins[number]
    sheet.net(name, (x, y), (x - length if side == 'L' else x + length, y),
              angle=180 if side == 'L' else 0)


flag_count = 0


def supply(sheet, name, x, y):
    global flag_count
    flag_count += 1
    p = sheet.part('SupplyFlag', f'#FLG{flag_count:02}', 'PWR_FLAG', x, y)
    sheet.net(name, p['1'], (x, y + 5))


def pulldown(sheet, ref, net, x, y):
    value = INPUTS['motor_pulldowns']['value'] if ref in INPUTS['motor_pulldowns']['references'] else 'TBD'
    p = sheet.part('Pulldown', ref, value, x, y)
    sheet.net(net, p['1'], (x, y - 7))
    sheet.net('GND_SYS', p['2'], (x, y + 7))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    power = Sheet('CyberTrack.kicad_sch', 'CyberTrack / Power and isolation', 1)
    control = Sheet('control.kicad_sch', 'CyberTrack / ESP32-S3 and BOOT', 2)
    drive = Sheet('drive.kicad_sch', 'CyberTrack / Motor drive', 3)
    effects_sheet = Sheet('effects.kicad_sch', 'CyberTrack / Water and bubbles', 4)
    ignition = Sheet('ignition-lv.kicad_sch', 'CyberTrack / Reserved ignition LV', 5)
    sheets = [power, control, drive, effects_sheet, ignition]

    power.text('01  POWER INPUT AND DISTRIBUTION', 8, 7, 0.9)
    power.text('A1 design candidate. Protection / switching blocks are NOT implemented circuits.', 8, 11)
    p = power.part('Battery5V', 'BT1', 'CK18650-1234S-NP / 5 V', 17, 25)
    f = power.part('Fuse', 'F1', 'RATING TBD', 34, 22)
    power.wire(p['OUT+'], f['1'])
    stub(power, p, 'OUT-', 'GND_SYS', 'R', length=2)
    a = power.part('InputProtection_TBD', 'U2', 'PROTECTION / TBD', 54, 25)
    power.wire(f['2'], (41, 22))
    power.wire((41, 22), a['IN+'])
    power.part('SupplyFlag', '#FLG00', 'PWR_FLAG', 41, 19)
    power.items.append(f'(junction (at {mm(41)} {mm(22)}) (diameter 0)'
                       f' (color 0 0 0 0) (uuid {power.new_id()}))')
    stub(power, a, 'RET', 'GND_SYS', length=2)
    b = power.part('MasterPower_TBD', 'U3', 'MASTER POWER / TBD', 87, 25)
    power.wire(a['OUT+'], b['IN+'])
    stub(power, b, 'GND', 'GND_SYS')
    stub(power, b, 'OUT+', '5V_SYS', 'R')
    sw = power.part('Disconnect', 'SW1', 'MASTER REQUEST / CONTACTS TBD', 87, 44)
    for number, contact in [('REQ_A', 'A'), ('REQ_B', 'B')]:
        x, y = b[number]
        sx, sy = sw[contact]
        power.wire((x, y), (x, sy))
        power.wire((x, sy), (sx, sy))
    power.text('SW1: low-current request candidate; contact mapping TBD.\nDo not route the total load through the unverified slide switch.\nU2/U3: selection, thresholds, reverse current and fail-off design are unresolved.', 8, 36, 0.5)
    power.text('BATTERY: output polarity / continuous current / protection not verified. Charging port excluded.', 8, 48, 0.5)

    f = power.part('Fuse', 'F2', 'TBD', 28, 60)
    stub(power, f, '1', '5V_SYS', length=3)
    jp = power.part('Disconnect', 'JP1', 'CTRL SERVICE LINK', 53, 60)
    power.wire(f['2'], jp['A'])
    stub(power, jp, 'B', '5V_CTRL', 'R')
    power.text('OPEN JP1 for USB service. Do not power USB and 5Vin together.', 8, 65, 0.5)
    f = power.part('Fuse', 'F3', 'TBD', 28, 77)
    stub(power, f, '1', '5V_SYS', length=3)
    sw = power.part('Disconnect', 'SW2', 'ACTUATOR ISOLATOR / TBD', 53, 77)
    power.wire(f['2'], sw['A'])
    stub(power, sw, 'B', '5V_ACT', 'R')
    power.text('SW2: ACTUATORS ONLY; controller remains powered (confirmed).\nDevice rating TBD; no MCU required to open. Re-arm / stored energy unverified.', 8, 82, 0.5)
    for i, name in enumerate(['5V_MOTOR_IN', '5V_WATER_IN', '5V_BUBBLE_IN', '5V_IGN_FUSED']):
        y = 58 + 10 * i
        f = power.part('Fuse', f'F{i+4}', 'TBD', 121, y)
        stub(power, f, '1', '5V_ACT', length=5)
        stub(power, f, '2', name, 'R', length=4)
    power.text('All four action groups may run concurrently.\nFuse / wire / connector ratings require a measured input budget.', 99, 94, 0.48)
    for i, name in enumerate(['GND_SYS', '5V_CTRL', '5V_MOTOR_IN', '5V_WATER_IN', '5V_BUBBLE_IN']):
        supply(power, name, 113 + 10 * i, 39)
    power.text('PWR_FLAG marks intended supply paths for ERC only; it is not measured power evidence.', 99, 48, 0.45)
    for other, x in zip(sheets[1:], [8, 35, 62, 89]):
        power.child(other, x, 100)

    control.text('02  EXISTING DEVELOPMENT BOARD AND RETAINED PERIPHERALS', 8, 7, 0.85)
    control.text('U1A and U1B are the SAME board. USB, regulator, reset, radio and on-board LED remain inside U1.', 8, 12)
    a = control.part('Existing_ESP32S3', 'U1', 'Existing ESP32-S3', 45, 48, 1)
    stub(control, a, '5Vin', '5V_CTRL')
    stub(control, a, 'GND', 'GND_SYS')
    for gpio, net in zip(action_gpios, action_nets):
        stub(control, a, f'IO{gpio}', net, 'R', length=4)
    sw = control.part('ButtonNO', 'SW3', 'BOOT / NO MOMENTARY', 20, 54)
    control.wire(sw['B'], a['IO0'])
    stub(control, sw, 'A', 'GND_SYS', length=3)
    control.local('BOOT_STOP_N', (25, 54))
    b = control.part('Existing_ESP32S3', 'U1', 'Existing ESP32-S3', 105, 48, 2)
    x = control.part('Retained_Peripherals', 'X1', 'RETAINED ASSEMBLY', 146, 48)
    for gpio, name, _ in peripherals:
        control.wire(b[f'IO{gpio}'], x[name])
    control.text('X1 is a LOGICAL interface, not a new 11-pin connector.\nExisting mic / amplifier / OLED / buttons retain their wiring.\nPeripheral power and auxiliary pins are not reconstructed.\nDo not infer module VCC or speaker grounding from this sheet.', 91, 78, 0.52)
    control.text('BOOT: dry contact to system ground; parallel to on-board BOOT.\nIt stops software actions. It does NOT isolate actuator power.\nHolding BOOT during reset may select ROM download mode.\nNo external pull-up / RC values are frozen here.', 8, 80, 0.52)
    control.text('PIN ID: IO8 = GPIO8; [L12] = photo-based header position.\nComponent side facing you, antenna UP, USB DOWN.\nL/R rows counted 1-22 from antenna to USB; verify continuity.\nNo new encoder / ultrasonic / servo GPIO allocation.', 8, 94, 0.52)
    control.text('Source: action_outputs.h + cybertrack_tools.cc (ct19).\nRetained peripherals: bread-compact-wifi/config.h.\nFirmware pin identity does not prove physical wiring.\nA1: no PCB transfer; see parameter-confirmation.md (E01-E10).', 91, 94, 0.52)

    drive.text('03  EXTERNAL BOOST CONVERTER AND DUAL H-BRIDGE', 8, 7, 0.85)
    boost = drive.part('MT3608', 'U4', 'MT3608 / TARGET 12 V', 31, 33)
    stub(drive, boost, 'IN+', '5V_MOTOR_IN')
    stub(drive, boost, 'IN-', 'GND_SYS')
    stub(drive, boost, 'OUT+', '12V_MOTOR', 'R')
    stub(drive, boost, 'OUT-', 'GND_SYS', 'R')
    h = drive.part('L298N_Module', 'U5', 'P13 / L298N', 88, 39)
    stub(drive, h, '+12V', '12V_MOTOR')
    stub(drive, h, 'GND', 'GND_SYS')
    for terminal, net in zip(['ENA', 'IN1', 'IN2', 'ENB', 'IN3', 'IN4'], motor_nets):
        stub(drive, h, terminal, net)
    drive.nc(h['+5V'])
    m1 = drive.part('DCMotor', 'M1', '37R-520 / A', 139, 29)
    m2 = drive.part('DCMotor', 'M2', '37R-520 / B', 139, 41)
    for hp, mp in [('OUT1', m1['A']), ('OUT2', m1['B']), ('OUT3', m2['A']), ('OUT4', m2['B'])]:
        drive.wire(h[hp], mp)
    drive.text('Remove ENA / ENB always-on jumpers.\nRetain only the verified regulator-jumper configuration.\nL298N +5V is intentionally unconnected.\n12 V bus is not guaranteed motor-terminal voltage.', 8, 48, 0.52)
    drive.text('A = left candidate; B = right candidate.\nVehicle direction still requires calibration.\nEncoder conductors are not connected.\nNeither motor terminal is a fixed ground.', 115, 52, 0.5)
    for i, net in enumerate(motor_nets):
        pulldown(drive, f'R{i+1}', net, 21 + i * 26, 80)
    drive.text('R1-R6: 10k, 1%, >=0.1 W; target 0603. At L298 inputs; actual module bias / reset state still need E05.\nST L298 Table 4 sizing: 10 uA x 10.1k = 0.101 V; added GPIO load at 3.3 V <= 0.433 mA (table conditions).\nPhoto control columns L to R: ENA, IN1, IN2, IN3, IN4, ENB; jumper contact identities need continuity check.\nEN LOW = free-running stop, not active braking. Pull-downs cannot stop a GPIO stuck HIGH. Keep SW2 independent.\nNew-supply current, thermal and reverse-energy tests pending; see parameter-confirmation.md for limits.', 8, 94, 0.52)

    effects_sheet.text('04  SEPARATE WATER AND BUBBLE POWER CHANNELS', 8, 7, 0.85)
    effects_sheet.text('MOS BEFORE buck converter. Keep each switched return separate from system ground and the other channel.', 8, 12, 0.52)
    for i, (name, y, mr, br, lr) in enumerate([('WATER', 34, 'U6', 'U7', 'A1'),
                                             ('BUBBLE', 72, 'U8', 'U9', 'A2')]):
        mos = effects_sheet.part('JZ_MOS', mr, f'P01 / {name}', 37, y)
        buck = effects_sheet.part('P12_Buck', br, 'P12 / TARGET 3.7 V', 86, y)
        load = effects_sheet.part('Load3V7', lr, f'{name} / 3.7 V', 136, y)
        for terminal, net in [('VIN+', f'5V_{name}_IN'), ('VIN-', 'GND_SYS'),
                              ('TRIG', f'{name}_EN'), ('GND', 'GND_SYS')]:
            stub(effects_sheet, mos, terminal, net)
        effects_sheet.wire(mos['VOUT+'], buck['IN+'])
        effects_sheet.wire(mos['VOUT-'], buck['GND'])
        effects_sheet.local(f'{name}_SW_P', (60, y - 4))
        effects_sheet.local(f'{name}_SW_N', (60, y + 4))
        effects_sheet.wire(buck['VO+'], load['+'])
        effects_sheet.local(f'3V7_{name}', (110, y - 4))
        effects_sheet.wire(load['-'], (115, y + 4))
        effects_sheet.local(f'{name}_SW_N', (115, y + 4))
    pulldown(effects_sheet, 'R7', 'WATER_EN', 29, 99)
    pulldown(effects_sheet, 'R8', 'BUBBLE_EN', 63, 99)
    effects_sheet.text('R7/R8 values TBD. P12 EN / trim retain existing settings, not modeled here.\nP12 common GND is the local switched return, NOT GND_SYS.\nJZ-MOS internal topology and 3.3 V trigger behavior require verification.\nDo not bypass the switch with test-instrument ground or added wiring.\nBuck capacitance may sustain output after MOS command goes LOW.', 82, 94, 0.5)

    ignition.text('05  IGNITION LOW-VOLTAGE INTERFACE - DISABLED', 8, 7, 0.9)
    ignition.text('No ignition-module HV circuitry, electrodes or HV wiring is included. This sheet authorizes no energization.', 8, 12, 0.55)
    jp = ignition.part('Disconnect', 'JP2', 'DNP / LEAVE OPEN', 25, 37, dnp=True)
    stub(ignition, jp, 'A', '5V_IGN_FUSED')
    ignition.net('5V_IGN_ISOLATED', jp['B'], (32, 37))
    mos = ignition.part('JZ_MOS', 'U10', 'P01 / COMMON CONTROL / DNP', 66, 43, dnp=True)
    for terminal, net in [('VIN+', '5V_IGN_ISOLATED'), ('VIN-', 'GND_SYS'),
                          ('TRIG', 'IGNITION_EN'), ('GND', 'GND_SYS')]:
        stub(ignition, mos, terminal, net)
    out = ignition.part('LV_Reserved', 'J9', 'LV RESERVE / DNP', 126, 43, dnp=True)
    ignition.wire(mos['VOUT+'], out['+'])
    ignition.wire(mos['VOUT-'], out['-'])
    ignition.local('IGNITION_SW_P', (91, 39))
    ignition.local('IGNITION_SW_N', (91, 47))
    supply(ignition, '5V_IGN_ISOLATED', 40, 62)
    pulldown(ignition, 'R9', 'IGNITION_EN', 66, 78)
    ignition.text('JP2 OPEN and output harness absent for initial validation.\nU10/J9 marked DNP in this review assembly.\nOne control channel is reserved for the shared MOS requested for two modules.\nOutput pin numbers are logical +/- only; no connector or current rating is frozen.', 8, 91, 0.55)
    ignition.text('Firmware: GPIO21, single action <= 5 s; cooldown >= elapsed software ON time.\nThese are software rules, NOT thermal protection or physical stop evidence.\nR9 value, protection, input current, cut-off and EMC remain unresolved.\nPWR_FLAG is an ERC declaration for the optional supply, not a populated link.', 88, 65, 0.52)

    for sheet in sheets:
        sheet.save()
    (OUT / 'CyberTrack.kicad_sym').write_text(
        '(kicad_symbol_lib (version 20241209) (generator "cybertrack_schematic")\n'
        + '\n'.join(lib_symbol(name, False) for name in LIB) + '\n)\n')
    (OUT / 'sym-lib-table').write_text(
        '(sym_lib_table (lib (name "CyberTrack") (type "KiCad")'
        ' (uri "${KIPRJMOD}/CyberTrack.kicad_sym") (options "")'
        ' (descr "CyberTrack logical module interfaces; no footprint assignment")))\n')
    # Keep project state minimal; do not silently suppress ERC findings.
    (OUT / 'CyberTrack.kicad_pro').write_text(json.dumps({
        'meta': {'filename': 'CyberTrack.kicad_pro', 'version': 1},
        'text_variables': {'REVISION': REVISION + ' - REVIEW ONLY'},
    }, indent=2) + '\n')
    (OUT / 'logical-components.json').write_text(json.dumps({
        'revision': REVISION, 'production_bom': False,
        'pin_ids': 'logical identity or silkscreen; NOT connector pad position',
        'sheets': [{ 'file': s.filename, 'page': s.page, 'parts': s.parts} for s in sheets],
    }, indent=2) + '\n')
    print(f'Generated {len(sheets)} editable KiCad schematic sheets in {OUT}')


if __name__ == '__main__':
    main()
