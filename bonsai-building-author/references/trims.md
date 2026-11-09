# Roof Trims

Declare which trim a roof wears; let the compiler find the edges that wear it.

## Declaration

```python
roof(model, "main-roof", storey="attic",
     boundary=[(0.0, 0.0), (8.0, 0.0), (8.0, 6.0), (0.0, 6.0)],
     angle=40.0, thickness=0.30, overhang=0.4,
     top_material="roof.structure", ceiling_material="ceiling.white",
     side_material="facade.render",
     covering="tile.clay", covering_material="tile.terracotta",
     verge_trim="verge.standard", verge_trim_material="metal.zinc")
roof_edge(model, "main-roof", 1, defines_slope=False)   # gable
roof_edge(model, "main-roof", 3, defines_slope=False)
```

That is the whole declaration. **No edge is named.** Four verge runs follow -
two per gable - and the same line on a roof hipped at both ends grows none.

This is the gutter's mitre-vs-stop-end rule one step further. A gutter still
states its own edge, because a gutter is a choice: an eave may or may not be
drained. A verge is not a choice - it is wherever the roof surface stops on a
rake, which is wherever a gable was already declared. Stating it again would
be restating what `defines_slope=False` has said.

`verge_trim_height`, `verge_trim_thickness` and `verge_trim_upstand` override
the profile's own section per roof.

## What maps to what in IFC

| declaration | IFC |
| --- | --- |
| `verge_trim=` | `IfcCovering` / `USERDEFINED`, `ObjectType="Flashing"` |
| its body | `IfcExtrudedAreaSolid` over an `IfcRectangleProfileDef` |
| its relation to the roof | `IfcRelCoversBldgElements`, shared with the tile covering |
| `verge_trim_material=` | `IfcRelAssociatesMaterial` |

No IFC version has a value for a flashing or a verge trim. The buildingSMART
thread asking for one died unresolved in 2019, so this is `USERDEFINED` with
`ObjectType` saying what it is - the same choice a gutter's stop-end makes
against `IfcPipeFittingTypeEnum` and a sill makes against
`IfcBuildingElementPart`.

A classification reference would say it properly - Uniclass `Pr_25_57_29` -
and is the honest next step. It is **not** written yet: it needs
`ifcopenshell.api.classification`, which nothing in this skill has exercised,
and an unverified API call in a template surfaces as a failure inside Blender
rather than at compile time. Add it behind a runtime probe, not on faith.

One `IfcRelCoversBldgElements` names every covering on the roof - the tile
field and every verge trim together. `RelatedCoverings` is a set in the schema
for exactly this, and a consumer asking what covers the roof should get one
answer rather than one relationship per trim.

The trim body is authored in the **IFC phase**. Unlike the tile field, it is
not replaced by a presentation mesh. A non-applied presentation modifier may
move its exposed outer face 1 mm outward where it competes with a coplanar
competitor surface - a wall face, or the roof body and covering it is seated
against. The inner face stays seated, and touching rake pieces share the
same outer-plane adjustment so their apex remains closed. IFC dimensions,
placements, and original mesh coordinates remain unchanged; Blender and the
evaluated GLB carry only the rendering clearance.

## Which edges get what

`trims.edge_kind()` is the whole rule, and it is a function of the solid
rather than of the declaration:

| adjacent faces | edge | trim |
| --- | --- | --- |
| two upward, convex, level | ridge | cap - see [caps.md](caps.md) |
| two upward, convex, raking | hip | cap - see [caps.md](caps.md) |
| two upward, concave | valley | lined - not built |
| one upward, level | eave | gutter |
| one upward, raking | **verge** | **the board below** |
| neither upward | - | nothing |

"Upward" means the face normal tips above horizontal, so a gable's vertical
plane and a rafter cut are both excluded and a verge falls out as *an edge of
a roof face whose neighbour is not roof surface, that is not level*.

`roof_edge(defines_slope=False)` produces the gable edges used by this rule.

