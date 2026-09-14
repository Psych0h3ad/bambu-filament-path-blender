# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Psych0h3ad

"""Round joins of the deposited bead envelope; source paths stay fixed.

At selected bends, split the sweep at the original centerline vertex. A revolved
copy of the local bead section fills the round join. At every Z level the union
is straight segment strips plus a vertex-centered disk: the convex corner is
circular while the concave boundary remains the strip intersection. This avoids
miter spikes and does not shortcut or fillet the G-code centerline.

Separate solids can overlap. Apply same-plane top coverage cleanup afterward.
This is illustrative deposition geometry, not a measured polymer flow model.
"""
import math
from collections import defaultdict
import numpy as np


def _angle(a, b):
    la, lb = np.linalg.norm(a), np.linalg.norm(b)
    if min(la, lb) < 1e-9:
        return 0.
    return math.acos(float(np.clip(np.dot(a, b)/(la*lb), -1, 1)))


def _needs_round(angle, width, error_mm):
    if angle < 1e-5:
        return False
    return width*.5*(1/max(math.cos(angle*.5), 1e-6)-1) > error_mm


def _directions(incoming, outgoing):
    incoming, outgoing = np.asarray(incoming[:2]), np.asarray(outgoing[:2])
    a, b = np.linalg.norm(incoming), np.linalg.norm(outgoing)
    return {'incoming_direction_xy': (incoming/a).tolist(), 'outgoing_direction_xy': (outgoing/b).tolist(),
            'incoming_segment_length_mm': float(a), 'outgoing_segment_length_mm': float(b)}


def split_for_round_joins(paths, max_miter_excess_mm=.001, features=None):
    """Retain every original segment, splitting only at original bend vertices."""
    output, joins = [], []
    for source_index, path in enumerate(paths):
        if features is not None and path.get('feature') not in features:
            output.append({**path, 'source_path_index': source_index, 'round_join_piece_index': 0})
            continue
        points = np.asarray(path['points_mm'], dtype=float)
        closed = len(points) >= 4 and np.max(np.abs(points[0]-points[-1])) <= 2e-6
        unique = points[:-1] if closed else points
        candidates = []
        indices = range(len(unique)) if closed else range(1, len(unique)-1)
        for index in indices:
            angle = _angle(unique[index]-unique[index-1], unique[(index+1)%len(unique)]-unique[index])
            if _needs_round(angle, path['width_mm'], max_miter_excess_mm):
                candidates.append(index)
                joins.append({**{k: v for k, v in path.items() if k != 'points_mm'},
                    'center_top_mm': unique[index].tolist(), 'source_path_index': source_index,
                    'original_source_path_index': source_index,
                    **_directions(unique[index]-unique[index-1], unique[(index+1)%len(unique)]-unique[index]),
                    'source_point_index': index, 'turn_degrees': math.degrees(angle),
                    'join_kind': 'original_path_bend'})
        if closed and candidates:
            # Rotate only the traversal start to an existing selected corner;
            # the circular list contains precisely the original source edges.
            start = candidates[0]
            points = np.concatenate((unique[start:], unique[:start+1]))
            candidates = sorted((index-start) % len(unique) for index in candidates)
            boundaries = candidates + [len(unique)]
        elif candidates:
            boundaries = [0] + candidates + [len(points)-1]
        else:
            boundaries = [0, len(points)-1]
        for part, (a, b) in enumerate(zip(boundaries[:-1], boundaries[1:])):
            output.append({**path, 'points_mm': points[a:b+1].tolist(),
                'source_path_index': source_index, 'round_join_piece_index': part})

    # A continuous extrusion may be split into several constant-width records.
    # Use the smaller adjoining width for a conservative local transition join.
    groups = defaultdict(list)
    for index, path in enumerate(paths):
        if path.get('path_id') is not None:
            groups[(path['path_id'], path.get('tool_index'), path.get('color'),
                    path.get('layer_top_z_mm'), path.get('layer_height_mm'))].append(index)
    for members in groups.values():
        if len(members) < 2:
            continue
        pairs = list(zip(members[:-1], members[1:])) + [(members[-1], members[0])]
        for left, right in pairs:
            a, b = paths[left], paths[right]
            if features is not None and (a.get('feature') not in features or b.get('feature') not in features):
                continue
            pa, pb = np.asarray(a['points_mm']), np.asarray(b['points_mm'])
            if np.linalg.norm(pa[-1]-pb[0]) > 2e-6:
                continue
            angle = _angle(pa[-1]-pa[-2], pb[1]-pb[0])
            width = min(a['width_mm'], b['width_mm'])
            if _needs_round(angle, width, max_miter_excess_mm):
                joins.append({**{k: v for k, v in a.items() if k != 'points_mm'},
                    'width_mm': width, 'center_top_mm': pa[-1].tolist(),
                    'source_path_index': left, 'source_point_index': len(pa)-1,
                    'next_source_path_index': right, 'turn_degrees': math.degrees(angle),
                    'original_source_path_index': left, 'next_original_source_path_index': right,
                    **_directions(pa[-1]-pa[-2], pb[1]-pb[0]),
                    'join_kind': 'continuous_record_transition'})
    before = sum(len(p['points_mm'])-1 for p in paths)
    for join in joins:
        join['retained_miter_error_mm'] = max_miter_excess_mm
    after = sum(len(p['points_mm'])-1 for p in output)
    assert before == after, (before, after)
    # Existing terminal classification sorts by source_path_index, then by a
    # local sweep split index. Each expanded piece needs a distinct ordered
    # index or local split 0/1/2 from separate pieces can interleave.
    for expanded_index, part in enumerate(output):
        original_index = part['source_path_index']
        part['original_source_path_index'] = original_index
        part['source_path_index'] = expanded_index
        if part.get('path_id') is None:
            part['original_path_id'] = None
            part['path_id'] = f'round_join_synthetic_source_{original_index}'
    return output, joins, {'original_paths': len(paths), 'split_paths': len(output),
        'original_segments': before, 'output_segments': after, 'source_segments_retained': True,
        'round_join_count': len(joins), 'max_retained_miter_radial_error_mm': max_miter_excess_mm,
        'included_features': sorted(features) if features is not None else 'all',
        'centerline_policy': 'Original points and source segments retained; closed-loop traversal start may rotate to an existing corner.'}


