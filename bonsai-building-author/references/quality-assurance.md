# Building quality assurance

QA measures and reports; it does not override the IFC-like authoring API or
automatically reposition architectural elements. Keep project-specific expected
measurements in the building script or its QA companion, not on `roof()` or a
second authoring interface. Record the source, datum, feature, expected value,
tolerance, and whether the measurement is published, scaled, or assumed.

## After IFC reload

- Run formal `ifcopenshell.validate` schema validation; successful geometry
  generation alone is not proof of valid IFC relationships.
- Check hierarchy, types, material associations, stable IDs, voids/fillings,
  and geometry generation. An opening occurrence must have exactly one host.
- Check structural levels and opening positions against the project. The
  agent declares slab/floor buildup so the final finish lands on the required
  level. It coordinates sill and opening-bottom placement without changing
  the intended window level. Do not hide misplaced construction with shrinkage.
- Check room and main floor-covering footprints against the regenerated native wall
  geometry, especially re-entrant corners, unequal-thickness joins and T
  junctions. Main room floor coverings must equal their room regions, without positive-area
  wall overlap or duplicate room regions. Check each floor datum separately;
  below-floor plinths and elevated walls are not room boundaries. Keep opening
  patches separate, adjacent to and contained in their one declared owner.
- Check slab boundaries against their declared construction role and intended
  wall-face relationship; the room-covering rule above does not set structural
  slab extents. Inspect sections through the perimeter wall, plinth, floor
  buildup, and terrain, including recesses and corners. Flag unintended solid
  overlap, exposed floor layers, and gaps in support beneath threshold finishes.
  Verify which element provides the intended exterior finish; do not conceal
  a construction conflict with a rendering offset.
- Inspect exposed strips beneath every floor-level door/window, including
  separate plinth/base walls. A slab top and an uncut plinth top can compete
  even when the terrace deck is correctly lower. Identify which element owns
  the finished threshold and coordinate the actual buildup and opening cuts;
  do not move the whole window or apply a generic rendering offset there.
- Glass-to-frame fit is generator-owned. Agents declare supported type
  sections, not individual pane vertices or ad-hoc internal clearances.

## Explicit corner-window acceptance

For every corner assembly, inspect horizontal sections through its frame,
including mid-height and near the head and sill. The two legs must meet at the
intended joint or declared corner post, without unintended gaps or overlap.
Check both wall cuts and the two sill mitres. Inspect close-up exterior views
from both sides against the reference, including pipes and other obstructions.

Individual window sizes, nonempty meshes, correct wall relationships and a
wide house screenshot do not establish that the assembly joins correctly.
The agent resolves explicit `along` values from the selected frame sections
and corrects them when QA fails; no automatic corner layout is introduced.

## Floor-level joinery acceptance

- Confirm the source calls for a conventional balcony frame or HST track.
  A sliding panel property alone does not prove lift-slide geometry.
- Inspect close-up bottom and plan sections: a balcony frame keeps its lower
  frame; HST has two depth tracks, the correct sliding side, overlapping
  meeting stiles and no full-depth centre mullion. Verify the head as well.
- Check track/base, jamb/base, glass/frame and interlock interfaces for
  competing exposed coplanar faces. Intended glass bite and hidden contacts
  are not z-fighting. Internal fit belongs in generator tests, not per-project
  vertex adjustments.
- Check IFC round-trip geometry, material roles, type metadata and one
  filling per opening. HST has `ParameterTakesPrecedence=False` and complete
  `BA_WindowAssembly` data, without a misleading stock `BBIM_Window` pset.
- Measure the physical bottom, rail top and overall height against declared
  values. Do not infer a flush installation from a low threshold recipe or
  fill across its track. Repeat the important shape checks in the GLB.

## After presentation and export

- Check roof-edge classifications against the local folds, especially both
  sides of intersecting roof wings. Caps belong only on ridges and hips;
  valleys and coplanar mesh seams must have none. Inspect the generated
  covering, not just the classifier's labels or the total cap count.
- Measure evaluated Blender geometry for finished features that do not exist
  in IFC, such as ridge-cap tops. Identify the feature precisely: structural
  roof plane, finished cap, fascia, gutter, and tile edge are different datums.
  Scope the measurement to those elements, excluding chimneys and scenery.
- Report expected, actual, delta and tolerance. Exact contracts can fail;
  uncertain raster-derived dimensions normally produce explicit warnings.
  Repeat important measurements in the GLB, accounting for its Y-up axes.
- The roof-body recess is a bounded, render-only plane adjustment, initially
  1 mm, at same-facing coplanar wall/roof surfaces with positive overlap area.
  It is not object scaling. The modifier leaves original mesh coordinates and
  IFC representations untouched and exports only its evaluated appearance.
  Regenerate it from source geometry, never accumulate offsets across reruns.
- Check separate verge flashings as well as the roof body. Their competing
  exposed faces move 1 mm outward in presentation only, while back faces and
  elevations stay fixed. Confirm both rakes meet at the apex and no modifier
  accumulates on reruns. Do not apply flashing clearance to opening thresholds.
- Check the separation and inspect for exposed cracks, changed silhouette or
  light leaks. Hidden back-to-front interfaces and designed tile laps are not
  z-fighting failures. Distinguish shadow acne and transparency sorting from
  competing surfaces; isolate lighting or materials when diagnosing them.
- Facade patterns have no batten or displaced geometry. Material recipes use
  physical scale/orientation, deterministic seeds, opaque patterned surfaces,
  real UVs and tangent-space normal maps for GLB. Preserve a usable flat IFC
  material/style fallback; richer Blender shaders must not replace IFC bodies.
- Inspect the material on an actual assigned building element with material
  lighting. Workbench material colours alone do not validate a procedural
  finish. Keep a responsive textured viewport as an additional inspection view.
- Verify GLB geometry, IDs, embedded textures, UVs/tangents, scale, materials,
  renderer errors and actual target rendering. Preserve editable native
  materials when temporarily assigning baked export derivatives.
