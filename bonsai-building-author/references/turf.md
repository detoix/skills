# Turf areas

Use `turf()` for an explicitly designed horizontal lawn area. It does not
resolve walls like `space()`, infer a plot, scatter plants, or generate blades.

```python
from building_author import turf

turf(model, "turf.rear", site="site", elevation=-0.32,
     boundary=[(-4, 14), (22, 14), (22, 24), (-4, 24)],
     name="Rear lawn")
```

Coordinates are metres in the authored project frame, with Blender Z up.
The boundary is a simple convex or concave polygon. The compiler normalizes
its winding. Self-intersections, collapsed boundaries and invalid site
references are errors. Use multiple explicit regions for separated lawns;
interior rings, curved edges and sloped ground are not supported yet. Do not
silently fill a hole or approximate a slope as flat. Obtain or explicitly
state assumed plot dimensions before placing a lawn.

## IFC and Blender

The area is `IfcSpace(USERDEFINED)`, `ObjectType="Turf"`, aggregated under
its `IfcSite`, with `Pset_SpaceCommon.IsExternal=True`. IFC4 explicitly permits
exterior spaces under sites and a `FootPrint/Curve2D` representation. Store the
closed plan boundary there and elevation in ObjectPlacement; do not invent a
space height or physical slab just to export a surface. Record NetFloorArea.
[IFC4 reference](https://standards.buildingsmart.org/IFC/RELEASE/IFC4/ADD2/HTML/schema/ifcproductextension/lexical/ifcspace.htm).

`BBAM_Landscape` persists SemanticId, Role and Version; IfcSpace has no Tag.
The original key and its stable GlobalId must survive IFC save/reload.

After reload the presentation phase reads that IFC footprint and placement
and creates an upward-facing, triangulated surface with metric UVs and a
simple turf PBR fallback. The surface is a generated derivative, separate
from the spatial object. Editing its Blender mesh changes an export; to
preserve edits across rebuilds, update the authored `turf()` boundary too.

## GLB contract

Export with `export_extras=True` (Include → Custom Properties). A surface node
carries this object custom property:

```json
{"landscape":{"version":1,"id":"turf.rear","role":"turf","ifcGlobalId":"…"}}
```

Its mesh is the coverage and elevation definition. Names are human labels;
never discover turf by parsing display names or requiring an ID prefix.
Blender's exporter converts geometry/transforms from Z up to glTF Y up;
custom coordinate arrays do not undergo that conversion, so do not duplicate
boundaries in extras. Apply the full node/world transform in the consumer.

Only the turf surface is renderable; do not export a duplicate space curve
or a spatial volume as grass geometry. A consumer without procedural grass
still sees the fallback lawn material. A consumer adding blades should use
this surface for its underlay and constrain blade roots to its triangles.
No turf definitions means no procedural lawn.

Validate IFC area/classification/placement after reload, then parse the GLB
and verify extras, transformed triangle area, elevation and upward normals.
Changing a Name must not change identity or classification. Re-running the
presentation phase must replace surfaces, not duplicate them.
