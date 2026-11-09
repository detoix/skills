# Gutters and Downspouts

Declare a gutter against a roof's **declared boundary edge**, and let the
compiler resolve the run, its corners, and its ends.

## Declaration

```python
gutter(model, "main-roof.eave.0", roof="main-roof", edge=0,
       profile="gutter.half_round", nominal_size=0.125,
       material="metal.zinc")

downspout(model, "main-roof.eave.0.ds.0", gutter="main-roof.eave.0",
          along=2.5, length=2.36, profile="downspout.round",
          nominal_size=0.100, termination="shoe",
          standoff=0.22, drop=0.12, bend_radius=0.08,
          material="metal.zinc")
```

The run follows boundary `edge`'s own **overhang line** - the mitred polygon
`roof()` already solves in `polygons.offset_polygon()` - so a gutter states no
coordinates of its own and moves when the roof moves. Positioning against a
declared edge rather than a skeleton face is the same choice `roof_window()`
makes, for the same reason: faces are straight-skeleton output whose numbering
shifts, edges are declared.

`along` measures from the run's own start, the vocabulary a window's `along`
already uses on its wall. `nominal_size` is EN 612's naming - the width across
- and `thickness` defaults to the profile's own cited gauge.

Each gutter owns its key namespace (`<gutter>.start-stop`,
`<gutter>.end-stop`).

[scripts/example_build.py](../scripts/example_build.py) drains its roof this
way: a half-round run with round pipes and shoes on one eave, a box run with
square pipes stopping square on the other, and every number for both derived
from the roof's and the wall type's own declared dimensions.

## What maps to what in IFC

| declaration | IFC |
| --- | --- |
| `gutter(...)` | `IfcPipeSegment` / `GUTTER` |
| `downspout(...)` round | `IfcPipeSegment` / `RIGIDSEGMENT`, body `IfcSweptDiskSolid` |
| `downspout(...)` rectangular | same, body `IfcRectangleHollowProfileDef` swept with a fixed reference |
| a mitred end | `IfcBooleanClippingResult` + `IfcHalfSpaceSolid` |
| a free end | `IfcPipeFitting` / `USERDEFINED`, `ObjectType="StopEnd"` |
| every one of them | `IfcDistributionSystem` / `RAINWATER`, by `IfcRelAssignsToGroup` |
| `nominal_size=` | `Pset_PipeSegmentTypeCommon.NominalDiameter` |
| `material=` | `IfcRelAssociatesMaterial` |

`GUTTER` and `RAINWATER` are both real IFC4 enumeration values, so neither is
a naming convention dressed up as semantics. A stop-end is the
one exception: `IfcPipeFittingTypeEnum` has no value for a closure - `ENTRY`
and `EXIT` both name flow it does not carry - so it is `USERDEFINED` with
`ObjectType` saying what it is, the same choice a sill makes against
`IfcBuildingElementPart`.

## Corners mitre themselves

Where two gutters meet at a roof corner they mitre, and **neither is told the
other's numbers**. The mitre plane bisects the turn, so each run cuts at the
same angle to its own axis, from its own section - and two runs that both do
that land on one plane by construction.

This is `sills.py`'s corner-window trick, one step generalised. A sill builds
the wedge into its own footprint because a sill is a flat slab. A gutter is a
swept section, so the same 45 degrees arrives as a half-space clip instead:

```
IfcBooleanClippingResult(DIFFERENCE,
    IfcExtrudedAreaSolid(section, length + overrun),
    IfcHalfSpaceSolid(plane at 45 degrees in plan, at the run's own end))
```

`gutters.mitre_normal()` is the whole rule: the plane's normal is the **sum**
of the two directions, not their difference. Their difference is the joint
*line*; using it mitres the wrong way and the two runs miss each other. The
incoming run keeps the negative side and the outgoing run the positive side,
which is why `gutter_payload` reverses the normal at a run's start.

An edge whose neighbour carries no gutter gets a stop-end instead - the
section closed into a **filled** polygon by `plate()`, extruded one sheet
thickness. Not `ring()`: the sheet's own outline extrudes into an annulus, a
hollow slice of the run flush against its own end face, closing nothing and
invisible against the metal it was cut from. Both conditions are derived from
which edges were declared, so neither is stated.

Two runs doubling back on themselves have no bisector at all, and
`mitre_normal` returns `None` for the compiler to refuse by name rather than
emitting a plane that is not a plane.

