# Roofs

Declare a roof from its base boundary, the way a roof tool does, and let the
compiler resolve overhang, skeleton, tiling, and openings.

## Declaration

```python
roof(model, "main-roof", storey="first",
     boundary=[(0.0, 0.0), (15.39, 0.0), (15.39, 12.0), (0.0, 12.0)],
     angle=30.0, thickness=0.30,
     top_material="roof.structure", ceiling_material="ceiling.white",
     side_material="facade.render",
     base_offset=2.407, overhang=0.5,
     covering="tile.clay", covering_material="tile.terracotta")
roof_edge(model, "main-roof", 1, defines_slope=False)   # gable
roof_edge(model, "main-roof", 3, defines_slope=False)

roof_window(model, "skylight.0", roof="main-roof",
            edge=0, along=4.5, up_slope=1.8, width=0.94, height=1.40,
            material="frame.metal", glazing="glazing")
```

`base_offset` positions the **eave**, not the wall top. With an overhang the
sloping span is the footprint plus both overhangs, so solve backwards from the
ridge you want:

```python
span = depth + 2 * overhang
eave_z = ridge_height - (span / 2) * tan(pitch)
```

Declare as many roofs as the building needs; each owns its key namespace
(`<roof>.edge.<i>`, `<roof>.covering`, `<window>.opening`).

Roof windows are positioned against a **declared boundary edge**, not a face
index: faces are straight-skeleton output whose numbering shifts whenever the
boundary changes, while edges are declared.

## What maps to what in IFC

The script's vocabulary follows IFC wherever IFC has an opinion. Encapsulate,
but never contradict.

| declaration | IFC |
| --- | --- |
| `roof(...)` | `IfcRoof`, `PredefinedType` derived from the gable flags |
| `top_material=`, `ceiling_material=`, `side_material=` | one `IfcShapeAspect` and material constituent per roof-body face role |
| `covering=` | `IfcCovering` / `ROOFING`, tied by `IfcRelCoversBldgElements` |
| `roof_window(...)` | `IfcWindow` / `SKYLIGHT` |
| its opening | `IfcOpeningElement` + `IfcRelVoidsElement` + `IfcRelFillsElement` |
| `profile=` | `IfcWindowType` + `IfcRelDefinesByType` |
| roof-window `material=` + `glazing=` | `IfcShapeAspect` per role + `IfcMaterialConstituentSet` |
| `boundary`, `angle`, `defines_slope` | the `BBIM_Roof` pset |

`defines_slope` has no IFC entity and should not have one - it is authoring
intent, and IFC's mechanism for that is a pset. Writing `BBIM_Roof` is what
keeps a script-authored roof editable by Bonsai's own roof tool instead of
arriving as dead geometry.

The roof body always declares three materials. Upward faces are `Top`,
downward faces are `Ceiling`, and every perimeter or cut face is `Side`.
They remain parts of one closed `IfcRoof`; the roles split its representation
items and bind one material constituent to each shape aspect.

A roof window is **one IFC element carrying both its materials**, not a BIM
element with a second copy of itself beside it. The frame procedure names a
role per face, those roles become one representation item and one
`IfcShapeAspect` each, and `set_shape_aspect_constituents` binds a material to
every aspect - so Bonsai imports the window already split into frame and pane
slots. Both its opening and its own body are placed in the roof face's frame
(X across the eave, Y up the slope, Z normal), so neither carries world
coordinates.

Use `ifcopenshell.api.feature.add_feature` / `add_filling`. The
`ifcopenshell.api.void` module most tutorials show does not exist in 0.8.5.

## Who does what

- **Overhang** is solved in `polygons.offset_polygon()` before any skeleton
  runs: each edge is pushed along its outward normal by its own overhang and
  neighbours are mitred. The skeleton then receives a plain polygon.
- **The solid** is Bonsai's `generate_hipped_roof_bmesh` - straight skeleton,
  gables, thickness normal to each plane, rafter edge cut.
- **The tile field** is laid out by `tiles.centres()` and cropped by boolean.
- **Ridge and hip caps** are laid out by `caps.spacing()` along the arrises
  `trims.edge_kind()` classifies, and merged into that same field. They are
  never cropped: a cap closes the join between two fields that were each cut
  flush to the arris, so it has to oversail it. See
  [references/caps.md](caps.md).

