---
name: bonsai-building-author
description: Author reliable IFC4 buildings as concise, line-oriented Python building scripts, execute them through Blender and Bonsai with Bonsai MCP, and produce validated IFC, polished Blender scenes, and presentation-grade Three.js GLBs. Use to create, reconstruct, extend, inspect, validate, or present buildings from briefs, plans, images, PDFs, existing IFC/Blender projects, or reusable building function packs.
---

# Bonsai Building Author

Make a full building script the primary authoring artifact. Use Bonsai MCP as
the execution layer; do not recreate Blender, Bonsai, IfcOpenShell, or MCP
functionality.

## Author the building as code

- Write flat, ordered function calls with stable semantic IDs and explicit
  references. Avoid deeply nested Python structures and raw IFC boilerplate.
- Compile the finished script to `ifc_source()` and `blender_source()`, then
  run those through the Bonsai MCP execution tools already available. The
  script declares and compiles; it never opens its own MCP connection.
- Name declarations and their arguments the way IFC names the things they
  produce. The language may encapsulate, and should stay shorter than raw IFC,
  but where the two would disagree the IFC wording wins - including its
  enumeration values, spelled exactly as the schema spells them.
- Import reusable components, materials, rules, and finishing procedures as
  ordinary Python functions.
- Keep project-specific dimensions, layout, and design intent in the building
  script.
- Treat a script-created IFC and `.blend` as full owned rebuilds; preserve
  stable semantic IDs across reruns and omit undeclared scene residue.

Use [scripts/example_build.py](scripts/example_build.py) as the minimal
executable example.

Declare walls as a reference line plus a wall type carrying material layers,
and let the layer priorities resolve the corners; read
[references/walls.md](references/walls.md) before authoring or extending one.

Declare roofs from their base boundary with per-edge gables, overhangs, tile
coverings, and roof windows; read [references/roofs.md](references/roofs.md)
before authoring or extending one.

Declare a gutter against a roof's declared boundary edge and let its corners
mitre themselves; read [references/gutters.md](references/gutters.md) before
authoring or extending one, or a downspout.

Declare which trim a roof wears, never which edges wear it - a verge is
wherever the roof surface stops on a rake, which a gable has already said;
read [references/trims.md](references/trims.md) before authoring or extending
a verge trim or a flashing.

Let a covering cap its own ridges and hips: a tile profile names the cap it is
catalogued with, and a cap goes wherever two roof faces fold away from each
other. Caps are presentation only and ride in the covering's own mesh; read
[references/caps.md](references/caps.md) before authoring or extending one.

Declare windows and doors against their host wall's reference line, with the
section on the type and only the overall size on the occurrence; read
[references/openings.md](references/openings.md) before authoring or extending
one. For floor-level glazing, distinguish a conventional balcony frame from
an HST lift-slide track; select the supported type recipe rather than adding
a doorstep strip or editing frame/glass internals in the project script.

Declare slabs from their plan boundary plus a slab type carrying material
layers, the way a roof is declared; read
[references/slabs.md](references/slabs.md) before authoring or extending one.

Declare spaces by a point inside them, not by their shape, and declare a
non-physical boundary between two spaces as a virtual element rather than a
wall with no material; read [references/spaces.md](references/spaces.md)
before authoring or extending either.

Keep a room's floor finish separate from the structural slab. Its plan
footprint is always the resolved `IfcSpace` footprint and has no
author-declared boundary or override. Do not extend either the space or that
main covering under an opening. Generate the floor area through each
floor-level opening as a separate `IfcCovering(FLOORING)`, contained in the
one adjacent space named by the opening's `threshold_space`; it inherits that
space's flooring material, type, thickness, elevation, and material recipe.
Never split the patch, merge it into either room covering, duplicate it, or
leave it unowned. Read [references/spaces.md](references/spaces.md) and
[references/openings.md](references/openings.md) for that boundary contract.

Declare a railing from its straight reference line, posts plus a top rail,
the way a wall is declared from its axis; read
[references/railings.md](references/railings.md) before authoring or
extending one. Neither a terrace nor a balcony has its own IFC entity - both
compose from `slab()`, the source's actual opening (`door()` or
`sliding_window()`), and `railing()`; read
[references/terraces.md](references/terraces.md) before authoring either.

Declare a boundary fence and matching driveway or pedestrian gate from their
straight reference lines and a measured welded-mesh or horizontal-slat family; read
[references/fences.md](references/fences.md) before authoring or extending
one.

Declare lawn areas with `turf(site=..., boundary=..., elevation=...)`; read
[references/turf.md](references/turf.md) before authoring or exporting turf.
The authored surface defines where a viewer may grow grass.

