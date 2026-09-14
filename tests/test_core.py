# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Psych0h3ad
"""Small generated fixtures; no user print data is required."""
from pathlib import Path
import importlib.util
import sys
import tempfile
import unittest
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('rounded_core', ROOT / 'makerchip_rounded_import/core/__init__.py')
core = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = core
spec.loader.exec_module(core)


def synthetic_gcode():
    return '''; BambuStudio synthetic test
; CONFIG_BLOCK_START
; filament_colour = #FFFFFF;#00B1B7;#000000
; CONFIG_BLOCK_END
G90
M83
G1 X0 Y0 Z0.1
T1
; OBJECT_ID: test-object
; FEATURE: Top surface
; LINE_WIDTH: 0.22
; LAYER_HEIGHT: 0.1
; Z_HEIGHT: 0.1
G1 X5 Y0 E0.01
; LINE_WIDTH: 0.25
G1 X10 Y0 E0.01
; stop printing object
'''


class GeometryTests(unittest.TestCase):
    def test_parser_dimensions_color_and_continuity(self):
        output = ROOT / 'test-output'
        output.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=output) as folder:
            path = Path(folder) / 'synthetic.gcode'
            text = synthetic_gcode()
            path.write_text(text, encoding='utf-8')
            mesh, report = core.build_from_gcode(path, audit=True)
            self.assertTrue(report['rounded_terminal_audit']['pass'])
            self.assertEqual(report['source_gcode'], 'synthetic.gcode')
            self.assertEqual(report['gcode']['colors'][1], '#00B1B7')
            self.assertEqual(report['gcode']['height_values_mm'], [.1])
            self.assertEqual(report['gcode']['width_range_mm'], [.22, .25])
            self.assertEqual(report['rounded_terminals']['counts']['open_terminal'], 2)
            self.assertEqual(report['rounded_terminals']['internal_join_count'], 1)
            self.assertTrue(np.all(mesh['quad_material_indices'] == 1))
            self.assertTrue(np.all(mesh['triangle_material_indices'] == 1))
            self.assertAlmostEqual(float(mesh['vertices'][:, 2].min()), 0, places=6)
            self.assertAlmostEqual(float(mesh['vertices'][:, 2].max()), .1, places=6)
            self.assertEqual(path.read_text(encoding='utf-8'), text)

    def test_terminal_and_topology_diagnostics(self):
        output = ROOT / 'test-output'
        output.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=output) as folder:
            report = core.round_bead_caps.run_diagnostics(folder)
            self.assertTrue(report['pass'], report)
            self.assertEqual(len(report['tests']), 9)
            self.assertTrue(report['tests']['closed']['audit']['closed_vertices_unchanged'])

    def test_missing_palette_is_rejected(self):
        output = ROOT / 'test-output'
        output.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=output) as folder:
            path = Path(folder) / 'synthetic.gcode'
            path.write_text('; OBJECT_ID: a\nG1 X1 E1\n', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'filament_colour'):
                core.inspect_gcode(path)


if __name__ == '__main__':
    unittest.main()
