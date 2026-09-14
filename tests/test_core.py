# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Psych0h3ad
"""Small generated fixtures; no user print data is required."""
from pathlib import Path
import importlib.util
import sys
import tempfile
import unittest
import math
import copy
from collections import Counter
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
    def test_arc_refinement_preserves_circle_direction_and_endpoint(self):
        start=[2.,0.,.1]
        for clockwise,end in ((False,[0.,2.,.1]),(True,[0.,-2.,.1]),(False,[2.,0.,.1]),(True,[2.,0.,.1])):
            points=core.transform_arc(start,end,{'I':-2.,'J':0.},clockwise)
            self.assertEqual(points[-1],end)
            xy=np.asarray([start]+points)[:,:2]
            self.assertTrue(np.allclose(np.linalg.norm(xy,axis=1),2.,atol=1e-12))
            mids=(xy[:-1]+xy[1:])*.5
            self.assertLessEqual(float((2-np.linalg.norm(mids,axis=1)).max()),core.ARC_CHORD_ERROR_MM+1e-12)
            cross=xy[:-1,0]*xy[1:,1]-xy[:-1,1]*xy[1:,0]
            self.assertTrue(np.all(cross<0) if clockwise else np.all(cross>0))

    def test_high_quality_wall_corner_defaults(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'corner.gcode'
            text = synthetic_gcode().replace('FEATURE: Top surface', 'FEATURE: Outer wall').replace('G1 X10 Y0', 'G1 X5 Y5')
            path.write_text(text, encoding='utf-8')
            mesh, report = core.build_from_gcode(path, audit=True)
            self.assertTrue(report['round_join_audit']['pass'])
            self.assertEqual(report['round_path_joins']['count'], 1)
            self.assertEqual(report['round_path_joins']['section_resolution'], 26)
            self.assertEqual(report['rounded_terminals']['intermediate_rings'], 11)
            self.assertEqual(report['rounded_terminals']['counts']['open_terminal'], 2)
            self.assertIn(4, mesh['quad_face_kind'])
            self.assertEqual(path.read_text(encoding='utf-8'), text)

    def test_split_order_keeps_only_two_true_ends(self):
        for degrees in (10, 20, 30):
            for length in (.0005, .001, .003, .005, .01, .02, .04):
                a = math.radians(degrees)
                dx, dy = length*math.cos(a), length*math.sin(a)
                vx, vy = math.cos(2*a), math.sin(2*a)
                ex, ey = 2+dx+vx, dy+vy
                source = [{'points_mm': [[x,y,.1] for x,y in [(0,0),(2,0),(2+dx,dy),(ex,ey),(ex-vy,ey+vx)]],
                           'width_mm':.22,'layer_height_mm':.1,'layer_top_z_mm':.1,
                           'feature':'Outer wall','tool_index':0,'path_id':1}]
                original = copy.deepcopy(source)
                prepared, joins, _ = core.round_path_joins.split_for_round_joins(source, max_miter_excess_mm=.005)
                mesh, meta = core.bead_mesh.mesh_polylines(prepared, ring_resolution=26)
                _, reasons, _ = core.round_bead_caps.classify_terminals(mesh, meta)
                self.assertEqual(sum(reason=='open_terminal' for pair in reasons for reason in pair), 2)
                self.assertEqual(source, original)
                edges = lambda paths: Counter((tuple(a),tuple(b)) for p in paths for a,b in zip(p['points_mm'][:-1],p['points_mm'][1:]))
                self.assertEqual(edges(source), edges(prepared))

    def test_sector_radius_height_and_short_edge_fallback(self):
        for width,height in ((.22,.1),(.1,.2)):
            for angle in (-179.9,-119,-90,30,90,119,179.9):
                rad = math.radians(angle)
                path = {'points_mm':[[-2,0,height],[0,0,height],[2*math.cos(rad),2*math.sin(rad),height]],
                        'width_mm':width,'layer_height_mm':height,'layer_top_z_mm':height,'feature':'Outer wall'}
                _, joins, _ = core.round_path_joins.split_for_round_joins([path])
                v,n,q,t,_ = core.round_path_joins._join_solid(joins[0],core.bead_mesh._section,.00025,26,64)
                self.assertLessEqual(float(np.linalg.norm(v[:,:2],axis=1).max()), width*.5+1e-7)
                self.assertAlmostEqual(float(v[:,2].min()), 0., places=6)
                self.assertAlmostEqual(float(v[:,2].max()), height, places=6)
        path['points_mm'][0]=[-.001,0,height]
        _, joins, _ = core.round_path_joins.split_for_round_joins([path])
        candidate = core.round_path_joins._join_solid(joins[0],core.bead_mesh._section,.00025,26,64)
        full = core.round_path_joins._full_join_solid(joins[0],core.bead_mesh._section,.00025,26,64)
        self.assertTrue(all(np.array_equal(a,b) for a,b in zip(candidate,full)))

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
            self.assertNotIn('paths', report)
            self.assertNotIn('path_ranges', mesh)
            self.assertIn('source_bead_paths', report)
            self.assertIn('quad_source_bead_index', mesh)
            self.assertEqual(report['rounded_terminals']['intermediate_rings'], 11)

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

    def test_coplanar_six_area_cases(self):
        square = [[0., 0.], [10., 0.], [10., 10.], [0., 10.]]
        cases = [
            ('disjoint', [[20., 0.], [22., 0.], [22., 2.], [20., 2.]], 100.),
            ('contained', [[3., 3.], [7., 3.], [7., 7.], [3., 7.]], 84.),
            ('identical', square, 0.),
            ('half', [[5., -1.], [12., -1.], [12., 11.], [5., 11.]], 50.),
            ('edge touch', [[10., 0.], [12., 0.], [12., 10.], [10., 10.]], 100.),
            ('diamond', [[5., 0.], [10., 5.], [5., 10.], [0., 5.]], 50.)]
        for name, clip, expected in cases:
            with self.subTest(name=name):
                fragments = core.coplanar_cleanup.subtract_convex(square, clip)
                self.assertAlmostEqual(sum(abs(core.coplanar_cleanup.signed_area(p)) for p in fragments), expected, places=8)

    def test_coplanar_guards_and_provenance(self):
        vertices = np.asarray([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
                               [.5, 0, 0], [1.5, 0, 0], [1.5, 1, 0], [.5, 1, 0]], np.float32)
        mesh = {'vertices': vertices, 'vertex_normals': np.tile([[0, 0, 1]], (8, 1)).astype(np.float32),
                'quads': np.asarray([[0, 1, 2, 3], [4, 5, 6, 7]], np.int32), 'triangles': np.empty((0, 3), np.int32),
                'colors': np.asarray(['#FFFFFF', '#00B1B7']), 'quad_material_indices': np.asarray([0, 1], np.int16),
                'triangle_material_indices': np.empty(0, np.int16), 'path_ranges': np.asarray([[0, 4, 0, 1, 0, 0], [4, 4, 1, 1, 0, 0]])}
        _, report = core.coplanar_cleanup.top_cleanup(mesh)
        self.assertEqual(report['changed_top_quads'], 0)
        mesh['quad_material_indices'][:] = 0
        mesh['quad_face_kind'] = np.asarray([3,3],np.uint8)
        clean, report = core.coplanar_cleanup.top_cleanup(mesh)
        self.assertEqual(report['changed_top_quads'], 1)
        self.assertAlmostEqual(report['duplicate_area_removed_mm2'], .5, places=8)
        self.assertTrue(np.array_equal(clean['vertices'][:8], vertices))
        self.assertTrue(np.all(clean['vertices'][:, 2] == 0))
        self.assertTrue(np.all(clean['triangle_input_face_index'] == 1))
        self.assertTrue(np.all(clean['triangle_source_bead_index'] == 1))
        self.assertTrue(np.all(clean['triangle_material_indices'] == 0))
        self.assertTrue(np.all(clean['triangle_face_kind'] == 3))
        mesh['vertices'] = vertices.copy()
        mesh['vertices'][4:, 2] = .1
        _, report = core.coplanar_cleanup.top_cleanup(mesh)
        self.assertEqual(report['changed_top_quads'], 0)


if __name__ == '__main__':
    unittest.main()
