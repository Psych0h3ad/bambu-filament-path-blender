# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Psych0h3ad

"""Remove duplicate same-material horizontal surface coverage, without offsets.

Convex polygon clipping in XY; NumPy only. Original bead coordinates are never
moved. Only a surface portion already covered by an earlier coplanar face is
removed. New intersection vertices are on the exact original plane.
"""
import math,time
from collections import defaultdict
import numpy as np

EPS=1e-9
AREA_EPS=1e-10

def signed_area(poly):
    if len(poly)<3:return 0.
    return .5*sum(float(a[0]*b[1]-a[1]*b[0])for a,b in zip(poly,poly[1:]+poly[:1]))

def clean(poly):
    out=[]
    for p in poly:
        if not out or math.dist(p,out[-1])>EPS:out.append(p)
    if len(out)>1 and math.dist(out[0],out[-1])<=EPS:out.pop()
    if len(out)<3 or abs(signed_area(out))<AREA_EPS:return []
    return out

def split_halfplane(poly,a,b):
    inside=[];outside=[]
    def cross(p):return (b[0]-a[0])*(p[1]-a[1])-(b[1]-a[1])*(p[0]-a[0])
    for p,q in zip(poly,poly[1:]+poly[:1]):
        dp,dq=cross(p),cross(q)
        if dp>=-EPS:inside.append(p)
        if dp<=EPS:outside.append(p)
        if (dp>EPS and dq< -EPS)or(dp< -EPS and dq>EPS):
            t=dp/(dp-dq);r=[p[0]+t*(q[0]-p[0]),p[1]+t*(q[1]-p[1])]
            inside.append(r);outside.append(r)
    return clean(inside),clean(outside)

def subtract_convex(subject,clip):
    intersection=subject
    for a,b in zip(clip,clip[1:]+clip[:1]):
        intersection,_=split_halfplane(intersection,a,b)
        if not intersection:return [subject]
    if abs(signed_area(intersection))<=AREA_EPS:return [subject]
    inside=subject;pieces=[]
    for a,b in zip(clip,clip[1:]+clip[:1]):
        inside,outside=split_halfplane(inside,a,b)
        if outside:pieces.append(outside)
        if not inside:break
    return pieces

