# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Psych0h3ad

"""Create a Blender mesh from the bundled rounded-bead core arrays.

The core uses millimeters; Blender receives meters. No existing scene object,
material, camera, render engine or world is replaced by this helper.
"""
import json
import bpy
import numpy as np


def _linear(value):
    return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4


def rgba_from_hex(color):
    text = str(color).lstrip('#')
    if len(text) not in (6, 8):
        raise ValueError('Invalid filament color: ' + str(color))
    rgb = [_linear(int(text[i:i+2], 16) / 255) for i in (0, 2, 4)]
    return (*rgb, 1.0)


def create_object(context, arrays, metadata, name='MakerChip_Rounded', center_xy=True, match_native_black=True):
    vertices = np.array(arrays['vertices'], dtype=np.float32, copy=True)
    quads = np.asarray(arrays['quads'], dtype=np.int32)
    triangles = np.asarray(arrays['triangles'], dtype=np.int32)
    if not len(vertices) or not np.all(np.isfinite(vertices)):
        raise ValueError('The generated mesh has no valid vertices.')
    lower, upper = vertices.min(axis=0), vertices.max(axis=0)
    offset = np.zeros(3, dtype=np.float32)
    if center_xy:
        offset[:2] = (lower[:2] + upper[:2]) * .5
        offset[2] = lower[2]
    vertices -= offset
    vertices *= .001
    nq, nt = len(quads), len(triangles)
    loop_vertices = np.concatenate((quads.ravel(), triangles.ravel()))
    loop_totals = np.concatenate((np.full(nq, 4, np.int32), np.full(nt, 3, np.int32)))
    loop_starts = np.empty(nq+nt, dtype=np.int32)
    loop_starts[0] = 0
    np.cumsum(loop_totals[:-1], out=loop_starts[1:])
    material_indices = np.concatenate((
        np.asarray(arrays['quad_material_indices'], dtype=np.int32),
        np.asarray(arrays['triangle_material_indices'], dtype=np.int32)))
    colors = [str(c) for c in arrays['colors']]
    if len(material_indices) != nq+nt or material_indices.max(initial=0) >= len(colors):
        raise ValueError('Material indices do not match the generated faces.')

    mesh = bpy.data.meshes.new(name)
    created_materials = []
    obj = None
    try:
        mesh.vertices.add(len(vertices))
        mesh.vertices.foreach_set('co', vertices.ravel())
        mesh.loops.add(len(loop_vertices))
        mesh.loops.foreach_set('vertex_index', loop_vertices)
        mesh.polygons.add(nq+nt)
        mesh.polygons.foreach_set('loop_start', loop_starts)
        mesh.polygons.foreach_set('loop_total', loop_totals)
        mesh.polygons.foreach_set('material_index', material_indices)
        mesh.polygons.foreach_set('use_smooth', np.ones(nq+nt, dtype=bool))
        mesh.update()
        for i, color in enumerate(colors):
            material = bpy.data.materials.new(f'{name} · Filament {i+1} {color}')
            created_materials.append(material)
            display_color = '#333333' if match_native_black and color.upper() == '#000000' else color
            rgba = rgba_from_hex(display_color)
            material.diffuse_color = rgba
            material['source_filament_color'] = color
            material['display_color'] = display_color
            material.use_nodes = True
            shader = next(n for n in material.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
            shader.inputs['Base Color'].default_value = rgba
            shader.inputs['Metallic'].default_value = 0
            shader.inputs['Roughness'].default_value = .45
            shader.inputs['IOR'].default_value = 1.46
            shader.inputs['Specular IOR Level'].default_value = .20
            mesh.materials.append(material)
        if 'vertex_normals' in arrays:
            mesh.normals_split_custom_set_from_vertices(np.asarray(arrays['vertex_normals'], dtype=np.float32))
        obj = bpy.data.objects.new(name, mesh)
        context.collection.objects.link(obj)
        for old in context.selected_objects:
            old.select_set(False)
        obj.select_set(True)
        context.view_layer.objects.active = obj
        obj['makerchip_importer'] = 'Bambu Rounded Beads'
        obj['source_units'] = 'mm; converted to Blender meters'
        obj['removed_origin_mm'] = [float(x) for x in offset]
        obj['source_gcode'] = str(metadata.get('source_gcode', ''))
        obj['source_filament_colors'] = json.dumps(colors)
        obj['match_native_black'] = match_native_black
        obj['rounded_caps'] = json.dumps(metadata.get('rounded_terminals', {}).get('counts', {}))
        obj['visualization_note'] = 'Illustrative bead geometry; not a fused polymer flow simulation.'
        context.view_layer.update()
        return obj
    except Exception:
        if obj is not None:
            bpy.data.objects.remove(obj, do_unlink=True)
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)
        for material in created_materials:
            if material.users == 0:
                bpy.data.materials.remove(material)
        raise
