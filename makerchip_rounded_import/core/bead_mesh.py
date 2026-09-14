# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Psych0h3ad

"""CPU-only extrusion bead meshes from actual sliced paths (millimeters).

Public API:
    mesh, report = mesh_polylines(paths, ring_resolution=10, simplify_tolerance_mm=0)
    mesh, report = segments_to_mesh(records, schema, feature_names)
    reduced_points = simplify_polyline(points, tolerance=.10)
    write_mesh(path, mesh, report)

mesh_polylines accepts dictionaries containing points_mm (N x 3, NOZZLE Z),
width_mm, layer_height_mm, layer_top_z_mm, feature, and optional path_id,
tool_index/color. No role is filtered by this function: pass exposed infill too.
The vertices remain in the supplied original print coordinate system. The caller chooses any desired coordinate normalization.

NPZ keys: vertices (float32 N x 3), vertex_normals (float32 N x 3), quads
(int32 Q x 4, outward sides), triangles (int32 T x 3, flat end caps), and
path_ranges (int64 P x 6: vertex_start/count, quad_start/count, triangle_start/count).
Per-path material, role, dimensions, and ranges are in companion metadata JSON.

Z is layer top, so centerline Z is reduced by height/2. Rounded horizontal
stadium sections have ten ring vertices. Circular/vertical-ellipse sections
use eight to avoid coincident vertices when width<=height. For render LOD,
ring_resolution=6 uses six ring vertices, and simplify_tolerance_mm=.10 runs
RDP within each original constant-section path while preserving endpoints.
Each continuous constant-section path is swept through averaged XY tangents
with lateral miter correction to retain width perpendicular to each span. Turns over120
degrees are split to avoid reversal tangents and severe foldovers. Endcaps
occur at open path ends, not at every segment. Closed paths weld end rings.
Any remaining tight-span inversion is detected on final float32 side faces
and split locally at its endpoints, retaining every input centerline point.

This is a visualization of slicer path placement, widths and heights, not
measured fused polymer shape, a Boolean union, or a physical flow simulation.
Separate bead solids may overlap; this does not establish a fused, watertight
complete printed object.
"""
from __future__ import annotations
from pathlib import Path
from collections import Counter
import hashlib
import json
import math
import time
import numpy as np

CONTINUITY_TOLERANCE_MM = 2e-6
SHARP_TURN_DEGREES = 120.
DEFAULT_SCHEMA = ['object_id','feature_id','layer_z_mm','layer_height_mm',
                  'line_width_mm','start_plate_xyz_mm','end_plate_xyz_mm',
                  'start_normalized_xyz_mm','end_normalized_xyz_mm',
                  'gcode_line','source_move_id','path_id']


def segments_to_polylines(records, schema=DEFAULT_SCHEMA, feature_names=None):
    """Join ordered segment records, splitting on all physical metadata changes.

    Records may be strict skin and supplemental records concatenated: sorting
    restores original G-code move order and stable arc-chord order. Optional
    tool_index/color fields in the schema also cause splits on changes.
    """
    col = {key:i for i,key in enumerate(schema)}
    def get(r,key,default=None):
        return r[col[key]] if key in col else default
    ordered = sorted(records,key=lambda r:(get(r,'gcode_line',0),get(r,'source_move_id',0)))
    paths = []
    previous_key = None
    active = None
    for r in ordered:
        start = np.asarray(get(r,'start_normalized_xyz_mm'),dtype=float)
        end = np.asarray(get(r,'end_normalized_xyz_mm'),dtype=float)
        key = tuple(get(r,k) for k in ['object_id','path_id','feature_id','layer_z_mm',
                                      'layer_height_mm','line_width_mm','tool_index','color'])
        if not np.all(np.isfinite([start,end])):
            raise ValueError('Nonfinite segment coordinates')
        if np.linalg.norm(end[:2]-start[:2]) <= 1e-10:
            raise ValueError('Zero XY deposition segment: inspect input before sweeping')
        contiguous = (active is not None and key==previous_key and
                      np.max(np.abs(np.asarray(active['points_mm'][-1])-start))<=CONTINUITY_TOLERANCE_MM)
        if not contiguous:
            feature_id = get(r,'feature_id')
            active = {
                'object_id':get(r,'object_id'), 'path_id':get(r,'path_id'),
                'feature':feature_names[feature_id] if feature_names is not None else str(feature_id),
                'feature_id':feature_id,
                'width_mm':get(r,'line_width_mm'), 'layer_height_mm':get(r,'layer_height_mm'),
                'layer_top_z_mm':get(r,'layer_z_mm'), 'gcode_line_start':get(r,'gcode_line'),
                'tool_index':get(r,'tool_index',0), 'color':get(r,'color'),
                'points_mm':[start.tolist(),end.tolist()],
            }
            paths.append(active)
        else:
            active['points_mm'].append(end.tolist())
        previous_key=key
    return paths


