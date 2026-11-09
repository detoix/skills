# Spaces

Declare a space by a point inside it, not by its shape. A room's true
boundary depends on how its walls resolve their corners, which only exists
once IfcOpenShell has regenerated them - the same reason a wall's own
corners are derived rather than declared (see
[references/walls.md](walls.md)). A space is resolved the same way: named by
a point, enclosed by whatever walls and virtual elements surround that
point.

## Declaration

```python
wall(model, "partition", storey="ground", wall_type="int.120",
     axis=((4.5, 0.0), (4.5, 4.0)), height=3.0)
# The partition stops short of the north wall on purpose - this closes the
# gap with no physical construction, so the two sides of the plan stay two
# spaces either side of a threshold that is only ever open.
virtual_element(model, "partition.divider", storey="ground",
                 axis=((4.5, 4.0), (4.5, 6.0)))

space(model, "bedroom",     storey="ground", at=(2.0, 2.0), height=2.5)
space(model, "living-room", storey="ground", at=(6.0, 3.0), height=2.5)

covering(model, "bedroom.flooring", space="bedroom",
         material="timber.flooring", thickness=0.015)
covering(model, "living-room.flooring", space="living-room",
         material="tile.ceramic", thickness=0.012)
```

## What maps to what in IFC

| declaration | IFC |
| --- | --- |
| `virtual_element(...)` | `IfcVirtualElement` |
| `space(...)` | `IfcSpace` |
| `covering(...)` | `IfcCovering` with `PredefinedType = FLOORING` |
| `predefined_type=` | `IfcSpaceTypeEnum` |
| `at=` | resolved to the enclosed region's boundary, then the extruded `Body` profile |

## A boundary with nothing physical is still its own entity

IFC's answer to a corridor that merely opens into a room, or any boundary
that separates two spaces without anything built there, is not a wall with
no material - it is `IfcVirtualElement`, a distinct entity carrying no
layers, no body, and no quantities. `virtual_element()` declares one along a
reference line exactly the way a wall declares its axis, so it joins a
wall's axis wherever the two share an endpoint and closes a space loop the
same way a wall would, without the model mistaking it for something built.

IFC's fuller picture also gives each side of that boundary an
`IfcRelSpaceBoundary` with `PhysicalOrVirtualBoundary = VIRTUAL`, both
pointing at the same `IfcVirtualElement`. This skill does not write that
relationship yet - see Traps below.

## Who does what

A space's shape is enclosed, not declared. Compilation (`space_payload` in
`compiler.py`) passes the physical walls' semantic keys and vertical extents,
the virtual elements' thin numerical boundaries, and the declared room points.
Physical wall rectangles are not room boundaries: the regenerated mitres,
butts and notches can occupy different areas at a join.

After all native wall regeneration and roof/slab clipping, the IFC runtime
(`space_geometry.py`) reads each wall's native world-coordinate tessellation.
It disables opening subtraction, so door and window voids do not merge rooms.
The current wall primitive is a vertical extrusion, optionally clipped at its
top; unioning its projected triangles gives its actual joined plan footprint.
No Blender object bounds, duplicate junction solver, or rectangle fallback is
used. Missing or invalid native geometry is a hard error.

Enclosures are resolved per storey **and floor datum**:

1. Only walls crossing the room's floor datum are considered. A plinth ending
   at that level, or a wall starting above it, does not bound that room. The
   native body's vertical extent is checked as well as its declaration.
2. The native wall footprints and virtual boundaries are unioned. A numerical
   0.1 micrometre precision grid welds coincident tessellation edges; it does
   not offset architectural surfaces.
3. A box padded 5 m past the obstacles' own bounds stands in for "outdoors".
4. The union is subtracted from that box. Regions touching its outer boundary
   are outdoors and are dropped; area ranking is not used.
5. Each declared space's `at` point is matched to the remaining region that
   contains it. A point that lands in no region - an open plan, a wall
   that never closes the loop - is a hard error naming the space, not a
   silently oversized room. Two spaces selecting the same region at the same
   datum are also rejected rather than receiving overlapping floors.

