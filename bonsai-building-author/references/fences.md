# Fences and matching gates

Use the public helpers for a straight residential boundary, a driveway gate,
and the smaller pedestrian gate (also called a **wicket**, or **furtka** in
Polish):

```python
from building_author import (
    driveway_gate,
    fence,
    gate_fence_connections,
    pedestrian_gate,
)
from building_author.materials import polyester_coated_steel

polyester_coated_steel(model, "fence.steel")

WICKET = ((5.08, 0.0), (6.065, 0.0))
wicket_left, _ = gate_fence_connections(
    WICKET, height=1.63, profile="fence.welded-mesh", leaves=1
)
fence(model, "boundary.mesh", storey="ground",
      path=((0.0, wicket_left[1]), wicket_left), height=1.63,
      profile="fence.welded-mesh", material="fence.steel",
      end_post=False)
pedestrian_gate(model, "boundary.wicket", storey="ground",
                path=WICKET, height=1.63,
                profile="fence.welded-mesh", material="fence.steel")
driveway_gate(model, "boundary.driveway", storey="ground",
              path=((7.0, 0.0), (10.010, 0.0)), height=1.63,
              profile="fence.welded-mesh", material="fence.steel")
```

Fence `path` endpoints are post centres. Gate `path` is intentionally
different: it spans the **clear passage between the inner post faces**. The
gate procedure derives its support-post centres and total installed width from
the selected product family. `base_offset` raises or lowers the entire
assembly from the storey elevation.

## The two product families