def _split_at_sharp_turns(points, threshold=SHARP_TURN_DEGREES):
    delta=np.diff(points[:,:2],axis=0)
    lengths=np.linalg.norm(delta,axis=1)
    if np.any(lengths<=1e-10):
        raise ValueError('Polyline has a zero-length XY segment')
    unit=delta/lengths[:,None]
    dot=np.einsum('ij,ij->i',unit[:-1],unit[1:])
    indices=(np.flatnonzero(dot<math.cos(math.radians(threshold)))+1).tolist()
    boundaries=[0]+indices+[len(points)-1]
    return [points[a:b+1] for a,b in zip(boundaries[:-1],boundaries[1:])],len(indices)


def simplify_polyline(points,tolerance=.01):
    """Ramer-Douglas-Peucker in input mm; endpoints are always preserved.

    Apply only inside an existing constant width/layer/feature path. This is a
    bounded render LOD approximation, never a change to the actual G-code.
    """
    points=np.asarray(points,dtype=float)
    if tolerance<=0 or len(points)<=2:
        return points.copy()
    keep=np.zeros(len(points),dtype=bool);keep[[0,-1]]=True
    stack=[(0,len(points)-1)]
    while stack:
        start,end=stack.pop()
        if end<=start+1:
            continue
        v=points[end]-points[start];vv=float(np.dot(v,v))
        p=points[start+1:end]
        if vv<=1e-20:
            distance=np.linalg.norm(p-points[start],axis=1)
        else:
            t=np.clip((p-points[start])@v/vv,0,1)
            distance=np.linalg.norm(p-(points[start]+t[:,None]*v),axis=1)
        local=int(np.argmax(distance));idx=start+1+local
        if distance[local]>tolerance:
            keep[idx]=True;stack.extend([(start,idx),(idx,end)])
    return points[keep]


def _section(width,height,ring_resolution=10):
    if width<=0 or height<=0:
        raise ValueError('Nonpositive extrusion width/height')
    if ring_resolution not in (6,10):
        raise ValueError('ring_resolution must be6 (render LOD) or10 (default)')
    if width>height+1e-9:
        # CCW in lateral/vertical coordinates; ring normal is forward tangent.
        half=ring_resolution//2
        theta=np.concatenate((np.linspace(-math.pi/2,math.pi/2,half),np.linspace(math.pi/2,3*math.pi/2,half)))
        side=np.asarray([1]*half+[-1]*half)
        u=side*(width-height)/2+np.cos(theta)*height/2
        v=np.sin(theta)*height/2
        nu,nv=np.cos(theta),np.sin(theta)
        kind=f'horizontal_stadium_{ring_resolution}'
    else:
        count=8 if ring_resolution==10 else 6
        theta=np.arange(count)*2*math.pi/count
        u=np.cos(theta)*width/2
        v=np.sin(theta)*height/2
        nu,nv=np.cos(theta)/(width/2),np.sin(theta)/(height/2)
        norm=np.hypot(nu,nv);nu/=norm;nv/=norm
        kind=f'circle_or_vertical_ellipse_{count}'
    return u,v,nu,nv,kind


