# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Psych0h3ad

"""Bambu annotated G-code → stadium beads with genuine terminal domes.

G-code is read as inert text only. No printer, network, subprocess, or filesystem
output is used by the public API. NumPy is the only non-standard dependency.
This is an illustrative extrusion geometry model, not physical flow simulation.
"""
from pathlib import Path
import collections
import hashlib
import math
import re
import time
import numpy as np
from . import bead_mesh, round_bead_caps, coplanar_cleanup, round_path_joins

PARAMS = re.compile(r'([XYZEFIJ])(-?(?:\d*\.)?\d+)')
GCODE = re.compile(r'^(G0|G1|G2|G3)(?:\s|$)')
TOOL = re.compile(r'^T(\d+)(?:\s|$)')
ARC_CHORD_ERROR_MM = .001
VALID_FEATURES = {'Outer wall','Inner wall','Top surface','Bottom surface',
    'Internal solid infill','Sparse infill','Gap infill','Bridge','Overhang wall',
    'Internal Bridge','Floating vertical shell','Ironing','Support','Support interface','Support transition'}

def transform_arc(start,end,p,clockwise):
    cx,cy = start[0]+p.get('I',0),start[1]+p.get('J',0)
    radius = math.hypot(start[0]-cx,start[1]-cy)
    if radius < 1e-8:
        return [end]
    a = math.atan2(start[1]-cy,start[0]-cx)
    b = math.atan2(end[1]-cy,end[0]-cx)
    sweep = (b-a)%(math.tau)
    if clockwise:
        sweep -= math.tau
    elif sweep < 1e-10:
        sweep = math.tau
    step = min(math.pi/8,2*math.acos(max(-1,1-ARC_CHORD_ERROR_MM/radius)))
    steps = max(1,math.ceil(abs(sweep)/max(step,1e-4)))
    result = [[cx+radius*math.cos(a+sweep*i/steps),cy+radius*math.sin(a+sweep*i/steps),start[2]+(end[2]-start[2])*i/steps] for i in range(1,steps)]
    return result+[end]


def inspect_gcode(filepath):
    path = Path(filepath)
    settings = {}
    labels = set()
    slicer = None
    in_config = False
    with path.open('r', encoding='utf-8-sig', errors='strict') as stream:
        for raw in stream:
            line = raw.strip()
            if line.startswith('; BambuStudio '):
                slicer = line[2:]
            if line == '; CONFIG_BLOCK_START':
                in_config = True
            elif line == '; CONFIG_BLOCK_END':
                in_config = False
            elif in_config and ' = ' in line:
                k, v = line[2:].split(' = ', 1)
                settings[k] = v
            if line.startswith('; OBJECT_ID: '):
                labels.add(line.split(': ', 1)[1])
            elif line.startswith('; start printing object, unique label id: '):
                labels.add(line.rsplit(': ', 1)[1])
    colors = re.findall(r'#[0-9A-Fa-f]{6}(?![0-9A-Fa-f])', settings.get('filament_colour', ''))
    if not colors:
        raise ValueError('The G-code has no CONFIG filament_colour palette. Export annotated G-code from Bambu Studio.')
    if not labels:
        raise ValueError('The G-code has no supported OBJECT_ID markers. Export an annotated one-object project from Bambu Studio.')
    return {'labels': sorted(labels), 'object_labels': sorted(labels), 'colors': colors,
            'settings': settings, 'slicer': slicer, 'file_bytes': path.stat().st_size}

