# Gardens

A garden has no IFC entity, and this skill does not invent one. It composes
from primitives this skill already has - [`turf()`](turf.md), `slab()`,
[`fence()`](fences.md) and [`railing()`](railings.md) - the same way a terrace
is `slab()` plus an opening plus a railing rather than a dedicated entity.

One primitive is missing: individual planting has no declaration yet. Author
the ground, the circulation and the enclosure with the language; see
[Planting](#planting) for what is not yet expressible and how to keep a
hand-authored garden honest until it is.

| | authored with | carries |
| --- | --- | --- |
| **ground** | `turf()` | lawn coverage and elevation |
| **paving** | `slab()` at grade | paths, courts, dining terraces |
| **enclosure** | `fence()` | boundary, gates, screens |
| **planting** | *no declaration* | beds, plants, ground-cover cutouts |

## Author in level order

Design a garden outward from its levels, not from its planting. Each step
below constrains the next, and reordering them produces a layout that has to
be rebuilt rather than adjusted.

1. **Levels.** Fix finished floor, terrace and lawn elevations, and the risers
   between them, before any boundary is drawn. A 300 mm level difference is a
   step or a wall; it is not a detail to resolve later.
2. **Circulation.** Route the walk from the building's real openings to where
   people actually go. A path that does not start at a `door()` or a
   `sliding_window()` is decoration.
3. **Beds.** Draw the planting beds as boundaries. They are the negative space
   of the lawn, so they are what removes turf.
4. **Planting.** Place plants inside the beds, last, once the beds are fixed.

## Levels and steps

Make each level change explicit. State the elevation of every surface and the
riser between adjacent ones, and keep risers consistent within one flight -
garden steps between roughly 120 mm and 170 mm read as a step; anything
smaller reads as a defect and trips people.

A finish laid over a stepped slab must follow the slab's actual outline, not
its bounding rectangle. Where a `slab()` carries a perimeter step, the finish
deck stops on the upper deck and the tread takes its own course; where the
slab is notched around a projecting bay or gable, the finish is cut to the
notch. A finish that spans a perimeter step cantilevers over a void, hides
the riser it was supposed to reveal, and reads as a floating lip.

The same rule governs open ground the slab does not carry. A notch that runs
past the wall it clears leaves a pocket; fill it with a mineral margin rather
than paving air or leaving a hole.

## Beds and ground-cover cutouts

A bed boundary and the lawn cutout under it are the same shape. Author it
once, as the bed, and derive the cutout. Authoring both invites them to
disagree, and a disagreement shows as grass growing through a bed or a bald
ring around one - neither of which raises an error anywhere.

Keep plant bases on the authored soil surface, and keep walking routes clear
of mature crowns rather than of the crowns a plant has on the day it is
placed.

## Planting

There is no `planting()` declaration. When there is, it belongs in this
language, beside `turf()`, and it should carry:

- **A bed boundary**, in the same polygon vocabulary `turf()` uses, that
  removes ground cover by being a bed rather than by a second authored shape.
- **Plant placements** with botanical identity - species, cultivar, age - and
  a position, rotation about the vertical axis and uniform scale. Age belongs
  to the plant, not to the model: it is what tells a consumer how large to
  grow it.
- **Stable semantic IDs** across rebuilds, as every other declaration keeps.

Its IFC home is `IfcGeographicElement` with `PredefinedType=USERDEFINED` and
an `ObjectType` naming the planting, aggregated under its `IfcSite` - the same
shape `turf()` takes with `IfcSpace(USERDEFINED)`, `ObjectType="Turf"`.
IFC4x3 adds a `VEGETATION` predefined type; IFC4 does not have one, so do not
spell an enumeration the target schema lacks.

**Author botany, not a renderer.** A plant declaration describes a plant in a
garden: what it is, how old it is, where it stands. It must not carry a
downstream library's vocabulary, property names or supported-species list. A
consumer that grows geometry from these placements maps them to its own
vocabulary at export or load time, and this language stays ignorant of which
consumer that is - exactly as `turf()` defines coverage without knowing what
grows blades on it.

Until the declaration exists, place plant markers by hand in the Blender
phase and record their identities in the project's own script. Do not write a
generator that owns the whole garden collection: it will replace what it did
not author, and re-running it becomes something the project has to warn
against rather than something it can rely on.

## GLB contract

`turf()` already exports its coverage; see [turf.md](turf.md) for the
`landscape` custom property and the rules that go with it. Paving and fences
export as ordinary geometry.

Planting exports as empties carrying their identity as object custom
properties, with the placement in the node transform. Apply the full
node/world transform in the consumer, and do not duplicate positions into
extras - Blender's exporter converts transforms from Z up to glTF Y up, and
custom property arrays do not undergo that conversion.

Reject an unknown species, an unsupported version or a duplicate ID loudly at
load. A silently skipped marker is a plant that never appears, in a scene
where nothing looks broken.

## Traps

- **A finish laid to the slab's bounding box.** It spans perimeter steps and
  notches, floating over a void. Cut the finish to the outline the slab
  actually carries.
- **Beds and cutouts authored separately.** They drift, and the drift is
  visible but not detectable.
- **Sloped lawn.** `turf()` supports horizontal regions at one elevation.
  Do not approximate a graded lawn as flat, and do not patch a height field in
  from outside the language without saying so in the project.
- **A garden generator that replaces its collection.** Rebuilding the design
  and exporting it are different operations; keep them separate, or every
  export risks discarding hand edits.
- **Planting placed before levels.** Plants sited against a provisional grade
  move when the grade is fixed, and their beds move with them.