### Convexity is the local fold at the shared edge

`edge_kind()` measures `(n_a x n_b) . edge_a`, with unit outward normals and
the shared edge directed along face A's outward winding. Positive means a
convex ridge or hip; negative means a valley. A coplanar subdivision carries
no trim.

`edge_kind_from_bmesh()` obtains that direction from face A's loop. It never
uses the edge's arbitrary vertex storage order. Exchanging the two faces
reverses both the cross product and the wound direction, so the classification
stays unchanged.

Whole-face centres are unsuitable here: a concave T-roof face can extend
across a neighbouring face's plane, making its centre report the opposite of
the local fold. Tests exercise both valleys of that roof, face and edge
storage permutations, and translated, rotated and mirrored roofs.

## The board, and why the extrusion is oblique

A verge trim is a board standing on edge along the rake: its outer face flush
with the roof's own gable plane, its top standing proud of the covering as a
raised lip, the rest of it lapping down over the roof's edge. That is what
`obróbka blacharska` looks like on a tiled gable, and what the reference
photograph shows.

So the section is an upright rectangle, and three things follow:

**It is an `IfcRectangleProfileDef`.** `XDim` and `YDim` are readable numbers
a consumer can query, where an arbitrary closed profile would be a coordinate
list to bound-box.

**Its plane is vertical.** One axis is world up, the other the horizontal
across the run. `verge_runs()` builds that frame as `(across, up, along)`,
right-handed by construction, where `across` points inboard and `up` is world
vertical **always**, whatever the rake does.

**The extrusion is oblique.** `ExtrudedDirection` is the rake, skew to that
vertical plane rather than normal to it. This is deliberate and is the whole
mechanism: an extrusion is a pure translation sweep, so every edge of the
profile stays parallel to itself for the length of the run. The board leans
with the rake while its vertical edges stay truly vertical.

Sweeping a section *perpendicular* to the rake instead - which is what a
`IfcFixedReferenceSweptAreaSolid` does, and what this module did first -
rotates the board about its own run and stands its edges normal to the roof
plane. It is visibly wrong against any gable, and it is wrong in a way that
looks like a lighting artefact rather than a modelling error.

### The section frame

```
across   inboard from the gable plane, so the outer face is at zero
up       world vertical, with zero on the roof's own arris
```

`upstand` is how far the top sits above that arris. `VergeProfile.centre()`
turns the three dimensions into the 2D position `IfcRectangleProfileDef`
carries, in pure Python, so the arithmetic is tested without Blender.

The section's zero sits on the arris, so the board stays flush with the roof edge.

### `upstand` is the one thing a trim asks the covering

Upstand controls the height of the lip above the arris.

It is derived, in `roof_payload`, as the covering's own envelope plus
`COVER_LIP`. A stated `verge_trim_upstand` still wins, and a roof carrying no
covering falls back to the profile's own.

The catalogue provides the board dimensions. The covering envelope
determines the installed lip height.

`COVER_LIP` is 40 mm and is **not a tolerance**. `CLEARANCE` and `SILL_RISE`
exist to stop two faces landing on one plane; this has to read as a lip from
the ground. A covering with more relief than a clay tile raises the trim by
exactly its own difference, without anyone restating it.

`resolved()` refuses an upstand at or beyond the height, which would put the
whole board above the arris with nothing lapping the edge. The kernel builds
that happily and nobody notices until they look at it.

### The placement is built column by column

`placement_matrix()` only turns a run in plan, which is all a level gutter
needs. A verge rakes and its frame's Y must be world up, so the template
writes the four columns directly. `caps.py` writes the same four columns,
with a bisector where this has the world-up constant.

The origin is the **lower** end of the arris, so `Depth` runs positive up the
rake. Orienting off the edge's own verts instead - which this did first -
puts the board on the outboard side of about half the verges on any roof,
because a bmesh edge has no direction of its own. `across` points into the roof
face using its local inward direction: the face normal crossed with the
face-wound edge direction.

