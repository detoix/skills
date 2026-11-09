# Ridge and Hip Caps

Declare which cap a covering wears; let the compiler find the arrises that
wear it.

## Declaration

```python
roof(model, "main-roof", storey="attic",
     boundary=[(0.0, 0.0), (8.0, 0.0), (8.0, 6.0), (0.0, 6.0)],
     angle=40.0, thickness=0.30, overhang=0.4,
     top_material="roof.structure", ceiling_material="ceiling.white",
     side_material="facade.render",
     covering="tile.clay", covering_material="tile.terracotta")
```

That is the whole declaration - there is no cap on that call at all. A
covering names its own cap, because a ridge fitting is sold against the
covering it caps, so `tile.clay` is already what says `cap.segmental`. Every
ridge and every hip of that roof is capped, and a shed roof takes the same
declaration and grows none.

`covering_cap="cap.half_round"` overrides the covering's own, for a roof that
wants a different cap without declaring a second covering.

This is `verge_trim`'s rule one step further again. A verge is wherever the
roof surface stops on a rake, which a gable has already said. A cap is
wherever two roof faces fold **away** from each other, which the boundary and
the gable flags have already said - and unlike a verge, it is not even a
choice of trim: an uncapped ridge is a hole, not a design.

[scripts/example_build.py](../scripts/example_build.py) caps its roof this
way, with nothing in the script mentioning it.

## What maps to what in IFC: nothing

A cap is **presentation only**. It is merged into the roof covering's own
Blender mesh - the mesh already swapped onto the `IfcCovering(ROOFING)` the
IFC phase built - so the file says the roof is covered in clay tile and the
capping is part of that covering, which is what it is.

There were three ways to do this and two of them were defensible:

| | |
| --- | --- |
| one `IfcCovering` per ridge and hip run | honest, queryable, and a shadow element |
| merged into the covering's mesh | **this** |
| a standalone Blender object | refused |

The third is out on a rule already written down. `references/roofs.md` refuses
exactly that for the tile field - *"not a second, BIM-less object placed
beside it"* - and a loose cap object would be the first in the skill and the
one the next person copies.

The first is the one a verge trim takes, and the reason a cap does not take it
is that a verge board genuinely **is** one continuous object, so a swept solid
is an honest description of it. A run of gąsiory is not one object, and its
IFC body would be a coarse extrusion nobody ever renders, existing only to
hold a length the roof solid already implies - `trims.edge_kind` reads every
ridge and hip straight off it.

What that costs, plainly: `IfcRelCoversBldgElements` lists the tile field and
the verge trims, and capping is folded silently into the field covering. A
takeoff asking for Uniclass `Pr_35_90_93_13` ridge fittings separately gets
nothing back. Promoting to the first row is one block in the IFC phase and
**no** rework here - the layout, the procedures and the merge are unchanged -
so it is a later addition rather than a rewrite.

### What IFC would say, if it said it

Worth recording, because it was researched and it is the path a promotion
takes. IFC has both halves:

- **Instancing.** `IfcRepresentationMap` plus `IfcMappedItem` carrying an
  `IfcCartesianTransformationOperator3D`, in a shape representation of type
  `MappedRepresentation`. It is the schema's block/cell/macro mechanism and a
  direct analogue of a `THREE.InstancedMesh`; it nests; and mirroring is legal
  outright, since the operator's own definition says `|T| = -1` includes it.
  IfcOpenShell 0.8.5 authors it through
  `ifcopenshell.api.geometry.map_representation` and
  `ifcopenshell.api.type.assign_type(should_map_representations=True)`. The
  cost is one IFC product per cap, which is the tile-field objection at a
  smaller scale rather than a different one.
- **A linear edge covering.** `IfcCovering`'s own documentation splits
  coverings for surfaces, which take material layers, from coverings for
  **edges** - `MOLDING`, `SKIRTINGBOARD`, `COPING` - which take material
  profiles and swept-solid bodies. A ridge cap is exactly that. No enum value
  names one, so it would be `ROOFING` or `USERDEFINED` with `ObjectType`, the
  choice a verge trim and a gutter stop-end both already make.

