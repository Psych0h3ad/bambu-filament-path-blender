# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Psych0h3ad

"""Round genuine open extrusion terminals of existing bead_mesh NPZ files.

CPU only; source arrays and files are never changed. Bodies are copied exactly.
Public API: round_caps(mesh, metadata, intermediate_rings=None, extent_fraction=.5)
            convert_file(source_npz, output_npz=None, intermediate_rings=None)
            run_diagnostics(output_dir=None)

The terminal is a scaled copy of the existing flattened section, swept outward
on an ellipsoidal dome: C + D*E*sin(theta) + S*cos(theta). E=width*extent_fraction
is bounded by width/2. It is an illustrative smooth polymer termination, not a
volume-conserving flow model. Original centerlines and layer section bounds are
unchanged. Closed components are unchanged. Coincident internal ends belonging
to the same source deposition path retain their original non-expanding flat
closures; this avoids artificial bulbs at meshing/width-change splits.

New NPZ source_vertex_index maps every vertex to the original NPZ: body and
retained centers map exactly; new dome rings map to their matching old endpoint
ring vertex; poles map to the old endcap center. Thus an existing shape-key
displacement array can be transplanted as new_basis + old_delta[source_vertex_index].
Do not replace new_basis positions with old shape-key coordinates.

Face kinds: 0 original body/closed surface, 1 rounded terminal, 2 retained flat
internal closure. source_face_index uses original combined [quads,triangles]
indexing; generated cap quads and triangles map to an old cap fan triangle.
Path ranges remain contiguous in separate vertex/quad/triangle arrays.
"""
from __future__ import annotations
from pathlib import Path
from collections import defaultdict, Counter
import argparse
import hashlib
import json
import math
import time
import numpy as np

ENDPOINT_TOLERANCE_MM = 2e-5


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _endpoint_info(mesh, meta):
    v, n = mesh['vertices'], mesh['vertex_normals']
    info = []
    for i, (p, row) in enumerate(zip(meta['paths'], mesh['path_ranges'])):
        vs, vc, qs, qc, ts, tc = map(int, row)
        k = int(p['section'].rsplit('_', 1)[1])
        closed = bool(p['closed'])
        if closed:
            assert tc == 0 and vc % k == 0, (i, row)
            info.append({'closed': True, 'k': k})
            continue
        assert tc == 2*k and (vc-2) % k == 0, (i, row)
        centers = [vs+vc-2, vs+vc-1]
        rings = [np.arange(vs,vs+k), np.arange(vs+vc-2-k,vs+vc-2)]
        for side, center in enumerate(centers):
            fan = mesh['triangles'][ts+side*k:ts+(side+1)*k]
            assert all(center in f for f in fan), ('Unexpected cap fan',i,side)
            direction = np.asarray(n[center],float)
            direction /= np.linalg.norm(direction)
            assert np.max(np.abs((v[rings[side]]-v[center])@direction)) < 1e-4
        info.append({'closed':False,'k':k,'centers':centers,'rings':rings,
                     'points':np.asarray(v[centers],float),'directions':np.asarray(n[centers],float)})
    return info