def _full_join_solid(join, section_fn, angular_error_mm=.001, section_resolution=10, min_sides=16):
    width, height = float(join['width_mm']), float(join['layer_height_mm'])
    u, z, nu, nz, _ = section_fn(width, height, section_resolution)
    levels = {}
    for radius, dz, radial_normal, vertical_normal in zip(abs(u), z, abs(nu), nz):
        key = round(float(dz), 12)
        if key not in levels or radius > levels[key][0]:
            levels[key] = (float(radius), float(radial_normal), float(vertical_normal))
    radius_max = width*.5
    step = 2*math.acos(max(-1., 1-angular_error_mm/max(radius_max, angular_error_mm)))
    sides = max(min_sides, int(math.ceil(math.tau/max(step, .001))))
    sides += sides % 2  # Planar cap sectors are convex four-vertex polygons.
    theta = np.arange(sides)*math.tau/sides
    xy = np.column_stack((np.cos(theta), np.sin(theta)))
    center = np.asarray(join['center_top_mm'], float).copy()
    center[2] -= height*.5
    vertices, normals, rings = [], [], []
    for dz, (radius, radial_normal, vertical_normal) in sorted(levels.items()):
        if radius < 1e-9:
            ring = np.asarray([len(vertices)], np.int32)
            vertices.append((center+[0, 0, dz]).tolist())
            normals.append([0, 0, -1 if dz < 0 else 1])
        else:
            ring = np.arange(len(vertices), len(vertices)+sides, dtype=np.int32)
            vertices.extend(np.column_stack((center[0]+radius*xy[:, 0], center[1]+radius*xy[:, 1],
                                              np.full(sides, center[2]+dz))).tolist())
            normals.extend(np.column_stack((radial_normal*xy, np.full(sides, vertical_normal))).tolist())
        rings.append(ring)
    quads, triangles = [], []
    for lower, upper in zip(rings[:-1], rings[1:]):
        if len(lower) == 1:
            triangles.extend([[int(lower[0]), int(upper[(j+1)%sides]), int(upper[j])] for j in range(sides)])
        elif len(upper) == 1:
            triangles.extend([[int(lower[j]), int(lower[(j+1)%sides]), int(upper[0])] for j in range(sides)])
        else:
            quads.extend([[int(lower[j]), int(lower[(j+1)%sides]), int(upper[(j+1)%sides]), int(upper[j])] for j in range(sides)])
    for at_top, ring in ((False, rings[0]), (True, rings[-1])):
        if len(ring) == 1:
            continue
        cap_center = len(vertices)
        dz = height*.5 if at_top else -height*.5
        vertices.append((center+[0, 0, dz]).tolist())
        normals.append([0, 0, 1 if at_top else -1])
        for j in range(0, sides, 2):
            face = [cap_center, int(ring[j]), int(ring[(j+1)%sides]), int(ring[(j+2)%sides])]
            quads.append(face if at_top else face[::-1])
    return (np.asarray(vertices, np.float32), np.asarray(normals, np.float32),
            np.asarray(quads, np.int32).reshape(-1, 4), np.asarray(triangles, np.int32).reshape(-1, 3), sides)


