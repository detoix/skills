# Walls

Declare a wall as a reference line plus a type. The layers, the corners, and
the body follow from that.

## Declaration

```python
wall_type(model, "ext.470", name="External Wall 470", predefined_type="SOLIDWALL", layers=[
    layer("plaster.internal", 0.010, priority=10, category="Inner finish"),
    layer("block.aac",        0.250, priority=90, category="LoadBearing"),
    layer("insulation.eps",   0.200, priority=20, category="Insulation"),
    layer("stucco.white",     0.010, priority=10, category="Outer finish"),
])

wall(model, "south-wall", storey="ground", wall_type="ext.470",
     axis=((0.0, 0.0), (8.0, 0.0)), height=3.0, direction_sense="NEGATIVE")

extend_to_structure(model, "attic-wall.top",
                    relating_element="main-roof",
                    related_element="attic-wall",
                    termination="TOP_SURFACE")
```

A wall never states its thickness: thickness is the sum of its type's layers,
and stating it twice invites the two to disagree.

## What maps to what in IFC

| declaration | IFC |
| --- | --- |
| `wall_type(...)` | `IfcWallType` + `IfcMaterialLayerSet` |
| `predefined_type=` | `IfcWallTypeEnum` |
| `layer(...)` | `IfcMaterialLayer` - `LayerThickness`, `Priority`, `Category` |
| `wall(...)` | `IfcWall` + `IfcRelDefinesByType` |
| `axis=` | the `Axis` representation, in `Plan/Axis/GRAPH_VIEW` |
| `offset_from_reference_line=`, `direction_sense=` | `IfcMaterialLayerSetUsage` |
| a shared axis end | `IfcRelConnectsPathElements`, `ATSTART`/`ATEND` |
| an axis end met mid-span | the same, `ATPATH` |
| `extend_to_structure(...)` | `Pset_WallCommon.ExtendToStructure` + `IfcRelConnectsElements` + resolved boolean body |

`IfcWallStandardCase` is deprecated. IFC4 wants a plain `IfcWall` that carries
a layer set usage and an axis, which is exactly what this produces.

## The reference line

`axis` is the reference line, not the centreline and not a face. The layer set
is then placed against it the way `IfcMaterialLayerSetUsage` defines it:

- `offset_from_reference_line` moves the layer set base off the reference line.
- `direction_sense` says which way the layers stack from that base, in
  declaration order. `POSITIVE` stacks toward +Y, which is the **left** of a
  wall walked from its start to its end.

Left at its default, the offset centres the wall on its reference line - half
a thickness to one side, layers stacking back across it. Naming a value
instead is how a reference line becomes a face, which is usually what a
structural grid wants.

Direction sense decides which side the first layer lands on, so it is a real
decision and not a formality. Walking a footprint anticlockwise puts the
interior on the left, so `NEGATIVE` is what makes a layer set declared
inside-out arrive inside-out. Get it backwards and the model is still valid
IFC - it just has the render on the inside.

## Corners are derived, not declared

Two walls are connected because their reference lines touch. `junctions.py`
derives that from the declared coordinates and emits the connection with IFC's
own types: `ATSTART` or `ATEND` where an axis ends, `ATPATH` where one wall's
end lands along another's length. Walls that merely cross without sharing an
end are not connected, because IFC has no connection type for that and neither
has a building.

There is deliberately no `wall_join()` in the language. A corner that had to
be declared could contradict the geometry that produced it.

`ifcopenshell.api.geometry.connect_wall` infers the same relationships by
intersecting geometry at runtime. Deriving them from the declaration instead is
exact, testable without Blender, and deterministic.

## Priority decides which wall prevails

`priority` is IFC's normalised [0, 100] integer on each layer, and it is what
resolves a corner: the higher-priority layer runs through, the lower one stops
against it. Equal priorities mitre.

Measured on an L of two 300 mm walls, reading the resulting profile of wall A:

| layer priorities | wall A's end |
| --- | --- |
| equal | mitres at 45 degrees, stepping at every layer boundary |
| B's core raised to 99 | stops dead at B's core face; B's core runs through |

This is why `priority` is a required argument rather than a defaulted one. A
layer set without priorities produces corners that merely look plausible.

Per-connection overrides exist in IFC - `RelatingPriorities` and
`RelatedPriorities` on the relationship, overriding the layer priorities at one
joint. The language does not expose them yet; add that when a real corner needs
to disagree with its materials, not before.

## Where a wall meets the ground

`base_offset` moves a wall down from its storey's elevation, and that is how a
building gets a base. A wall run below the datum is an ordinary wall: same
axis, its own type, its own layers.

```python
wall(model, "south-plinth", storey="ground", wall_type="plinth.440",
     axis=((0.0, 0.0), (8.0, 0.0)), height=0.30, base_offset=-0.30,
     direction_sense="NEGATIVE")
```