def classify_terminals(mesh, metadata, tolerance=ENDPOINT_TOLERANCE_MM):
    """Use source provenance AND coincident endpoints; never spatial proximity alone.

    Source path_id survives constant-width segmentation. input_path_index (or
    source_path_index where present) survives sharp-turn/foldover subdivision.
    Adjacent components in the same deposition identity are joined. A coincident
    last-to-first closure is also retained, including loops split for meshing.
    Slicer role/tool/travel-separated path IDs are not reclassified by proximity.
    """
    info = _endpoint_info(mesh, metadata)
    reasons = [['closed','closed'] if x['closed'] else ['open_terminal','open_terminal'] for x in info]
    groups = defaultdict(list)
    for i, p in enumerate(metadata['paths']):
        if info[i]['closed']:
            continue
        identity = ('path_id',p['path_id']) if p.get('path_id') is not None else ('input',p.get('source_path_index',p['input_path_index']))
        key = (identity,p.get('object_id'),p.get('tool_index'),p.get('color'),
               p.get('layer_top_z_mm'),p.get('layer_height_mm'))
        groups[key].append(i)
    joins = []
    for members in groups.values():
        members.sort(key=lambda i:(metadata['paths'][i].get('source_path_index',metadata['paths'][i]['input_path_index']),
                                   metadata['paths'][i].get('split_piece_index',0)))
        pairs=list(zip(members[:-1],members[1:]))
        if len(members)>1:
            pairs.append((members[-1],members[0]))
        for a,b in pairs:
            gap=float(np.linalg.norm(info[a]['points'][1]-info[b]['points'][0]))
            if gap>tolerance:
                continue
            pa,pb=metadata['paths'][a],metadata['paths'][b]
            ai=pa.get('source_path_index',pa['input_path_index'])
            bi=pb.get('source_path_index',pb['input_path_index'])
            reason='synthetic_mesh_split' if ai==bi else 'continuous_source_path_transition'
            reasons[a][1]=reason; reasons[b][0]=reason
            joins.append({'end_component':a,'start_component':b,'reason':reason,
                          'path_id':pa.get('path_id'),'gap_mm':gap})
    return info,reasons,joins


