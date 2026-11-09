# Renderer-neutral material recipe primitives

This file is the shared vocabulary for the canonical material recipes in
this directory. It is pseudocode, not a Blender, Three.js, GLSL, TSL, Python,
or Material Maker implementation. A target translation must preserve these
semantics; native nodes, node groups, shader expressions, or procedural bake
steps are interchangeable implementation details.

## Evaluation and coordinates

- Scalars are IEEE-754 floating point. Vector arithmetic and functions are
  component-wise unless stated otherwise.
- `uv` increases right in `u` and up in `v`. A recipe first maps the target
  surface into metres, then divides by its declared `tile_size_m`.
- Periodic fields use `wrap(p) = (fract(p.x), fract(p.y))`, where
  `fract(x) = x - floor(x)`. `mod_pos(x, y) = x - y*floor(x/y)` for `y > 0`.
- `clamp(x,a,b) = min(max(x,a),b)` and `clamp01(x) = clamp(x,0,1)`.
- `mix(a,b,t) = a*(1-t) + b*t` and does not clamp `t`.
- `step(edge,x)` is `0` when `x < edge`, otherwise `1`.
- `smoothstep(a,b,x)` is `q*q*(3-2*q)` with
  `q = clamp01((x-a)/(b-a))` and requires `a != b`.
- Unless a recipe opts out, evaluate periodic procedural fields at wrapped
  coordinates and use repeat sampling. Never depend on object origin or mesh
  bounding-box size after the recipe's metre mapping has been established.

## Colour and PBR values

Recipe palette literals are sRGB coefficients in `[0,1]`. Convert every
palette endpoint to linear light before interpolation or blend math:

```text
srgb_to_linear(c) = c/12.92                         when c <= 0.04045
                    ((c+0.055)/1.055)^2.4           otherwise
linear_to_srgb(c) = 12.92*c                         when c <= 0.0031308
                    1.055*c^(1/2.4)-0.055           otherwise
```

Clamp negative linear colour before encoding. `base_color` and `emission` are
linear inside the recipe and colour-managed by the target. `roughness`,
`metallic`, `height`, `normal`, `ao`, masks, and all noise fields are linear
non-colour data. Clamp final `roughness`, `metallic`, `ao`, and `alpha` to
`[0,1]`.

## Version-specific source operations

Material Maker 0.94, 0.95, and 0.96pre do not share one interchangeable hash,
noise, levels, transform-mode, or blend implementation. Each material recipe
therefore defines the exact version-specific operations it uses, including
seed derivation and octave behaviour. Never replace a recipe's legacy
“Perlin” or value-noise formula with a target renderer's similarly named node.

## Ramps, ranges, levels, and transforms

`gradient_ramp(x, stops)` sorts `(position, sRGB colour)` stops by position,
converts endpoints to linear, clamps beyond the end stops, and linearly
interpolates between the surrounding stops.

`linear_map(x, in0, in1, out0, out1, clamp_result=false)` is
`out0 + (x-in0)*(out1-out0)/(in1-in0)`. Clamp to the ordered output range only
when `clamp_result` is true.

`levels_midpoint(x, in_black, in_mid, in_white, out_black, out_white)` is the
version-neutral piecewise midpoint operation used only when a recipe names it:

```text
t = clamp01((x-in_black)/(in_white-in_black))
m = clamp01((in_mid-in_black)/(in_white-in_black))
y = 0.5*t/m                              when t < m
    0.5 + 0.5*(t-m)/(1-m)                otherwise
return mix(out_black, out_white, y)      # require 0 < m < 1
```

For a colour, apply `levels_midpoint` per channel. A recipe that lists a threshold
`value` and `width` uses
`tones_step(x,value,width) = smoothstep(value-width/2, value+width/2, x)`.
`tones_range(x,a,b,softness)` is the product of a rising `tones_step` at `a`
and the inverse of a rising `tones_step` at `b`, both with the stated
`softness`.

`transform_uv(uv, scale, rotate_turns, translate, pivot=(0.5,0.5))` applies
scale about `pivot`, then counter-clockwise rotation by
`rotate_turns*2*pi`, then translation. `sample_transformed(field,...,mode)`
uses wrapped coordinates for `repeat`, clamps to `[0,1]` for `extend`, and
returns zero outside `[0,1]` for `clip`.

## Blend modes

Every blend receives `background`, `foreground`, and `opacity`; this operand
order is normative. First calculate the mode component-wise, then return
`mix(background, mode_result, clamp01(opacity))`.