Sharing the axis with the wall above is what recesses the plinth face. Both
runs centre on the same reference line, so a layer set that sums thinner sits
back symmetrically - 470 above and 440 below leaves 15 mm of shadow on each
side. A recess stated as its own number could disagree with the layers that
produce it.

Openings are not inherited. A plinth is declared without them and therefore
has none, which is what a threshold above grade wants; a door whose sill sits
at grade has to void the plinth run as well as the wall.

Which base a building has is a decision the script states, not a default: a
recessed plinth, typically 300 mm, or none at all with the wall starting at
grade. Neither follows from the rest of the declaration, so a building that
says nothing gets nothing. A ground `slab()` sets its own level through
`base_offset` the same way - see [slabs.md](slabs.md) - so the two have to
agree on where grade is rather than each assuming it.

Coordinate their horizontal boundaries too: a recessed plinth does not trim
an adjacent slab. Check where the floor buildup terminates against the wall
and base, so its layers do not protrude past the intended exterior finish.
Choose that relationship from the slab's construction role as described in
[slabs.md](slabs.md#choose-the-construction-boundary), including any separate
support needed beneath opening thresholds.

## Who does what

`ifcopenshell.api.geometry.regenerate_wall_representation` owns the corner. It
reads the layer set, the priorities, and the connection types, and produces the
mitres, butts, and notches - including composite profiles where a join cuts all
the way through. The skill supplies the declaration and stays out of the
geometry, exactly as it does with the roof skeleton.

Bonsai's own wall tools read the same data, so a script-authored wall stays
editable in Bonsai's UI rather than arriving as dead geometry.

Order matters: every connection must exist **before** any wall regenerates,
because a wall's body is a function of its connections.

`regenerate_wall_representation` never touches an opening. It runs once per
wall in the IFC phase, before any window or door exists, and owns corners
only - not voids. An opening's own `add_feature` call (see
[openings.md](openings.md)) is data-only too: it writes the
`IfcRelVoidsElement` relationship and nothing else, so nothing in the IFC
phase ever forces a wall's Blender object back in sync with the voids it
now carries. A wall can reach the live scene still looking unopened even
though its IFC data is entirely correct - measured on a wall carrying three
openings, which reached the scene at the polygon count of a plain unopened
box. The presentation phase closes this: its first step recalculates every
wall that carries an opening (`bim.recalculate_wall`, the same operator
Bonsai's own UI uses), before any material or tile work reads the scene.
This is unconditional compiler boilerplate - a project script never calls
it itself.

## Extend to the structure above

`extend_to_structure()` uses IFC's own property and relationship roles. The
element above is the `RelatingElement`; the wall is the `RelatedElement`. One
declaration creates one `IfcRelConnectsElements`, whose two roles name one
element pair. A wall declares only one structure above it, so execution order
can never decide which body wins:

```python
extend_to_structure(model, "partition.top",
                    relating_element="main-roof",
                    related_element="attic-partition")
```

The relating element may be an `IfcRoof` or an `IfcSlab`. The wall receives
`Pset_WallCommon.ExtendToStructure = TRUE`. `termination="UNDERSIDE"` is the
default: Bonsai clips the wall against the downward face of the structure, as
an internal partition ordinarily requires. `termination="TOP_SURFACE"` clips
against its upward face instead, so a gable wall occupies the roof's structural
depth and stops immediately below the separate roof covering. The termination
choice is authoring intent; IFC's standard property says only that the wall
extends to the structure above and does not prescribe one of its faces.

Bonsai records the required boolean so subsequent wall regeneration preserves
it. The relationship's `TOP` description and `BBIM_Boolean` property set are
Bonsai authoring metadata; the wall, relationship, standard property, and
resolved body remain ordinary IFC. `TOP_SURFACE` changes the wall termination;
it does not change the roof body's plan overhang. If only the covering should
project past the gable, the roof body and covering must also declare different
overhangs.

## Layers need no presentation work

IfcOpenShell splits a layered wall's body per layer on import, and Bonsai gives
each layer its own Blender material slot at exactly the declared thicknesses. A
wall arrives already split and already materialled.

The presentation phase therefore upgrades those imported materials in place
rather than reassigning slots: `imported_materials()` finds them through their
surface style and applies the same Principled graph the rest of the skill uses.
Clearing a layered wall's slots to paint it one colour would throw away the
layer breakdown IFC just worked out.

## Traps

- A wall with no `IfcMaterialLayerSet` regenerates to **no body at all** -
  `get_layers()` returns empty and the function bails. This is why a wall type
  is always required and why there is no single-material shortcut.
- The `Axis` representation lives in `Plan/Axis/GRAPH_VIEW`, not under `Model`.
  Everything that reads a wall measures from it.
- A wall's axis is always stored running in +X in its own local coordinates.
- Reference lines are drawn in plan, so two walls stacked on one axis - a
  plinth and its wall - touch there without meeting. They are not connected,
  and `junctions.py` needs each wall's `base_z` and `height` to tell that
  apart from a corner.