def round_caps(mesh, metadata, intermediate_rings=None, extent_fraction=.5):
    if not 0 < extent_fraction <= .5:
        raise ValueError('extent_fraction must be >0 and <=0.5')
    if intermediate_rings is not None and not 1 <= intermediate_rings <= 15:
        raise ValueError('intermediate_rings must be1..15 or None')
    begun=time.perf_counter()
    oldv=np.asarray(mesh['vertices']);oldn=np.asarray(mesh['vertex_normals'])
    oldq=np.asarray(mesh['quads']);oldt=np.asarray(mesh['triangles'])
    oldqm=np.asarray(mesh.get('quad_material_indices',np.zeros(len(oldq),np.int16)))
    oldtm=np.asarray(mesh.get('triangle_material_indices',np.zeros(len(oldt),np.int16)))
    if len(oldqm)!=len(oldq) or len(oldtm)!=len(oldt):
        raise ValueError('Material array length mismatch')
    info,reasons,joins=classify_terminals(mesh,metadata)
    allv=[];alln=[];allq=[];allt=[];allmap=[];allqm=[];alltm=[]
    allqsrc=[];alltsrc=[];allqkind=[];alltkind=[];ranges=[];paths=[]
    nv=nq=nt=0
    for pi,(p,row,item) in enumerate(zip(metadata['paths'],mesh['path_ranges'],info)):
        vs,vc,qs,qc,ts,tc=map(int,row);k=item['k']
        body_count=vc if item['closed'] else vc-2
        verts=[oldv[vs:vs+body_count].copy()]
        normals=[oldn[vs:vs+body_count].copy()]
        bindings=[np.arange(vs,vs+body_count,dtype=np.int64)]
        qlist=[oldq[qs:qs+qc].astype(np.int64)-vs]
        tlist=[];qmlist=[oldqm[qs:qs+qc].copy()];tmlist=[]
        qsrc=[np.arange(qs,qs+qc,dtype=np.int64)];tsrc=[]
        qkind=[np.zeros(qc,np.uint8)];tkind=[]
        local_nv=body_count
        cap_meta=[]
        for side in ([] if item['closed'] else [0,1]):
            center_old=item['centers'][side]
            center=oldv[center_old].astype(float)
            direction=oldn[center_old].astype(float)
            direction/=np.linalg.norm(direction)
            ring_old=item['rings'][side]
            fan_old_indices=np.arange(ts+side*k,ts+(side+1)*k)
            fan_mat=oldtm[fan_old_indices]
            assert np.all(fan_mat==fan_mat[0]), ('Mixed fan materials',pi,side)
            material=int(fan_mat[0])
            if reasons[pi][side]!='open_terminal':
                new_center=local_nv; local_nv+=1
                verts.append(center[None]);normals.append(direction[None])
                bindings.append(np.asarray([center_old],np.int64))
                faces=oldt[fan_old_indices].astype(np.int64)-vs
                faces[faces==center_old-vs]=new_center
                tlist.append(faces);tmlist.append(fan_mat)
                tsrc.append(len(oldq)+fan_old_indices);tkind.append(np.full(k,2,np.uint8))
                cap_meta.append({'side':side,'kind':reasons[pi][side],'extent_mm':0.})
                continue
            ring=oldv[ring_old].astype(float)
            profile=ring-center
            # Orient section boundary CCW about the outward terminal axis.
            area_vector=np.cross(profile,np.roll(profile,-1,axis=0)).sum(axis=0)
            order=np.arange(k) if np.dot(area_vector,direction)>0 else np.arange(k-1,-1,-1)
            ring_old=ring_old[order];profile=profile[order]
            profile_normals=oldn[ring_old].astype(float)
            support=np.einsum('ij,ij->i',profile_normals,profile)
            extent=float(p['width_mm'])*extent_fraction
            count=intermediate_rings if intermediate_rings is not None else 7
            previous=ring_old-vs
            # Match a boundary edge to the corresponding old cap triangle for
            # source-face binding, independent of old transformed winding.
            fan_by_edge={tuple(sorted(int(x) for x in f if int(x)!=center_old)):int(fi)
                         for f,fi in zip(oldt[fan_old_indices],fan_old_indices)}
            source_fan=np.asarray([fan_by_edge[tuple(sorted((int(ring_old[i]),int(ring_old[(i+1)%k]))))]
                                   for i in range(k)],np.int64)
            for theta in np.linspace(0,math.pi/2,count+2)[1:-1]:
                c,s=math.cos(theta),math.sin(theta)
                ring_v=center+direction*(extent*s)+profile*c
                ring_n=profile_normals*c+direction[None]*(support/extent*s)[:,None]
                ring_n/=np.linalg.norm(ring_n,axis=1)[:,None]
                current=np.arange(local_nv,local_nv+k);local_nv+=k
                verts.append(ring_v);normals.append(ring_n);bindings.append(ring_old)
                qlist.append(np.column_stack((previous,np.roll(previous,-1),np.roll(current,-1),current)))
                qmlist.append(np.full(k,material,np.int16));qsrc.append(len(oldq)+source_fan)
                qkind.append(np.ones(k,np.uint8));previous=current
            pole=local_nv;local_nv+=1
            verts.append((center+direction*extent)[None]);normals.append(direction[None])
            bindings.append(np.asarray([center_old],np.int64))
            tlist.append(np.column_stack((previous,np.roll(previous,-1),np.full(k,pole))))
            tmlist.append(np.full(k,material,np.int16));tsrc.append(len(oldq)+source_fan)
            tkind.append(np.ones(k,np.uint8))
            cap_meta.append({'side':side,'kind':'rounded_open_terminal','extent_mm':extent,
                             'intermediate_rings':count,'source_cap_center_vertex':center_old})
        v=np.concatenate(verts).astype(np.float32);n=np.concatenate(normals).astype(np.float32)
        q=np.concatenate(qlist).astype(np.int32)
        t=np.concatenate(tlist).astype(np.int32) if tlist else np.empty((0,3),np.int32)
        assert len(v)==local_nv
        allv.append(v);alln.append(n);allq.append(q+nv);allt.append(t+nv)
        allmap.append(np.concatenate(bindings));allqm.append(np.concatenate(qmlist))
        alltm.append(np.concatenate(tmlist) if tmlist else np.empty(0,np.int16))
        allqsrc.append(np.concatenate(qsrc));alltsrc.append(np.concatenate(tsrc) if tsrc else np.empty(0,np.int64))
        allqkind.append(np.concatenate(qkind));alltkind.append(np.concatenate(tkind) if tkind else np.empty(0,np.uint8))
        ranges.append([nv,len(v),nq,len(q),nt,len(t)])
        newp=dict(p)
        newp.update(vertex_start=nv,vertex_count=len(v),quad_start=nq,quad_count=len(q),triangle_start=nt,triangle_count=len(t),
                    original_ranges=list(map(int,row)),terminal_caps=cap_meta)
        paths.append(newp);nv+=len(v);nq+=len(q);nt+=len(t)
    out={
        'vertices':np.concatenate(allv),'vertex_normals':np.concatenate(alln),
        'quads':np.concatenate(allq),'triangles':np.concatenate(allt),
        'path_ranges':np.asarray(ranges,np.int64),'source_vertex_index':np.concatenate(allmap),
        'quad_source_face_index':np.concatenate(allqsrc),'triangle_source_face_index':np.concatenate(alltsrc),
        'quad_face_kind':np.concatenate(allqkind),'triangle_face_kind':np.concatenate(alltkind),
    }
    # Preserve scalar/palette/custom metadata arrays, excluding geometry-indexed arrays.
    for key,value in mesh.items():
        if key not in {'vertices','vertex_normals','quads','triangles','path_ranges','quad_material_indices','triangle_material_indices','material_perface'}:
            if key in out:
                raise ValueError('Input appears already rounded: '+key)
            out[key]=np.asarray(value).copy()
    if 'quad_material_indices' in mesh or 'triangle_material_indices' in mesh:
        out['quad_material_indices']=np.concatenate(allqm)
        out['triangle_material_indices']=np.concatenate(alltm)
        out['material_perface']=np.r_[out['quad_material_indices'],out['triangle_material_indices']]
    result=dict(metadata)
    result['paths']=paths
    result['original_counts']=metadata.get('counts',{})
    result['counts']={**metadata.get('counts',{}),'vertices':nv,'quads':nq,'endcap_triangles':nt}
    result['bounds_mm']=[out['vertices'].min(axis=0).astype(float).tolist(),out['vertices'].max(axis=0).astype(float).tolist()]
    result['rounded_terminals']={
        'algorithm':'Scaled original section ellipsoidal dome, with exact shared base ring.',
        'intermediate_rings':intermediate_rings if intermediate_rings is not None else 7,
        'extent_fraction_of_width':extent_fraction,
        'counts':dict(Counter(reason for pair in reasons for reason in pair)),
        'internal_join_count':len(joins),'internal_joins':joins,'endpoint_match_tolerance_mm':ENDPOINT_TOLERANCE_MM,
        'growth':{'vertices':nv-len(oldv),'quads':nq-len(oldq),'triangles':nt-len(oldt),
                  'vertex_factor':nv/len(oldv),'polygon_factor':(nq+nt)/(len(oldq)+len(oldt))},
        'original_bounds_mm':[oldv.min(axis=0).astype(float).tolist(),oldv.max(axis=0).astype(float).tolist()],
        'source_vertex_index_binding':'Exact old index for copied vertices; matching endpoint ring vertex for each new dome ring; old cap center for pole. Apply old shape-key DISPLACEMENTS to new basis.',
        'source_face_index_binding':'Original combined [quads,triangles] face indexing; generated cap surfaces bind corresponding old fan triangle.',
        'face_kind_schema':{'0':'original body or closed surface','1':'rounded open terminal','2':'non-expanding internal closure'},
        'internal_join_policy':'Retain exact original flat closures at coincident synthetic subdivisions and same-path width/metadata transitions. This avoids extra bulbs or gaps; existing neighboring bead solids can overlap.',
        'provenance_limit':'A source path_id can also begin at slicer role/tool/travel changes. Coincident endpoints with different source path IDs are not merged without evidence of uninterrupted deposition.',
        'physical_limit':'Illustrative terminal shape, not measured polymer flow, volume conservation, Boolean fusion, or collision-proof printed-object geometry.',
        'elapsed_seconds':time.perf_counter()-begun,
    }
    result['normal_convention']='Outward CCW. Rounded terminal quads and pole triangles use continuous analytical normals; preserved internal fan faces may remain flat.'
    result['npz_schema']={k:{'shape':list(v.shape),'dtype':str(v.dtype)} for k,v in out.items()}
    return out,result