```text
normal(b,f)     = f
multiply(b,f)   = b*f
screen(b,f)     = 1-(1-b)*(1-f)
lighten(b,f)    = max(b,f)
overlay(b,f)    = 2*b*f                       when b <= 0.5
                  1-2*(1-b)*(1-f)             otherwise
burn(b,f)       = 0                           when f <= 0
                  1-min(1,(1-b)/f)            otherwise
dodge(b,f)      = 1                           when f >= 1
                  min(1,b/(1-f))              otherwise
soft_light(b,f) = b-(1-2*f)*b*(1-b)           when f <= 0.5
                  b+(2*f-1)*(sqrt(b)-b)        otherwise
```

Clamp mode inputs and results to `[0,1]` unless the recipe explicitly says an
intermediate is high-dynamic-range. `invert(x) = 1-x`.

## HSV adjustment

`rgb_to_hsv` and `hsv_to_rgb` use the conventional six-sector transform with
hue wrapped to `[0,1)`. `adjust_hsv(rgb, hue_turns, saturation_factor,
value_factor)` converts linear RGB to HSV, adds and wraps hue, multiplies
saturation and value, clamps them to `[0,1]`, and converts back to linear RGB.

## Buffered filters

Some legacy nodes are neighbourhood operations rather than point functions.
When a recipe invokes one, rasterize its input at the recipe's declared
`working_resolution` using texel-centre samples and periodic wrap. This raster
is temporary evaluation state, never a checked-in texture asset.

- `sample_buffer(field,N)` creates that `N x N` periodic scalar or colour
  field. Sampling between texels is bilinear and wraps at every boundary.
- `gaussian_blur_periodic(field,sigma_px)` is a separable normalized Gaussian
  convolution using integer offsets through `ceil(3*sigma_px)`.
- `slope_warp(source,driver,amount)` samples `source` at
  `uv + amount*normalize_or_zero(gradient(driver))`; the central-difference
  gradient step is one texel of the working raster.
- `make_tileable(field,falloff)` blends each border with its opposite border
  across a band of fractional width `falloff`; apply horizontally and then
  vertically. The blend weight is `smoothstep(0,falloff,d)` where `d` is the
  wrapped distance to the nearer border.
- `curvature(field)` is the periodic five-point Laplacian
  `left+right+down+up-4*center`, remapped as the calling recipe states.

If a target cannot reproduce a buffered source node natively, it may generate
the temporary field while building the material and internalize the result in
the standalone target. It must record the substitution and still pass the
recipe's visual acceptance checks.

## Height, normal, and ambient occlusion

Height is a scalar fraction that the recipe converts to metres with
`height_scale_m`. To produce the canonical OpenGL tangent-space normal, use
central differences in physical metres:

```text
du = (H(uv+(e,0))-H(uv-(e,0))) * height_scale_m / (2*e*tile_size_m.x)
dv = (H(uv+(0,e))-H(uv-(0,e))) * height_scale_m / (2*e*tile_size_m.y)
normal = normalize((-du, -dv, 1))
```

Use `e = 1/bake_resolution` for a bake and an equivalent derivative scale for
a live shader. OpenGL `+Y` is canonical; invert the green component only for a
target that explicitly consumes DirectX normals.

`ambient_occlusion_from_height(H,uv,radius_m,strength)` samples eight evenly
spaced directions at radii `1/4`, `1/2`, `3/4`, and `1` of `radius_m`.
For each sample calculate the positive horizon slope above the centre; average
all 32 values and return `clamp01(1-strength*average)`. This deterministic
approximation is used only where a recipe requests AO.

## Canonical outputs

Each recipe resolves exactly this record, even when values are constants:

```text
MaterialSample {
  base_color: linear RGB,
  roughness:  scalar [0,1],
  metallic:   scalar [0,1],
  height:     scalar [0,1],
  normal:     OpenGL tangent-space direction in [-1,1] or a height-to-normal link,
  ao:         scalar [0,1],
  alpha:      scalar [0,1]
}
```

Encode a normal map as `0.5*normal + 0.5`. For a live Blender graph, the normal
may be constructed from height by a Bump
node instead of materializing RGB. For Three.js it may be evaluated in the
shader or generated into a project-local map. For GLB, bake Base Color,
Normal, and ORM (`R=AO`, `G=roughness`, `B=metallic`) and embed them.
