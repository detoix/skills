# Function Packs

Extend the building language with ordinary Python modules and functions.
Explicit imports are the discovery mechanism.

## Function shape

Take the `Building` as the first argument, use stable semantic IDs, and compose
core declarations or presentation operations. Runtime edits happen only when
the compiled script is sent through Bonsai MCP execution.

Name each function as the entity noun it declares, matching its `Ifc*` class
(`wall`, `chimney`), not an imperative verb (`add_wall`, `add_chimney`) — IFC
itself has no "add wall," only "wall."

```python
def chimney(model, key, *, storey, position, size, height, material):
    return extrusion(
        model,
        key,
        ifc_class="IfcChimney",
        storey=storey,
        position=(*position, 0.0),
        size=size,
        height=height,
        material=material,
    )
```

This shape is illustrative. The shipped packs are `materials` (`stucco`,
`glass`, `roof_tile`, coating and frame helpers), `openings`
(`corner_window`, `sliding_window`, and named opening types), `fences`
(`fence`, matching driveway/pedestrian gates, and their connection solver),
`tiles`, and `roof_windows`. Add an entity function when a real building needs
it, not to fill out the example.

Name arguments after the IFC attributes they set, and validate enumerations
against the schema's own values (`values.WALL_TYPES`, `values.DIRECTION_SENSE`)
rather than a friendlier set of your own. A pack that renames IFC's concepts
makes every reader translate twice.

A pack that builds geometry returns the contract in `procedures.py` -
`(verts, faces, uvs, slots)` - and writes each mesh out in code rather than
loading a model file. Keep one procedure per type: two tile types share no
shape code, because a shared builder stops being readable the moment the
shapes diverge. `slots` names a material role per face, so a mesh with more
than one material can say which face is which.

Measure the numbers a procedure hardcodes from a real source, and say in the
docstring where they came from. Invented dimensions look plausible and stay
wrong.

Prefer composing existing language functions such as `wall`, `extrusion`, and
`material`. Keep the fixed compiler primitives small.

## Pack rules

- Keep declaration side effects local to the `Building` until it is compiled.
- Separate IFC-semantic operations from Blender-only presentation operations.
- Own only the semantic IDs created by the function.
- Target presentation work through stable semantic IDs, not transient Blender
  object names or topology indices.
- Return explicit IDs or diagnostics when useful.
- Keep output deterministic where inputs permit it.
- Cover declaration, validation, and compilation in
  `scripts/tests/test_building_author.py`; run it with
  `python -m unittest discover -s tests` from `scripts/`. It needs no Blender.
- Test IFC-producing functions against IFC relationships and geometry.
- Test presentation functions in Blender and the final Three.js GLB.

Keep a one-off procedure in the project script. Move it into a function pack
only after reuse proves the abstraction.