## What is deliberately not built

- **Step flashing.** Genuinely modular - discrete pieces let into successive
  mortar joints, 5 x 7 in with a 2 in lap and a 4 in minimum on each leg -
  and it needs a wall reference, which a roof does not have. Both reasons
  point the same way.
- **Apron flashing**, at a head abutment. Continuous, so a rectangle would
  nearly do - but it still needs the wall. A roof has never heard of walls,
  and deriving an abutment by proximity is the guess dressed as a default
  that `standoff` and `corner_reach` both exist to refuse. It must be
  declared with both references, and the compiler is the only thing that sees
  both.
- **Valleys.** `edge_kind` names them, and nothing consumes that yet. A lined
  valley is not additive: the trough sits *under* the covering, so the tiles
  must be cut back from the centre line, and `crop_to_face()` currently runs
  them flush to the arris. Scope it as a change to the crop, not as another
  profile.
- **Laps.** A run is one length. Real trim comes in 2 m pieces lapped
  100-150 mm, so a 4.4 m rake is really three - the same call `gutters.py`
  makes for unions and expansion joints. Those figures are in the table
  below rather than in `trims.py`: nothing computes with them, and a
  constant nothing reads is a fact pretending to be code.

## The apex closes itself

Two verge boards meet at a gable's ridge end and need no mitre, no clip and
no closure piece. That is a consequence of the vertical-edge design rather
than luck, and it is worth stating because the obvious expectation - that
this needs the gutter's corner-window trick - is wrong:

- Both rakes of one gable lie in the **same** vertical plane, because the
  gable end *is* that plane. So both boards share an outer face and an
  `across`.
- An oblique extrusion's end cap is parallel to its own profile plane, so
  each board terminates on a plane of constant `along` - here, the vertical
  plane through the ridge end.
- Both arrises meet at that point, and both boards carry the same `upstand`
  and `height`, so their two end sections are identical.

Identical sections on a coincident plane butt flush. In the example the two
west-gable runs start at y = 6.4 and y = -0.4, each travelling 3.4 m in plan,
and both terminate at y = 3.0.

This is the payoff for sweeping a vertical section obliquely instead of
sweeping a section perpendicular to each rake. Perpendicular sections would
arrive at the apex tilted toward each other by twice the pitch and would
genuinely need mitreing.

## Vocabulary

In `roof_windows.py`, the flashing margin is the distance the skylight
frame extends over the roof covering. A verge trim is a separate element
whose IFC `ObjectType` is `Flashing`.

## Reference values

| quantity | value | source |
| --- | --- | --- |
| `verge.standard` section | **170 x 80 mm** | Pokrycia.pl, `wiatrownica do blachodachówki` |
| supply length | **2 m**, custom to 6 m | Pokrycia.pl |
| made-to-measure ranges | A 100-300, B 50-200, C 30-100 mm; L to 1950 mm | Blachara |
| sheet gauge | 0.50 / 0.75 mm steel, 0.70 mm aluminium | CDD Polska, Paneltech |
| `verge.deep` section | 250 x 120 mm | near the top of the made-to-measure range |
| `COVER_LIP` | 40 mm | how far the board's top reads proud of the covering |
| `upstand`, on `tile.clay` | 129 mm | derived: the tile's 89 mm envelope plus the lip |
| end lap | 100-150 mm | Cladco |
| step flashing piece | 5 x 7 in, 2 in lap, 4 in min leg | InterNACHI, Engineer Fix |

`height` and `thickness` are the catalogued pair - the face down the gable by
the leg in over the covering. `upstand` is not catalogued and cannot be: it
is where the trim is fixed rather than what it is, so it is derived from the
covering, per the section above.

The board is **solid**. A real `wiatrownica` is folded from 0.5-0.75 mm coil
over a timber barge, and the fold, the drip and the timber are one rectangle
here. A future profile that models the fold should start from the
made-to-measure A/B/C ranges above.
