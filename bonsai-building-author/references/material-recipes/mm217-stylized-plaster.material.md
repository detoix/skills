---
schema: building-author/material-recipe/v1
id: material-maker.217.stylized-plaster
title: Stylized plaster
source_author: Tarox
source_license: CC0-1.0
source_engine: Material Maker 0.96pre-mats
tile_size_m: [0.75, 0.75]
working_resolution: 1024
reference_export_resolution: 2048
height_scale_m: 0.0012
normal_convention: OpenGL tangent space (+Y)
---

# MM217 Stylized plaster

This is the single renderer-neutral definition of
`material-maker.217.stylized-plaster`. It is normative pseudocode, not a
Blender implementation, a Three.js implementation, or an invitation to use a
renderer's vaguely similar noise nodes. An authoring agent translates this
recipe into the requested project's native material, then leaves only that
project-local result. Shared, version-neutral notation is defined in
[primitives.md](./primitives.md); every Material Maker 0.96pre-specific
operation used here is defined inline below.

## Provenance and authority

After [Stylized plaster by Tarox](https://www.materialmaker.org/material?id=217) (CC0); node semantics follow Material Maker 0.96.

## Surface mapping and physical interpretation

Material Maker did not publish a physical size. This library fixes one so two
agents cannot make different-looking buildings:

- One procedural repeat is exactly **0.75 m x 0.75 m**.
- On a planar facade, `v` increases in world up. Let `n` be the outward face
  normal and `up=(0,0,1)`; `u` increases along `normalize(cross(up,n))`.
- Anchor metre coordinates at the project/world origin, not at each object's
  bounding-box minimum. The recipe coordinate is
  `uv = (dot(P_world,U)/0.75, dot(P_world,up)/0.75)`.
- Mirror neither axis. If authored UVs are supplied instead, they must encode
  that metre scale and orientation. All procedural fields repeat every unit.
- The source height `Hsource` occupies a narrow part of `[0,1]`. The canonical
  PBR height output is `height01=clamp01((Hsource-0.89)/0.10)` and optional
  displacement is `height_m=0.0012*(height01-0.5)`, giving at most **1.2 mm
  peak-to-peak**. This is a documented facade-scale adaptation, not a value
  claimed by Tarox.
- The source Material node's `depth_scale=0.42` is disconnected from any depth
  input. It is inert and must not be interpreted as metres or displacement.

## Numeric, colour, and output contract

- Evaluate legacy noise/hash math as IEEE-754 binary32 where practical.
  Cross-backend acceptance is numeric tolerance, not identical transcendental
  rounding.
- All noise, masks, height, roughness, normal, and AO are non-colour data.
- Palette literals below are source sRGB. Decode each endpoint to linear light
  before interpolation or blending. Encode only a baked/display Base Color.
- Output is opaque dielectric plaster: `metallic=0`, `roughness=1`, `alpha=1`,
  emission black, transmission zero, and dielectric F0 `0.04` if a target
  requires it.
- `normal` is OpenGL tangent-space (+Y). Flip green only for an explicitly
  DirectX consumer.

Palette constants, with precomputed linear values for auditability:

| Name | source sRGB | scene-linear RGB |
|---|---|---|
| `ochre` | `(0.703125, 0.497389, 0.315857)` | `(0.452451529, 0.211632396, 0.081337281)` |
| `sand` | `(0.785156, 0.757361, 0.607269)` | `(0.578972501, 0.534062217, 0.327097121)` |
| `ivory` | `(0.949219, 0.890878, 0.808319)` | `(0.888346383, 0.769481877, 0.618023821)` |

`ramp2(x) = gradient_ramp(x, [(0,ochre),(1,ivory)])`.

`ramp3(x) = gradient_ramp(x,
[(0,ochre),(0.463636,sand),(1,ivory)])`.

## Material Maker 0.96pre primitive semantics

These definitions override similarly named generic operations. Scalar formulas
extend component-wise to RGB.

### Hashes and seeds

```text
mm_mod(x,y) = x - y*floor(x/y)
mm_rand(p):
    return fract(cos(mm_mod(dot(p,(13.9898,8.141)),3.14))*43758.5453)

mm_rand2(p):
    return fract(cos(mm_mod((dot(p,(13.9898,8.141)),
                             dot(p,(3.4562,17.398))),
                            (3.14,3.14)))*43758.5453)
```

Unlocked legacy seeds came from node positions:

```text
local_seed(x,y) = c_remainder(
    (trunc(x)*0x1f1f1f1f) XOR trunc(y), 65536)
seed(node) = local_seed(node.x,node.y) + seed(parent_transmitting_graph)
```

`c_remainder` truncates the quotient toward zero and `XOR` is signed two's
complement. Do not recalculate seeds in a target; use this normative table:

| Field | Noise | seed | scale | octaves | persistence |
|---|---|---:|---:|---:|---:|
| `cell_detail` | Cellular4 / Manhattan F2-F1 | `-80` | `(1,1)` | `9` | `0.43` |
| `cell_driver` | Cellular2 / Euclidean F2-F1 | `-8744` | `(1,1)` | `7` | `1.0` |
| `value_detail` | Value | `-35974` | `(3,3)` | `2` | `0.5` |
| `grunge_a` | Perlin | `118153` | `(5,5)` | `15` | `0.62` |
| `grunge_b` | Perlin | `2737` | `(5,5)` | `15` | `0.62` |
| `warp2.r/g/b` | Perlin | `-7801/-25866/-25602` | `(5,5)` | `15` | `0.62` |
| `warp3.r/g/b` | Perlin | `-7633/-25698/-25434` | `(5,5)` | `15` | `0.62` |

The custom graph deliberately requests 15 octaves even though the old editor
slider normally stopped at 10; the source shader loop accepts 15, so 15 is
normative.

### Base noise and normalized FBM

For every base noise call, `coord` is already `uv*size`:

```text
lattice_origin(coord,size,seed) =
    floor(coord) + mm_rand2((float(seed),1-float(seed))) + size

value_noise(coord,size,seed):
    o = lattice_origin(coord,size,seed); f = fract(coord)
    p00 = mm_rand(mm_mod(o, size))
    p01 = mm_rand(mm_mod(o+(0,1), size))
    p10 = mm_rand(mm_mod(o+(1,0), size))
    p11 = mm_rand(mm_mod(o+(1,1), size))
    t = f*f*(3-2*f)
    return mix(mix(p00,p10,t.x), mix(p01,p11,t.x), t.y)

perlin_noise(coord,size,seed):
    o = lattice_origin(coord,size,seed); f = fract(coord)
    angle(dx,dy) = mm_rand(mm_mod(o+(dx,dy),size))*2*pi
    grad(dx,dy) = (cos(angle(dx,dy)),sin(angle(dx,dy)))
    p00 = dot(grad(0,0), f)
    p01 = dot(grad(0,1), f-(0,1))
    p10 = dot(grad(1,0), f-(1,0))
    p11 = dot(grad(1,1), f-(1,1))
    t = f*f*(3-2*f)
    return 0.5 + mix(mix(p00,p10,t.x),mix(p01,p11,t.x),t.y)

cellular_f2_f1(coord,size,seed,metric):
    o = lattice_origin(coord,size,seed); f = fract(coord)
    nearest = 2; second = 2
    for dx in {-1,0,1}, dy in {-1,0,1}:
        r = mm_rand2(mm_mod(o+(dx,dy),size))
        if metric == EUCLIDEAN:
            point = r+(dx,dy); distance = length(f-point)
        if metric == MANHATTAN_HALF_JITTER:
            point = 0.5*r+(dx,dy)
            distance = abs(f.x-point.x)+abs(f.y-point.y)
        update nearest and second with distance
    return second-nearest

mm_fbm(uv,kind,seed,size,octaves,persistence):
    total=0; weight_sum=0; weight=1
    repeat octaves times:
        n = base_kind(uv*size,size,seed)
        total += n*weight; weight_sum += weight
        size *= 2; weight *= persistence
    return total/weight_sum
```

There are no folds and no octave offsets. `cell_detail` uses
`MANHATTAN_HALF_JITTER`; `cell_driver` uses `EUCLIDEAN`.

### Transform, blend, level, and threshold operations

The source Transform samples a field after this inverse coordinate transform:

```text
mm_transform_clamp(field,uv,translate,angle_rad,scale):
    q = uv-translate-(0.5,0.5)
    r = (cos(angle)*q.x + sin(angle)*q.y,
        -sin(angle)*q.x + cos(angle)*q.y)
    return field(clamp(r/scale+(0.5,0.5),(0,0),(1,1)))
```

Material Maker's blend operand order is `foreground, background, opacity`.
It is intentionally different from the argument order of the shared generic
blend notation:

```text
mm_multiply(f,b,a) = a*(f*b)+(1-a)*b
mm_lighten(f,b,a)  = a*max(f,b)+(1-a)*b
mm_difference(f,b,a) = a*clamp01(b-f)+(1-a)*b

overlay_channel(f,b):
    return 2*f*b                         if f < 0.5
    return 1-2*(1-f)*(1-b)              otherwise
mm_overlay(f,b,a) = a*overlay_channel(f,b)+(1-a)*b

burn_channel(f,b):
    return f if f == 0 else max(1-(1-b)/f,0)
mm_burn(f,b,a) = a*burn_channel(f,b)+(1-a)*b

dodge_channel(f,b):
    return f if f == 1 else min(b/(1-f),1)
mm_dodge(f,b,a) = a*dodge_channel(f,b)+(1-a)*b
```

Do not pre-clamp the signed high-pass field. Clamp only where a formula says
so. Source `tones_step` is linear, not Hermite smoothstep:

```text
mm_tones_step(x,value,width) =
    clamp01((x-value)/max(0.0001,width)+0.5)
```

The source Levels operation is:

```text
t = clamp01((x-in_min)/(in_max-in_min))
m = (in_mid-in_min)/(in_max-in_min)
y = 0.5 * (t/m)                         when t < m
    0.5 * (1+(t-m)/(1-m))               otherwise
levels = out_min+y*(out_max-out_min)
```

Here `(in_min,in_mid,in_max)=(0,0.5,1)` and
`(out_min,out_max)=(0.933523,1)`, so it simplifies exactly to
`levels_plaster(x)=0.933523+0.066477*clamp01(x)`.

### Fixed buffers and Gaussian blur

`buffer_N(field)` samples at texel centres into a periodic `N x N` raster,
stores binary32, and later samples bilinearly with repeat. This is the
deterministic portability definition of Material Maker 0.96's GPU Buffer. The
old graph did not pin GPU render-target precision; binary32 is the intentional
canonicalization.

The high-pass blur is the old 101-tap separable filter, not the generic
three-sigma blur:

```text
mm_gaussian_axis(A,uv,axis,N=1024,sigma=27.9):
    sum=0; weight_sum=0
    for i from -50 through 50 inclusive:
        w=exp(-0.5*(i/sigma)^2)/(2*pi*sigma^2)
        sum += sample_repeat_bilinear(A,uv+axis*i/N)*w
        weight_sum += w
    return sum/weight_sum

mm_gaussian_2d(A) = buffer_1024(
    mm_gaussian_axis(buffer_1024(
        mm_gaussian_axis(buffer_1024(A),X)),Y))
```

### Make-tileable and distance-to-top warp

The source calls its Make Tileable node with `w=0.25`; the implementation
halves it, so `we=0.125` below:

```text
mm_make_tileable(F,uv):
    a=F(uv)
    b=F(fract(uv+(0.5,0.5)))
    kab=sin((pi/2)*clamp01((length(uv-(0.5,0.5))-0.5+we)/we))
    c=F(fract(uv+(0.25,0.25)))
    edge_mid_distance=min(length(uv-(0,0.5)), length(uv-(0.5,0)),
                          length(uv-(1,0.5)), length(uv-(0.5,1)))
    kabc=sin((pi/2)*clamp01((edge_mid_distance-we)/we))
    return mix(c,mix(a,b,kab),kabc)
```

The Warp node uses `mode=Distance to top`, `amount=0.005`, and
`epsilon=0.095`. Source and driver are the same `F`:

```text
mm_distance_top_warp(F,uv):
    sx=F(fract(uv+(0.095,0)))-F(fract(uv-(0.095,0)))
    sy=F(fract(uv+(0,0.095)))-F(fract(uv-(0,0.095)))
    delta=(sx,sy)*(1-F(uv))
    return F(uv+0.005*delta)
```

### Normal, AO, and smooth curvature

For an arbitrary periodic height buffer `H`, the source Sobel vector at
resolution `N` is:

```text
mm_sobel(H,uv,N):
    d=1/N
    r=( 1,-1)*H(uv+( d,-d)) + (-1, 1)*H(uv+(-d, d))
    r+=( 1, 1)*H(uv+( d, d)) + (-1,-1)*H(uv+(-d,-d))
    r+=( 2, 0)*H(uv+( d, 0)) + (-2, 0)*H(uv+(-d, 0))
    r+=( 0, 2)*H(uv+( 0, d)) + ( 0,-2)*H(uv+( 0,-d))
    return r
```

The target-facing canonical normal converts the source strength to OpenGL:

```text
normal = normalize((-mm_sobel(buffer_2048(Hsource),uv,2048)*16, +1))
```

The leading minus sign makes increasing physical height tilt the outward
normal toward the lower neighbour, matching the shared height convention.
Omitting it inverts every pit and bump.

AO is exactly the source's low-frequency difference at `N=512`, with
`sigma=50`, 101 taps per Gaussian axis, and exponent `1`:

```text
Hb=buffer_512(Hsource)
low=mm_gaussian_axis(buffer_512(
        mm_gaussian_axis(Hb,X,N=512,sigma=50)),Y,N=512,sigma=50)
ao=pow(1-clamp01(low-Hb),1)
```

Smooth curvature uses `N=1024` and intensity `1`. Define the source's internal
yellow normal encoding and emboss response:

```text
Ninternal=0.5*normalize((mm_sobel(buffer_1024(Hsource),uv,1024)*8,-1))+0.5

emboss(width,uv):
    r=(0,0); d=1/1024
    for dx=-width..width, dy=-width..width:
        if abs(dx)>0.5 or abs(dy)>0.5:
            q=Ninternal(uv+d*(dx,dy)).xy
            r += q*cos((atan2(dy,dx),atan2(dy,dx))-(0,0.5)*pi)
                 / length((dx,dy))
    r=r/width+0.5
    return 0.5*(r.x+r.y)
```

For widths `(1,2,4,8,16)`, the old Fast Blur receives requested sigmas
`(2,5,8,16,34)`, which at a 1024 input become effective pixel sigmas
`(1,2,4,8,17)` via `max(1,floor(requested_sigma*1024/2048))`. Its mip-assisted
sampling is driver-dependent. The canonical deterministic approximation is a
periodic normalized Gaussian truncated at three effective sigmas. The inputs
and assignments are exact:

```text
E1(uv)=emboss(1,uv);   B1=gaussian_blur_periodic(buffer_1024(E1),sigma_px=1)
E2(uv)=emboss(2,uv);   B2=gaussian_blur_periodic(buffer_1024(E2),sigma_px=2)
E4(uv)=emboss(4,uv);   B4=gaussian_blur_periodic(buffer_1024(E4),sigma_px=4)
E8(uv)=emboss(8,uv);   B8=gaussian_blur_periodic(buffer_1024(E8),sigma_px=8)
E16(uv)=emboss(16,uv); B16=gaussian_blur_periodic(buffer_1024(E16),sigma_px=17)

curvature = 1-mm_overlay(B1,
                mm_overlay(B2,
                  mm_overlay(B4,
                    mm_overlay(B8,B16,1),1),1),1)
```

This Fast Blur substitution is the only intentional filter approximation. A
translation must record it as `mm096_fast_blur_3sigma`; it must not substitute
a renderer Curvature node with unknown scale.

## Canonical connected DAG

Every name below is a field function. Evaluate at recipe `uv`; buffer calls
create temporary build state only.

### 1. Surface height foundation

```text
D(uv)=mm_fbm(uv,EUCLIDEAN_F2_F1,-8744,(1,1),7,1.0)
F(uv)=mm_fbm(uv,MANHATTAN_HALF_JITTER_F2_F1,-80,(1,1),9,0.43)

T(uv):
    control=D(uv)
    translate=(2*(2*control-1),2*(2*control-1))
    angle=radians(-72.55*(2*control-1))
    return mm_transform_clamp(F,uv,translate,angle,(1,1))

Tbuf=buffer_1024(T)
Blur=mm_gaussian_2d(T)
High(uv)=Tbuf(uv)-Blur(uv)                 # signed; do not clamp
Tile(uv)=mm_make_tileable(High,uv)
Warped(uv)=mm_distance_top_warp(Tile,uv)
I(uv)=1-Warped(uv)
Rot90(uv)=I((uv.y,1-uv.x))                 # source 90 degree clamp transform
J(uv)=max(I(uv),Rot90(uv))                 # Lighten, opacity 1

V(uv)=mm_fbm(uv,VALUE,-35974,(3,3),2,0.5)
L(uv)=levels_plaster(J(uv))
source_height_unbuffered(uv)=mm_multiply(V(uv),L(uv),0.1)
Hsource=buffer_1024(source_height_unbuffered)
height01(uv)=clamp01((Hsource(uv)-0.89)/0.10)
```

`Hsource` preserves the graph's exported scalar and drives its derived maps;
`height01` is the fixed physical remap exposed to a PBR consumer. The Multiply
line includes the 90% source background by definition; it is
`L*(0.9+0.1*V)`, not `L*V*0.1`.

### 2. Connected Plain Grunge height output

```text
A(uv)=mm_fbm(uv,PERLIN,118153,(5,5),15,0.62)
B(uv)=mm_fbm(uv,PERLIN,2737,(5,5),15,0.62)
W2(uv)=(mm_fbm(uv,PERLIN,-7801,(5,5),15,0.62),
        mm_fbm(uv,PERLIN,-25866,(5,5),15,0.62),
        mm_fbm(uv,PERLIN,-25602,(5,5),15,0.62))
W3(uv)=(mm_fbm(uv,PERLIN,-7633,(5,5),15,0.62),
        mm_fbm(uv,PERLIN,-25698,(5,5),15,0.62),
        mm_fbm(uv,PERLIN,-25434,(5,5),15,0.62))

mingle(in1,in2,W,wx,wy,mode,uv):
    p1=uv+2*(wx*W(uv).r,-wy*W(uv).g)
    p2=uv-2*(wx*W(uv).g,-wy*W(uv).r)
    a=smoothstep(0,1,W(uv).b)
    return mode(in1(p1),in2(p2),a)

M1(uv)=mingle(A,B,W3, 0.5, 0.5,mm_burn, uv)
M2(uv)=mingle(B,A,W2,-0.5,-0.5,mm_dodge,uv)

extended_overlay(uv):
    w=W2(uv)
    p1=uv+2*(0.5*w.r,0.5*w.g)
    p2=uv-2*(0.5*w.g,0.5*w.r)
    a=smoothstep(0,1,w.b)
    out0=mm_overlay(M1(p1),M2(p2),a)
    out1=mm_overlay(M1(p2),M2(p1),a)
    return (out0,out1)

(O0,O1)=extended_overlay(uv)
mask=mm_tones_step(A(uv),0.48,0.66)
G0(uv)=mm_burn(O0,O1,mask)
G(uv)=mm_tones_step(G0(uv),0.48,0.66)
Gbuf=buffer_1024(G)
```

Only the Plain Grunge `Heights` output above reaches this material. Its second
`Colors` output, `graph_4`, and their downstream nodes are dead in the source
graph and are deliberately omitted; generating them changes no PBR output.

### 3. Base Color and final outputs

```text
base_height_colour(uv)=ramp2(J(uv))
curvature_colour(uv)=mm_overlay(curvature(uv),base_height_colour(uv),0.3)
grunge_colour(uv)=ramp3(Gbuf(uv))
base_color(uv)=mm_multiply(grunge_colour(uv),curvature_colour(uv),0.2)

MaterialSample {
    base_color = base_color(uv)             # linear RGB
    roughness  = 1.0
    metallic   = 0.0
    height     = height01(uv)
    normal     = source OpenGL normal defined above
    ao         = source AO defined above
    alpha      = 1.0
}
```

## Translation and internalization rule

An agent may express point operations as native nodes/shader expressions or
evaluate this DAG into project-local procedural maps. The buffered filters are
often clearer as temporary build-time rasters. If maps are generated, pack
them into the standalone `.blend`, create project-local Three.js textures, or
embed them in GLB; do not add texture binaries to this library and do not keep
an external path dependency. The generated target is a normal editable native
PBR material, not another canonical recipe.

Required baked channels are Base Color (sRGB), OpenGL Normal (non-colour), and
ORM (`R=AO`, `G=roughness=1`, `B=metallic=0`). Height is optional non-colour.

## Visual and numeric acceptance

Inspect a render on the actual external facade layer, not only a shader ball.
It passes only when all of the following hold:

1. The overall read is warm pale ivory plaster, never gray concrete, yellow
   paint, or plastic.
2. Restrained ochre-gray scrape marks and shallow pits break the surface. They
   remain sparse; large black cavities or a uniform speckle field fail.
3. At the fixed 0.75 m repeat, broad breakup reads at roughly hand/trowel scale
   and the fine marks remain subordinate at a normal building view.
4. Roughness is fully diffuse (`1.0`): grazing light reveals relief and broad
   tonal rolloff but no tight varnished highlight.
5. The normal faces outward under a moving grazing light. A green-channel flip
   that turns every pit into a bump fails.
6. AO stays close to white over flat plaster and darkens only recesses; it must
   not make the whole facade dirty.
7. Opposite tile edges match. At a 2048 bake, Base Color/height/AO seam error
   must be at most `2/255`; paired normal directions must have dot product at
   least `0.995`.
8. Re-evaluation with the same recipe and resolution must match within
   `1e-5` for scalar fields before 8-bit encoding. Different GPU trigonometric
   rounding may exceed bit identity but not that visual tolerance.
9. As a scalar sanity check, the 1024 `Hsource` field should remain roughly
   in `[0.88,0.99]` with mean in `[0.92,0.95]`. Values spanning most of
   `[0,1]` usually mean the Levels or Multiply operand order is wrong.
10. Compare against the published preview under neutral daylight plus one
    grazing light. Match its pale body, sparse warm scuffs, and shallow relief;
    do not attempt to copy its transparent background or exact sphere lighting.

Record with the generated material: recipe id, tile
size, bake resolution if any, normal convention, and the named Fast Blur
substitution. A render that fails these checks is not complete even if the
material graph compiled.