The resulting polygon is extruded through
`ifcopenshell.api.geometry.add_slab_representation` - the same primitive
[slabs](slabs.md) use, reused because a space's body is the same shape as a
slab's: a closed polygon extruded by a depth. Reusing the call is reusing
that primitive, not a claim that a space is a kind of slab.

## A room finish has the room footprint plus separate threshold patches

A structural [`slab()`](slabs.md) may span several rooms. It is not divided
to make those rooms, and it is not divided merely because their finishes
differ. A room is the `IfcSpace` above; a flooring finish is a separate
`IfcCovering` with `PredefinedType = FLOORING` associated with that space.

That main flooring footprint is derived, never declared. It must equal the
resolved plan footprint of its `space` exactly. There is no independent
`boundary`, no offset, and no override: moving the walls changes the space,
and the covering follows the same result. A material recipe changes how that
covering renders; it never decides where the covering ends.

The plan area under a floor-level opening is deliberately not part of either
room region: the obstacle union removes the enclosing wall's whole footprint
before opening voids are considered. Leave both `IfcSpace` bodies and both
main room coverings unchanged. For each such opening, generate one additional
`IfcCovering` with `PredefinedType = FLOORING` over the opening width and the
host wall's exact plan thickness. This threshold covering is a separate IFC
occurrence, not another boundary on the main covering and not another region
on the space.

The opening's `threshold_space` names which adjacent room owns that separate
covering. Spatially contain the threshold covering directly in that
`IfcSpace`, and inherit its main flooring covering's material, type,
thickness, elevation, and material recipe. Give the patch an opening-derived
stable ID such as `<opening>.threshold-flooring`; changing ownership must not
replace the physical occurrence. Never split the patch at the wall centreline,
aggregate it into the main covering, add it to both spaces, or leave it with no
spatial container. See [openings.md](openings.md).

`covering(...)` deliberately accepts only `space`, `material`, and
`thickness` as geometric inputs. Compilation places its top at the space base
datum and reuses the resolved room polygon. It also derives any selected
threshold rectangle from the opening and host wall, then verifies at IFC
execution time that the selected room actually touches that rectangle. This
adjacency measurement uses the same numerical plan tolerance as native wall
resolution and requires shared edge length, not corner-only contact. It does
not offset either the room or the threshold geometry.

## Traps

- A declared point that lands outside every wall loop is a hard error, not a
  space the size of the building. If a space's storey has no walls or
  virtual elements at all, that is caught even earlier, before the union
  runs.
- A resolved region containing an interior ring, such as an isolated wall
  island within a room, is rejected by the current space extrusion. It is
  never silently filled over. Supporting such a room requires an IFC profile
  with voids; the current single-outline emitter does not provide one.
- Native triangle projection is valid for the supported vertical wall
  primitive and its top clipping. A future sloped or variable-section wall
  primitive would need native sections at the room's floor datum instead.
- Two spaces cannot currently share one physical wall on one side and a
  virtual element on the other and still resolve as adjacent unless that
  wall or virtual element actually closes the loop; a one-millimetre gap in
  the declared axes is enough to merge two intended rooms into one region
  (or open the loop to the exterior entirely).
- `IfcRelSpaceBoundary` is not written. Neither Bonsai's own space tools
  generate it, so this tracks that gap rather than quietly working around
  it; add it when a real use needs the boundary relationship, not before.
- `Pset_SpaceCommon` and `Qto_SpaceBaseQuantities` are not written either.
  `predefined_type` and the extruded body are the only data a script-authored
  space carries beyond its name; add the property and quantity sets the same
  way `EPset_Parametric` is added for a slab, once something reads them.
- A space's `height` is a plain extrusion depth, not a clear-height
  calculation against a ceiling or a sloped roof underside. A space under a
  sloping roof still extrudes as a flat prism; nothing clips it to the
  slope.
- A space may have at most one main flooring covering. That invariant keeps
  threshold inheritance unambiguous; model a finish change as another space,
  not as two competing main coverings on one room.
- A threshold owner must be on the opening's storey, carry one main flooring
  covering, and meet the opening at its own floor datum. The compiled IFC also
  rejects a named owner whose resolved room region is not adjacent.