| `profile=` | verified source data used by the procedure | supported heights |
| --- | --- | --- |
| `"fence.welded-mesh"` | [Betafence Nylofor 2D](https://www.betafence.com/en/nylofor-2d) 2500 mm panels, 200 x 50 mm mesh, twin 6 mm horizontal wires, and 5 mm vertical wires; [D-Lox](https://www.betafence.com/en/d-lox) 60 x 40 mm rectangular posts, front-mounted panels, and 2520 mm normal post centres | fence: 0.63, 0.83, 1.03, 1.23, 1.43, 1.63, 1.83, 2.03, 2.43 m; gate: union of the two official series described below |
| `"fence.horizontal-slat"` | [Dlimity Horizon 020](https://www.dlimity.net/en-gb/horizon-aluminio-020) 100 x 30 mm aluminium slats, 20 mm clear gaps, and 80 x 50 mm posts; the [current technical sheet](https://www.dlimity.net/descargas) governs with at most 1800 mm between aluminium post axes | fence: 0.12 through 1.92 m in 0.12 m increments; gate: 1.20 through 2.16 m in 0.12 m increments |

The welded-mesh procedure models the D-Lox installation accurately enough to
preserve its distinguishing construction: the 2500 mm panel sits on the front
of 60 x 40 mm posts whose normal centres are 2520 mm apart. A cut final panel
is allowed. If a run is only a few millimetres longer than a whole number of
modules, the bays are redistributed rather than producing a negative or
near-zero final panel.

Horizon uses the largest practical bays no wider than 1.8 m. The live
marketing page says 2.0 m, but the current downloadable technical sheet says
1.8 m for aluminium (and 1.58 m for PVC), so the stricter technical value
governs. Only catalogue
heights are accepted, so an arbitrary height cannot silently leave a partial
slat at the top.

Both procedures use closed box solids. Nylofor's physically round wires are
square-section approximations; caps, clips, fasteners, foundations, and gate
hardware are omitted. These are presentation-grade product procedures, not
fabrication or structural designs.

The APIs interpret `height` as one overall visual/IFC envelope, consistently
with the other railing profiles. Installation documents additionally call for
20-50 mm panel ground clearance and distinguish a Robusta wing height from
installed post height. Foundations and those allowances are not added above
the declared envelope; this is an explicit presentation simplification.

## Matching driveway and pedestrian gates

`driveway_gate()` creates a closed two-leaf swing gate.
`pedestrian_gate()` creates a closed one-leaf swing gate and accepts
`operation_type="SINGLE_SWING_LEFT"` or `"SINGLE_SWING_RIGHT"`.
`direction_sense` reverses the local frame without moving the assembly out of
its declared passage.

The welded-mesh gates use the published
[Robusta-Nylofor gate family](https://www.betafence.com/en/robusta-nylofor-gates):

| helper | clear passage accepted | support posts | resulting post centres / total width at the 1.63 m example height |
| --- | --- | --- | --- |
| `pedestrian_gate()` | 0.985 m | 80 x 80 mm | 1.065 / 1.145 m |
| `driveway_gate()` | 3.010 or 4.090 m | published 80 or 100 mm square section, selected by size/height | 3.090 / 3.170 m for the 3.010 m passage at 1.63 m high |

Betafence's current sources conflict on standard F/2D gate heights. The live
F/2D/2DS table publishes 1.03, 1.23, 1.43, 1.63, 1.83, 2.03, and 2.43 m;
its linked 2025 flyer labels a second F/2D/2D Super table but publishes 1.03,
1.23, 1.53, 1.73, 2.03, and 2.43 m. The helper accepts the union and records
the conflict here. Width data agrees: a 3.010 m clear gate uses 80 mm posts
and is 3.170 m overall through 2.03 m, changing to 100 mm posts and 3.210 m
overall only at 2.43 m.

Dlimity publishes matching made-to-measure
[pedestrian gates](https://www.dlimity.net/en-gb/puertas-peatonales) and
[double-swing driveway gates](https://dlimity.net/en-gb/puertas-doble-batiente)
for Horizon 020. Their published slat, gap, post, height, and 20 mm ground
clearance data are retained where they describe the fence. Dlimity does not
publish gate post or leaf-frame cross-sections; the visual procedure borrows
the matching fence's verified 80 x 50 mm post and the Robusta family's
documented 60 x 40 mm frame as explicit representative envelopes, not as
Dlimity fabrication data. Dlimity says gates are made to measure but publishes
no gate-width maximum on these pages; the helper therefore enforces only the
minimum needed by its visual frame. Confirm structural span and hardware with
the supplier for a real order.

Gates are emitted closed. IFC operation metadata records how they open, but a
plain GLB export is static; animating leaves requires a separate presentation
workflow with per-leaf nodes and rotations.

## Joining fence runs to gate posts

The gate owns both support posts. Use the connection helper rather than
repeating post arithmetic:

```python
left, right = gate_fence_connections(
    gate_path, height=height, profile=profile, leaves=2
)
fence(model, "left", storey="ground", path=(boundary_start, left),
      height=height, profile=profile, material=finish, end_post=False)
fence(model, "right", storey="ground", path=(right, boundary_end),
      height=height, profile=profile, material=finish, start_post=False)
```

This keeps the infill engaged with the support while preventing duplicate,
coincident post shells in IFC and GLB. `scripts/example_build.py` demonstrates
both sides of a pedestrian gate and driveway gate. On Horizon the returned
points are the gate-post centres. On Nylofor the longitudinal coordinate is
still the post centre, while the fence centreline is shifted across the run so
the front face of its shallow 60 x 40 D-Lox post aligns with the deeper
Robusta post; without that offset the front-mounted panel would intersect it.
Draw the adjacent runs in the same direction as the gate path so local front
has the same meaning.

Horizon slats enter the solid post proxy by 4 mm at a shared support. That is
the procedure's concealed channel engagement; the channel and fasteners are
not separately modelled at this presentation level. The overlap is therefore
intentional, while duplicate post shells and exposed face clashes are not.

Fence corners are deliberately not automatic in this first implementation.
Two ordinary runs meeting at an endpoint would each own a post; Horizon also
publishes a distinct 65 x 65 mm corner post. Use isolated straight runs or
explicit endpoint suppression only when one known support owns the junction.
Do not claim that two overlapping terminal posts form a resolved corner.

## IFC mapping

The authoritative output remains IFC4:

| declaration | IFC4 result |
| --- | --- |
| `fence(...)` | one `IfcRailing`, `PredefinedType=USERDEFINED`, `ObjectType="Fence"` |
| fence posts / panels | `Post` and `Infill` shape aspects |
| either gate helper | one free-standing `IfcDoor`, `PredefinedType=GATE` |
| gate fixed supports / leaves | `Post`, `Framing`, and `Infill` shape aspects |
| gate `path` width | `IfcDoor.OverallWidth`, representing clear passage |
| pedestrian operation | `SINGLE_SWING_LEFT` or `SINGLE_SWING_RIGHT` |
| driveway operation | `DOUBLE_DOOR_SINGLE_SWING` |

IFC4 has no `FENCE` member in `IfcRailingTypeEnum`, hence the honest
user-defined classification. IFC4.3 adds a native `FENCE` enumerator. A
free-standing gate does not void a wall, so it receives direct spatial
containment and no `IfcOpeningElement`, `IfcRelFillsElement`, or `BBIM_Door`
parametric claim. The [IFC4 `GATE` enumerator](https://standards.buildingsmart.org/IFC/RELEASE/IFC4/ADD2_TC1/HTML/schema/ifcsharedbldgelements/lexical/ifcdoortypeenum.htm)
is expressly available on `IfcDoor`.

## Materials and GLB

Use one matching finish key on every member of a family:

- `polyester_coated_steel()` records the Nylofor/D-Lox galvanized-steel
  substrate and an anthracite polymer surface.
- `anthracite_aluminium()` records the Horizon technical sheet's RAL 7021
  lacquered aluminium and a conservative dark-grey approximation; Dlimity
  does not publish calibrated RGB or roughness values.

Both fallbacks use only core glTF PBR values: linear base colour, scalar
roughness, `metallic=0`, and `alpha=1`. The visible coloured coating is an
opaque dielectric even when the substrate is metal. Fence openness is real
geometry between wires or slats, never alpha masking, so the material survives
IFC reload and ordinary GLB export without transmission extensions, UVs,
procedural nodes, or blend-order artifacts.
Both also request backface culling, so Blender's GLB exporter receives a
deterministic single-sided material for these consistently outward-facing,
closed solids rather than inheriting an old material datablock's state.

Welded mesh is necessarily dense: a visible residential boundary is the
intended scale. Large sites and distant context models should use a future
coarse LOD rather than stretching this 50 mm module across kilometres.
