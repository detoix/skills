# Terraces and balconies

Neither has its own IFC entity, and this skill does not invent one. Both are
a composition of primitives this skill already has - `slab()`, the source's
actual opening (`door()` or `sliding_window()`), and
[`railing()`](railings.md) - the same way a room is `wall()` plus
`virtual_element()` plus `space()` rather than a dedicated `IfcRoom`. See
[references/railings.md](railings.md) for what real exported IFC and the
buildingSMART community actually do here, and why.

What tells a terrace from a balcony is not an IFC concept, it is which two
primitives compose it:

| | the deck | how it meets the building |
| --- | --- | --- |
| **terrace** | `slab()` at (or close to) grade | stands on its own, or on a `BASESLAB` |
| **balcony** | `slab()` cantilevered off an upper storey | its `boundary` runs flush against the host wall, unconnected beyond that - see Traps |

## A ground-level wooden terrace

```python
slab_type(model, "terrace.wood", name="Wooden Terrace Deck", predefined_type="FLOOR", layers=[
    layer("concrete", 0.100, priority=90, category="LoadBearing", name="Concrete Base"),
    layer("timber.decking", 0.030, priority=10, category="Finish", name="Timber Decking"),
])
slab(model, "terrace", storey="ground", slab_type="terrace.wood",
     boundary=[(1.5, 6.0), (6.5, 6.0), (6.5, 9.5), (1.5, 9.5)],
     base_offset=-0.130, name="Terrace")

from building_author.openings import sliding_window

sliding_window(model, "terrace-slider", wall="north-wall",
               window_type="wt.slider", along=3.0, sill_height=0.0,
               overall_width=3.00, overall_height=2.30,
               is_external=True, name="Terrace Sliding Window")
```

A ground-level deck like this is left unguarded here - low enough off the
garden that this example gives it no `railing()` at all. Guarding it is the
same declaration the balcony below uses, just on the `"guardrail.timber"`
profile instead: nothing about `railing()` is deck-specific, so add one the
moment the deck's own height off grade calls for it.

`base_offset` is the negative of the type's total thickness, the same rule
[`slabs.md`](slabs.md) gives for a floor a wall should stand on flush - here
it is the exterior ground that should meet the deck flush instead, at the
opening threshold.

The example assumes `wt.slider` has already declared
`SLIDINGHORIZONTAL` window panels as shown in [openings.md](openings.md). If
the source instead identifies a hinged garden door, use `door()`; floor-level
glazing is not enough reason to change an `IfcWindow` into an `IfcDoor`.

## An elevated, cantilevered balcony

```python
slab_type(model, "balcony.floor", name="Balcony Slab 180", predefined_type="FLOOR", layers=[
    layer("concrete", 0.150, priority=90, category="LoadBearing", name="Structural Slab"),
    layer("tile.outdoor", 0.030, priority=10, category="Finish", name="Outdoor Tile"),
])
slab(model, "balcony", storey="attic", slab_type="balcony.floor",
     boundary=[(8.0, 1.5), (9.2, 1.5), (9.2, 4.5), (8.0, 4.5)],
     base_offset=-0.180, name="Balcony")

door(model, "balcony-door", wall="east-gable", door_type="dt.entrance",
     along=3.0, overall_width=1.00, overall_height=2.10,
     is_external=True, name="Balcony Door")

railing(model, "balcony.rail.outer", storey="attic",
        path=((9.2, 1.5), (9.2, 4.5)), height=1.0,
        profile="guardrail.steel",
        post_material="frame.metal", rail_material="frame.metal",
        infill_material="frame.metal")
```

`predefined_type="FLOOR"` on both slab types, never `BASESLAB`, is
deliberate: `BASESLAB` is IFC's word for a slab bearing on the ground, and a
cantilevered balcony does not. A ground terrace could take either - `FLOOR`
is used here too, because real exported files do the same (see
[railings.md](railings.md)) and because it keeps both examples' slab types
identical in kind, differing only in their layers and where they sit.

## Guarding an open perimeter is more than one `railing()`

Both examples above guard only the one edge shown. A balcony open on three
sides needs three declarations - one per straight run, exactly as three
walls make an open-sided room:

```python
railing(model, "balcony.rail.outer", storey="attic",
        path=((9.2, 1.5), (9.2, 4.5)), height=1.0, ...)
railing(model, "balcony.rail.south", storey="attic",
        path=((8.0, 1.5), (9.2, 1.5)), height=1.0, ...)
railing(model, "balcony.rail.north", storey="attic",
        path=((9.2, 4.5), (8.0, 4.5)), height=1.0, ...)
```

`railing()` never mitres one run's end post against another's, the same trap
[railings.md](railings.md) documents; three runs meeting at a shared corner
still declare three independent end posts there rather than one.

## Traps

- A cantilevered balcony's slab is not structurally connected to its host
  wall by anything this skill writes. `extend_to_structure()` is the
  opposite relationship - a wall reaching up to a structure above it, such as
  a roof or floor slab - not a slab reaching sideways into a wall; declaring
  a balcony's `boundary` flush against the wall's face is what makes the two
  meet, the same way `slabs.md` notes a slab has no corners to resolve against a
  neighbour and has to be declared already flush.
- Nothing checks that a balcony or terrace slab's `boundary` actually reaches
  its host wall, or that a `door()` or `sliding_window()` declared onto it
  lands within the deck's own footprint. Both are the script's to get right,
  the same way a window's position on its wall is.
- `space(predefined_type="EXTERNAL")` is not used above. A space is resolved
  by enclosing every `wall()` and `virtual_element()` on its storey into
  regions (see [spaces.md](spaces.md)); an open deck guarded only by
  `railing()` encloses nothing; `space_payload` never reads a railing as an
  obstacle. Giving a terrace or balcony its own queryable `IfcSpace` needs
  `virtual_element()` runs closing its open sides first, the same way an
  interior room needs walls.