IFC4.3's `IfcLinearPlacement` with `IfcPointByDistanceExpression` is the
literal "place things at distances along a curve", and is the wrong tool: it
is alignment machinery, it is 4.3 only, and this skill targets IFC4.

## Which arrises get one

`trims.edge_kind()` already answered this and nothing consumed it. Two of its
five verdicts are caps:

| adjacent faces | edge | this module |
| --- | --- | --- |
| two upward, convex, level | ridge | **capped** |
| two upward, convex, raking | hip | **capped** |
| two upward, concave | valley | lined - not built |
| one upward, level | eave | gutter |
| one upward, raking | verge | the board below |

`cap_runs()` in the presentation phase harvests the first two the way
`verge_runs()` in the IFC phase harvests the fifth.

Caps are merged into the covering **before** the roof windows are subtracted
from it, so a window reaching a ridge cuts its cap along with the field. That
puts overlapping caps inside the boolean, which is safe for the reason it is
already safe for tiles: a tile field laps course over course, so the solver
has been taking self-intersecting input since the first roof.

## A cap sits on the bisector, which is why it carries an `up`

`trims.VergeRun` deliberately returns no `up`: a verge board's is world
vertical for every run there will ever be. `caps.CapRun` carries one, because
a cap straddles two faces and sits on the plane that bisects them - vertical
on a ridge, tilted on a hip.

That bisector is cheap to build here, and only here:

```
up = UP - along * UP.dot(along)
```

world up with the run's own direction taken out of it. It is the true face
bisector **because every roof in this skill slopes at one agreed pitch** -
`skeleton.require_supported` refuses anything else - so the two faces meeting
on any arris are symmetric about the vertical plane through it. On a roof of
mixed pitches this would be wrong, so the pitch rule is what makes the frame
correct.

`across` is `up x along`, so the frame is right-handed by construction and no
vert or face order can flip a cap over - the same guard `verge_runs` needs for
the same reason.

## Where a cap sits is derived, never declared

A cap has to clear the covering under it. How far that is depends on the
covering's relief and on how steeply the roof falls away from the arris, and
both are known where the cap is built, so neither is stated:

```
seat    = envelope / cosine - foot * tangent
tangent = sqrt(1 - cosine^2) / cosine
```

`cosine` is the run's own bisector against either face normal - one number
that yields both. `envelope` is `tiles.TileProfile.envelope()`, the same
number `trims.upstand_over()` takes.

A cap asks the covering for exactly two things, and `relief` is the second:
how far the surface drops back again *across* the run, between the highs
`envelope` measures. A cap is one section swept along a straight arris, so it
cannot follow a corrugation it crosses at an angle - a pantile's rolls, a
seam's upstands. The skirt turns down at its tip by exactly the relief and
closes the shadow gap instead of pretending it is not there.

A flat tile has zero relief and needs no lip. For a pantile, calculate
the relief from the sampled section.

`seat` puts the **foot** of the skirt - the half width where it leaves the
crown - exactly on the covering's top surface. The skirt then lies flat along
that surface for its whole width, at the roof's pitch. The seat follows the
covering height so the skirt closes against the tiles.

## A piece is not one swept section

Four things happen along a piece, and every one of them exists because a run
has to **end** somewhere:

```
z = 0              head, barrel drawn in by `inset`
z = nose           full section
z = length - nose  full section, then a step out by `rim`
z = length         section closed over onto its own skirts
```

### The dome

A run ends at an eave, and its last piece is the one thing on a hip that gets
looked at from directly below. Swept and left open it is a tube you see
straight up. That is the whole reason a cap cannot be an extrusion, and it is
the first thing anybody notices on a hipped roof.

A flat plate across the mouth is not the answer either: it closes the hole and
still reads as a tube that was sawn off. The barrel has to **close over**, the
way the moulded end of a real ridge tile does. It follows `sqrt(1 - t^2)` over
the last `nose`, which leaves the barrel tangent at the start and arrives flat
at the tip - the two things that make it read as moulded rather than as a cone.