def audit_mesh(mesh,metadata,source=None):
    """Complete float32 area/winding/topology checks; no physical-union claim."""
    v=np.asarray(mesh['vertices'],float);n=np.asarray(mesh['vertex_normals'],float)
    q=mesh['quads'];t=mesh['triangles'];ranges=mesh['path_ranges']
    triangles=np.concatenate((q[:,[0,1,2]],q[:,[0,2,3]],t))
    crosses=np.cross(v[triangles[:,1]]-v[triangles[:,0]],v[triangles[:,2]]-v[triangles[:,0]])
    area=np.linalg.norm(crosses,axis=1)/2
    reference=np.einsum('ij,ij->i',crosses,n[triangles].mean(axis=1))
    # Radial sector closures use explicit flat loop normals in Blender.
    # Their curved boundary vertex normals are tangent to the cut plane.
    # Edge orientation and positive volume below independently check winding.
    if 'quad_face_kind' in mesh and 'triangle_face_kind' in mesh:
        flat_radial=np.concatenate((mesh['quad_face_kind']==4,mesh['quad_face_kind']==4,mesh['triangle_face_kind']==4))
        reference[flat_radial]=0
    edges=np.concatenate((np.stack((q,np.roll(q,-1,axis=1)),axis=-1).reshape(-1,2),
                          np.stack((t,np.roll(t,-1,axis=1)),axis=-1).reshape(-1,2)))
    keys=np.minimum(edges[:,0],edges[:,1]).astype(np.int64)*len(v)+np.maximum(edges[:,0],edges[:,1])
    order=np.argsort(keys);keys=keys[order]
    starts=np.r_[0,np.flatnonzero(np.diff(keys))+1]
    incidence=np.diff(np.r_[starts,len(keys)])
    balance=np.add.reduceat(np.where(edges[:,0]<edges[:,1],1,-1)[order],starts)
    expected=np.zeros(3,np.int64);valid=True;confined=True;volumes=[]
    for vs,vc,qs,qc,ts,tc in ranges:
        valid &= bool(np.array_equal([vs,qs,ts],expected));expected+=[vc,qc,tc]
        faces=np.concatenate((q[qs:qs+qc][:,[0,1,2]],q[qs:qs+qc][:,[0,2,3]],t[ts:ts+tc]))
        confined &= bool(faces.min()>=vs and faces.max()<vs+vc)
        a,b,c=(v[faces[:,i]]-v[vs] for i in range(3))
        volumes.append(float(np.einsum('ij,ij->i',a,np.cross(b,c)).sum()/6))
    valid &= bool(np.array_equal(expected,[len(v),len(q),len(t)]))
    result={
        'finite':bool(np.isfinite(v).all() and np.isfinite(n).all()),
        'ranges_contiguous_complete':valid,'faces_confined_to_component':confined,
        'boundary_or_nonmanifold_edges':int((incidence!=2).sum()),'inconsistently_oriented_edges':int((balance!=0).sum()),
        'triangles_degenerate_area_lt_1e_10_mm2':int((area<1e-10).sum()),
        'triangles_inverted_against_analytic_normal':int(((reference< -1e-10)&(area>1e-9)).sum()),
        'minimum_triangle_area_mm2':float(area.min()),'minimum_component_signed_volume_mm3':min(volumes),
        'nonpositive_signed_volume_components':sum(x<=0 for x in volumes),
        'normal_length_range':[float(np.linalg.norm(n,axis=1).min()),float(np.linalg.norm(n,axis=1).max())],
        'scope':'Each component tested for closed oriented edge topology; separate solids may overlap. No Boolean-union or collision audit.',
    }
    if source is not None:
        mapping=mesh['source_vertex_index']
        result['source_vertex_mapping_valid']=bool(len(mapping)==len(v) and mapping.min()>=0 and mapping.max()<len(source['vertices']))
        result['copied_body_vertices_exact']=True
        result['copied_body_quads_exact']=True
        for newrow,oldrow,p in zip(ranges,source['path_ranges'],metadata['paths']):
            nvs,nvc,nqs,nqc,nts,ntc=map(int,newrow);ovs,ovc,oqs,oqc,ots,otc=map(int,oldrow)
            bc=ovc if p['closed'] else ovc-2
            result['copied_body_vertices_exact'] &= bool(np.array_equal(mesh['vertices'][nvs:nvs+bc],source['vertices'][ovs:ovs+bc]))
            result['copied_body_quads_exact'] &= bool(np.array_equal(mapping[mesh['quads'][nqs:nqs+oqc]],source['quads'][oqs:oqs+oqc]))
        if 'quad_material_indices' in source:
            old_material=np.r_[source['quad_material_indices'],source['triangle_material_indices']]
            result['source_face_material_binding_exact']=bool(
                np.array_equal(mesh['quad_material_indices'],old_material[mesh['quad_source_face_index']]) and
                np.array_equal(mesh['triangle_material_indices'],old_material[mesh['triangle_source_face_index']]) and
                np.array_equal(mesh['material_perface'],np.r_[mesh['quad_material_indices'],mesh['triangle_material_indices']]))
    result['pass']=bool(result['finite'] and valid and confined and not any(result[k] for k in (
        'boundary_or_nonmanifold_edges','inconsistently_oriented_edges','triangles_degenerate_area_lt_1e_10_mm2',
        'triangles_inverted_against_analytic_normal','nonpositive_signed_volume_components'))
        and result.get('source_vertex_mapping_valid',True) and result.get('copied_body_vertices_exact',True)
        and result.get('copied_body_quads_exact',True) and result.get('source_face_material_binding_exact',True))
    return result


