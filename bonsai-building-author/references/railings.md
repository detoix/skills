# Railings

Declare a railing from its straight reference line and a named design, the
way a roof window is declared from its opening and a named profile - not
from raw dimensions a script has to already know how to set safely.

## Declaration

```python
railing(model, "balcony.rail.outer", storey="attic",
        path=((9.2, 1.5), (9.2, 4.5)), height=1.0,
        profile="guardrail.steel",
        post_material="frame.metal", rail_material="frame.metal",
        infill_material="frame.metal")
```

`path` is a reference line exactly as a wall's `axis` is: a straight run, not
a face. A guarded perimeter with a corner is declared as more than one
`railing()`, the same way a wall with a corner is more than one `wall()`.

## What maps to what in IFC

| declaration | IFC |
| --- | --- |
| `railing(...)` | `IfcRailing` |
| `predefined_type=` | `IfcRailingTypeEnum` - IFC4's set: `BALUSTRADE`, `GUARDRAIL`, `HANDRAIL`, `USERDEFINED`, `NOTDEFINED` (`FENCE` is IFC4.3 only) |
| `profile=` | which of `railings.PROFILES` builds the body |
| `path=` | the run the profile is placed along |
| `height=` | `Pset_RailingCommon.Height`, and the guard's own top elevation |
| the profile's own parts | one `IfcShapeAspect` per part it names |
| `post_material=`, `rail_material=`, `infill_material=`, `shoe_material=`, `glazing_material=` | a material constituent per shape aspect the chosen profile actually has |

## A profile is a real design, not five tunable floats

`profile` names one of `railings.PROFILES`, the same way `roof_window()`
names one of `roof_windows.PROFILES`:

| `profile=` | parts (shape aspects) | what it is |
| --- | --- | --- |
| `"guardrail.steel"` (default) | `Post`, `Infill`, `Rail` | steel tube posts, horizontal cable-proxy infill, a tube cap rail |
| `"guardrail.timber"` | `Post`, `Infill`, `Rail` | 4x4 posts, horizontal slat infill, a flat 2x6 cap rail |
| `"balustrade.glass"` | `Shoe`, `Glazing` | one frameless glass pane in an aluminium base shoe, no posts |
| `"fence.welded-mesh"` | `Post`, `Infill` | flat twin-wire rectangular mesh fence; use through `fence()` |
| `"fence.horizontal-slat"` | `Post`, `Infill` | mostly opaque horizontal aluminium slat fence; use through `fence()` |

Each profile owns its own proportions - post size and spacing, infill
spacing, rail section - fixed inside
[`railings.py`](../scripts/building_author/railings.py), not exposed as
arguments here. A steel guardrail and a timber guardrail are different
assemblies, not the same posts-and-rail box in a different material; letting
a caller retune one into a copy of the other with five floats is exactly the
implicitness a named profile avoids. `railings.py`'s own module docstring
cites where every dimension came from - IBC 1015.4 / IRC R312.1.3's 4-inch
sphere rule for both guardrails' infill spacing, published steel tube and
cable-system post spacing, the IRC's own cap on a 4x4 post's span, and
published frameless-balustrade glazing and base-shoe dimensions - because no
measured asset for a railing ships with this project the way a tile or a
window frame's numbers do.

Only `height` and which run to guard are a script's own decision; nothing
about a guard's safety geometry should be a number a caller has to already
know how to pick correctly.

Boundary fences have their own narrower declaration and product research in
[`fences.md`](fences.md). Do not call their profiles through `railing()`:
`fence()` supplies IFC4's required `USERDEFINED` / `ObjectType="Fence"`
classification and binds its one material to both fence parts. Only fence
profiles accept `start_post=False` or `end_post=False`; use those flags when a
known matching gate post owns the junction, as described there. Driveway and
pedestrian gates are standalone `IfcDoor(GATE)` products, not railings.

## Posts and rail are one product, not several

A guardrail profile's body is built by
[`railings._post_and_rail_guard()`](../scripts/building_author/railings.py):
posts, horizontal infill, and one continuous top rail, in the path's own
local frame - X along the run, Y across it, Z up from the run's own base.
That is placed in the world the same way a roof window's frame is placed on
its roof face: one rotation about Z onto the path's own angle, one
translation to its start point at `base_offset` above the storey.

Every part becomes one `IfcRailing` carrying one shape aspect per part,
exactly the way a window carries `Lining`, `Framing` and `Glazing` - one
product, materials split by role, not a BIM-less second copy holding another
material. A material argument left `None` for a role the chosen profile
does not have is simply unused; passing `shoe_material` to a guardrail
profile has no effect, because no aspect named `Shoe` exists on that body for
it to bind to.

## Posts fit the spacing, they never stretch it

Both guardrail profiles space their posts to a target, not an exact count:
the run's length is rounded to the nearest whole number of bays and a post
always lands at both ends - the same "fit the module, never stretch it" rule
`tiles.centres()` follows rather than spacing posts unevenly to hit an exact
count. Infill bars are spaced the same way, rounded so every gap - against
the deck, against the rail, and between two bars - stays at or under the
cited sphere-rule maximum rather than merely averaging under it.

A post is held `CLEARANCE` (4 mm) short of the rail's own top face, the same
clearance [`roof_windows.py`](../scripts/building_author/roof_windows.py) holds every
shell apart by, so a post's cap face is never exactly coincident with the
rail's underside. The post still runs up into the rail's volume; only its
own top face is short of it.

## Traps

- A railing has no corners to resolve against a neighbouring railing, the
  same trap `slabs.md` documents for slabs: two runs that should meet flush
  have to declare paths that already do, and each run's end posts land
  wherever its own `path` ends, undeflected by anything joining it there.
- None of this is a certified guard. The sphere rule is honoured by
  proportion - every gap is solved to stay at or under the cited maximum -
  not verified against an actual sphere, and no load calculation backs any
  member size a profile builds. A round tube post or cable is also built as
  a square-section box, because this module only builds boxes; see
  `railings.py`'s own module docstring for the complete list of what each
  profile simplifies.
- These profiles are purpose-built procedures, not a reproduction of
  Bonsai's own railing generator (`WALL_MOUNTED_HANDRAIL`'s swept disk, or
  `FRAMELESS_PANEL`'s bmesh operator pipeline). A script-authored railing is
  therefore **not** re-editable through Bonsai's Railing tool the way a
  script-authored roof or slab is through the roof and slab tools - no
  `BBIM_Railing` pset is written, because writing one shaped for a generator
  this railing's body does not actually match would silently regenerate a
  different shape the next time Bonsai's own tool touched it. Only the real,
  generator-independent `Pset_RailingCommon.Height` is written.
- `height` is measured from `base_offset`, not from the storey's own
  elevation directly - the same relationship a slab's `base_offset` has to
  its storey, so a railing standing on a slab whose top sits above or below
  the bare storey elevation still needs `base_offset` set to that slab's own
  top, not left at its default of `0.0`.