It scales the **whole section** about the seat line, not only its height.
Dropping the crown alone leaves the tip as wide as the body, so the piece ends
in a full-width strip that reads as a chamfer however smooth the curve over it
is; it has to roll over in plan as well as in section. That is also why the
skirts pull in over the dome where along the body they never move - past the
last course there is nothing left for them to lie on.

The last ring keeps a tenth of its size rather than collapsing to a point,
which would leave the sweep's final band with no area at all.

### The inset, and why one mesh is enough

A closure would ordinarily mean two objects - a plain piece and a special end
piece - and the field would then have to know which is which. It does not.
The same closure is on **every** piece, and each head is drawn in by `inset`
so the dome of the piece above sits over it. One mesh, repeated, and the last
piece on a run is simply the one whose dome nobody covers.

`inset` has to exceed the gauge, or the dome and the head it covers lie on
each other and z-fight down the whole overlap.

### The rim, which is the joint

The section steps out where the closure begins, so the dome starts on a hard
edge rather than fading into the piece it covers. That edge is what a run
reads as: without it the dome tapers away into its neighbour and the whole
ridge is one extruded tube with no joint anywhere along it.

This is the real detail, not a device. Ridge tiles come two ways: butt-jointed
with a uniform **10 mm gap** pointed in mortar (or left open under a cleat on
a dry-fix system), or **capped** - carrying "a raised section at one end that
laps onto the end of the next ridge tile, to protect the butt joint", sold that
way precisely so no mortar is exposed. These are the second kind.

`rim` is deliberately **not** measured against the gauge. It is a step in the
*silhouette* - what makes a run read as units - where a gauge is a step in the
*surface*. A moulded clay unit has a 16 mm wall and a 12 mm rim, and the rim is
the one seen from the ground. A folded metal capping laps by a fold instead, so
`cap.seam` carries 3 mm.

## The run ends on the arris

A cap run cannot be cropped the way a tile field can - there is no face to
intersect it with - and a stub piece at a hip foot is visible from the ground.
So the module is **fitted**: the run is divided into whole pieces and every
piece is cut to the same slightly-short length, which is the one thing a run
of ridge tiles genuinely is on site.

A piece is one step of body plus a nose that laps the piece below, so `n` of
them reach `n * step + nose`. `spacing()` solves *that* against the arris,
which is what lands the last dome **on** the eave. Laying them at the module
and letting the tail fall where it may overhangs by a whole nose - and on a
hip that is the piece nobody can miss.

Round the count **up** so the fitted step stays within the profile module.
Each nose then overlaps the next piece throughout the run.

A run shorter than the nose that has to close it is refused rather than
fitted, and a test pins `piece >= step` across every profile over run lengths
from just past a nose to thirty modules.

## Each covering brings its own cap

`TileProfile.cap` names it, the way the profile already names its `build` and
its `stagger`. That is where it belongs: a ridge fitting is sold against the
covering it caps, so the covering is the thing that knows.

| covering | cap | why that one |
| --- | --- | --- |
| `tile.clay`, flat interlocking | `cap.segmental` | faceted crown breaking to straight flanks |
| `tile.celtic`, profiled | `cap.half_round` | an arc, matching the pantile's own roll |
| `tile.standing_seam` | `cap.seam` | folded sheet, no arc at all |

The first row is the one that is easy to get wrong, and this document got it
wrong first. **"Plain tile" and "flat tile" are two different coverings that
share a word in English.** The small double-lap *plain* tile takes a
half-round; a *flat interlocking* tile - which is what `tile.clay` is, 0.2928
x 0.47 m on a single lap - takes an angular or segmental ridge, and a
half-round on it looks wrong to anyone who has seen a roof.

One cap serves a covering's ridges **and** its hips. In the trade they differ -
a plain tile roof runs a half-round on the ridge and a shallower third round on
the hips - and that split is deliberately not modelled: `trims.edge_kind` tells
the two apart and nothing here consumes the distinction.

## Sections are solid, where a gutter's is a shell

