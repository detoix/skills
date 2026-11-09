# Slabs

Declare a slab from its plan boundary plus a type, the way a roof is
declared - not from its layers restated on the occurrence.

## Declaration

```python
slab_type(model, "floor.200", name="Ground Floor Slab 200", predefined_type="BASESLAB", layers=[
    layer("concrete", 0.150, priority=90, category="LoadBearing", name="Structural Slab"),
    layer("screed",   0.050, priority=10, category="Finish",      name="Screed"),
])

slab(model, "ground-slab", storey="ground", slab_type="floor.200",
     boundary=[(0.0, 0.0), (8.0, 0.0), (8.0, 6.0), (0.0, 6.0)],
     base_offset=-0.200, name="Ground Slab")
```

A slab never states its own depth: depth is the sum of its type's layers,
exactly as a wall's thickness is - stating it twice invites the two to
disagree.

A slab also does not constitute a room. One structural slab may span several
`IfcSpace` occurrences, and different room finishes do not make it several
slabs. A room-specific flooring finish is a separate `IfcCovering(FLOORING)`
whose plan footprint is derived exactly from the room's final resolved
footprint; declare it with `covering(...)` as described in
[spaces.md](spaces.md). Do not imitate it with a thin room-sized slab.

## Choose the construction boundary

State the slab's construction role and intended edge relationship in the
building script before choosing its boundary. A foundation raft may support
perimeter walls; an internal floor buildup may stop at their finished inner
face. Neither relationship follows automatically from `BASESLAB`, the building
footprint, or the room footprints. Use the project's intended construction,
and record an assumption when the source does not establish it.

Do not reuse the exterior footprint for an internal buildup without checking
its junction with the perimeter wall and plinth. Resolve the specified face
at recesses and corners as well as along straight runs.

All layers in one layered slab share its plan boundary. If the structural
concrete, insulation, or screed need different extents, declare separate
construction elements with their actual boundaries rather than forcing them
into one layer set. Room floor finishes remain separate space-derived
coverings. Verify the resulting junction using [quality-assurance.md](quality-assurance.md).

## What maps to what in IFC

| declaration | IFC |
| --- | --- |
| `slab_type(...)` | `IfcSlabType` + `IfcMaterialLayerSet` |
| `predefined_type=` | `IfcSlabTypeEnum` |
| `layer(...)` | `IfcMaterialLayer` - `LayerThickness`, `Priority`, `Category` |
| `slab(...)` | `IfcSlab` + `IfcRelDefinesByType` |
| `boundary=` | the extruded `Body` profile |
| `material=` + `tiers=` | one `IfcSlab`, several `IfcExtrudedAreaSolid`, one `IfcRelAssociatesMaterial` |
| a wall reaching a slab above | `extend_to_structure()` - the same primitive a wall uses against a roof |

For that relationship, the target surface is the slab's base - its underside.
The applicable slab boundaries must cover the wall's complete plan footprint,
and that underside must lie above the wall base. A ground slab below a wall is
therefore never its `extend_to_structure()` target.

## The boundary extrudes upward from `base_offset`

`boundary` is walked in the layer set's `AXIS3` stacking direction: the slab
extrudes upward from `base_offset`, which is the elevation of the slab's own
base, not its top. A ground slab that a storey's walls should stand on
flush - the ordinary case - declares `base_offset` as the negative of its
own total thickness, so the top lands exactly at the storey elevation:

```python
slab(model, "ground-slab", storey="ground", slab_type="floor.200",
     boundary=SQUARE, base_offset=-0.200)   # top at elevation 0.0
```

Left at its default of `0.0`, the slab's *base* sits at the storey
elevation and the body extrudes upward through it - the right choice for a
roof slab or a landing whose underside, not its top, is the reference.

`boundary` reuses the same closed-footprint check a roof's `boundary` does:
at least three corners, no repeated corner, the first corner not restated as
the last.

## Layered, or tiered

A slab is declared one of two ways, and they are mutually exclusive.

**Layered** is everything above: a `slab_type` carrying an
`IfcMaterialLayerSet`, and one `boundary`. Every layer shares that boundary,
because that is what a layer set *means* - one profile, sliced through its
thickness. A ground slab, a landing, a balcony.