def _sector_join_solid(join, section_fn, angular_error_mm=.001, section_resolution=10, min_sides=16):
    """Closed outer convex sector; all omitted disk points lie in adjacent strips.

    Call only if both adjacent finite segments reach at least width/2. The
    circular profile and chord error are the same as a complete join disk.
    """
    width, height = float(join['width_mm']), float(join['layer_height_mm'])
    incoming, outgoing = np.asarray(join['incoming_direction_xy']), np.asarray(join['outgoing_direction_xy'])
    turn = math.atan2(float(incoming[0]*outgoing[1]-incoming[1]*outgoing[0]), float(np.dot(incoming, outgoing)))
    start = math.atan2(incoming[1], incoming[0]) - math.copysign(math.pi/2, turn) + min(turn, 0.)
    max_step = min(math.tau/min_sides, 2*math.acos(max(-1., 1-angular_error_mm/max(width*.5, angular_error_mm))))
    steps = max(2, math.ceil(abs(turn)/max_step)); steps += steps % 2
    theta = np.linspace(start, start+abs(turn), steps+1)
    xy = np.column_stack((np.cos(theta), np.sin(theta)))
    u, z, nu, nz, _ = section_fn(width, height, section_resolution)
    levels = {}
    for radius, dz, radial, vertical in zip(abs(u), z, abs(nu), nz):
        key = round(float(dz), 12)
        if key not in levels or radius > levels[key][0]:
            levels[key] = (float(radius), float(radial), float(vertical))
    center = np.asarray(join['center_top_mm'], float).copy(); center[2] -= height*.5
    vertices, normals, rings, axes = [], [], [], []
    for dz, (radius, radial, vertical) in sorted(levels.items()):
        axis = len(vertices); axes.append(axis)
        vertices.append((center+[0, 0, dz]).tolist())
        if abs(abs(dz)-height*.5) < 1e-10:
            normals.append([0, 0, math.copysign(1., dz)])
        else:
            mid = start+abs(turn)*.5
            normals.append([-math.cos(mid), -math.sin(mid), 0.])
        if radius < 1e-9:
            rings.append(np.asarray([axis], np.int32)); continue
        ring = np.arange(len(vertices), len(vertices)+steps+1, dtype=np.int32)
        vertices.extend(np.column_stack((center[0]+radius*xy[:, 0], center[1]+radius*xy[:, 1], np.full(steps+1, center[2]+dz))).tolist())
        normals.extend(np.column_stack((radial*xy, np.full(steps+1, vertical))).tolist())
        rings.append(ring)
    quads, triangles, flat_quads, flat_triangles = [], [], [], []
    def face(ids):
        ids = list(dict.fromkeys(map(int, ids)))
        (flat_quads if len(ids)==4 else flat_triangles).append(len(quads) if len(ids)==4 else len(triangles))
        (quads if len(ids)==4 else triangles).append(ids)
    for index, (lower, upper) in enumerate(zip(rings[:-1], rings[1:])):
        if len(lower)==1:
            triangles.extend([[int(lower[0]),int(upper[j+1]),int(upper[j])] for j in range(steps)])
        elif len(upper)==1:
            triangles.extend([[int(lower[j]),int(lower[j+1]),int(upper[0])] for j in range(steps)])
        else:
            quads.extend([[int(lower[j]),int(lower[j+1]),int(upper[j+1]),int(upper[j])] for j in range(steps)])
        face([axes[index], lower[0], upper[0], axes[index+1]])
        face([lower[-1], axes[index], axes[index+1], upper[-1]])
    for at_top, ring, axis in ((False,rings[0],axes[0]), (True,rings[-1],axes[-1])):
        if len(ring)==1: continue
        for j in range(0,steps,2):
            ids=[axis,int(ring[j]),int(ring[j+1]),int(ring[j+2])]
            quads.append(ids if at_top else ids[::-1])
    qkind, tkind = np.full(len(quads),3,np.uint8), np.full(len(triangles),3,np.uint8)
    qkind[flat_quads]=4; tkind[flat_triangles]=4
    return (np.asarray(vertices,np.float32), np.asarray(normals,np.float32),
            np.asarray(quads,np.int32).reshape(-1,4), np.asarray(triangles,np.int32).reshape(-1,3), steps,qkind,tkind)