### Why the mitre is stated locally

Every mitre is expressed in its own run's frame - X along itself, Y across, Z
up - never in world coordinates. Handing both runs the shared world plane
produces *identical geometry* and quietly destroys the property that makes
this work: the two would then depend on a value neither could derive alone,
and a roof edge moving would need both to be resolved together.

This also removes the acute-corner hazard a single continuous swept corner
has. IfcOpenShell mitres a sweep's own corners blindly - a 15 degree turn on a
130 mm section returns a self-intersecting solid with no error at all - but a
per-run clip has no such corner to degenerate.

## Sections are profiles, not meshes

`railings.py` returns a mesh and `assign_role_split_body` splits it, because a
guardrail is posts, infill and a rail: three parts in one product. A gutter is
one folded sheet swept along a straight run, and IFC has words for exactly
that, so `gutters.py` returns **profiles** and the IFC phase sweeps them.

That is the same doctrine, not an exception to it. A swept solid carries its
section as readable numbers, so a consumer reads a 125 mm half-round back off
the file; the same gutter written as a face set is a coordinate list nobody
can query - the dead geometry the skill already refuses elsewhere.

### The section frame, and its one axis flip

`gutters.py` states a section as `(u up, v toward the building)`, which reads
like a manufacturer's drawing. An extrusion's profile plane is placed with
`Axis=(1,0,0)` and `RefDirection=(0,0,1)`, so its own Y comes out of the cross
product pointing *away* from the building. `section_profile()` negates `v`
once, at that single seam, rather than inside a procedure that has no business
knowing about IFC placements.

`v = 0` is the **back** of the gutter, not its centre. A gutter hangs off a
fascia, and a run placed on its own eave line then needs no lateral offset. A
centred section puts half the gutter inboard of that line - which is inside
the roof. Every profile is drawn centred and shifted onto its back datum by
`_backed()`, once.

## Where a gutter hangs

`base_offset` positions the **eave**, and the eave is the roof's *top*
surface. The roof is `thickness / cos(pitch)` deep measured vertically at that
line - 0.346 m for a 0.30 m buildup at 30 degrees - so a run hung at the eave
elevation sits inside the roof solid, and so does everything hanging off it.

`gutter_payload` therefore drops the run by exactly that, putting its top edge
on the roof's underside where a fascia would be. Its back upstand still laps
about 20 mm up past that, which is the detail rather than a clash: a drip laps
into the gutter, and a deliberate small overlap is what the skill already uses
in `SILL_RISE` and `OPENING_REACH` to avoid coplanar faces.

The **roof's single agreed pitch** is used, not the edge's own.
`skeleton.require_supported` already refuses a roof whose slope-defining edges
disagree, and one pitch is what guarantees every run on a roof hangs at the
same height. Two runs at different heights would each still mitre at 45
degrees and no longer meet - trading a visible clash for an invisible one.

## What a downspout is allowed to know

A downspout references exactly one thing: **its gutter**. It starts at that
gutter's `sole()` - the section's own lowest point - and falls.

It knows nothing about the roof, and nothing about any wall. That is what
makes it reliable rather than merely correct today: it cannot clash with a
roof it never consulted, because the gutter it hangs from does not, and it
inherits that by construction rather than by checking.

`drop` is derived: a pipe swans back **under** the roof's overhang, so it has
to fall clear of the soffit before turning inboard, and how far that is
belongs to the gutter's roof. The gutter publishes `sole_above_soffit` and the
compiler adds the pipe's own half width and a clearance. The pipe is handed
the figure, never asked for it, so it still references nothing but its gutter.

That one is worth stating plainly because raising the run to the drip edge is
what created the need for it: at the old soffit-line hang, 0.12 m was enough,
and afterwards 236 vertices of every swan neck ran through the roof.

So `standoff` is **stated, not derived**. How far back the pipe reaches
depends on what it is fixed to, and neither the downspout nor its gutter knows
that. Defaulting it from the roof's overhang would teach the downspout about
the roof to solve a problem that belongs to the wall - a guess dressed as a
default. `corner_reach`'s lesson, one more time: derive what is derivable
locally, declare what needs knowledge from outside. The authoring agent owns
that arithmetic, because it is the only thing that sees both.

`sheet_thickness` is the **pipe's** own gauge. It was called `wall_thickness`,
which in a module where "wall" is a loaded word read like a reference to a
building element it must never have.