Both phases recompute the skeleton from the same resolved payload rather than
passing geometry between them, so the compiled batches stay independent.

## The skeleton seam

`bpypolyskel` is a third-party package (prochitecture/bpypolyskel), not Bonsai
code. Its entry point takes a **single scalar** `tan`, which is what makes it
unweighted:

```python
polygonize(verts, firstVertIndex, numVerts, holesInfo=None,
           height=0.0, tan=0.0, faces=None, unitVectors=None)
```

So edges that define slope must currently agree on pitch.
`skeleton.classify()` detects disagreement and `validate()` rejects it by name,
rather than letting the unweighted skeleton emit a roof that merely looks
plausible. Gables never force this, because a gable imposes no pitch.

That refusal is also what makes the `BBIM_Roof` pset safe to write: anything
carrying it is by construction something Bonsai can regenerate identically.

**Promotion path.** The backward-compatible generalisation is to let `tan`
accept either a float or one value per edge; a scalar then reproduces today's
output exactly. `skeleton.weights()` already returns that per-edge sequence.
Promoting the work upstream is a file move plus a signature widening, followed
by a small patch to `generate_hipped_roof_bmesh`. Keep anything written toward
that goal pure Python, depending on nothing beyond `mathutils` and the standard
library, and pin the scalar case with tests first.

Do not fork Bonsai to get there. The weighted skeleton has no dependency on
`bpy`, IFC, or Bonsai, and a fork would make the skill require a patched
install instead of a stock one.

## Procedures build every mesh

Tiles, ridge caps and window frames are **procedures, not assets**. One
procedure per type, each standalone and readable; adding a type means writing
another procedure next to the existing ones, not extending a shared engine.

Every procedure returns the contract in `procedures.py`:

```python
(verts, faces, uvs, slots)
```

`slots` names a **material role** per face - `"tile"`, `"frame"`, `"glazing"`.
A procedure knows a pane is glass; it has no business knowing which glass the
building declared. The declaration maps roles onto materials, and those roles
become Blender material slots and IFC constituents alike. Returning one
material per mesh silently paints a window frame with the pane's material.

`procedures.validate_mesh()` checks face, uv, and slot counts agree and that
indices exist, at the procedure boundary rather than as a confusing Blender
error later.

## Layout, then crop

`tiles.centres()` builds a grid
at the tile's own module, snapped with `floor()`, offset course by course by
the bond, keeping a tile when **any** of its four corners falls inside the
face. Fixed module spacing, never stretched - stretching leaves visible gaps
between tiles.

### The bond

`covering_stagger` is the fraction of a tile width each course is offset from
the one below, at least zero and strictly below one. It **accumulates** up the
roof, so the ordinary patterns are the ordinary values rather than special
cases:

| stagger | pattern |
| --- | --- |
| `0.0` | stacked - every course in the same columns |
| `0.5` (default) | broken bond, repeating every two courses |
| `1/3` | running bond, repeating every three |

A whole width would land back on the same columns, which is why the range
stops short of one.
Each profile carries its own default, and `covering_stagger` overrides it per
roof, so one tile can be laid stacked on one roof and broken on another
without declaring two profiles.

### The sweep bounds

A tile is a candidate while its own extent crosses the face's, not while its
centre is inside. The keep test is on the tile's corners while the sweep steps
its centre, so bounding by the centre leaves a
course short of the edge by up to half a module. Because the bond moves that
shortfall from course to course, it reads as every second course ending early.
The bond breaks the near bound the same way: an offset course starts a fraction
of a module late unless the sweep steps back onto the tile that still overlaps.

Both comparisons are strict, so a tile that would only touch the bound is never
laid - it would contribute nothing but a degenerate solid for the crop to
resolve. On a face measuring a whole number of modules this makes the sweep
identical to a centre-bounded one, which is exactly why the shortfall hides on
tidy test geometry.

Courses run from the eave upwards. The first course sits half a module above
`v = 0` so its lower edge lands on the eave; centring it there would bury half
the eave course below the roof edge. The caller must hand in a frame whose
`v = 0` is the eave, which `face_frame()` guarantees by anchoring on the face's
lowest horizontal edge.