A cap is drawn as a centreline and then **closed onto the covering**: one
point under the arris, on the covering's own surface, turns the outer curve
into a filled silhouette. The curve is sampled at the same twelve segments per
half turn `references/gutters.md` justifies.

The solid section closes gaps under the skirt on profiled coverings and
avoids building an inner wall.

## What is deliberately not built

- **The junction fitting.** Where two hips meet a ridge, three runs converge
  and their caps overlap. A real roof uses a moulded junction there. Runs are
  laid independently and the barrels hide the overlap. Mitreing them would
  mean each run knowing about its neighbours, which is the coupling
  `gutters.mitre_normal` exists to avoid and cannot avoid at a three-way
  meeting.
- **A separate hip fitting.** The trade sells a shallower unit for hips - a
  third round against a half-round ridge, or a bonnet on plain tiles. One cap
  serves both here.
- **Valleys.** `edge_kind` names them and still nothing consumes it. A lined
  valley is not additive - the trough sits under the covering, so the tiles
  have to be cut back - so it is a change to the crop, not another profile.
- **Closure strips.** A cap's underside is one section, so it bridges a
  corrugated covering from high point to high point and leaves a recess at
  each low point - as deep as the relief, 30 mm on the pantile and 38 mm on
  the standing seam. A real roof plugs those with a profiled closure cut to
  the covering's own corrugation. Going solid turned them from slots into a
  tunnel into shallow dents, which is most of the fix; the rest needs the cap
  to know the covering's *bay spacing* and not only its relief, and that is a
  coupling worth deciding deliberately rather than adding in passing.
- **Mortar bedding and dry-ridge systems.** A cap sits on its seat with air
  under it. Neither the bedding nor a ridge batten is modelled.
- **Laps between pieces as a separate thing.** The nose is the piece's own
  overhang, not a joint anyone can query.

## Reference values

Measured, not invented. Pinned in `scripts/tests/`.

| quantity | value | source |
| --- | --- | --- |
| clay ridge, supply length | **300 mm** (450 in concrete) | Dreadnought, Russell Roof Tiles |
| half round ridge | 220 wide, 115 high | Dreadnought clay ridge range |
| angle ridge, 90 deg | 255 wide, 185 high | same |
| hogback ridge, 90 deg | 265 wide, 180 high | same |
| third round ridge (a hip fitting) | 240 wide, 85 high | same |
| angular ridge included angle | 75 / 90 / 105 / 115 deg | matched to the roof pitch |
| butt joint between ridge tiles | **10 mm**, pointed | Roof Tile Association |
| `cap.segmental` section | 250 wide, 115 crown, 60 flat, 22 segment | the catalogue rows above |
| `cap.half_round` section | 220 wide, 110 crown, 90 foot | the catalogue rows above |
| both, sheet | 16 mm | a moulded clay unit's wall |
| both, module / nose / inset / rim | 300 / 100 / 22 / 12 mm | 300 is catalogue; the rest are this design |
| `cap.seam` section | 240 wide, 70 crown, 60 foot, 30 flat | a folded capping over a 38 mm seam |
| its sheet, and its rim | 0.7 / 3 mm | ordinary steel coil, as `gutters.py` uses |
| its crown against its foot | 70 > 60 x tan(45 deg) | a crown under that sits below the arris |
| barrel sampling | 12 segments per half turn | chord error below the material gauge |
| dome sampling | 6 stations over one nose | the silhouette reads as moulded at that |
| Uniclass, clay ridge fitting | `Pr_35_90_93_13` | NBS Uniclass Pr table |
| Uniclass, clay hip fitting | `Pr_35_90_93_12` | NBS Uniclass Pr table |

Use catalogue dimensions for ridge fittings.

`nose`, `inset` and `rim` are **not** catalogued and cannot be - they describe
how a piece is drawn so one mesh can repeat and still finish at an eave, which
is a modelling problem rather than a product one.

The two Uniclass codes are recorded rather than written: classifying anything
needs `ifcopenshell.api.classification`, which nothing in this skill has
exercised, and `references/trims.md` already parks the same step behind the
same runtime probe.