def _sweep(points,width,height,ring_resolution=10):
    if np.ptp(points[:,2])>CONTINUITY_TOLERANCE_MM:
        raise ValueError('Nonhorizontal path: this converter uses XY tangents')
    # Never auto-close a short single segment: a closed polygon needs>=3 edges.
    closed=bool(len(points)>=4 and np.max(np.abs(points[0]-points[-1]))<=CONTINUITY_TOLERANCE_MM)
    if closed:
        points=points[:-1]
        edges=np.roll(points,-1,axis=0)-points
        unit=edges[:,:2]/np.linalg.norm(edges[:,:2],axis=1)[:,None]
        tangents=unit+np.roll(unit,1,axis=0)
    else:
        edges=np.diff(points,axis=0)
        unit=edges[:,:2]/np.linalg.norm(edges[:,:2],axis=1)[:,None]
        tangents=np.vstack((unit[0],unit[:-1]+unit[1:],unit[-1]))
    lengths=np.linalg.norm(tangents,axis=1)
    if np.any(lengths<1e-8):
        raise ValueError('Reversal tangent remains after path splitting')
    tangents/=lengths[:,None]
    # An uncorrected averaged tangent narrows an entire straight span when its
    # only vertices are corners. Miter scaling preserves its specified width
    # measured perpendicular to either adjacent segment. Sharp turns split
    # before this stage, bounding the amplification to2.
    if closed:
        miter=1/np.maximum(np.einsum('ij,ij->i',tangents,unit),.5)
    else:
        miter=np.ones(len(points))
        if len(points)>2:
            miter[1:-1]=1/np.maximum(np.einsum('ij,ij->i',tangents[1:-1],unit[:-1]),.5)
    lateral=np.column_stack((-tangents[:,1],tangents[:,0],np.zeros(len(points))))
    u,v,nu,nv,section_kind=_section(width,height,ring_resolution)
    k=len(u);n=len(points)
    centers=points.copy();centers[:,2]-=height/2
    vertices=centers[:,None,:]+lateral[:,None,:]*(u[None,:,None]*miter[:,None,None])
    vertices[:,:,2]+=v
    normals=lateral[:,None,:]*nu[None,:,None]
    normals[:,:,2]+=nv
    vertices=vertices.reshape(-1,3);normals=normals.reshape(-1,3)
    ring=np.arange(k,dtype=np.int32)
    starts=np.arange(n if closed else n-1,dtype=np.int32)[:,None]*k
    ends=((np.arange(n if closed else n-1,dtype=np.int32)+1)%n)[:,None]*k
    quads=np.stack(np.broadcast_arrays(starts+ring,starts+(ring+1)%k,
                                       ends+(ring+1)%k,ends+ring),axis=-1).reshape(-1,4)
    if closed:
        triangles=np.empty((0,3),dtype=np.int32)
    else:
        cap_start=len(vertices);cap_end=cap_start+1
        vertices=np.vstack((vertices,centers[0],centers[-1]))
        cap_normals=np.asarray([[-tangents[0,0],-tangents[0,1],0],
                               [tangents[-1,0],tangents[-1,1],0]])
        normals=np.vstack((normals,cap_normals))
        triangles=np.vstack((
            np.column_stack((np.full(k,cap_start),((ring+1)%k),ring)),
            np.column_stack((np.full(k,cap_end),(n-1)*k+ring,(n-1)*k+(ring+1)%k)),
        )).astype(np.int32)
    return vertices,normals,quads,triangles,closed,section_kind


def _folded_spans(sweep):
    """Find local inverted/degenerate spans after final float32 quantization."""
    vertices,normals,quads,triangles,closed,section_kind=sweep
    v=vertices.astype(np.float32).astype(float)
    n=normals.astype(np.float32).astype(float)
    a=quads[:,[0,1,2]];b=quads[:,[0,2,3]]
    ca=np.cross(v[a[:,1]]-v[a[:,0]],v[a[:,2]]-v[a[:,0]])
    cb=np.cross(v[b[:,1]]-v[b[:,0]],v[b[:,2]]-v[b[:,0]])
    area_a=np.linalg.norm(ca,axis=1)/2;area_b=np.linalg.norm(cb,axis=1)/2
    da=np.einsum('ij,ij->i',ca,n[a].mean(axis=1))
    db=np.einsum('ij,ij->i',cb,n[b].mean(axis=1))
    bad=((da< -1e-10)&(area_a>1e-9))|((db< -1e-10)&(area_b>1e-9))
    bad|=(area_a<1e-10)|(area_b<1e-10)
    ring_size=int(section_kind.rsplit('_',1)[1])
    return np.flatnonzero(bad.reshape(-1,ring_size).any(axis=1))


def _safe_sweeps(points,width,height,ring_resolution):
    """Split only locally folded spans; retain every original centerline point."""
    stack=[points]
    result=[]
    added_splits=0
    unresolved=0
    while stack:
        piece=stack.pop()
        sweep=_sweep(piece,width,height,ring_resolution)
        bad=_folded_spans(sweep)
        if not len(bad):
            result.append((piece,sweep))
            continue
        cuts=sorted({int(i) for span in bad for i in (span,span+1) if 0<i<len(piece)-1})
        if not cuts:
            unresolved+=len(bad)
            result.append((piece,sweep))
            continue
        boundaries=[0]+cuts+[len(piece)-1]
        added_splits+=len(cuts)
        # Reversed stack insertion preserves original path ordering.
        stack.extend([piece[a:b+1] for a,b in zip(boundaries[:-1],boundaries[1:])][::-1])
    return result,added_splits,unresolved


