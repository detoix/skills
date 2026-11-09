---
schema: building-author/material-recipe/v1
id: original.honey-timber-facade
title: Honey vertical timber facade
source_author: Project-authored original mathematical material
source_license: No third-party texture or graph incorporated
tile_size_m: [1.152, 2.304]
working_resolution: 1024
normal_convention: OpenGL tangent space (+Y)
---

# Honey vertical timber facade

This is the sole renderer-neutral recipe for an original vertical timber
facade finish. Board rhythm, palette and physical relief are configurable
visual parameters, not product specifications or measured construction details.

The carrier is an already declared continuous `IfcCovering(CLADDING)` or
existing material region. The recipe changes shading only: no batten objects,
displacement, facade overlays, subdivisions, expansion or clipping.

## Coordinates and dimensions

Read the shared [primitives.md](primitives.md) vocabulary. Use explicit metric
UVs with `U` across the facade and `V` vertically upward:

```text
u = dot(P - facade_origin, facade_tangent) / 1.152
v = (P.z - facade_origin.z) / 2.304
```

The facade tangent is a declared horizontal unit vector; the east return uses
the Y axis, while front and rear elevations use X. Preserve the same origin
and phase across adjacent coplanar regions. Store the origin and tangent in
project object metadata. Never stretch UVs to an object's bounding box. A
normal map uses UVs with consistent orientation; map return faces using their
own horizontal tangent instead of creating zero-area UV islands.

One horizontal repeat contains 16 apparent boards on a 72 mm pitch. The dark
joint is 10 mm wide, with a 1.5 mm transition on either side. The maximum
shader height is 1.98 mm. The surface stays continuous and opaque; its dark
stripes do not form physical gaps. No horizontal board-end joints are drawn.

## Canonical mathematical field

All trigonometric arguments are radians. `fract`, `clamp01`, `smoothstep`,
`mix`, and sRGB conversion have their definitions in `primitives.md`. Palette
literals below are sRGB; convert to linear before blending. Pinned constants
are the deterministic seed; there is no renderer-specific noise function.

```text
TAU = 2*pi
board = floor(fract(u)*16)
variation = 0.5 + 0.5*sin(TAU*(board*0.61803398875 + 0.137))
q = fract(u*16)
edge_distance_m = min(q, 1-q)*0.072
face = smoothstep(0.005, 0.0065, edge_distance_m)

grain = 0.5
        + 0.32*sin(TAU*(128*u + 0.13*sin(TAU*3*v)))
        + 0.18*sin(TAU*(320*u + 0.10*sin(TAU*7*v)))
wood_weight = 0.28 + 0.48*variation + 0.15*grain
wood = mix(srgb_to_linear((0.45,0.27,0.12)),
           srgb_to_linear((0.77,0.56,0.31)), wood_weight)
base_color = mix(srgb_to_linear((0.16,0.13,0.10)), wood, face)
roughness = mix(0.82, 0.55 + 0.10*(1-grain) + 0.035*variation, face)
height_m = face*(0.0018 + 0.00018*grain)
ao = 1 - 0.12*(1-face)
metallic = 0
alpha = 1
```

Grain is elongated vertically and periodic in both UV directions. Material
height affects bump/normal only. Derive a tangent-space normal with the shared
physical central-difference convention. For a `W x H` bake, use independent
`du=1/W`, `dv=1/H` and physical widths `1.152 m`, `2.304 m`:

```text
dx = (height_m(u+du,v)-height_m(u-du,v))/(2*du*1.152)
dy = (height_m(u,v+dv)-height_m(u,v-dv))/(2*dv*2.304)
normal = normalize((-dx,-dy,1))
```

## Target materialization

- Blender keeps editable local native math, mix, Principled and Bump nodes.
  The Bump input receives metre-valued height, Distance 1, Strength 1. No
  external texture or addon shader is needed to evaluate the material.
- The equivalent mathematical field may be rasterized with NumPy at texel
  centres instead of running a lighting-dependent Cycles bake. Default output
  is 1024 x 1024; 512 x 512 is acceptable for a quick preview. This raster is a
  generated bake of the same formula, not another canonical implementation.
- Embed Base Color, OpenGL Normal and ORM (`R=AO`, `G=roughness`, `B=0`) in
  the GLB. Base Color is sRGB; Normal and ORM are Non-Color. Use real UVs,
  triangulated export geometry and tangent-space normals.
- Pack generated images into `.blend`. Keep the native procedural material
  assigned after export; swap to image-based derivative materials only for
  export and restore source slots afterward. A disconnected active Base Color
  image node may supply Workbench's Texture preview without changing the shader.
- IFC retains the continuous covering and its original construction material
  and simplified flat color. This recipe does not author IFC textures.

Store the recipe ID, path, physical tile size, board pitch, gap width, bake
resolution and normal convention in generated material metadata.

## Acceptance checks

1. All fields are finite. Roughness, AO and alpha stay within [0,1]; metallic
   is exactly zero. The mathematical field repeats at `u+1` and `v+1`.
2. Joint centers have `face=0`, zero height, roughness 0.82, and the dark joint
   palette. Board centers have `face=1` and height from 1.8 to 1.98 mm.
3. U spans a 72 mm apparent module; all grain follows the vertical V direction.
   The east return must retain the same physical pitch as the rear facade.
4. At building distance the read is warm timber with restrained vertical
   joints; close up, grain is visible without high-contrast zebra stripes.
5. Inspect one assigned rear facade and the east return under grazing light.
   Check seam phase, normal direction and baked/native similarity.
6. IFC/object counts must reflect the declared continuous facade zones, with
   no individual facade batten geometry or displacement modifier.

Normal mapping cannot reproduce deep gaps, parallax or a batten silhouette.
That limitation is intentional in this texture-only representation.
