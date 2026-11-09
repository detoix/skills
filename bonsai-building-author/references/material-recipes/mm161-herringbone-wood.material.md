---
schema: building-author/material-recipe/v1
id: material-maker.161.herringbone-wood
title: Wood Planks Floor from Deus Ex Mankind Divided
source_author: Kyrylo
source_license: CC-BY (version not specified by publisher)
source_engine: Material Maker 0.94
tile_size_m: [1.20, 1.20]
working_resolution: 2048
height_scale_m: 0.004
normal_convention: OpenGL tangent space (+Y)
---

# MM161 — herringbone wood

This is the single canonical, renderer-neutral recipe for Material Maker
material 161. It is an agent-readable specification, not a Blender or
Three.js implementation. Translate it into ordinary native material data only
when authoring a target project; do not check a generated renderer copy back
into this library.

## Identity, authority, and licence

After [Wood Planks Floor from Deus Ex Mankind Divided by Kyrylo](https://www.materialmaker.org/material?id=161), licensed CC-BY (version not specified by the publisher); node semantics follow Material Maker 0.94. This recipe fully resolves the graph so a target author does not need Material Maker.

Carry this attribution in every generated `.blend`, Three.js project, GLB
package, or redistributed material:

> “Wood Planks Floor from Deus Ex Mankind Divided” by Kyrylo, sourced from
> Material Maker material 161, licensed CC-BY (version not specified by the
> publisher); translated from the canonical recipe for the target project.

Also record these changes from the published graph:

1. `metallic=1` in the unconnected Material node is overridden to `0`; timber
   is a dielectric.
2. The source has no physical scale. This recipe fixes one tile at `1.20 m`
   square, yielding `300 x 50 mm` boards.
3. The source mortar coefficient `0.008` would yield a `0.8 mm` full joint at
   that scale. The canonical building adaptation uses a visible `2.5 mm`
   joint, hence coefficient `0.025` in the same source formula.
4. Material Maker's format-0 normal is negative-Z and resolution-dependent.
   The canonical output is positive-Z OpenGL tangent space derived from a
   declared `4 mm` physical height range.

All other connected graph values and operations are preserved below.

## Mapping and physical dimensions

Use a stable planar metre mapping. For the terrace, local `+X` is `+u`, local
`+Y` is `+v`, and local `+Z` is the surface normal. `P0` is exactly the
building project's local origin `(0,0,0)` expressed in the same project
coordinate system as `P`; it is not chosen per object. Evaluate

```text
uv = ((dot(P-P0, X_axis) / 1.20),
      (dot(P-P0, Y_axis) / 1.20))
```

The fields below are periodic with period one. Do not normalize coordinates by
an object's bounding box: adjacent coplanar objects must share the same metre
scale and the exact `P0=(0,0,0)` phase. An explicit UV set is acceptable when
it encodes this mapping. Mirrored UV islands are not acceptable because they
reverse the tangent-space normal and grain. Store `mapping_origin_m=(0,0,0)`
in generated material metadata.

| Canonical dimension | Value |
| --- | ---: |
| `tile_size_m` | `(1.20, 1.20)` |
| herringbone lattice | `24 x 24` cells per tile |
| board length | `0.300 m` (`6/24` tile) |
| board width | `0.050 m` (`1/24` tile) |
| full visible joint | `0.0025 m` |
| per-edge mortar inset | `0.00125 m` |
| normalized mortar coefficient | `0.025` |
| normalized bevel coefficient | `0.001` (source's minimum for `bevel=0`) |
| physical height range | `0.004 m` |
| source/working resolution | `2048 x 2048` (`size=11`) |
| preferred PBR bake | `2048 x 2048`; minimum `1024 x 1024` |

At `2048²`, the canonical joint is about `4.27` texels wide. Preserve physical
dimensions if a project requests another bake resolution.

## Exact Material Maker 0.94 primitives used here

Use the basic `fract`, positive `mod`, `floor`, `clamp`, `mix`, `step`,
`smoothstep`, sRGB conversion, and final `MaterialSample` conventions from
`primitives.md`. The following functions are version-specific and normative
for this recipe; do not substitute a renderer's generic Noise Texture or a
gamma-style levels control.

All trigonometric arguments are radians. Evaluate procedural scalar math with
IEEE-754 float semantics. Small last-bit differences in the cosine hash across
GPU vendors are acceptable; changing its constants or topology is not.

```text
mm094_rand(p):
    return fract(cos(dot(p, (13.9898, 8.141))) * 43758.5453)

mm094_rand2(p):
    return fract(cos((dot(p, (13.9898, 8.141)),
                      dot(p, ( 3.4562,17.3980)))) * 43758.5453)

mm094_value_fbm(uv, cells, octaves, persistence, seed):
    seed_offset = mm094_rand2((float(seed), 1.0-float(seed)))
    size = cells
    value_sum = 0
    weight_sum = 0
    weight = 1
    repeat octaves times:
        p = uv * size
        cell = floor(p)
        f = smoothstep(0, 1, fract(p))
        h00 = mm094_rand(seed_offset + mod_pos(cell+(0,0), size))
        h10 = mm094_rand(seed_offset + mod_pos(cell+(1,0), size))
        h01 = mm094_rand(seed_offset + mod_pos(cell+(0,1), size))
        h11 = mm094_rand(seed_offset + mod_pos(cell+(1,1), size))
        octave = mix(mix(h00,h10,f.x), mix(h01,h11,f.x), f.y)
        value_sum += weight * octave
        weight_sum += weight
        size *= 2
        weight *= persistence
    return value_sum / weight_sum
```

The seed does **not** increment between octaves. The source called this node
“Perlin”, but it is interpolated value-noise FBM.

Material Maker 0.94 levels are piecewise linear around a midpoint that maps to
`0.5`; they are not a gamma curve:

```text
mm094_levels(x, in_min, in_mid, in_max, out_min, out_max):
    t = clamp((x-in_min)/(in_max-in_min), 0, 1)
    m = (in_mid-in_min)/(in_max-in_min)
    if t < m: y = 0.5*t/m
    else:     y = 0.5*(1 + (t-m)/(1-m))
    return out_min + y*(out_max-out_min)

mm094_linear_map(x, in_min, in_max, out_min, out_max):
    return out_min + (x-in_min)*(out_max-out_min)/(in_max-in_min)
    # intentionally not clamped

mm094_normal(foreground, background, amount):
    return amount*foreground + (1-amount)*background

mm094_multiply(foreground, background, amount=1):
    return amount*foreground*background + (1-amount)*background

mm094_screen(foreground, background, amount=1):
    return amount*(1-(1-foreground)*(1-background))
           + (1-amount)*background
```

The two source Transform variants sample with this inverse-coordinate
transform:

```text
mm094_transform_uv(uv, translate, rotate_degrees, scale):
    q = uv - translate - (0.5,0.5)
    a = radians(rotate_degrees)
    r = (cos(a)*q.x + sin(a)*q.y,
        -sin(a)*q.x + cos(a)*q.y)
    return r/scale + (0.5,0.5)
```

The nested Warp2 transforms apply `fract` to that result (`repeat=true`). The
top `transform2` has `mode=2`, meaning no clamp and no wrap. With its exact
`90°` parameters it samples its input at `(v, 1-u)`. The input noise is already
periodic, so the unbounded coordinates remain seamless.

## Exact herringbone field

This is Material Maker 0.94's `bricks_hb` and `brick` math with the one declared
joint-width adaptation. `row_offset=0.5` and `corner=0.3` are present in the
source node but do not participate in its herringbone mask or direction output.

```text
herringbone(uv):
    count = (6,6)
    repeat = 2
    period_cells = count.x + count.y               # 12
    c = period_cells * repeat                      # 24
    corner = floor(uv*c)
    cdiff = mod_pos(corner.x-corner.y, period_cells)

    if cdiff < count.x:
        bmin = (corner-(cdiff,0))/c
        bmax = (corner-(cdiff,0)+(count.x,1))/c
    else:
        back = period_cells-cdiff-1
        bmin = (corner-(0,back))/c
        bmax = (corner-(0,back)+(1,count.y))/c

    board_size = bmax-bmin
    min_size = min(board_size.x, board_size.y)      # 1/24
    centre = 0.5*(bmin+bmax)

    mortar_uv = 0.025 * min_size                   # 1.25 mm per edge
    bevel_uv = max(0.001, 0.0) * min_size          # source bevel=0
    round_uv = 0.0
    d = abs(uv-centre) - 0.5*board_size + (round_uv+mortar_uv)
    signed_distance = length(max(d,(0,0)))
                      + min(max(d.x,d.y),0) - round_uv
    board_mask = clamp(-signed_distance/bevel_uv, 0, 1)

    direction = 0.5*(sign(board_size.x-board_size.y)+1)
    # direction=1 for a horizontal board, 0 for a vertical board
    return board_mask, direction
```

The mask is `1` on a board and `0` in a joint. The source coefficient `0.008`
must remain in the provenance record, but generated targets use `0.025` so the
same `2.5 mm` physical joint appears in Blender, Three.js, and GLB.

## Pinned seeds

Material Maker 0.94 derived unlocked node seeds from integer-truncated graph
positions and parent seeds. The resolved values are pinned here so a target
does not need to emulate editor positions:

| Field | Source derivation | Resolved seed |
| --- | --- | ---: |
| main wood value FBM | local `-31401` + Wood texture graph `-32754` | `-64155` |
| Warp2 value FBM | local `55134` + locked Warp2 graph `-14471` | `40663` |

The Bricks seed is irrelevant: this graph uses only its seed-free mask and
direction outputs.

## Canonical DAG

Palette literals are sRGB. Convert both endpoints to linear before the final
mix. Their precomputed linear values are included as a cross-check:

```text
LIGHT_SRGB = (0.530000, 0.506150, 0.434600)
DARK_SRGB  = (0.070000, 0.069475, 0.066500)
LIGHT_LINEAR ~= (0.242866814, 0.219777697, 0.158421266)
DARK_LINEAR  ~= (0.005981060, 0.005920948, 0.005586981)
```

Evaluate this graph for every `uv`:

```text
# Nested graph “Warp2”. Both translation maps use the same scalar field.
NW(p) = mm094_value_fbm(p, (23,3), 3, 0.4, 40663)

n0 = NW(uv)
q1 = mm094_transform_uv(
         uv,
         ( 0.275*(2*n0-1), -0.470*(2*n0-1) ),
         0, (1,1))
w1 = NW(fract(q1))
q2 = mm094_transform_uv(
         uv,
         ( 0.275*(2*w1-1), -0.470*(2*w1-1) ),
         0, (1,1))
w2 = NW(fract(q2))

# Graph “Wood texture”.
MAIN = mm094_value_fbm(uv, (26,4), 10, 0.75, -64155)
WARP_TONED = mm094_levels(w2, 0, 0.284091, 1,
                               0.346591, 1)
GRAIN = mm094_normal(MAIN, WARP_TONED, 0.61)

# Rotate grain exactly 90 degrees and select it by board orientation.
B, D = herringbone(uv)
GRAIN_90 = GRAIN((uv.y, 1-uv.x))
horizontal = mm094_multiply(D, GRAIN_90, 1)
vertical   = mm094_multiply(1-D, GRAIN, 1)
ORIENTED_GRAIN = mm094_screen(horizontal, vertical, 1)

# Base colour. Source blend_4 and blend_6.
colour_weight = mm094_multiply(B, ORIENTED_GRAIN, 1)
base_color = mm094_normal(LIGHT_LINEAR, DARK_LINEAR, colour_weight)

# Roughness. Source blend_7 then levels.
rough_input = mm094_screen(ORIENTED_GRAIN, 1-B, 1)
roughness = clamp(mm094_levels(rough_input, 0, 0.58125, 1, 0, 1), 0, 1)

# Source bump branch, then canonical positive-Z physical height.
grain_height = mm094_linear_map(ORIENTED_GRAIN,
                                0.15, 0.95, 0.46, 0.51)
source_negative_z_height = mm094_screen(grain_height, 1-B, 1)
height = clamp(1-source_negative_z_height, 0, 1)

metallic = 0
ao = 1
alpha = 1
```

`GRAIN` is a function, not a cached scalar: `GRAIN_90` evaluates the entire
wood-texture subgraph at the transformed coordinate. The source's asymmetric
FBM cells (`26 x 4`) make streaks elongated along a vertical board; the exact
90° selection makes them follow a horizontal board as well.

### Height and normal

`height=0` is the bottom of a joint and `height=1` is the maximum possible
surface elevation. The physical offset is `height * 0.004 m`. Derive the live
or baked normal from this field in physical metres:

```text
e = 1 / working_resolution                     # 1/2048 by default
du = (height(uv+(e,0))-height(uv-(e,0))) * 0.004 / (2*e*1.20)
dv = (height(uv+(0,e))-height(uv-(0,e))) * 0.004 / (2*e*1.20)
normal_xyz = normalize((-du,-dv,1))             # OpenGL, +Y, positive Z
normal_rgb = 0.5*normal_xyz + 0.5               # only when baking RGB
```

Material Maker's connected source node used a periodic `2048²` buffer,
strength `1`, and format `0`. Its internal Sobel multiplier was
`strength*2048/128 = 16`, with neutral Z pointing negative. That convention is
recorded for provenance only. Do not send it directly to Blender, Three.js, or
glTF, and do not “fix” this recipe by merely flipping the green channel.

The final output is:

```text
MaterialSample {
    base_color: base_color,        # linear RGB
    roughness:  roughness,
    metallic:   0,
    height:     height,
    normal:     normal_xyz or the stated height-to-normal link,
    ao:         1,
    alpha:      1
}
```

Use an ordinary dielectric PBR surface: IOR `1.5`, no transmission, no
clearcoat, no emission, and no displacement unless the target explicitly asks
for it. The normal/bump is always active.

## On-demand target materialization

- **Blender:** create one local material with an ordinary Principled BSDF and
  local native node groups. Unroll the fixed FBM octaves if necessary. A native
  Bump node may consume the canonical physical height. The saved `.blend` must
  render after the authoring script and repository are removed: no linked
  libraries, add-on-only nodes, or external files. If temporary baked maps are
  used, pack them into the `.blend`.
- **Three.js:** generate project-local TSL/GLSL for the same DAG, or evaluate
  the DAG into transient maps and connect them to `MeshStandardMaterial`.
  Treat Base Color as sRGB at the texture boundary and all other maps as
  non-colour. Do not import a parallel material implementation from this
  library.
- **GLB:** bake Base Color, OpenGL Normal, and ORM
  (`R=1`, `G=roughness`, `B=0`) with repeat sampling, real UVs, tangents, and
  triangulated geometry. Embed all images in the GLB. The bake is project
  output, never material-library source.
- **IFC:** retain `timber.decking` and its simplified scalar style. IFC is not
  the visual master.

Store the recipe id, source title, author, source URL, hash, bare `CC-BY`
licence string, attribution text, tile/board/joint dimensions, and the four
declared adaptations in generated material metadata.

## Target-independent acceptance checks

Automated checks:

1. All outputs are finite. `roughness`, `metallic`, `height`, `ao`, and
   `alpha` remain in `[0,1]`; metallic is exactly `0`, AO exactly `1`, and
   alpha exactly `1`.
2. Every output is periodic: samples at `uv`, `uv+(1,0)`, and `uv+(0,1)` agree
   within `1e-4` away from the bevel discontinuity.
3. Horizontal and vertical board bounding boxes are exactly `6/24 x 1/24`
   and `1/24 x 6/24`. Their physical size is `300 x 50 mm`.
4. At horizontal board centre `(5/24, 2.5/24)`, `B=1`, `D=1`. A double-precision
   reference gives `ORIENTED_GRAIN≈0.64324`, `roughness≈0.57402`, and
   `height≈0.50917`; allow `±0.03` for target hash precision.
5. At vertical board centre `(0.5/24, 4/24)`, `B=1`, `D=0`. Reference values
   are `ORIENTED_GRAIN≈0.67971`, `roughness≈0.61757`, and `height≈0.50689`;
   allow `±0.03`.
6. At joint point `(5/24, 2/24)`, `B=0`, Base Color equals `DARK_LINEAR`,
   roughness is `1`, and height is `0`.
7. A `2048²` mask has a full joint width of about `4.27` texels. It must not
   collapse to a one-pixel alias or expand into a grout band.

Visual check on the actual terrace, under a neutral grazing area light:

- the read is charcoal-dark herringbone wood, not tan boards and not metal;
- the chevrons are regular, seamless, and made from 6:1 boards;
- grain is visibly elongated along each board's long axis and rotates exactly
  90° between board orientations;
- joints are narrow, dark, rough, and recessed; plank faces carry restrained
  shallow grain with narrow satin highlights;
- there is no square noise patch, isotropic grain, UV swimming, green-channel
  inversion, external bitmap dependency, or metallic edge tint.

Compare those characteristics with the published preview, not its exact sphere
lighting or exposure. Inspect at both building view and a grazing close-up
before accepting the generated target.

## Primary implementation sources and known uncertainty

The inlined formulas below are Material Maker 0.94 semantics.

Known uncertainty is explicit: the catalog gives no CC-BY version, and the
publisher gives no physical tile size. The `1.20 m` tile, `2.5 mm` joint,
`4 mm` height range, positive-Z normal, and metallic-zero correction are this
library's canonical building adaptations, not claims about the author's
original dimensions. Cosine-hash results can vary slightly with shader float
precision, which is why QA uses topology, physical dimensions, and tolerant
sample values rather than requiring bit-identical pixels.