The field is then **merged into one mesh per roof and cropped by boolean**:

- `crop_to_face()` intersects each face's field with a prism spanning that
  face. Per face, not per roof, because tiles from adjacent faces overlap
  along ridges and hips and each face wants cropping to its own plane.
- `subtract_window()` differences each roof window's opening box out of the
  covering - the same box that voids the IFC roof, so the hole in the tiles is
  the hole in the BIM.

Boolean with the `EXACT` solver is the **only** crop. Bisecting edge by edge is
far faster but valid only on convex regions, and a reflex corner in the roof
boundary produces faces that are not convex. Keeping both would mean a second
path exercised rarely and trusted wrongly. Boolean also caps the cut faces, so
trim is a finish rather than a correctness dependency.

### Both booleans set `use_self`, and must

The field self-intersects: every unit laps the course below it, and a
pantile's rolls interpenetrate their neighbours besides. `EXACT` assumes
operands that do not, and given ones that do it returns **nothing** - no
error, no warning, an empty mesh, and a roof with no covering on it.

Splitting the tile field by face separates adjacent fields. Laps within a
face still intersect and require `use_self`.

An empty result from a non-empty field now raises. A boolean that eats its
whole input is the failure this is most likely to hit and the hardest to see -
every later stage runs happily on nothing.

Cost is real: seconds per roof, dominated by the solver. That is the price of
one robust path.

### The tile field never enters the IFC

The IFC phase gives `IfcCovering` a real, correctly classified, correctly
related body - `covering_shell()`, a thin offset shell over the roof's own
sloping faces - and stops there. The presentation phase finds that same
object afterward, by its stable key, and swaps its mesh for the cropped tile
field with its ridge and hip caps merged in (`obj.data = mesh`). Same element,
same `IfcCovering`, new Blender mesh - not a second, BIM-less object placed
beside it.

That swap is Blender-only. Nothing calls back into `ifcopenshell` to update
the covering's `IfcShapeRepresentation`, so saving the `.ifc` after the
presentation phase still writes the coarse shell, never the tile-level
mesh - tile detail exists only in the live Blender scene, a saved `.blend`,
and a GLB export. This is deliberate, not a gap to close: an IFC file is
for BIM queries - area, classification, relationships - and nobody queries
one for the position of tile #4,382. Sixteen thousand tile vertices in the
IFC would be pure bloat for a question the file was never meant to answer.

## Render-only wall contact relief

After reload, `roof_recess.py` detects same-facing coplanar roof/wall faces
with overlapping area. The presentation phase applies a non-destructive
1 mm inward plane offset to the competing roof-body surfaces. Adjacent planes
constrain the vertex motion; this is not global scaling or a changed roof
thickness declaration. Gable side faces retreat horizontally where necessary.
The original mesh coordinates, `BBIM_Roof`, IFC body, tile field and caps are
unchanged. The saved Blender scene and evaluated GLB carry the modifier's
result. See [quality-assurance.md](quality-assurance.md) for verification and
the distinction between visible conflicts and legitimate hidden contacts.

## Preset values

The tests pin these covering and skylight defaults.

| Quantity | Value |
| --- | --- |
| Tile layout module | 0.3 x 0.4 m |
| Tile mesh | 0.2928 x 0.47 x 0.04 m |
| Tile tilt | 6 degrees |
| Skylight flashing margin | 0.07 m |
| Skylight frame base colour and metallic | (0.095, 0.095, 0.095), metallic 0.8 |
| Glazing | (0.8, 0.8, 0.8), metallic 0.5, alpha 0.5 |

There is **one** glazing recipe, `glass()`, and every pane in the building
uses it - facade window, fixed light and skylight alike. Splitting glazing by
where the element sits is a lighting decision dressed up as a material.

The tile is 0.47 m long on a 0.4 m course, so it laps 0.07 m; the 6 degree
tilt is what makes that lap sit, since `0.4 * tan(6 deg)` is one tile
thickness of rise per course. Tile and module were designed together - if one
is changed and the relationship breaks, the module is probably wrong.

Every shell in a window is held `CLEARANCE` off its neighbour. Coincident
faces z-fight, and a test asserts no two shells share a coordinate plane.