**Tiered** is one `material` and a list of `(boundary, height)` pairs,
stacked bottom-up from `base_offset`:

```python
TERRACE_DECK = [(1.5, 6.0), (6.5, 6.0), (6.5, 9.5), (1.5, 9.5)]
TERRACE_STEP = [(1.2, 6.0), (6.8, 6.0), (6.8, 9.8), (1.2, 9.8)]

slab(model, "terrace", storey="ground", predefined_type="FLOOR",
     material="timber.decking",
     tiers=[(TERRACE_STEP, 0.150), (TERRACE_DECK, 0.150)],
     base_offset=-0.300)
```

Every footprint is stated. Nothing is offset, mirrored, or inferred from
which edge faces a building - a terrace that steps down to a garden says
where each tier goes, and three steps are three pairs of differing heights.

### Why tiers are not layers

Two reasons, and neither is style.

A layer set requires **one profile**. Tiers have different ones, so they
cannot be expressed as `IfcMaterialLayerSet` at all - which is also why a
tiered slab writes a plain `IfcRelAssociatesMaterial` instead, and why
`IfcSlabStandardCase` is not used for one: that subtype is the one that
requires the body to match its layer set. Plain `IfcSlab` does not.

And a tiered slab is **one material**. Declaring it as layers would write
that material once per tier, each entry carrying nothing but a thickness -
and a thickness belongs with the boundary it applies to, not in a parallel
list the occurrence has to match by index.

It is still **one `IfcSlab`**. Several extrusions in a single `SweptSolid`
representation, not several elements: `IfcShapeRepresentation.Items` is a
set, and several swept solids in it is exactly what the schema allows.

`validate()` refuses a slab that declares both ways, neither way, tiers with
no material, or a layer set with a material of its own.

### What a tiered slab gives up

No `EPset_Parametric` / `Bonsai.DumbLayer3`. That pset is what keeps a
layered slab editable by Bonsai's own slab tool, and that tool regenerates a
body from a layer set - so claiming it on a tiered slab would invite the tool
to flatten the tiers back into one prism. A tiered slab is authored geometry
and stays that way.

Per-layer thickness also stops being readable from the material description.
It survives as each tier's own `IfcExtrudedAreaSolid.Depth`, which is a
number a consumer can still read, just not where a takeoff would look for a
buildup. For one material that is no loss; for a real buildup, use layers.

## Who does what

`ifcopenshell.api.geometry.add_slab_representation` builds the extruded
body from the boundary and the resolved depth - the same call Bonsai's own
slab tool (`DumbSlabGenerator`) makes when a slab is drawn from a polyline
in the viewport. A script-authored slab and a Bonsai-drawn one are built by
the identical code path.

`LayerSetDirection` is set to `AXIS3` directly on the resulting
`IfcMaterialLayerSetUsage`, the same attribute Bonsai's own generator sets.
IfcOpenShell reads it on import to split the single extruded body into one
Blender material slot per layer, at the declared thicknesses - a slab
arrives already split, exactly as a layered wall does.

`EPset_Parametric.Engine = "Bonsai.DumbLayer3"` is written for the same
reason `BBIM_Roof` is: it is what keeps a script-authored slab editable by
Bonsai's own slab tool afterwards, rather than arriving as dead geometry.

## Traps

- A slab's `boundary` is absolute, in the building's own coordinates - not
  relative to any wall, and not offset by a wall's thickness. A slab meant
  to reach a wall's outer face has to say so in the boundary itself; nothing
  derives it from the walls the way a room's shape is derived (see
  [references/spaces.md](spaces.md)).
- There is no `overhang` on a slab the way a roof has one. A slab that
  should oversail its walls declares that in `boundary` directly, or by
  running its boundary corners through `polygons.offset_polygon()` before
  declaring - the same function the roof phase uses.
- A slab has no corners to resolve against neighbouring slabs. Two slabs
  that should meet flush have to declare boundaries that already do; nothing
  mitres them the way `junctions.py` mitres two walls.
- Do not split a structural slab at room boundaries merely to assign ceramic,
  timber, or another room finish. Material layers describe one buildup over
  the slab's one boundary; room finishes belong to space-derived floor
  coverings instead. The finish through a floor-level opening is another
  opening-derived `IfcCovering`, never a thin slab and never an extension of
  either room covering.
