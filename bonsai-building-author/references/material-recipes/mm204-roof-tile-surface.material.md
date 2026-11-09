---
schema: building-author/material-recipe/v1
id: material-maker.204.stylized-roof-tiles.surface-v1
title: Stylized Roof Tiles — physical-tile surface adaptation
source_author: ninao
source_license: CC0-1.0
source_engine: Material Maker 0.95
tile_size_m: [1.8, 1.6]
physical_tile_size_m: [0.2928, 0.47]
working_resolution: 2048
height_scale_m: 0
normal_convention: geometric surface normal
---

# MM204 stylized roof-tile surface

This is the single canonical, renderer-neutral recipe for
`material-maker.204.stylized-roof-tiles` (the example material
`tile.terracotta`). It is pseudocode, not a Blender or Three.js
implementation. An agent materializes it on demand as an ordinary native
material in the target project. This file is authoritative for the **surface-only**
adaptation used on the skill's already-modelled physical roof tiles.

Read `primitives.md` first for the common coordinate, colour-management, PBR,
and output conventions. The Material Maker 0.95 operations below are inlined
because similarly named operations in later Material Maker releases, Blender,
or Three.js are not interchangeable.

## Identity and provenance

After [Stylized Roof Tiles by ninao](https://www.materialmaker.org/material?id=204) (CC0); node semantics follow Material Maker 0.95.

## Surface contract and physical mapping

The target geometry is one physical clay tile per mesh instance/cell. Its
measured dimensions and layout are already canonical elsewhere in this skill:

```text
tile_mesh_m       = (0.2928 across_eave, 0.4700 up_slope, 0.0400 thick)
layout_module_m   = (0.3000 across_eave, 0.4000 course_exposure)
course_stagger    = 0.5 tile on odd rows
tile_tilt         = 6 degrees (geometry, never shader displacement)
source_atlas      = (6 columns, 4 rows)
source_period_m   = layout_module_m * source_atlas = (1.8, 1.6)
reference_raster  = 2048 x 2048       # Material node size=11
```

`u` runs left-to-right across a tile and `v` runs tail/eave-to-head/ridge.
Let `cell=(column,row)` be stable integer layout coordinates. For the top face,
the canonical roof-plane coordinate is:

```text
tile_center_m.x = 0.3000 * (cell.x + 0.5*mod_pos(cell.y, 2))
tile_center_m.y = 0.4000 * cell.y
roof_xy_m       = tile_center_m
                + ((u-0.5)*0.2928, (v-0.5)*0.4700)
q               = wrap(roof_xy_m / (1.8, 1.6))
```

On tile edges, use the same roof-plane projection for `q`; do not restart the
pattern on each face. A target may derive `cell` from the roof-covering layout
or store it as a face/vertex attribute. Object name, object origin, random
session state, and bounding-box normalization are forbidden inputs. The same
roof and recipe seed must therefore reproduce the same result in Blender,
Three.js, and a GLB bake.

## Exact source-to-surface adaptation

Material Maker's source builds a second 6-by-4 field of complete rounded tile
silhouettes. The building author already builds and overlaps real tile meshes.
Keeping both would draw false scalloped outlines across the physical tiles.
The following split is normative.

### Retained

- Albedo `graph_4`: its cubic clay ramp, per-instance colour modulation,
  colour value noise, folded value FBM, Voronoi weathering masks, blend modes,
  and final HSV adjustment.
- Roughness `graph_5`: its value-noise fields, Screen blend, and Levels map.
- Only the **random instance-colour output** of Height/`tiler`, evaluated once
  for each physical `cell`. It is calculated before the source tiler's pose
  transforms, so retaining it does not retain fake geometry.
- Material constants: metallic `0`, opaque alpha, no emission, no SSS.

### Removed or analytically collapsed

- Height/`Telha`: `sdbox(w=.281818,h=.269091,cx=0,cy=.127273)`,
  `sdcircle(r=.29,cx=0,cy=-.07)`, Smooth Boolean Union (`op=0,k=.11`),
  `sdshow(bevel=.05)`, the `-90` degree linear black-to-white gradient, its
  Multiply blend (`amount=.91`), the horizontal black/white/black gradient
  (`0:black, .506645:white, 1:black`), its Multiply blend (`amount=1`), and
  the final `180` degree rotation.
- Height/`tiler` pattern output and pose/value controls:
  `tx=6`, `ty=4`, `overlap=2`, `scale=(1,1)`, `fixed_offset=.5`,
  random offset `.24`, random rotation `5.8` degrees, random scale `.09`, and
  random value `.21`. The `6x4` period, half-course stagger, and instance seed
  survive only in the physical mapping and instance-colour formula.
- Height Levels (`in_min=.472441`, `in_mid=.700787`, `in_max=.937008`,
  `out_min=0`, `out_max=1`) and all macro height output.
- Top-level `normal_map(size=11,strength=.44,format=Default,buffer=true)`,
  `occlusion2(size=11,radius=134,strength=1.6,quality=1)`, inverted depth,
  and the pass-through `graph_2`. They describe the omitted silhouette, not a
  clay microfinish. Their canonical surface replacements are neutral normal,
  AO `1`, and height `0`.
- Albedo's disconnected `noise(size=4,density=.5)` node.
- Albedo's height-only base shaping collapses with neutral height `h=.5`:
  Smooth Curvature (`size=11,quality=16,strength=2,radius=2,buffer=true`)
  returns `.5`; Tones Range (`value=.12,width=.47,contrast=0,invert=false`)
  returns `0`; consequently its brown foreground
  `(0.402344,0.184277,0.053436)` has zero opacity and the base is exactly the
  cubic clay ramp at `.5`.
- Roughness's `invert(height)` and Overlay collapse exactly: with `height=.5`,
  the Overlay foreground is `.5`, which returns the background value noise.

This is not permission to invent a different tile shape. If a target has no
physical tiles, it must build them from the building skill's tile procedure;
it must not restore the source graph's texture-space silhouettes.

## Material Maker 0.95 scalar and vector semantics

All palette literals below are sRGB and are converted to linear before ramp or
blend math, as required by `primitives.md`. RNG/noise outputs and masks are
linear non-colour values. Operations are component-wise where applicable.

### Hashes and effective seeds

Material Maker 0.95 used these hashes (`mod_pos` and `fract` are defined in
`primitives.md`):

```text
mm95_rand(p):
  return fract(cos(mod_pos(dot(p,(13.9898,8.141)), 3.14)) * 43758.5453)

mm95_rand2(p):
  d = (dot(p,(13.9898,8.141)), dot(p,(3.4562,17.398)))
  return fract(cos(mod_pos(d,(3.14,3.14))) * 43758.5453)

mm95_rand3(p):
  d = (dot(p,(13.9898,8.141)), dot(p,(3.4562,17.398)),
       dot(p,(13.254,5.867)))
  return fract(cos(mod_pos(d,(3.14,3.14,3.14))) * 43758.5453)
```

Unlocked node seeds in 0.95 were derived with signed integer arithmetic:

```text
local_seed(x,y) = truncating_remainder(
                    (trunc(x)*0x1f1f1f1f) XOR trunc(y), 65536)
effective_seed  = local_seed + parent_graph_seed
```

The effective values for this graph are fixed here; do not recompute them from
rounded layout positions:

| use | seed | origin |
| --- | ---: | --- |
| tile instance colour | `-16587` | locked Height/`tiler` |
| albedo colour value noise | `-32491` | locked `perlin_color` |
| albedo folded value FBM | `5552` | position `(607.222961,49.977104)` + graph seed `-46336` |
| albedo Voronoi | `-38868` | position `(585.302856,251.909134)` + graph seed `-46336` |
| roughness value noise | `-71473` | locked `perlin` |
| roughness value FBM | `-29913` | position `(-407.756256,-280.363342)` + graph seed `-61496` |

### Value noise used by legacy `perlin` nodes

Despite the node name, this is multi-octave **value noise**, not gradient
Perlin noise:

```text
mm95_value_octaves(uv, size, octaves, persistence, seed):
  seed2 = mm95_rand2((seed, 1-seed))
  sum = 0; weight = 1; weights = 0
  repeat octaves times:
    xy = floor(uv*size)
    f00 = mm95_rand(seed2 + mod_pos(xy,                         size))
    f10 = mm95_rand(seed2 + mod_pos(xy+(1,0),                   size))
    f01 = mm95_rand(seed2 + mod_pos(xy+(0,1),                   size))
    f11 = mm95_rand(seed2 + mod_pos(xy+(1,1),                   size))
    t = smoothstep((0,0),(1,1),fract(uv*size))
    n = mix(mix(f00,f10,t.x), mix(f01,f11,t.x), t.y)
    sum += weight*n; weights += weight
    size *= 2; weight *= persistence
  return sum/weights

mm95_colour_value_octaves(...) is identical except every corner uses
mm95_rand3 and the accumulator/result are RGB.
```

### Value FBM used by `fbm2(noise=0)`

```text
mm95_fbm_value_cell(coord, size, seed):
  o = floor(coord) + mm95_rand2((seed,1-seed)) + size
  f = fract(coord)
  p00 = mm95_rand(mod_pos(o,                         size))
  p10 = mm95_rand(mod_pos(o+(1,0),                   size))
  p01 = mm95_rand(mod_pos(o+(0,1),                   size))
  p11 = mm95_rand(mod_pos(o+(1,1),                   size))
  t = f*f*(3-2*f)
  return mix(mix(p00,p10,t.x), mix(p01,p11,t.x), t.y)

mm95_fbm_value(uv, size, folds, octaves, persistence, seed):
  sum = 0; weight = 1; weights = 0
  repeat octaves times:
    n = mm95_fbm_value_cell(uv*size, size, seed)
    repeat folds times: n = abs(2*n-1)
    sum += weight*n; weights += weight
    size *= 2; weight *= persistence
  return sum/weights
```

### Voronoi Nodes output

Only output 0 (`Nodes`, distance to the nearest cell centre) is used:

```text
mm95_voronoi_nodes(uv, size, stretch, intensity, randomness, seed):
  x = uv*size
  n = floor(x); f = fract(x)
  seed2 = mm95_rand2((seed,1-seed))
  best_d2 = 8; best_center = (0,0)
  for j=-1..1, i=-1..1:
    g = (i,j)
    o = randomness * mm95_rand2(seed2 + mod_pos(n+g+size, size))
    center = g+o
    d2 = dot((center-f)*stretch, (center-f)*stretch)
    if d2 < best_d2: best_d2=d2; best_center=center
  absolute_center = best_center+n
  return intensity * length((x-absolute_center)*stretch)
```

This recipe calls it with `size=(8,8)`, `stretch=(1,1)`, `intensity=.99`,
`randomness=.85`, `seed=-38868`. The source's second border-distance pass is
not evaluated because no connection consumes it.

### Physical-tile instance colour

This is the 0.95 tiler's pre-transform instance colour for the physical cell's
central candidate. It retains the source variation but none of its fake pose
or silhouette:

```text
mm95_instance_colour(cell):
  atlas = (6,4)
  pos = fract((mod_pos(cell,atlas)+(0.5,0.5))/atlas-(0.5,0.5))
  seed2 = mm95_rand2(pos + (-16587,-16587))
  return mm95_rand3(seed2)
```

Only its green component is connected by the source graph.

### Tones, cubic ramp, and Levels

```text
mm95_tones_step(x, value, width, invert):
  y = clamp((x-value)/max(0.0001,width)+0.5, 0, 1)
  return 1-y if invert else y

mm95_tones_range(x, value, width, contrast, invert):
  s = clamp((x-value)/max(0.0001,width)+0.5, 0, 1)
  y = clamp((min(s,1-s)*2)/(1-contrast), 0, 1)
  return 1-y if invert else y
```

The albedo ramp uses MM 0.95 interpolation mode `3` (Cubic). For its three
ordered linear-light colours `(p0,c0),(p1,c1),(p2,c2)`:

```text
mm95_cubic3(x):
  if x < p0: return c0
  if x < p1:
    d = (x-p0)/(p1-p0)
    b = mix(c0,c1,d)
    c = mix(c1,c2,(x-p1)/(p2-p1))       # intentional extrapolation
    return mix(c,b,1-0.5*d)
  if x < p2:
    d = (x-p1)/(p2-p1)
    a = mix(c0,c1,(x-p0)/(p1-p0))       # intentional extrapolation
    b = mix(c1,c2,d)
    return mix(a,b,0.5+0.5*d)
  return c2
```

The exact ramp stops are:

```text
p0=0       c0=srgb_to_linear((0.056759,0.042191,0.308594))
p1=0.5681  c1=srgb_to_linear((0.863281,0.219193,0.219193))
p2=1       c2=srgb_to_linear((0.906250,0.876243,0.138062))
```

For a scalar channel, MM 0.95 Levels is:

```text
mm95_levels(x, in_min, in_mid, in_max, out_min, out_max):
  t = clamp((x-in_min)/(in_max-in_min), 0, 1)
  m = (in_mid-in_min)/(in_max-in_min)
  dark = step(m,t)
  y = 0.5 * mix(t/m, 1+(t-m)/(1-m), dark)
  return out_min + y*(out_max-out_min)
```

### Exact blend operand order

`foreground` is source port 0, `background` is source port 1, and
`opacity = amount*mask*foreground_alpha`. Alpha is `1` throughout this recipe.
Do not substitute the version-neutral blend definitions from `primitives.md`:

```text
mm95_blend_multiply(F,B,o) = o*(F*B) + (1-o)*B
mm95_blend_screen(F,B,o)   = o*(1-(1-F)*(1-B)) + (1-o)*B

mm95_overlay_component(F,B) =
  2*F*B                         if F < 0.5
  1-2*(1-F)*(1-B)               otherwise
mm95_blend_overlay(F,B,o) = o*mm95_overlay_component(F,B)+(1-o)*B

mm95_burn_component(F,B) = F if F == 0 else max(1-(1-B)/F,0)
mm95_blend_burn(F,B,o) = o*mm95_burn_component(F,B)+(1-o)*B

mm95_soft_component(F,B) =
  2*F*B + F*F*(1-2*B)           if B < 0.5
  2*F*(1-B) + sqrt(F)*(2*B-1)   otherwise
mm95_blend_soft(F,B,o) = o*mm95_soft_component(F,B)+(1-o)*B
```

### MM 0.95 HSV adjustment

Use the conventional branchless RGB/HSV conversion recorded in Material
Maker 0.95, with epsilon `1e-10`. In normative pseudocode:

```text
mm95_adjust_hsv(rgb,hue,saturation,value):
  hsv = rgb_to_hsv(rgb, epsilon=1e-10)
  hsv.h = fract(hsv.h+hue)
  hsv.s = clamp(hsv.s*saturation,0,1)
  hsv.v = clamp(hsv.v*value,0,1)
  return hsv_to_rgb(hsv)
```

## Canonical DAG

The following graph is the complete runtime recipe. No unlisted random input,
texture, renderer default, object coordinate, or colour conversion may affect
it.

```text
# Palette literals (sRGB -> linear exactly once)
tile_tint = srgb_to_linear((0.599939,0.780392,0.035294))
weather_tint = srgb_to_linear((0.361328,0.033875,0.152832))

# Height-dependent source base, analytically collapsed for physical geometry
neutral_height = 0.5
curvature = 0.5
height_band = mm95_tones_range(neutral_height,.12,.47,0,false)  # exactly 0
clay_base = mm95_cubic3(curvature)
# Source brown=(.402344,.184277,.053436), Multiply amount=1,
# but height_band=0, so clay_base remains the ramp value.

# Per-cell colour modulation
instance = mm95_instance_colour(cell)
accented = mm95_blend_overlay(
  foreground=tile_tint,
  background=clay_base,
  opacity=.33*instance.g)

# Large colour breakup
colour_noise = mm95_colour_value_octaves(
  q, size=(3,3), octaves=3, persistence=.5, seed=-32491)
burned = mm95_blend_burn(
  foreground=colour_noise, background=accented, opacity=.21)

# Sparse two-noise weathering mask
folded = mm95_fbm_value(
  q, size=(18,18), folds=1, octaves=3, persistence=.5, seed=5552)
cells = mm95_voronoi_nodes(
  q, size=(8,8), stretch=(1,1), intensity=.99,
  randomness=.85, seed=-38868)
fold_mask = mm95_tones_step(folded, value=.48, width=.12, invert=false)
cell_mask = mm95_tones_step(cells, value=.20, width=.06, invert=true)
weather_mask = mm95_blend_multiply(
  foreground=fold_mask, background=cell_mask, opacity=1)  # fold_mask*cell_mask
weathered = mm95_blend_soft(
  foreground=weather_tint, background=burned,
  opacity=.23*weather_mask)
base_color = mm95_adjust_hsv(
  weathered, hue=0, saturation=1.02735, value=1.16645)

# Roughness; the neutral-height Overlay is exactly value_noise
value_noise = mm95_value_octaves(
  q, size=(4,4), octaves=3, persistence=.5, seed=-71473)
rough_fbm = mm95_fbm_value(
  q, size=(8,8), folds=0, octaves=5, persistence=.5, seed=-29913)
rough_mix = mm95_blend_screen(
  foreground=value_noise, background=rough_fbm, opacity=.55)
roughness = mm95_levels(
  rough_mix,
  in_min=.41875, in_mid=.6125, in_max=1,
  out_min=.4125, out_max=.96875)

MaterialSample {
  base_color: clamp01(base_color),
  roughness:  clamp01(roughness),
  metallic:   0,
  height:     0,
  normal:     (0,0,1),
  ao:         1,
  alpha:      1
}
```

Emission is black, transmission is `0`, and the dielectric F0 is the target's
ordinary non-metal default (nominal `0.04`). Do not infer metallic colour from
the saturated highlights.

## Target materialization and export

- **Blender:** build an ordinary editable node material in the `.blend`. The
  recipe path and provenance are custom metadata, not a runtime dependency.
  Any internally generated bake used to realize the legacy hash/noise must be
  packed into the standalone `.blend`; no source texture binary belongs in
  this library.
- **Three.js:** materialize the same DAG as native shader/TSL logic or generate
  project-local PBR maps. Do not import a permanent second implementation from
  this repository.
- **GLB:** bake Base Color and ORM at the chosen delivery resolution, encode
  Base Color as sRGB and ORM as non-colour, and embed them. A neutral normal
  texture may be omitted because physical tile geometry supplies the normal.
- **IFC fallback:** sRGB base `(0.863281,0.219193,0.219193)`, roughness `.62`,
  metallic `0`; IFC does not carry this procedural DAG.

## Visual acceptance

Judge the generated material on the physical sloped roof field, not on a flat
swatch alone.

- The overall read is saturated warm coral/vermillion clay, with controlled
  orange-red tile-to-tile shifts, magenta/dark weathering, and broad matte to
  satin roughness variation. It must not become lime green despite the source
  overlay tint.
- Every visible tile outline, lap, thickness, and cast shadow comes from the
  physical mesh. Any second 6-by-4 scalloped pattern, painted overlap shadow,
  or silhouette bump is a failure.
- Patterning is continuous in roof-plane metres and repeats exactly every
  `1.8 m` across the eave and `1.6 m` up the slope. Adjacent faces must not
  show UV seams caused by restarting local coordinates.
- Render at least one overcast/soft-key view and one grazing-light view. Compare
  hue balance and variation density against the official preview while
  ignoring the preview's rounded macro tile silhouette.
- Confirm metallic `0`, no emission, no alpha blend, no displacement, neutral
  tangent normal, and roughness within the Levels output interval
  `[.4125,.96875]`.
- Before delivery, inspect the native Blender or Three.js result and the baked
  GLB result side by side. A colour-space double conversion, generic Noise
  substitution, or lost per-cell `instance.g` variation is not acceptable.

## Period-correct upstream definitions

The inlined formulas below are Material Maker 0.95 semantics.

Uncertainty is limited to floating-point implementation differences between
CPU, GPU, and native node evaluators. Preserve operation order and full listed
constants; visual parity is required, but cross-vendor bit identity is not.
