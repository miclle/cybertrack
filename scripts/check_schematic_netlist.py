#!/usr/bin/env python3
"""Audit the KiCad-exported XML netlist against critical CyberTrack interfaces."""

import argparse
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET


def check(path):
    root = ET.parse(path).getroot()
    nets = {}
    node_net = {}
    for net in root.findall('./nets/net'):
        name = net.attrib['name']
        nodes = {(n.attrib['ref'], n.attrib['pin']) for n in net.findall('node')}
        nets[name] = nodes
        for node in nodes:
            assert node not in node_net, f'Duplicate node: {node}'
            node_net[node] = name
    results = []

    def same(description, *nodes):
        names = {node_net[node] for node in nodes}
        assert len(names) == 1, (description, nodes, names)
        results.append(dict(check=description, net=next(iter(names)), passed=True))

    def separate(description, *nodes):
        names = {node_net[node] for node in nodes}
        assert len(names) == len(nodes), (description, names)
        results.append(dict(check=description, passed=True))

    mapping = [('8', 'ENA'), ('9', 'IN1'), ('10', 'IN2'),
               ('11', 'ENB'), ('12', 'IN3'), ('13', 'IN4')]
    for i, (gpio, terminal) in enumerate(mapping):
        same(f'Motor GPIO{gpio} -> {terminal}', ('U1', f'IO{gpio}'), ('U5', terminal), (f'R{i+1}', '1'))
    for gpio, mos, r in [('18', 'U6', 'R7'), ('17', 'U8', 'R8'), ('21', 'U10', 'R9')]:
        same(f'Effect GPIO{gpio} -> {mos}', ('U1', f'IO{gpio}'), (mos, 'TRIG'), (r, '1'))
    same('BOOT dry contact', ('U1', 'IO0'), ('SW3', 'B'))
    same('BOOT ground', ('U1', 'GND'), ('SW3', 'A'))
    same('Controller external 5 V service link', ('JP1', 'B'), ('U1', '5Vin'))
    same('12 V stays on motor supply', ('U4', 'OUT+'), ('U5', '+12V'))
    separate('Controller is not connected to motor 12 V', ('U1', '5Vin'), ('U5', '+12V'))
    for mos, buck, load in [('U6', 'U7', 'A1'), ('U8', 'U9', 'A2')]:
        same(f'{mos} switched positive -> buck', (mos, 'VOUT+'), (buck, 'IN+'))
        same(f'{mos} switched return -> buck and load', (mos, 'VOUT-'), (buck, 'GND'), (load, '-'))
        same(f'{buck} 3.7 V -> load', (buck, 'VO+'), (load, '+'))
        same(f'{mos} power and control reference', ('U1', 'GND'), (mos, 'VIN-'), (mos, 'GND'))
    separate('All switched returns remain separate', ('U1', 'GND'), ('U6', 'VOUT-'), ('U8', 'VOUT-'), ('U10', 'VOUT-'))
    for pin, motor, terminal in [('OUT1', 'M1', 'A'), ('OUT2', 'M1', 'B'),
                                 ('OUT3', 'M2', 'A'), ('OUT4', 'M2', 'B')]:
        same(f'{pin} -> {motor}.{terminal}', ('U5', pin), (motor, terminal))
    separate('Four H-bridge terminals are not tied together or grounded',
             ('U5', 'OUT1'), ('U5', 'OUT2'), ('U5', 'OUT3'), ('U5', 'OUT4'), ('U1', 'GND'))
    five = node_net.get(('U5', '+5V'))
    assert five is None or nets[five] == {('U5', '+5V')}, 'L298N +5V unexpectedly connected'
    results.append(dict(check='L298N +5V has no external connection', passed=True))
    same('Ignition disconnect supply side', ('F7', '2'), ('JP2', 'A'))
    same('Ignition disconnect load side', ('JP2', 'B'), ('U10', 'VIN+'))
    separate('Ignition disconnect not bypassed', ('JP2', 'A'), ('JP2', 'B'))
    same('Ignition LV output positive', ('U10', 'VOUT+'), ('J9', '+'))
    same('Ignition LV output return', ('U10', 'VOUT-'), ('J9', '-'))
    for gpio, interface in [('4', 'MIC_WS'), ('5', 'MIC_SCK'), ('6', 'MIC_DATA'),
                            ('7', 'AMP_DATA'), ('15', 'AMP_BCLK'), ('16', 'AMP_LRCK'),
                            ('41', 'OLED_SDA'), ('42', 'OLED_SCL'), ('47', 'TALK_INPUT'),
                            ('40', 'VOLUME_UP'), ('39', 'VOLUME_DOWN')]:
        same(f'Retained GPIO{gpio}', ('U1', f'IO{gpio}'), ('X1', interface))
    for i in range(1, 10):
        same(f'R{i} returns to system ground', (f'R{i}', '2'), ('U1', 'GND'))
    same('Controller and actuator branches start before SW2', ('U3', 'OUT+'), ('F2', '1'), ('F3', '1'))
    same('Controller fuse feeds service link', ('F2', '2'), ('JP1', 'A'))
    same('Actuator fuse feeds SW2', ('F3', '2'), ('SW2', 'A'))
    same('SW2 output feeds all actuator fuses', ('SW2', 'B'), *((f'F{i}', '1') for i in range(4, 8)))
    separate('SW2 is not bypassed by controller supply', ('SW2', 'A'), ('SW2', 'B'), ('U1', '5Vin'))
    components = {c.attrib['ref']: c for c in root.findall('./components/comp')}
    for i in range(1, 10):
        expected = '10k 1%' if i <= 6 else 'TBD'
        assert components[f'R{i}'].findtext('value') == expected, f'Wrong R{i} value'
        results.append(dict(check=f'R{i} value {expected}', passed=True))
    repo = Path(__file__).resolve().parents[1]
    positions = json.loads((repo / 'hardware/schematic/design-inputs.json').read_text())['controller_header']['positions']
    pins = root.find("./libparts/libpart[@part='Existing_ESP32S3']/pins")
    actual = {p.attrib['num']: p.attrib['name'] for p in pins}
    assert len(positions) == 23
    for number, position in positions.items():
        assert actual[number].endswith(f'[{position}]'), (number, position, actual[number])
        results.append(dict(check=f'U1 {number} photo position {position}', passed=True))
    source = (repo / 'firmware/esp32-audio/action_outputs.h').read_text()
    for name, number in [('WaterPin', 18), ('BubblesPin', 17), ('IgnitionPin', 21)]:
        assert re.search(rf'{name}\s*=\s*GPIO_NUM_{number}\b', source)
    for a, b, c in [(8, 9, 10), (11, 12, 13)]:
        assert f'GPIO_NUM_{a}, GPIO_NUM_{b}, GPIO_NUM_{c}' in source
    results.append(dict(check='Actuator assignments match current firmware', passed=True))
    return dict(passed=True, net_count=len(nets), checks=results,
                evidence='KiCad-exported electrical netlist; not a physical wiring or power test')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('netlist', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = check(args.netlist)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(f'PASS: {len(result["checks"])} connectivity/source checks; {result["net_count"]} nets')