Compose a garden from `turf()`, grade-level `slab()` paving and `fence()`,
authored in level order; individual planting has no declaration yet. Read
[references/gardens.md](references/gardens.md) before laying out a garden,
its levels or its beds.

## Execute in phases

1. Establish the architectural and presentation outcome.
2. Author or revise the complete building script.
3. Validate the complete script and derive its runtime requirements.
4. Read [references/runtime-preflight.md](references/runtime-preflight.md) and
   run the required read-only probes.
5. Execute IFC work in one logical batch through Bonsai MCP IFC execution.
6. Save the IFC and reload it once through Bonsai MCP.
7. Follow [references/quality-assurance.md](references/quality-assurance.md):
   validate the IFC schema, hierarchy, relationships, geometry, stable IDs,
   and every corner-window assembly after reload.
8. For every declared material recipe, read its one canonical renderer-neutral
   recipe and create the requested target-native material on demand; then
   apply Blender modifiers, lighting, scene dressing, and custom finishing
   operations through Bonsai MCP Blender execution.
9. Save the `.blend`, inspect every recipe on an assigned building element,
   measure finished reference features, check exposed surface conflicts, and
   test any baked GLB in its Three.js target. Report approximation warnings.

## Preserve the operating boundary

- Author IFC data through Bonsai MCP's IFC execution facilities.
- Author presentation-only Blender data through its Blender execution
  facilities.
- Treat IFC as authoritative for architectural elements, spatial structure,
  openings, classifications, properties, quantities, and construction
  materials.
- Keep render-only details, complex shaders, lighting, cameras, and scene
  dressing separate from generated IFC meshes and linked by stable semantic
  identifiers.
- Keep exactly one canonical, text-only, renderer-neutral recipe for each
  procedural material. Follow
  [references/materials.md](references/materials.md), translate the recipe
  into ordinary native Blender or Three.js material code during the current
  authoring task, and do not maintain renderer-specific implementations inside
  this skill. A recipe's one-line credit is attribution only, not another
  execution contract. A generated `.blend` keeps its local editable nodes;
  generated Three.js code belongs to that target project.
- Treat the GLB material as a generated derivative, not as the authoring graph.
  Bake procedural outputs to generated textures at a declared resolution, then
  drive Material Output with one glTF-compatible Principled BSDF (or Emission)
  using only Base Color, Metallic, Roughness, Normal, Emission, and Alpha.
  Embed those generated maps in the GLB or keep them in ignored build output;
  do not commit them as library source assets.
- Any mesh carrying a normal map needs a real UV map and triangulated faces,
  or Blender cannot export its tangents; keep the Normal Map node in tangent
  space and set normal/roughness/metallic images to Non-Color, or the GLB
  silently loses or corrupts that data.
- Let Bonsai and IfcOpenShell build any element they already generate
  parametrically, and write the pset that keeps it editable by the tool that
  owns it. An element the skill could only emit as a fixed mesh arrives as
  dead geometry; supply the declaration and stay out of the geometry.
- Apply presentation operations after IFC reload so they are deterministic and
  repeatable.
- Facade board/batten patterns are materials on existing wall or continuous
  covering surfaces, never individual battens, relief/displacement geometry,
  or additional coplanar texture planes. A covering may retain its real overall
  construction thickness. Generate and bake the pattern with metric mapping.
- At competing wall/roof surfaces, render the roof body slightly recessed
  using the non-applied presentation modifier. Render a competing verge
  flashing's exposed face slightly outward instead, keeping its back seated
  and its apex joint closed. Keep IFC parameters and geometry authoritative.
  Do not use these exceptions to shift slabs, flooring, sills, openings, or
  component internals; follow the QA responsibility split.
- Build repeated presentation geometry with a procedure per type rather than a
  shipped model file, and merge the result into one mesh per element. Every
  procedure returns `(verts, faces, uvs, slots)`, where `slots` names a
  material role per face; a mesh with more than one material must say which
  face is which.
- Crop presentation geometry with a boolean against a solid, not by clipping
  against each edge in turn. Edge clipping is only valid on convex regions,
  and it is the same boolean that cuts openings.
- Treat a presentation-grade Three.js GLB as a first-class deliverable.
- Reuse MCP queries, save/reload operations, screenshots, geometry operations,
  and exports directly; do not wrap them without a demonstrated repeated need.

## Extend with ordinary functions

Read [references/function-packs.md](references/function-packs.md) before adding
a reusable function.

- Use Python modules as function packs and explicit imports as discovery.
- Compose existing primitives before adding infrastructure.
- Keep one-off finishing functions in the project; promote them to a pack when
  reuse is demonstrated.
- Infer preflight requirements from the operations a function emits.
- Keep architectural rules separated into hard errors, configurable warnings,
  and aesthetic advice.
- Record assumptions and unresolved uncertainty.