def extract_paths(filepath, object_label=None):
    gcode = Path(filepath)
    info = inspect_gcode(gcode)
    if object_label is None:
        if len(info['labels']) != 1:
            raise ValueError('Multiple object labels found; specify object_label or export a one-object project.')
        object_label = info['labels'][0]
    label = str(object_label)
    if label not in info['labels']:
        raise ValueError(f'Object label {label} is not in {info["labels"]}')
    colors = info['colors']
    center = [0., 0., 0.]
    name = gcode.stem
    xyz = [0.,0.,0.]
    absolute_xyz = True
    relative_e = False
    last_e = 0.
    obj_id = None
    feature = None
    width = None
    height = None
    layer_top = None
    tool = None
    paths = []
    last_path = None
    last_key = None
    last_continuity_key = None
    last_continuity_end = None
    continuous_path_id = 0
    source_move_id = 0
    settings = {}
    in_config = False
    layers = set()
    counts = collections.Counter()
    arc_count = 0
    unknown_tools = set()
    line_count = 0
    with gcode.open('r', encoding='utf-8-sig', errors='strict') as stream:
        for raw in stream:
            line_count += 1
            line = raw.strip()
            if line == '; CONFIG_BLOCK_START':
                in_config = True
            elif line == '; CONFIG_BLOCK_END':
                in_config = False
            elif in_config and ' = ' in line:
                k,v = line[2:].split(' = ',1)
                settings[k] = v
            if line.startswith(';'):
                if line.startswith('; start printing object, unique label id: '):
                    obj_id = line.rsplit(': ',1)[1]
                    last_key = None
                    last_continuity_key = None
                elif line.startswith('; OBJECT_ID: '):
                    # Profiles with exclude_object=0 omit start/stop labels but
                    # still emit this identifier before object deposition.
                    obj_id = line.split(': ',1)[1]
                    last_key = None
                    last_continuity_key = None
                elif line.startswith('; stop printing object'):
                    obj_id = None
                    last_key = None
                    last_continuity_key = None
                elif line.startswith('; FEATURE: '):
                    feature = line.split(': ',1)[1]
                elif line.startswith('; LINE_WIDTH: '):
                    width = float(line.split(': ',1)[1])
                elif line.startswith('; LAYER_HEIGHT: '):
                    height = float(line.split(': ',1)[1])
                elif line.startswith('; Z_HEIGHT: '):
                    layer_top = float(line.split(': ',1)[1])
                continue
            code = line.split(';',1)[0]
            if code.startswith('M83'):
                relative_e = True
            elif code.startswith('M82'):
                relative_e = False
            elif code == 'G90':
                absolute_xyz = True
            elif code == 'G91':
                absolute_xyz = False
            tool_match = TOOL.match(code)
            if tool_match:
                candidate = int(tool_match[1])
                if candidate<len(colors):
                    tool = candidate
            if code.startswith('G92 '):
                p = {k:float(v) for k,v in PARAMS.findall(code)}
                if 'E' in p:
                    last_e = p['E']
                for i,key in enumerate('XYZ'):
                    if key in p:
                        xyz[i] = p[key]
                continue
            move = GCODE.match(code)
            if not move:
                continue
            p = {k:float(v) for k,v in PARAMS.findall(code)}
            previous = xyz.copy()
            for i,key in enumerate('XYZ'):
                if key in p:
                    xyz[i] = p[key] if absolute_xyz else xyz[i]+p[key]
            if 'E' in p:
                de = p['E'] if relative_e else p['E']-last_e
                last_e = p['E'] if not relative_e else last_e+p['E']
            else:
                de = 0.
            if obj_id != label:
                continue
            if de<=0 or feature not in VALID_FEATURES or not ('X' in p or 'Y' in p):
                last_key = None
                last_continuity_key = None
                continue
            if tool is None:
                unknown_tools.add(tool)
                continue
            if math.dist(previous[:2],xyz[:2])<1e-8 and move[1] in ['G0','G1']:
                continue
            if width is None or height is None or width <= 0 or height <= 0:
                raise ValueError(f'Missing or invalid LINE_WIDTH/LAYER_HEIGHT at line {line_count}')
            key = (feature,tool,width,height,layer_top)
            previous_normalized = [round(previous[i]-center[i],7) for i in range(3)]
            continuity_key = (feature,tool,height,layer_top)
            if continuity_key!=last_continuity_key or last_continuity_end is None or math.dist(previous_normalized,last_continuity_end)>1e-6:
                continuous_path_id += 1
            last_continuity_key = continuity_key
            last_continuity_end = [round(xyz[i]-center[i],7) for i in range(3)]
            source_move_id += 1
            if key!=last_key or last_path is None or math.dist(last_path['points_mm'][-1],previous_normalized)>1e-6:
                last_path = {'feature':feature,'tool_index':tool,'color':colors[tool],
                    'width_mm':width,'layer_height_mm':height,'layer_top_z_mm':layer_top,
                    'path_id':continuous_path_id,'points_mm':[previous_normalized],
                    'segment_gcode_lines':[],'segment_source_move_ids':[]}
                paths.append(last_path)
            last_key = key
            if move[1] in ['G2','G3']:
                points = transform_arc(previous,xyz.copy(),p,move[1]=='G2')
                arc_count += 1
            else:
                points = [xyz.copy()]
            last_path['points_mm'].extend([[round(point[i]-center[i],7) for i in range(3)] for point in points])
            last_path['segment_gcode_lines'].extend([line_count]*len(points))
            last_path['segment_source_move_ids'].extend([source_move_id]*len(points))
            layers.add(layer_top)
            counts[feature] += 1
    if not paths:
        raise ValueError(f'{name}: no deposition for selected object label {label}; inspect G-code object markers before continuing')

    if unknown_tools:
        raise ValueError(f'Unresolved filament tool before deposition: {unknown_tools}')
    info.update({'selected_object_label': label, 'gcode_sha256': hashlib.sha256(gcode.read_bytes()).hexdigest(),
                 'layer_count': len(layers), 'layer_tops_mm': sorted(layers),
                 'path_count': len(paths), 'continuous_path_count': continuous_path_id,
                 'segment_count': sum(len(p['points_mm']) - 1 for p in paths),
                 'arc_move_count': arc_count, 'arc_chord_error_mm': ARC_CHORD_ERROR_MM,
                 'deposited_move_count_by_feature': dict(counts),
                 'width_range_mm': [min(p['width_mm'] for p in paths), max(p['width_mm'] for p in paths)],
                 'height_values_mm': sorted(set(p['layer_height_mm'] for p in paths)),
                 'included_features': sorted(set(p['feature'] for p in paths))})
    return paths, info

