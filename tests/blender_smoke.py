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
from test_core import synthetic_gcode

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
    (output / 'blender_smoke.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report))
