# SPDX-License-Identifier: GPL-3.0-or-later
"""Regression for coincident bed-facing surfaces on face-down prints."""
import unittest
import numpy as np
from test_core import core


def rectangles(specs):
    vertices, normals, faces, materials = [], [], [], []
    for x, y, z, sign, material in specs:
        start = len(vertices)
        vertices.extend([[x,y,z],[x+2,y,z],[x+2,y+2,z],[x,y+2,z]])
        normals.extend([[0,0,sign]]*4)
        faces.append([start,start+1,start+2,start+3] if sign > 0 else
                     [start,start+3,start+2,start+1])
        materials.append(material)
    return {'vertices': np.asarray(vertices,np.float32),
            'vertex_normals': np.asarray(normals,np.float32),
            'quads': np.asarray(faces,np.int32),
            'triangles': np.empty((0,3),np.int32),
            'quad_material_indices': np.asarray(materials,np.int16),
            'triangle_material_indices': np.empty(0,np.int16),
            'quad_face_kind': np.arange(len(faces),dtype=np.int8),
            'triangle_face_kind': np.empty(0,np.int8),
            'colors': np.asarray(['#AABBCC','#DDEEFF'])}


class HorizontalSurfaceTests(unittest.TestCase):
    def test_both_sides_keep_union_winding_normals_and_source_faces(self):
        mesh = rectangles([(0,0,.2,1,0),(1,1,.2,1,0),
                           (0,0,0,-1,0),(1,1,0,-1,0)])
        cleaned, report = core.coplanar_cleanup.flat_surface_cleanup(mesh)
        self.assertEqual(report['changed_top_quads'], 1)
        self.assertEqual(report['changed_bottom_quads'], 1)
        self.assertTrue(np.array_equal(cleaned['vertices'][:16],mesh['vertices']))
        self.assertTrue(np.array_equal(cleaned['vertex_normals'][:16],mesh['vertex_normals']))
        self.assertEqual(report['plane_offset_mm'], 0)
        self.assertAlmostEqual(report['duplicate_area_removed_mm2'], 2)
        area = {1:0., -1:0.}
        polygons = {1:[], -1:[]}
        for kind in ('quad','triangle'):
            for face, source in zip(cleaned[kind+'s'],cleaned[kind+'_input_face_index']):
                points = cleaned['vertices'][face].astype(float)
                sign = 1 if source < 2 else -1
                normal = cleaned['vertex_normals'][face]
                self.assertTrue(np.all(normal == [0,0,sign]))
                self.assertTrue(np.all(points[:,2] == mesh['vertices'][mesh['quads'][source,0],2]))
                signed = core.coplanar_cleanup.signed_area(points[:,:2].tolist())
                self.assertGreater(signed*sign, 0)
                area[sign] += abs(signed)
                polygons[sign].append(points[:,:2])
        self.assertAlmostEqual(area[1], 7)
        self.assertAlmostEqual(area[-1], 7)
        # Independent occupancy probe: one covering face in the original union,
        # no new holes and no duplicate coplanar fragments on either side.
        for sign, faces in polygons.items():
            for x in np.arange(-.3713,3.4,.2371):
                for y in np.arange(-.3181,3.4,.2137):
                    expected = (0<x<2 and 0<y<2) or (1<x<3 and 1<y<3)
                    coverage = 0
                    for face in faces:
                        edges = np.roll(face,-1,axis=0)-face
                        point = np.asarray([x,y])-face
                        cross = (edges[:,0]*point[:,1]-edges[:,1]*point[:,0])*sign
                        coverage += bool(np.all(cross >= -1e-9))
                    self.assertEqual(coverage,int(expected),(sign,x,y))

    def test_material_plane_and_opposite_facing_are_separate(self):
        # All footprints coincide, but none may cancel another group.
        mesh = rectangles([(0,0,0,1,0),(0,0,0,-1,0),
                           (0,0,0,-1,1),(0,0,.2,-1,0)])
        cleaned, report = core.coplanar_cleanup.flat_surface_cleanup(mesh)
        self.assertEqual(report['changed_top_quads'],0)
        self.assertEqual(report['changed_bottom_quads'],0)
        for key in ('vertices','vertex_normals','quads','triangles',
                    'quad_material_indices','quad_face_kind'):
            self.assertTrue(np.array_equal(cleaned[key],mesh[key]),key)

    def test_top_only_compatibility_keeps_bottom_faces(self):
        mesh = rectangles([(0,0,0,-1,0),(1,1,0,-1,0)])
        cleaned, report = core.coplanar_cleanup.top_cleanup(mesh)
        self.assertEqual(report['candidate_bottom_quads'],0)
        self.assertTrue(np.array_equal(cleaned['quads'],mesh['quads']))


if __name__ == '__main__':
    unittest.main()
