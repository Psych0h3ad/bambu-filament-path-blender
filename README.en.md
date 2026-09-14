# Bambu Rounded Beads for Blender

[日本語](README.md) · [Download](https://github.com/Psych0h3ad/bambu-rounded-beads-blender/releases/latest) · [GitHub Sponsors](https://github.com/sponsors/Psych0h3ad)

Turn annotated Bambu Studio G-code into a Blender mesh with visible printed layers and rounded extrusion ends. The add-on was made for a MakerChip rendering tutorial and can import other models that use the supported annotations.

It reconstructs illustrative deposited-bead sections from the original line widths and layer heights, preserves filament material assignments, and adds dome caps at genuine open path ends. It creates a new mesh from G-code; it does not bevel a native OBJ.

## Install

1. Download **Bambu_Rounded_Beads-1.0.0.zip** from [Releases](https://github.com/Psych0h3ad/bambu-rounded-beads-blender/releases/latest). Use the installable asset, not GitHub's automatic “Source code (zip)”.
2. In Blender, open **Edit → Preferences → Add-ons**.
3. Open the upper-right menu, choose **Install from Disk**, and select the ZIP without extracting it.
4. Enable **Bambu Rounded Beads**.

Uses NumPy bundled with Blender; no additional Python installation is normally needed. Installation, enabling, and importing were tested on **Blender 5.2.1 LTS for Windows**. The add-on declares Blender 4.5 as its minimum, but other versions and operating systems have not all been tested. The verified slicer version is Bambu Studio 2.8.2.61.

## Use

1. Slice a plate containing **one object** in Bambu Studio, then export annotated `.gcode`.
2. Switch Blender to Object Mode and choose **File → Import → Bambu G-code — Rounded Beads (.gcode)**.
3. Select the file. Leave **Object Label** blank when the file contains one object.
4. Set **Center XY / Ground Z** and **Match Native Black** as desired, then click **Import Rounded Beads**.
5. The new object is named `MakerChip_Rounded`. If a native OBJ overlaps it, hide that original object in both viewport and render.
6. Set your camera, lighting, and materials, then render. Existing cameras, lights, materials, and render settings are retained.

| Option | Behavior |
| --- | --- |
| Object Label | Selects one object identifier from a multi-object file. If left blank, an error lists available identifiers when there is more than one. |
| Center XY / Ground Z | Centers the generated XY bounds and grounds the lowest vertex at Z=0. Millimeters are converted to Blender meters. |
| Match Native Black | Displays source `#000000` as `#333333` for comparison with Bambu's native OBJ palette. Original source colors remain in material properties. |

There is no nozzle-diameter input. Bead dimensions come from the G-code's **LINE_WIDTH / LAYER_HEIGHT** annotations. Nozzle diameter and deposited line width are different values.

## Geometry

- Usually ten vertices around a flattened bead section, with eight for circular/vertical-ellipse cases.
- Three intermediate dome rings at genuine open terminals; maximum outward extent is half the local line width.
- No expanding caps at same-path width transitions or synthetic meshing subdivisions; closed paths receive no terminal domes.
- Includes supported deposition roles such as exposed sparse infill and preserves tool/material IDs.
- No straight-path simplification. XY G2/G3 arcs are tessellated with a target maximum chord error of 0.005 mm.

This is **illustrative rendering geometry**, not polymer-flow, fusion, or volume-conservation simulation. Separate bead volumes may overlap. It is not a Boolean-unified printable replacement model.

## Input scope and performance

Requires Bambu annotations including `filament_colour` inside `CONFIG_BLOCK`, object identifiers, `FEATURE`, `LINE_WIDTH`, and `LAYER_HEIGHT`. Does not directly import 3MF or OBJ. Arbitrary G-code dialects, other arc planes such as G18/G19, and radius-form arcs are not guaranteed to work.

A 40 mm, 30-layer chip can produce about 4.51 million vertices and 4.85 million faces. Time and memory requirements depend strongly on the file and computer. Start with one object.

G-code is read as inert text. The add-on does not send printer commands, contact a network, or modify the source file. Generated objects record the source filename, without the user's absolute filesystem path.

## Development and validation

With Python and NumPy installed:

```sh
python -m unittest discover -s tests -v
python tools/build_release.py
```

The installable ZIP is written to `dist/`. To exercise the actual Blender importer:

```sh
blender --background --factory-startup --python tests/blender_smoke.py
```

Tests generate synthetic paths at runtime; no user models, G-code projects, or printer profiles are included. Checks cover open ends, closed loops, continuous width transitions, face winding, closed edge topology, material assignments, unit scale, and retention of an existing scene.

## Support development

I make small tools for the things I wish already existed. If this helps your workflow, consider supporting development through [GitHub Sponsors](https://github.com/sponsors/Psych0h3ad). Sponsors are welcome!

Report bugs and ideas in [Issues](https://github.com/Psych0h3ad/bambu-rounded-beads-blender/issues). Only attach reproductions that you have permission to share publicly.

## License

Copyright © 2026 Psych0h3ad. **GPL-3.0-or-later**; see [LICENSE](LICENSE). This is an independent project, not an official Bambu Lab or Blender Foundation add-on.