### `IfcCenterLineProfileDef` says this, and does not work

The schema has exactly the right entity: a centreline plus a `Thickness`,
`ProfileType = AREA`, legal in any swept area solid, present since IFC2X3. It
is not used, because **IfcOpenShell 0.8.5 ignores that `Thickness`** and
closes the bare centreline into a filled polygon - so a 0.6 mm gutter arrives
as a solid lump of metal. A four-point centreline at 20 mm thickness returns
eight vertices at the raw centreline coordinates; the explicit ring returns
sixteen, at plus and minus 10 mm.

So `sheet_ring()` offsets the centreline both ways here. The offset is
**mitred**, not per-vertex: offsetting each vertex along its own normal
pinches a ninety degree fold to `t / sqrt(2)`, and the sheet stops being one
gauge. It is the same mitred offset a roof's overhang polygon already uses,
done on an open run rather than a closed one, and a test pins the perpendicular
thickness along every segment.

## Two shapes, each

Both a gutter and a downspout name a `profile` against a registry and carry
only their own size, the way a railing names a design and a window a type.

| | round | square / rectangular | other |
| --- | --- | --- | --- |
| gutter | `gutter.half_round` | `gutter.box` | `gutter.concealed` |
| downspout | `downspout.round` | `downspout.rectangular` | |

`nominal_size` is the outside dimension across - a diameter for a round pipe,
a width for a rectangular one, the gutter's width for a gutter - which is how
all of them are catalogued. Left unstated it takes the profile's own.

A rectangular pipe's `aspect` (depth over width) lives on the **profile**, not
the occurrence, so a round pipe is never asked for a second dimension it has
no use for. A non-square rectangular pipe is another registry entry, not
another argument on every call.

## Downspouts

One element follows the whole path. It drops clear of the gutter, turns
toward the wall while descending, then continues vertically.

A **round** pipe is one `IfcSweptDiskSolid`. `InnerRadius` bores it for free,
which is why it is one solid and not a difference of two.

A **rectangular** pipe is an `IfcRectangleHollowProfileDef` - carrying `XDim`,
`YDim` and `WallThickness` as readable numbers - swept by an
`IfcFixedReferenceSweptAreaSolid`, because a profile has an orientation a disk
does not.

That reference is **local X**, along the gutter the pipe hangs from. Every
segment of a downspout's path lies in the local Y-Z plane, so local X is
perpendicular to every tangent on it, which is what the schema demands: a
`FixedReference` parallel to the tangent anywhere along the directrix is
invalid. Global Z would be exactly that mistake, since the pipe's own straight
run is vertical.

`StartParam` and `EndParam` are omitted for both - a polyline is already a
bounded curve, which is what the schema's `DirectrixBounded` rule asks for,
and supplying them means restating a parameterisation that differs between the
two curve types.

### `length` is the whole fall

`length` measures from the gutter's sole to the end of the straight run, not
the segment left over after the swan neck. It is the dimension that can be
measured on site, so it is the one a script states; turning it into a segment
is arithmetic, and arithmetic belongs in the compiler rather than in every
call. Changing `drop` or `standoff` then moves the neck and nothing else.

`validate()` refuses a run whose own neck would use up its whole fall.

### Terminations

`straight` stops the pipe square, for a gully directly below. `shoe` adds a
kicked segment throwing the water clear of the wall.

The shoe's mouth is inclined **without being cut**: a swept solid ends
perpendicular to its own directrix, so a kicked final segment arrives with its
mouth already on the slant. No clip, no second profile, one extra point on the
path - kicked to negative local Y, outboard, using the direction the gutter
already establishes.

`SHOE_ANGLE` is 67.5 degrees **from vertical** - the deflection, which is how
Polish catalogues name an elbow and the opposite of how UK ones do. A `kolano
67,5 stopni` and a "112.5 degree offset bend" are the same fitting: 67.5 +
112.5 = 180. Bryza and Gamrat PVC run 67.5; KJG and Bryza steel run 72. It is
a module constant rather than a per-downspout argument, because one angle is
what makes every shoe on a building match; a script built on a steel system
changes it in one place.

Forty-five degrees, which this had first, is neither: it reads as a lazy
dogleg rather than a shoe, and it came from a UK source describing the
included angle.