def _join_solid(join, section_fn, angular_error_mm=.001, section_resolution=10, min_sides=16, return_face_kinds=False):
    radius = float(join['width_mm'])*.5
    # A far unselected corner can miter-cut the end of an adjoining strip.
    # r(sec(a/2)-1)<=error bounds that axial cut by sqrt(2*r*error+error^2).
    # Reserve that distance too, so every omitted disk point is still covered.
    error = float(join.get('retained_miter_error_mm', .001))
    required_length = radius+math.sqrt(2*radius*error+error*error)+2e-6
    long_enough = min(join.get('incoming_segment_length_mm', 0), join.get('outgoing_segment_length_mm', 0)) >= required_length
    fn = _sector_join_solid if long_enough else _full_join_solid
    result = fn(join, section_fn, angular_error_mm, section_resolution, min_sides)
    if return_face_kinds:
        return result if long_enough else (*result,np.full(len(result[2]),3,np.uint8),np.full(len(result[3]),3,np.uint8))
    return result[:5]


def append_round_joins(mesh, metadata, joins, section_fn, angular_error_mm=.001, section_resolution=10, min_sides=16):
    """Append closed join volumes after true terminal rounding, before top cleanup."""
    result = {k: np.asarray(v).copy() for k, v in mesh.items() if k not in (
        'source_vertex_index', 'quad_source_face_index', 'triangle_source_face_index', 'material_perface')}
    if not joins:
        return result, metadata
    vv, nn, qq, tt, qm, tm, qk, tk = [result['vertices']], [result['vertex_normals']], [result['quads']], [result['triangles']], \
        [result['quad_material_indices']], [result['triangle_material_indices']], [result['quad_face_kind']], [result['triangle_face_kind']]
    paths = list(metadata['paths'])
    ranges = result['path_ranges'].tolist()
    nv, nq, nt = len(mesh['vertices']), len(mesh['quads']), len(mesh['triangles'])
    sector_count = disk_count = 0
    for join in joins:
        v, n, q, t, sides, qkind, tkind = _join_solid(join, section_fn, angular_error_mm, section_resolution, min_sides, True)
        is_sector = bool(np.any(qkind==4) or np.any(tkind==4))
        sector_count += is_sector; disk_count += not is_sector
        vv.append(v); nn.append(n); qq.append(q+nv); tt.append(t+nv)
        material = int(join.get('tool_index', 0))
        qm.append(np.full(len(q), material, np.int16)); tm.append(np.full(len(t), material, np.int16))
        qk.append(qkind); tk.append(tkind)
        ranges.append([nv, len(v), nq, len(q), nt, len(t)])
        paths.append({**join, 'input_path_index': join['source_path_index'], 'closed': True,
            'section': f'round_join_lathe_{sides}', 'vertex_start': nv, 'vertex_count': len(v),
            'quad_start': nq, 'quad_count': len(q), 'triangle_start': nt, 'triangle_count': len(t),
            'segments': 0, 'geometry_kind': 'round_path_join', 'terminal_caps': []})
        paths[-1]['round_join_shape'] = 'outer_convex_sector' if is_sector else 'full_disk_short_segment_fallback'
        nv += len(v); nq += len(q); nt += len(t)
    result.update(vertices=np.concatenate(vv), vertex_normals=np.concatenate(nn), quads=np.concatenate(qq), triangles=np.concatenate(tt),
                  quad_material_indices=np.concatenate(qm), triangle_material_indices=np.concatenate(tm),
                  quad_face_kind=np.concatenate(qk), triangle_face_kind=np.concatenate(tk), path_ranges=np.asarray(ranges, np.int64))
    report = dict(metadata)
    report['paths'] = paths
    report['counts'] = {**metadata['counts'], 'vertices': nv, 'quads': nq, 'endcap_triangles': nt,
                        'round_join_solids': len(joins), 'swept_paths': len(paths),
                        'closed_paths': int(metadata['counts'].get('closed_paths', 0))+len(joins)}
    report['round_path_joins'] = {'count': len(joins), 'angular_chord_error_mm': angular_error_mm,
        'outer_sector_count': sector_count, 'full_disk_short_segment_count':disk_count,
        'section_resolution': section_resolution, 'minimum_angular_sides': min_sides,
        'method': 'Outer convex sectors of revolved bead sections; full disk fallback when either adjacent segment is shorter than radius+sqrt(2*radius*miter_error+miter_error^2)+2e-6 mm. Original centerline unchanged.',
        'face_kind': 3, 'radial_closure_face_kind':4, 'separate_volumes_overlap': True, 'join_solids_appended_after_true_terminal_rounding': True}
    report['bounds_mm'] = [result['vertices'].min(axis=0).astype(float).tolist(), result['vertices'].max(axis=0).astype(float).tolist()]
    report['npz_schema'] = {k: {'shape': list(v.shape), 'dtype': str(v.dtype)} for k, v in result.items()}
    return result, report
