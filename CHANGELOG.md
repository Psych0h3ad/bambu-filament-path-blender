# Changelog

## 1.1.1 — 2026-09-14

- Rename the product to Bambu Filament Path across the Blender interface, documentation, and installable ZIP.
- Move the repository to `Psych0h3ad/bambu-filament-path-blender`; keep existing releases and assets.
- Preserve all geometry code, defaults, and internal module/operator IDs so existing installations can be updated in place.

## 1.1.0 — 2026-09-14

- Increase all filament cross-sections to 26 points (24 for circles/vertical ellipses) and true terminal domes to 11 intermediate rings; preserve source centerlines, width, and layer height.
- Refine source XY G2/G3 arc tessellation from 0.005 mm to 0.001 mm chord error while retaining arc center, direction, and exact move endpoints.
- Round outer and inner wall bends with at least a 64-segment-circle equivalent and 0.00025 mm maximum chord error. Use outer convex sectors where adjacent strips cover the omitted disk; retain complete disks for short segments, including a conservative residual-miter margin.
- Preserve ordered expanded source identities so local safe-sweep splits cannot create false terminal caps. Retain original source indices separately.
- Give internal radial sector closures explicit flat loop normals while keeping smooth curved-surface normals.
- Fix dark self-shadow specks from coincident flat top faces by removing duplicate coverage only where material and plane height match exactly. Keep original vertices fixed and place new clipping intersections on the original plane; no artificial Z offset.
- Preserve face kinds, material IDs, analytic normals, and explicit face-to-input-face/source-path provenance after cleanup. Retire obsolete contiguous path ranges rather than exposing stale indices.
- Explicitly remind users to hide the previous native model in both viewport and render; never hide existing objects automatically.

Restart Blender after updating the ZIP, then re-import the G-code. Previously imported meshes are not modified automatically. Version 1.0.1 was an internal validation candidate and was not published separately.

## 1.0.0 — 2026-09-14

Initial public release.

- Blender File → Import operator for annotated Bambu G-code.
- Source-width and layer-height filament cross-sections, preserved filament material IDs, and rounded genuine path terminals.
- No expanding bulbs at continuous-path width transitions or synthetic mesh splits.
- Optional XY centering, floor placement, and native black preview matching.
- Source filenames retained without absolute user paths.
- Japanese and English installation instructions, synthetic geometry tests, Blender import smoke test, and reproducible installable ZIP builder.

Tested with Blender 5.2.1 LTS on Windows and Bambu Studio 2.8.2.61 input. Geometry is an illustration for rendering, not fused-polymer simulation.