def mesh_polylines(paths, sharp_turn_degrees=SHARP_TURN_DEGREES,ring_resolution=10,simplify_tolerance_mm=0.):
    """Return (mesh arrays, JSON-serializable report) without filtering features."""
    begun=time.perf_counter()
    verts=[];normals=[];quads=[];triangles=[];ranges=[];path_meta=[]
    nv=nq=nt=0
    turns=0
    fold_splits=0
    unresolved_folds=0
    input_segments=0
    for input_index,path in enumerate(paths):
        points=np.asarray(path['points_mm'],dtype=float)
        if points.ndim!=2 or points.shape[1]!=3 or len(points)<2 or not np.all(np.isfinite(points)):
            raise ValueError(f'Invalid points at input path {input_index}')
        width=float(path['width_mm']);height=float(path['layer_height_mm'])
        input_segments+=len(points)-1
        if simplify_tolerance_mm>0:
            points=simplify_polyline(points,simplify_tolerance_mm)
        pieces,turn_count=_split_at_sharp_turns(points,sharp_turn_degrees)
        turns+=turn_count
        safe=[]
        for sharp_piece_index,piece in enumerate(pieces):
            swept,added,unresolved=_safe_sweeps(piece,width,height,ring_resolution)
            fold_splits+=added;unresolved_folds+=unresolved
            safe.extend((sharp_piece_index,p,s) for p,s in swept)
        for piece_index,(sharp_piece_index,piece,sweep) in enumerate(safe):
            v,n,q,t,closed,section_kind=sweep
            verts.append(v.astype(np.float32));normals.append(n.astype(np.float32))
            quads.append(q+nv);triangles.append(t+nv)
            ranges.append([nv,len(v),nq,len(q),nt,len(t)])
            metadata={k:value for k,value in path.items() if k!='points_mm'}
            metadata.update({'input_path_index':input_index,'split_piece_index':piece_index,
                             'sharp_piece_index':sharp_piece_index,
                             'segments':len(piece)-1,'closed':closed,'section':section_kind,
                             'vertex_start':nv,'vertex_count':len(v),'quad_start':nq,'quad_count':len(q),
                             'triangle_start':nt,'triangle_count':len(t)})
            path_meta.append(metadata)
            nv+=len(v);nq+=len(q);nt+=len(t)
    mesh={
        'vertices':np.concatenate(verts) if verts else np.empty((0,3),np.float32),
        'vertex_normals':np.concatenate(normals) if normals else np.empty((0,3),np.float32),
        'quads':np.concatenate(quads).astype(np.int32) if quads else np.empty((0,4),np.int32),
        'triangles':np.concatenate(triangles).astype(np.int32) if triangles else np.empty((0,3),np.int32),
        'path_ranges':np.asarray(ranges,dtype=np.int64).reshape(-1,6),
    }
    report={
        'units':'millimeter', 'coordinate_system':'Original input print coordinates; no assembly transform applied.',
        'source_z_semantics':'Nozzle/layer top; bead center Z=source Z-layer_height/2.',
        'counts':{'input_paths':len(paths),'source_segments':input_segments,'swept_paths':len(path_meta),
                  'sharp_turn_splits':turns,'vertices':nv,'quads':nq,'endcap_triangles':nt,
                  'local_foldover_splits':fold_splits,'unresolved_foldover_spans':unresolved_folds,
                  'closed_paths':sum(p['closed'] for p in path_meta)},
        'bounds_mm':[mesh['vertices'].min(axis=0).astype(float).tolist(),mesh['vertices'].max(axis=0).astype(float).tolist()] if nv else None,
        'sharp_turn_split_threshold_degrees':sharp_turn_degrees,
        'ring_resolution_requested':ring_resolution,
        'polyline_simplification_tolerance_mm':simplify_tolerance_mm,
        'continuity_tolerance_mm':CONTINUITY_TOLERANCE_MM,
        'normal_convention':'Outward CCW faces. Quad sides may be smooth; cap triangles should be flat shaded.',
        'join_rule':'Rings use averaged XY tangents with lateral miter compensation to preserve segment-normal width. Turns beyond the threshold split into independently capped paths.',
        'local_foldover_guard':'Inverted or degenerate side spans are detected after float32 quantization and split at their endpoints. All source centerline points are retained; neighboring bead ends overlap instead of generating inward or twisted side faces.',
        'npz_schema':{k:{'shape':list(v.shape),'dtype':str(v.dtype)} for k,v in mesh.items()},
        'path_ranges_columns':['vertex_start','vertex_count','quad_start','quad_count','triangle_start','triangle_count'],
        'paths':path_meta,
        'elapsed_conversion_seconds':time.perf_counter()-begun,
        'scope':'Actual slicer paths with illustrative stadium bead cross sections. Separate bead volumes may overlap; not fused-flow simulation, Boolean union, or a complete watertight printed object.',
    }
    return mesh,report


def segments_to_mesh(records,schema=DEFAULT_SCHEMA,feature_names=None,**kwargs):
    return mesh_polylines(segments_to_polylines(records,schema,feature_names),**kwargs)


def write_mesh(path,mesh,report):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    np.savez_compressed(path,**mesh)
    report['npz_file']=str(path.resolve())
    report['npz_bytes']=path.stat().st_size
    report['npz_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
    path.with_suffix('.json').write_text(json.dumps(report,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