`bend_radius` left at zero mitres each bend at half angle, which is what a
folded sheet elbow looks like. A positive one replaces each corner with a real
tangent arc, and there the arc's midpoint has to lie **on** the arc: a point
picked by averaging its ends is collinear often enough that the kernel rejects
the entire curve, surfacing as a shape failure naming only the product. For a
fillet set back `d` along legs meeting at `theta`, the radius is
`d * tan(theta/2)` and the centre sits `d / cos(theta/2)` from the corner along
the bisector.

A swan neck's middle leg is only `standoff * sqrt(2)` long, so both its fillets
clamp to half of it and meet exactly at its midpoint. That is a smooth, valid
path whose two tangent points are the same coordinate - and appending both
leaves a zero-length `IfcLineIndex` between them, which the kernel rejects as
a whole curve. `_fillet_path` reuses the point rather than repeating it.
Comparing segment indices does not catch this; comparing coordinates does.

`validate()` rejects a level or rising swan neck. A downspout belongs to its
storey and joins the rainwater system. It has no `IfcOpeningElement`.

### They arrive as Blender curves

Bonsai imports `IfcSweptDiskSolid` natively, as a Blender **curve with a round
bevel** rather than a mesh - the downspout's `bevel_depth` is its own outside
radius. It stays parametric on both sides of the import, which a mesh
representation would not. A rectangular pipe arrives as an ordinary mesh: its
sweep is not one of the forms Bonsai recognises natively.

`IfcSweptDiskSolidPolygonal` is in the IFC4 schema and looks like the better
fit for a filleted run, but IfcOpenShell's kernel fails to process it outright
("Failed to process shape"). Plain `IfcSweptDiskSolid` with an arc directrix is
the path that works.

## Gutters are level

Real installations fall toward an outlet. These do not, and that is a
deliberate limit rather than an omission: fall tilts each run's own
`ObjectPlacement` by its own angle, and two runs falling toward *different*
outlets tilt by different angles - so their mitre planes stop being coplanar
and the joint opens by the difference. Level keeps the coincidence exact.

Adding fall means solving the outlets first and giving both runs at a corner
one shared tilt, which is a different design, not a parameter.

## Traps that cost real time

- **`IfcHalfSpaceSolid`'s plane is in the object frame**, not the swept
  solid's `Position` frame. A plane written in the extrusion's own frame cuts
  nothing - no error, just an unclipped solid. This is why a run's direction
  lives in its `ObjectPlacement` and never in `IfcExtrudedAreaSolid.Position`.
- The extrusion must **overrun** the corner before the plane cuts it back.
  Stopping exactly on the corner leaves the cut coplanar with the end face and
  the boolean nothing to resolve. `MITRE_OVERRUN` is that margin, as a
  multiple of the section's own half width.
- `ifc_api.system.add_system` takes **only** `ifc_class`. Name and predefined
  type are set on the entity afterwards.
- A half-round's sole sits at `(-nominal/2, -nominal/2)`: **up and across are
  the same number**. Anything that carries the two positionally can be
  transposed and still pass every test written against the default profile.
  `drop_point` is a named mapping for exactly that reason - as a pair it was
  swapped in the template, and only a box gutter showed it, throwing each pipe
  37.5 mm sideways out of its own trough. Any test of a two-axis quantity here
  runs over every profile, not just the default one.

## Reference values

| quantity | value | source |
| --- | --- | --- |
| half-round gutter, domestic | 0.125 m nominal | EN 612 |
| gutter widths, UK | 112 mm half round, 114 mm square line | Kalsi Plastics |
| sheet, steel / zinc | 0.6 / 0.7 mm | EN 612 ordinary range |
| downspout, round | 0.100 m OD, 1.5 mm wall | pairs with a 125 mm gutter |
| round downpipe sizes | 50, 65, 68, 80 mm (UK); 80-150 mm (PL steel) | Kalsi Plastics; KJG |
| square downpipe sizes | 65 x 65, 80 x 80 mm | Kalsi Plastics |
| shoe / elbow deflection | 67.5 deg (PVC), 72 deg (steel) | Bryza, Gamrat, KJG |
| box gutter depth | 0.8 x width | ordinary box proportion |
| trough sampling | 12 segments per half turn | chord error below the sheet thickness |

The trough is sampled rather than carried as an arc: twelve segments holds the
chord error under a tenth of a millimetre at 125 mm, which is finer than the
sheet itself. The sweep is exact; only the section is faceted.