def convert_file(source_npz, output_npz=None, intermediate_rings=None, audit=True):
    source_npz=Path(source_npz)
    output_npz=Path(output_npz) if output_npz else source_npz.with_name(source_npz.stem+'_round.npz')
    if source_npz.resolve()==output_npz.resolve():
        raise ValueError('Source overwrite forbidden')
    with np.load(source_npz,allow_pickle=False) as packed:
        source={k:packed[k] for k in packed.files}
    metadata=json.loads(source_npz.with_suffix('.json').read_text(encoding='utf-8'))
    mesh,report=round_caps(source,metadata,intermediate_rings)
    report['source_npz_file']=str(source_npz.resolve());report['source_npz_sha256']=_sha(source_npz)
    if audit:
        report['rounded_terminal_audit']=audit_mesh(mesh,report,source)
        if not report['rounded_terminal_audit']['pass']:
            raise ValueError('Rounded mesh audit failed: '+json.dumps(report['rounded_terminal_audit']))
    from .bead_mesh import write_mesh
    write_mesh(output_npz,mesh,report)
    return report


def run_diagnostics(output_dir=None):
    from .bead_mesh import mesh_polylines,write_mesh
    output_dir=Path(output_dir) if output_dir else Path(__file__).resolve().parent/'round_caps_diagnostics'
    output_dir.mkdir(parents=True,exist_ok=True)
    specs={
        'open_line':[[0,0,.2],[10,0,.2]],
        'short_line':[[0,0,.2],[.005,0,.2]],
        'curved':[[3*math.sin(a),3*(1-math.cos(a)),.2] for a in np.linspace(0,1.4,20)],
        'closed':[[3*math.cos(a),3*math.sin(a),.2] for a in np.linspace(0,2*math.pi,49)],
        'thin_ironing':[[230,70,3.0075],[234,70,3.0075]],
        'internal_sharp_split':[[0,0,.2],[5,0,.2],[.5,1,.2]],
        'width_transition':[[0,0,.2],[5,0,.2]],
        'closed_split_loop':[[((3 if i%2==0 else .8)*math.cos(i*math.pi/5)),
                              ((3 if i%2==0 else .8)*math.sin(i*math.pi/5)),.2] for i in range(11)],
        'transformed_mirrored_line':[[0,0,.2],[10,0,.2]],
    }
    result={}
    for name,points in specs.items():
        h=.0075 if name=='thin_ironing' else .2
        path={'points_mm':points,'width_mm':.42,'layer_height_mm':h,'layer_top_z_mm':points[0][2],
              'feature':'diagnostic','path_id':100,'tool_index':0,'color':'#4080C0'}
        paths=[path]
        if name=='width_transition':
            paths.append({**path,'points_mm':[[5,0,.2],[10,0,.2]],'width_mm':.55})
        source,meta=mesh_polylines(paths,ring_resolution=10)
        layer_axis=np.asarray([0.,0.,1.])
        if name=='transformed_mirrored_line':
            a=math.radians(37)
            transform=np.asarray([[-1,0,0],[0,math.cos(a),-math.sin(a)],[0,math.sin(a),math.cos(a)]])
            source['vertices']=(source['vertices']@transform.T).astype(np.float32)
            source['vertex_normals']=(source['vertex_normals']@transform.T).astype(np.float32)
            source['quads']=source['quads'][:,::-1].copy()
            source['triangles']=source['triangles'][:,::-1].copy()
            layer_axis=transform@layer_axis
        source['colors']=np.asarray(['#4080C0'])
        source['quad_material_indices']=np.zeros(len(source['quads']),np.int16)
        source['triangle_material_indices']=np.zeros(len(source['triangles']),np.int16)
        source['material_perface']=np.zeros(len(source['quads'])+len(source['triangles']),np.int16)
        mesh,report=round_caps(source,meta)
        audit=audit_mesh(mesh,report,source)
        original_z=source['vertices']@layer_axis
        new_z=mesh['vertices']@layer_axis
        audit['layer_z_bounds_preserved']=bool(new_z.min()>=original_z.min()-1e-6 and new_z.max()<=original_z.max()+1e-6)
        audit['expected_round_terminal_count']=0 if name in ('closed','closed_split_loop') else 2
        audit['round_terminal_count_correct']=report['rounded_terminals']['counts'].get('open_terminal',0)==audit['expected_round_terminal_count']
        audit['pass'] &= audit['layer_z_bounds_preserved'] and audit['round_terminal_count_correct']
        if name=='closed':
            audit['closed_vertices_unchanged']=bool(np.array_equal(mesh['vertices'],source['vertices']))
            audit['closed_faces_unchanged']=bool(np.array_equal(mesh['quads'],source['quads']))
            audit['pass'] &= audit['closed_vertices_unchanged'] and audit['closed_faces_unchanged']
        if name in ('internal_sharp_split','width_transition','closed_split_loop'):
            audit['internal_join_preserved']=report['rounded_terminals']['internal_join_count']>0
            audit['pass'] &= audit['internal_join_preserved']
        report['rounded_terminal_audit']=audit
        write_mesh(output_dir/(name+'_round.npz'),mesh,report)
        result[name]={'audit':audit,'terminal_counts':report['rounded_terminals']['counts'],
                      'growth':report['rounded_terminals']['growth'],'bounds_mm':report['bounds_mm']}
    summary={'pass':all(x['audit']['pass'] for x in result.values()),'tests':result}
    (output_dir/'diagnostic_audit.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source_npz',nargs='?');parser.add_argument('--output')
    parser.add_argument('--rings',type=int);parser.add_argument('--diagnostics',action='store_true')
    args=parser.parse_args()
    if args.diagnostics:
        report=run_diagnostics(args.output)
        print(json.dumps(report,indent=2))
        if not report['pass']:
            raise SystemExit(1)
    else:
        if not args.source_npz:
            parser.error('source_npz or --diagnostics required')
        report=convert_file(args.source_npz,args.output,args.rings)
        print(json.dumps({k:report[k] for k in ['npz_file','counts','bounds_mm','rounded_terminal_audit']}))
