# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Psych0h3ad

"""Blender GUI for the bundled, explicit Bambu G-code visualization pipeline."""
bl_info = {
    'name': 'Bambu Rounded Beads',
    'author': 'Psych0h3ad.tech',
    'version': (1, 0, 0),
    'blender': (4, 5, 0),
    'location': 'File > Import > Bambu G-code — Rounded Beads (.gcode)',
    'description': 'Create illustrated extrusion beads and rounded real path ends from Bambu G-code',
    'category': 'Import-Export',
    'doc_url': 'https://github.com/Psych0h3ad/bambu-rounded-beads-blender',
    'tracker_url': 'https://github.com/Psych0h3ad/bambu-rounded-beads-blender/issues',
}

from pathlib import Path
import traceback
import bpy
from bpy.props import BoolProperty, StringProperty
from bpy_extras.io_utils import ImportHelper
from .blender_mesh import create_object


class IMPORT_SCENE_OT_bambu_rounded_beads(bpy.types.Operator, ImportHelper):
    """Read one object's Bambu G-code; create a rendering mesh with rounded path ends"""
    bl_idname = 'import_scene.bambu_rounded_beads'
    bl_label = 'Import Rounded Beads'
    bl_options = {'REGISTER', 'UNDO'}
    filename_ext = '.gcode'

    filter_glob: StringProperty(default='*.gcode', options={'HIDDEN'})
    object_label: StringProperty(
        name='Object Label', default='',
        description='Leave blank for a G-code file containing one object; use an OBJECT_ID label for multiple objects')
    center_xy: BoolProperty(
        name='Center XY / Ground Z', default=True,
        description='Center the generated bounds in XY and place the lowest point at Z = 0')
    match_native_black: BoolProperty(
        name='Match Native Black', default=True,
        description='Display source #000000 as #333333 to match the native Bambu OBJ palette; preserve original color IDs')

    def draw(self, context):
        layout = self.layout
        layout.label(text='One sliced object recommended', icon='INFO')
        layout.prop(self, 'object_label')
        layout.prop(self, 'center_xy')
        layout.prop(self, 'match_native_black')
        box = layout.box()
        box.label(text='Width / layer height: from G-code')
        box.label(text='Section: 10 points; dome: 3 rings')
        box.label(text='End extent: half the local line width')
        box.label(text='No path simplification')
        layout.label(text='Large files may take a few minutes.')

    def execute(self, context):
        from .core import build_from_gcode, inspect_gcode
        path = Path(self.filepath)
        if not path.is_file():
            self.report({'ERROR'}, 'Choose an existing Bambu .gcode file.')
            return {'CANCELLED'}
        if context.mode != 'OBJECT':
            self.report({'ERROR'}, 'Switch to Object Mode before importing.')
            return {'CANCELLED'}
        context.window_manager.progress_begin(0, 100)
        try:
            summary = inspect_gcode(path)
            labels = [str(value) for value in summary['labels']]
            selected_label = self.object_label.strip() or None
            if selected_label is None and len(labels) != 1:
                self.report({'ERROR'}, 'Multiple objects: set Object Label to one of: ' + ', '.join(labels))
                return {'CANCELLED'}
            context.window_manager.progress_update(10)
            arrays, metadata = build_from_gcode(
                path, object_label=selected_label,
                ring_resolution=10, intermediate_rings=3, simplify_tolerance_mm=0)
            context.window_manager.progress_update(80)
            metadata['source_gcode'] = path.name
            obj = create_object(
                context, arrays, metadata, 'MakerChip_Rounded',
                center_xy=self.center_xy, match_native_black=self.match_native_black)
            obj['source_object_label'] = str(selected_label or labels[0])
            context.window_manager.progress_update(100)
            self.report({'INFO'}, f'Created {obj.name}: {len(obj.data.vertices):,} vertices. Hide the native chip before rendering.')
            return {'FINISHED'}
        except Exception as exc:
            traceback.print_exc()
            self.report({'ERROR'}, str(exc)[:600])
            return {'CANCELLED'}
        finally:
            context.window_manager.progress_end()


def import_menu(self, context):
    self.layout.operator(IMPORT_SCENE_OT_bambu_rounded_beads.bl_idname,
                         text='Bambu G-code — Rounded Beads (.gcode)')


def register():
    bpy.utils.register_class(IMPORT_SCENE_OT_bambu_rounded_beads)
    bpy.types.TOPBAR_MT_file_import.append(import_menu)


def unregister():
    bpy.types.TOPBAR_MT_file_import.remove(import_menu)
    bpy.utils.unregister_class(IMPORT_SCENE_OT_bambu_rounded_beads)