def _flat_cleanup(mesh,region_xy=None,top_z=None,cell_mm=1.,normal_signs=(1,)):
    begun=time.perf_counter();vertices=mesh['vertices'];quads=mesh['quads'];normals=mesh['vertex_normals']
    material=np.asarray(mesh['quad_material_indices'])
    ids=[];face_signs={}
    for start in range(0,len(quads),100000):
        q=quads[start:start+100000];v=vertices[q];n=normals[q]
        up=np.all(n[:,:,2]>.999999,axis=1)
        down=np.all(n[:,:,2]<-.999999,axis=1)
        facing=(up if 1 in normal_signs else np.zeros(len(q),bool))|(down if -1 in normal_signs else np.zeros(len(q),bool))
        keep=(np.ptp(v[:,:,2],axis=1)==0)&facing
        if top_z is not None:keep&=np.abs(v[:,:,2].mean(1)-top_z)<1e-5
        if region_xy:
            x0,y0,x1,y1=region_xy
            keep&=(v[:,:,0].max(1)>x0)&(v[:,:,0].min(1)<x1)&(v[:,:,1].max(1)>y0)&(v[:,:,1].min(1)<y1)
        selected=np.flatnonzero(keep)
        ids.extend((selected+start).tolist())
        face_signs.update((int(i+start),1 if up[i] else -1)for i in selected)
    grid=defaultdict(list);polys={};bboxes={};changed={};area_removed=0.;pairs=0
    for count,idx in enumerate(ids):
        v=vertices[quads[idx]].astype(float);poly=v[:,:2].tolist()
        if signed_area(poly)<0:poly.reverse()
        # Use CCW clipping polygons; restore the original facing on output.
        cross=[]
        for a,b,c in zip(poly,poly[1:]+poly[:1],poly[2:]+poly[:2]):
            cross.append((b[0]-a[0])*(c[1]-b[1])-(b[1]-a[1])*(c[0]-b[0]))
        if min(cross)<-EPS:
            raise ValueError(f'Nonconvex horizontal quad {idx}; triangulate it before coplanar cleanup')
        bbox=[min(p[0]for p in poly),min(p[1]for p in poly),max(p[0]for p in poly),max(p[1]for p in poly)]
        plane=float(v[0,2]);mat=int(material[idx])
        # Opposite-facing surfaces at the same height are separate groups.
        cells=[(plane,mat,face_signs[idx],x,y)for x in range(math.floor(bbox[0]/cell_mm),math.floor(bbox[2]/cell_mm)+1)for y in range(math.floor(bbox[1]/cell_mm),math.floor(bbox[3]/cell_mm)+1)]
        candidates=sorted(set(p for cell in cells for p in grid[cell]))
        fragments=[poly]
        for other in candidates:
            b=bboxes[other]
            if min(bbox[2],b[2])-max(bbox[0],b[0])<=EPS or min(bbox[3],b[3])-max(bbox[1],b[1])<=EPS:continue
            pairs+=1;parts=[]
            for fragment in fragments:parts.extend(subtract_convex(fragment,polys[other]))
            fragments=parts
            if not fragments:break
        removed=abs(signed_area(poly))-sum(abs(signed_area(p))for p in fragments)
        if removed>AREA_EPS:
            changed[idx]=fragments;area_removed+=removed
        polys[idx]=poly;bboxes[idx]=bbox
        for cell in cells:grid[cell].append(idx)
    # Keep original coordinates and all unaffected faces exactly. Only clipped
    # horizontal quads are replaced with convex pieces on the same plane.
    keep=np.ones(len(quads),bool);newv=[];newn=[];newt=[];newm=[];sourceq=[];new_signs=[]
    for idx,fragments in changed.items():
        keep[idx]=False;z=float(vertices[quads[idx,0],2]);sign=face_signs[idx]
        for poly in fragments:
            start=len(vertices)+len(newv)
            newv.extend([[p[0],p[1],z]for p in poly])
            newn.extend([[0,0,sign]for p in poly])
            for i in range(1,len(poly)-1):
                newt.append([start,start+i,start+i+1]if sign==1 else[start,start+i+1,start+i])
                newm.append(material[idx]);sourceq.append(idx);new_signs.append(sign)
    result={k:np.array(mesh[k],copy=False)for k in ['colors']}
    result['vertices']=np.concatenate((vertices,np.asarray(newv,np.float32).reshape(-1,3)))
    result['vertex_normals']=np.concatenate((normals,np.asarray(newn,np.float32).reshape(-1,3)))
    result['quads']=quads[keep]
    newt=np.asarray(newt,np.int32).reshape(-1,3)
    precision_guard_dropped=0
    if len(newt):
        tv=result['vertices'][newt]
        twice_area=(tv[:,1,0]-tv[:,0,0])*(tv[:,2,1]-tv[:,0,1])-(tv[:,1,1]-tv[:,0,1])*(tv[:,2,0]-tv[:,0,0])
        valid=twice_area*np.asarray(new_signs)>2*AREA_EPS
        # Check the final float32 coordinates with float64 arithmetic as well.
        # Cancellation in a very thin cut fragment can inflate float32 area.
        tv64=tv.astype(np.float64)
        stable_area=(tv64[:,1,0]-tv64[:,0,0])*(tv64[:,2,1]-tv64[:,0,1])-(tv64[:,1,1]-tv64[:,0,1])*(tv64[:,2,0]-tv64[:,0,0])
        stable=stable_area*np.asarray(new_signs)>2*AREA_EPS
        precision_guard_dropped=int((valid&~stable).sum())
        valid&=stable
    else:valid=np.empty(0,bool)
    dropped=int((~valid).sum())
    newt=newt[valid];newm=np.asarray(newm,np.int16)[valid];sourceq=np.asarray(sourceq,np.int32)[valid]
    result['triangles']=np.concatenate((mesh['triangles'],newt))
    result['quad_material_indices']=material[keep]
    result['triangle_material_indices']=np.r_[mesh['triangle_material_indices'],newm]
    result['quad_face_kind']=np.asarray(mesh.get('quad_face_kind',np.zeros(len(quads),np.int8)))[keep]
    result['triangle_face_kind']=np.r_[mesh.get('triangle_face_kind',np.zeros(len(mesh['triangles']),np.int8)),np.asarray(mesh.get('quad_face_kind',np.zeros(len(quads),np.int8)))[sourceq]]
    # These indices refer to this cleanup's INPUT mesh, with combined face order
    # [quads, triangles]. They are not misleading one-to-one vertex bindings.
    result['quad_input_face_index']=np.flatnonzero(keep).astype(np.int32)
    result['triangle_input_face_index']=np.r_[np.arange(len(mesh['triangles']),dtype=np.int32)+len(quads),sourceq]
    if 'path_ranges' in mesh:
        ranges=np.asarray(mesh['path_ranges'])
        result['quad_source_bead_index']=(np.searchsorted(ranges[:,2],result['quad_input_face_index'],side='right')-1).astype(np.int32)
        old_tri_beads=np.searchsorted(ranges[:,4],np.arange(len(mesh['triangles'])),side='right')-1
        cut_beads=np.searchsorted(ranges[:,2],sourceq,side='right')-1
        result['triangle_source_bead_index']=np.r_[old_tri_beads,cut_beads].astype(np.int32)
    report={'candidate_top_quads':sum(face_signs[i]==1 for i in ids),
            'candidate_bottom_quads':sum(face_signs[i]==-1 for i in ids),
            'tested_bbox_pairs':pairs,'changed_top_quads':sum(face_signs[i]==1 for i in changed),
            'changed_bottom_quads':sum(face_signs[i]==-1 for i in changed),
            'cleaned_normal_signs':list(normal_signs),
            'precision_guard_dropped_triangles':precision_guard_dropped,
            'new_intersection_vertices':len(newv),'replacement_triangles':len(newt),'duplicate_area_removed_mm2':area_removed,
            'original_vertices_unchanged':bool(np.array_equal(result['vertices'][:len(vertices)],vertices)),
            'unaffected_quads_unchanged':True,'same_material_only':True,'plane_offset_mm':0,
            'affected_source_quad_indices':list(changed),'replacement_source_quad_indices':sourceq.tolist(),
            'float32_subresolution_triangles_dropped':dropped,
            'original_vertex_count':len(vertices),
            'face_provenance':'quad_input_face_index / triangle_input_face_index refer to input combined [quads,triangles]. Optional source_bead_index refers to input path_ranges / metadata source_bead_paths. Old contiguous ranges are retired after cleanup.',
            'elapsed_seconds':time.perf_counter()-begun,
            'scope':'Surface coverage union is preserved in XY; coincident duplicate horizontal coverage is subtracted within the same material, exact plane and facing. Bottom fragments retain downward normals and winding. Independent component watertightness is intentionally not asserted after removing internal duplicate surfaces.'}
    return result,report


def top_cleanup(mesh,region_xy=None,top_z=None,cell_mm=1.):
    """Compatibility entry point: clean upward-facing flat coverage only."""
    return _flat_cleanup(mesh,region_xy,top_z,cell_mm,normal_signs=(1,))


def flat_surface_cleanup(mesh,region_xy=None,top_z=None,cell_mm=1.):
    """Clean both flat sides, including the bed-facing side of face-down prints."""
    return _flat_cleanup(mesh,region_xy,top_z,cell_mm,normal_signs=(1,-1))
