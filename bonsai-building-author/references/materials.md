# Procedural materials

This library keeps exactly one renderer-neutral authoring recipe per material
under `references/material-recipes/`. That recipe is the contract an agent
translates on demand. The library does not contain a maintained Blender port,
Three.js port, baked map, or render.

Each recipe carries a one-line credit to the third-party graph it was derived
from (or states it is a project-authored original).

`scripts/building_author/materials.py` declares only construction-material
identity, a flat IFC/presentation fallback, and the canonical recipe path. The
compiled Blender fallback stores that path as
`building_author_material_recipe` so the executing agent can find the work
that remains.

A recipe never creates, divides, expands, or clips the element carrying it.
In particular, a flooring recipe does not split a slab into rooms. A room
finish belongs on an `IfcCovering(FLOORING)` whose footprint is the final
resolved `IfcSpace` footprint, with no separately declared boundary; see
[spaces.md](spaces.md). Recipe translation begins only after that IFC element
and its material association already exist. A separate threshold covering
under a floor-level opening inherits the chosen room covering's material and
therefore receives the same recipe translation without a second recipe.

## On-demand authoring contract

For every distinct `material_recipe` emitted by a building script:

1. Read the referenced `.material.md` file and its shared
   `references/material-recipes/primitives.md` vocabulary completely. The
   one-line credit is attribution only, never the runtime interface.
2. Translate that one recipe into the requested target. Do not add the
   generated renderer implementation back to this skill.
3. Apply it to every material carrying the same semantic recipe pointer. Use
   the material key/custom property, never a guessed display or object name.
4. Preserve the recipe's physical mapping, colour-space rules, output ranges,
   adaptations, source attribution, and deterministic seeds.
5. Render it on at least one assigned building element. Compare it with the
   published preview and the recipe's visual acceptance checks; correct scale,
   seams, relief, and roughness before declaring the model complete.
6. Record the recipe path and any target-specific approximation in the
   generated project.

### Blender

After IFC reload, replace each tagged scalar fallback with ordinary local
Blender nodes and local node groups. The saved `.blend` must remain standalone,
and the finished material must appear as a normal editable material in the
Shading workspace after the generation script and this repository are gone.
Do not leave linked libraries, source textures, add-on-only nodes, or external
files.

### Three.js

Translate the same recipe during the Three.js task into project-local
TSL/GLSL or procedural texture-generation code. Preserve the same coordinates,
scale, seeds, PBR values, and stated adaptations. That generated code belongs
to the target project, not this library.

### IFC and GLB

IFC keeps the declared construction-material identity and flat colour/style;
it is not the visual master.

GLB cannot carry the procedural authoring graph. Bake the generated target
material at an explicitly chosen resolution, connect the maps to one
glTF-compatible Principled material, and embed them in the GLB. Base Color and
Emission are colour data. Roughness, Metallic, Normal, AO, height, masks, and
noise are non-colour data. A normal-mapped mesh needs real UVs, tangent-space
normals, and triangulated export geometry. Generated maps belong in ignored
build output, never in this source library.

## Selected recipes and minimal-example assignments

### Original honey vertical timber facade

- Recipe: `references/material-recipes/honey-timber-facade.material.md`
- Provenance: original mathematical material; no third-party graph or bitmap.
- Assignment: continuous facade `IfcCovering(CLADDING)` regions using the
  `timber.honey` construction material.
- QA elements: rear timber facade and its east return, under grazing light.

The apparent 72 mm timber rhythm, warm color, directional grain and shallow
normal relief are entirely shading. This recipe must not create individual
battens or use displacement. Native editable Blender nodes and generated
NumPy texture bakes implement the same declared formula. Generated material
code and images stay in project output; the library keeps this text recipe.

### MM217 — Stylized plaster

- Recipe: `references/material-recipes/mm217-stylized-plaster.material.md`
- After [Stylized plaster by Tarox](https://www.materialmaker.org/material?id=217) (CC0)
- Assignment: `stucco.white`, the `External Render` outer layer of external
  wall type `ext.470`
- QA element: an exterior wall under grazing daylight

The target is warm ivory plaster with restrained trowel breakup, shallow pits,
and sparse darker flecks, not concrete craters or a visible repeating tile.

### MM204 — Stylized Roof Tiles

- Recipe: `references/material-recipes/mm204-roof-tile-surface.material.md`
- After [Stylized Roof Tiles by ninao](https://www.materialmaker.org/material?id=204) (CC0)
- Assignment: `tile.terracotta`, used by the main roof's physical
  `tile.clay` covering
- QA element: the generated sloped roof tiles

The skill already models individual tiles, so the canonical adaptation uses
only the source graph's clay colour, variation, and roughness. Physical tile
geometry supplies all relief. The recipe deliberately omits the graph's macro
tile silhouettes and overlap relief, which would draw a second tile pattern
over the real geometry.

### MM161 — Wood Planks Floor from Deus Ex Mankind Divided

- Recipe: `references/material-recipes/mm161-herringbone-wood.material.md`
- After [Wood Planks Floor by Kyrylo](https://www.materialmaker.org/material?id=161) (CC-BY, version not specified by the publisher)
- Assignment: `timber.decking` on the two-tier terrace slab
- QA element: the terrace under grazing light

The target is charcoal herringbone timber with directional grain, readable
plank joints, and narrow satin highlights. The canonical adaptation forces
metallic to zero.

Carry this attribution with every generated `.blend`, Three.js project, GLB
package, or redistributed material:

> “Wood Planks Floor from Deus Ex Mankind Divided” by Kyrylo, sourced from
> Material Maker material 161, licensed CC-BY (version not specified by the
> publisher); translated from the canonical recipe for the target project.

## Change control

Do not commit downloaded previews, renders, baked maps, `.blend` files, GLBs,
or generated target implementations as material-library source. When a
canonical recipe changes, inspect new target renders and document the reason.
