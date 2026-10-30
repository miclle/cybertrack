"""Reject regressions in the exported ultrasonic interface, without editing drawings."""
from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from check_schematic_netlist import check

NETLIST = Path(__file__).resolve().parents[2] / 'hardware/schematic/checks/CyberTrack.net.xml'


class UltrasonicNetlistTests(unittest.TestCase):
    def reject(self, edit):
        root = ET.parse(NETLIST).getroot()
        edit(root)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'changed.xml'
            ET.ElementTree(root).write(path)
            with self.assertRaises((AssertionError, KeyError)):
                check(path)

    @staticmethod
    def net(root, ref, pin):
        return next(n for n in root.findall('./nets/net')
                    if any(x.get('ref') == ref and x.get('pin') == pin for x in n.findall('node')))

    def move(self, root, pin, ref, target_pin):
        old = self.net(root, 'U11', pin)
        node = next(x for x in old.findall('node') if x.get('ref') == 'U11' and x.get('pin') == pin)
        old.remove(node)
        self.net(root, ref, target_pin).append(node)

    def test_current_export(self):
        result = check(NETLIST)
        self.assertTrue(result['passed'])
        self.assertEqual(len(result['checks']), 112)

    def test_swapped_trig_echo(self):
        def swap(root):
            for node in root.findall('./nets/net/node'):
                if node.get('ref') == 'U11' and node.get('pin') in ('TRIG', 'ECHO'):
                    node.set('pin', {'TRIG': 'ECHO', 'ECHO': 'TRIG'}[node.get('pin')])
        self.reject(swap)

    def test_five_volt_supply(self):
        self.reject(lambda root: self.move(root, 'VCC', 'U1', '5Vin'))

    def test_switched_return_ground(self):
        self.reject(lambda root: self.move(root, 'GND', 'U6', 'VOUT-'))

    def test_wrong_echo_direction(self):
        def reverse(root):
            pin = root.find("./libparts/libpart[@part='Ultrasonic_Module']/pins/pin[@num='ECHO']")
            pin.set('type', 'input')
        self.reject(reverse)


if __name__ == '__main__':
    unittest.main()