def build_from_gcode(filepath, object_label=None, ring_resolution=26,
                     intermediate_rings=11, simplify_tolerance_mm=0., audit=False,
                     progress_callback=None, round_wall_corners=True):
    begun = time.perf_counter()
    def progress(message):
        if progress_callback:
            progress_callback(message)
    if ring_resolution not in (6, 10, 26):
        raise ValueError('ring_resolution must be 6, 10, or 26')
    if not 1 <= intermediate_rings <= 15:
        raise ValueError('intermediate_rings must be between 1 and 15')
    if simplify_tolerance_mm < 0:
        raise ValueError('simplify_tolerance_mm must be nonnegative')
    if round_wall_corners and simplify_tolerance_mm != 0:
        raise ValueError('Round wall corners requires original paths without simplification')
    progress('Reading object paths and filament colors')
    paths, info = extract_paths(filepath, object_label)
    # Remove large bed offsets before float32 meshing; this improves tiny-feature
    # numerical precision. Z retains its physical deposition value.
    minimum = np.min(np.asarray([np.min(p['points_mm'],axis=0) for p in paths]),axis=0)
    maximum = np.max(np.asarray([np.max(p['points_mm'],axis=0) for p in paths]),axis=0)
    offset = [(minimum[0]+maximum[0])/2, (minimum[1]+maximum[1])/2, 0.]
    for path in paths:
        path['points_mm'] = (np.asarray(path['points_mm']) - offset).tolist()
        # Detailed per-segment source lists are not needed by geometry or GUI;
        # retain path identity, features, and exact dimension tags.
        path.pop('segment_gcode_lines', None)
        path.pop('segment_source_move_ids', None)
    joins, preparation = [], {}
    if round_wall_corners:
        progress('Preparing round outer and inner wall bends')
        paths, joins, preparation = round_path_joins.split_for_round_joins(
            paths, max_miter_excess_mm=.001, features={'Outer wall', 'Inner wall'})
    progress('Sweeping the original widths and layer heights')
    mesh, meta = bead_mesh.mesh_polylines(paths, ring_resolution=ring_resolution,
                                         simplify_tolerance_mm=simplify_tolerance_mm)
    mesh['colors'] = np.asarray(info['colors'])
    mesh['quad_material_indices'] = np.zeros(len(mesh['quads']), np.int16)
    mesh['triangle_material_indices'] = np.zeros(len(mesh['triangles']), np.int16)
    for p in meta['paths']:
        mesh['quad_material_indices'][p['quad_start']:p['quad_start']+p['quad_count']] = p['tool_index']
        mesh['triangle_material_indices'][p['triangle_start']:p['triangle_start']+p['triangle_count']] = p['tool_index']
    progress('Rounding genuine open terminals')
    result, report = round_bead_caps.round_caps(mesh, meta, intermediate_rings=intermediate_rings, extent_fraction=.5)
    if audit:
        progress('Auditing topology, exact body preservation, and material binding')
        report['rounded_terminal_audit'] = round_bead_caps.audit_mesh(result, report, source=mesh)
        if not report['rounded_terminal_audit']['pass']:
            raise ValueError('Generated geometry did not pass its topology audit')
    if round_wall_corners:
        progress('Adding high resolution round wall corners')
        result, report = round_path_joins.append_round_joins(result, report, joins, bead_mesh._section,
            angular_error_mm=.00025, section_resolution=ring_resolution, min_sides=64)
        report['round_join_preparation'] = preparation
        if audit:
            report['round_join_audit'] = round_bead_caps.audit_mesh(result, report)
            if not report['round_join_audit']['pass']:
                raise ValueError('Round corner geometry did not pass its topology audit')
    # Audit intact bead volumes above. Removing already-covered top surface
    # fragments is a surface operation, so old contiguous bead ranges retire.
    del mesh
    progress('Removing duplicate coplanar top coverage')
    result, cleanup = coplanar_cleanup.top_cleanup(result)
    report['source_bead_paths'] = report.pop('paths')
    report['pre_cleanup_counts'] = report['counts'].copy()
    report['counts'].update(vertices=len(result['vertices']), quads=len(result['quads']), triangles=len(result['triangles']))
    report['coplanar_cleanup'] = cleanup
    report['path_range_scope'] = 'Source bead paths refer to the pre-cleanup mesh; output arrays intentionally omit stale per-path ranges.'
    report['source_path_ranges_columns'] = report.pop('path_ranges_columns', [])
    report['rounded_terminal_audit_scope'] = 'Pre-cleanup closed bead components. Final surface cleanup preserves source coordinates and removes duplicate same-material, exact-plane top coverage; independent bead watertightness is not asserted afterward.'
    report['npz_schema'] = {key: {'shape': list(value.shape), 'dtype': str(value.dtype)} for key, value in result.items()}
    report.update({'source_gcode': Path(filepath).name, 'gcode': info,
                   'normalization_removed_xyz_mm': offset,
                   'coordinate_system': 'Millimeters, bed XY offset removed; original deposition Z. GUI may center final mesh bounds and place its bottom at zero.',
                   'elapsed_build_seconds': time.perf_counter()-begun,
                   'array_bytes': sum(v.nbytes for v in result.values()),
                   'scope': 'Annotated Bambu G-code, selected object, all feature roles including exposed sparse infill. High resolution bead sections and genuine end domes; round convex joins on Outer wall and Inner wall. Coplanar top coverage cleanup retains exact source coordinates. Separate volumes may overlap. No centerline smoothing, reslicing, Boolean fusion, or physical flow simulation.'})
    progress('Rounded geometry ready')
    return result, report
