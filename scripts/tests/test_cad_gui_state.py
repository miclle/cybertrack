import struct
import unittest

from scripts.cad_gui_state import read_material_list, write_material_list


class MaterialListTests(unittest.TestCase):
    def test_reorder_faces_with_different_string_lengths(self):
        dark = struct.pack("<4I2f", 1, 2, 3, 4, 0.8, 0)
        blue = struct.pack("<4I2f", 5, 6, 7, 8, 0.4, 0)

        def fields(*values):
            return b"".join(struct.pack("<I", len(value)) + value for value in values)

        dark_strings = fields(b"", b"", b"material-1")
        blue_strings = fields(b"texture", b"images/texture", b"material-2")
        header = struct.pack("<I", 2)
        saved = header + dark + blue + dark_strings + blue_strings

        self.assertEqual(read_material_list(saved), [(dark, dark_strings), (blue, blue_strings)])
        self.assertEqual(write_material_list(read_material_list(saved)[::-1]),
                         header + blue + dark + blue_strings + dark_strings)
