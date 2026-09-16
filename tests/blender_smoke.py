# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Psych0h3ad
"""Run with Blender --background --factory-startup --python this_file."""
from pathlib import Path
import hashlib
import json
import sys
import tempfile
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
from test_core import synthetic_gcode, synthetic_qidi_gcode

if '--' in sys.argv:
    archive = Path(sys.argv[sys.argv.index('--') + 1]).resolve()
    assert archive.is_file()
    bpy.ops.preferences.addon_install(filepath=str(archive), overwrite=True)
    bpy.ops.preferences.addon_enable(module='makerchip_rounded_import')
    import makerchip_rounded_import as addon
    assert '/scripts/addons/' in Path(addon.__file__).as_posix()
else:
    sys.path.insert(0, str(ROOT))
    import makerchip_rounded_import as addon
    addon.register()

assert addon.bl_info['name'] == 'Bambu Filament Path'
assert addon.bl_info['version'] == (1, 1, 2)
assert addon.IMPORT_SCENE_OT_bambu_rounded_beads.bl_label == 'Import Filament Path'

existing = {obj.name for obj in bpy.data.objects}
output = ROOT / 'test-output'
output.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(dir=output) as folder:
    path = Path(folder) / 'synthetic.gcode'
    path.write_text(synthetic_gcode().replace('FEATURE: Top surface', 'FEATURE: Outer wall').replace('G1 X10 Y0', 'G1 X5 Y5'), encoding='utf-8')
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    result = bpy.ops.import_scene.bambu_rounded_beads(filepath=str(path))
    assert result == {'FINISHED'}, result
    obj = bpy.context.view_layer.objects.active
    assert obj.name.startswith('MakerChip_Rounded')
    assert obj['makerchip_importer'] == 'Bambu Filament Path'
    assert existing.issubset({item.name for item in bpy.data.objects})
    assert tuple(obj.scale) == (1, 1, 1)
    assert tuple(obj.location) == (0, 0, 0)
    assert abs(obj.dimensions.z - .0001) < 1e-9
    assert obj['source_gcode'] == 'synthetic.gcode'
    assert obj.data.has_custom_normals
    assert obj['cap_intermediate_rings'] == 11
    assert json.loads(obj['round_wall_corners'])['count'] == 1
    flat_faces = [face for face in obj.data.polygons if not face.use_smooth]
    assert flat_faces
    for face in flat_faces:
        for loop in face.loop_indices:
            assert (obj.data.corner_normals[loop].vector-face.normal).length < .001
    assert json.loads(obj['coplanar_top_cleanup'])['plane_offset_mm'] == 0
    assert all(face.material_index == 1 for face in obj.data.polygons)
    assert obj.data.materials[2]['source_filament_color'] == '#000000'
    assert obj.data.materials[2]['display_color'] == '#333333'
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before
    report = {'pass': True, 'blender': bpy.app.version_string, 'vertices': len(obj.data.vertices),
              'faces': len(obj.data.polygons), 'zip_installed': '--' in sys.argv,
              'existing_scene_retained': True, 'source_unchanged': True,
              'source_absolute_path_omitted': True, 'normals': True, 'material_ids': True}
    qidi_path = Path(folder) / 'synthetic-qidi.gcode'
    qidi_path.write_text(synthetic_qidi_gcode(), encoding='utf-8')
    qidi_before = hashlib.sha256(qidi_path.read_bytes()).hexdigest()
    before_second = {item.name for item in bpy.data.objects}
    result = bpy.ops.import_scene.bambu_rounded_beads(filepath=str(qidi_path))
    assert result == {'FINISHED'}, result
    qidi = bpy.context.view_layer.objects.active
    assert before_second.issubset({item.name for item in bpy.data.objects})
    assert abs(qidi.dimensions.z - .0006) < 1e-9
    assert qidi['source_gcode'] == 'synthetic-qidi.gcode'
    assert qidi['source_object_label'] == 'generated-qidi'
    assert qidi.data.has_custom_normals
    assert {face.material_index for face in qidi.data.polygons} == {0, 1, 2}
    assert json.loads(qidi['round_wall_corners'])['count'] == 2
    assert json.loads(qidi['rounded_caps'])['open_terminal'] == 6
    assert qidi['cap_intermediate_rings'] == 11
    assert hashlib.sha256(qidi_path.read_bytes()).hexdigest() == qidi_before
    report['qidi_04_nozzle_synthetic'] = {'pass': True, 'vertices': len(qidi.data.vertices),
        'faces': len(qidi.data.polygons), 'annotated_heights_mm': [.2, .4],
        'widths_mm': [.42, .45, .5, .09, .407], 'materials': 3,
        'source_unchanged': True, 'existing_scene_retained': True}
    (output / 'blender_smoke.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report))
