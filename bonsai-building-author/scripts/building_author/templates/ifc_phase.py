"""IFC phase, executed inside Bonsai through `execute_ifc_code`.

The host injects `ifcopenshell`, `ifc_api`, and `tool` into the namespace.
`compile_ifc` replaces the two placeholder constants below with real
literals; every other line runs exactly as written here.
"""

import dataclasses
import json
import math
import re
import sys
import uuid

import bmesh
import numpy as np
import shapely
from mathutils import Vector

try:
    from bonsai.bim.ifc import IfcStore
except ImportError:
    from blenderbim.bim.ifc import IfcStore

# `ifc_api` is `ifcopenshell.api`, which does not import its own submodules.
# Reaching `ifc_api.unit` and friends only works once they are imported.
for _submodule in (
    "unit",
    "root",
    "project",
    "context",
    "aggregate",
    "geometry",
    "spatial",
    "material",
    "style",
    "type",
    "feature",
    "pset",
    "system",
):
    __import__(f"ifcopenshell.api.{_submodule}")

# `ifcopenshell.util` needs the same treatment as `ifcopenshell.api`.
for _submodule in ("element", "representation"):
    __import__(f"ifcopenshell.util.{_submodule}")

# Bonsai already solves the roof solid: straight skeleton, gable handling,
# thickness extrusion normal to each plane, and the rafter edge cut. The
# skill supplies the overhang polygon and the per-edge gable flags.
from bonsai.bim.module.model.roof import generate_hipped_roof_bmesh

# IfcOpenShell already builds a window and a door from their lining and panel
# properties, as real swept solids carrying Lining, Framing and Glazing shape
# aspects. These are the settings it accepts, which is not the same set the
# schema puts on the property sets - a door leaf's framing is an input with no
# IFC attribute, and a window panel's OperationType an attribute with no
# geometric effect. Reading the field names off the generator is what keeps
# the two apart without a hand-maintained list.
from ifcopenshell.api.geometry.add_door_representation import (
    DoorLiningProperties,
    DoorPanelProperties,
)
from ifcopenshell.api.geometry.add_window_representation import (
    WindowLiningProperties,
    WindowPanelProperties,
)


BUILD_NAME = "@@BUILD_NAME@@"
OPERATIONS = json.loads("@@OPERATIONS@@")
TURFS = json.loads("@@TURFS@@")
ROOFS = json.loads("@@ROOFS@@")
WALLS = json.loads("@@WALLS@@")
SLABS = json.loads("@@SLABS@@")
SPACES = json.loads("@@SPACES@@")
COVERINGS = json.loads("@@COVERINGS@@")
RAILINGS = json.loads("@@RAILINGS@@")
GATES = json.loads("@@GATES@@")
GUTTERS = json.loads("@@GUTTERS@@")
EXTEND_TO_STRUCTURE = json.loads("@@EXTEND_TO_STRUCTURE@@")
OPENINGS = json.loads("@@OPENINGS@@")
COMPOSED_WINDOWS = json.loads("@@COMPOSED_WINDOWS@@")
SILLS = json.loads("@@SILLS@@")
CORNER_OPENINGS = json.loads("@@CORNER_OPENINGS@@")
PACKAGE_ROOT = "@@PACKAGE_ROOT@@"

# The window frame is the tested procedure rather than a copy inlined here,
# so IFC and the presentation build the same shape from the same code.
#
# Blender's interpreter outlives a run, so a package imported by an earlier
# one stays cached with its old code: edit a procedure, re-run, and the build
# silently repeats the previous geometry. A rebuild owns its output, so the
# package is dropped and re-imported rather than trusted to be current.
if PACKAGE_ROOT not in sys.path:
    sys.path.insert(0, PACKAGE_ROOT)
for _cached in [
    name
    for name in sys.modules
    if name == "building_author" or name.startswith("building_author.")
]:
    del sys.modules[_cached]
from building_author import (  # noqa: E402
    composed_windows,
    gutters,
    railings,
    roof_windows,
    sills,
    space_geometry,
    tiles,
    trims,
    window_assemblies,
)

UP = Vector((0.0, 0.0, 1.0))
_PLANAR_EPS = 1e-6


def covering_shell(bm, thickness):
    """A thin solid over the roof's sloping faces, for the IfcCovering body.

    IFC gets the covering as a real element with honest but coarse geometry;
    the presentation phase swaps in the tile field, linked by the same Tag.
    Putting 16k verts of tiles into the IFC would bloat it for no semantic
    gain.
    """

    verts = []
    faces = []
    for face in bm.faces:
        normal = face.normal.normalized()
        if normal.z <= _PLANAR_EPS:
            continue
        base = len(verts)
        count = len(face.verts)
        for vert in face.verts:
            verts.append(tuple(vert.co))
        for vert in face.verts:
            verts.append(tuple(vert.co + normal * thickness))
        faces.append(tuple(range(base + count - 1, base - 1, -1)))
        faces.append(tuple(range(base + count, base + count * 2)))
        for index in range(count):
            following = (index + 1) % count
            faces.append(
                (
                    base + index,
                    base + following,
                    base + count + following,
                    base + count + index,
                )
            )
    return verts, faces


def face_frames(bm, boundary):
    """Map each boundary edge index to the frame of the face rising from it.

    Roof windows are declared against a boundary edge, because edges are
    declared while faces are skeleton output whose numbering shifts. This is
    where that reference is resolved into a real face and its ``(origin,
    eave, up_slope, normal)`` frame, with the origin on the eave.
    """

    frames = {}
    for face in bm.faces:
        normal = face.normal.normalized()
        if normal.z <= _PLANAR_EPS:
            continue
        verts = [vert.co for vert in face.verts]
        eave_edge, lowest = None, None
        for index in range(len(verts)):
            start, end = verts[index], verts[(index + 1) % len(verts)]
            if abs(start.z - end.z) > _PLANAR_EPS:
                continue
            height = (start.z + end.z) / 2.0
            if lowest is None or height < lowest:
                lowest, eave_edge = height, (start.copy(), end.copy())
        if eave_edge is None:
            continue

        eave = (eave_edge[1] - eave_edge[0]).normalized()
        up_slope = normal.cross(eave)
        if up_slope.z < 0.0:
            eave, up_slope = -eave, -up_slope
            eave_edge = (eave_edge[1], eave_edge[0])

        midpoint = (eave_edge[0] + eave_edge[1]) / 2.0
        best, best_distance = None, None
        for index in range(len(boundary)):
            a = Vector((*boundary[index], 0.0))
            b = Vector((*boundary[(index + 1) % len(boundary)], 0.0))
            span = b - a
            length = span.length
            if length < _PLANAR_EPS:
                continue
            point = Vector((midpoint.x, midpoint.y, 0.0))
            t = max(0.0, min(1.0, (point - a).dot(span) / (length * length)))
            distance = (point - (a + span * t)).length
            if best_distance is None or distance < best_distance:
                best, best_distance = index, distance
        if best is not None:
            frames[best] = (eave_edge[0].copy(), eave, up_slope.normalized(),
                            normal)
    return frames


def verge_runs(bm):
    """Every raking free edge of a roof solid, as a placed run.

    `trims.edge_kind` does the classifying; this only harvests what it needs
    off the bmesh and turns the answer into a frame. An edge with anything
    other than two adjacent faces is skipped rather than guessed at - the
    solver produces none on a closed solid, and one that appears is not
    something a trim should be draped over regardless.

    Each run comes back as a `trims.VergeRun`, which names its own fields -
    two of them are perpendicular horizontal unit vectors that a positional
    tuple would let anyone transpose in silence.

    The frame's third axis is world up, always, whatever the rake does. That
    is the property the whole thing exists to hold: the section is stated in a
    vertical plane, so the board's vertical edges stay vertical. It is not
    returned, because it never varies.

    The frame is right-handed by construction - ``along`` is ``across x up`` -
    so no vert order and no face order can flip it. Orienting off the edge's
    own verts, which is what this did first, puts the board on the outboard
    side of about half the verges on any roof.
    """

    bm.normal_update()
    found = []
    for edge in bm.edges:
        if len(edge.link_faces) != 2:
            continue
        face_a, face_b = edge.link_faces
        span = edge.verts[1].co - edge.verts[0].co
        if span.length < _PLANAR_EPS:
            continue
        normal_a = face_a.normal.normalized()
        kind = trims.edge_kind_from_bmesh(edge)
        if kind != trims.VERGE:
            continue

        # Exactly one of the two is roof surface - that is what made this a
        # verge rather than a hip - so the board sits against it unambiguously.
        face = face_a if normal_a.z > trims.UPWARD_EPS else face_b
        low, high = sorted(
            (edge.verts[0].co.copy(), edge.verts[1].co.copy()),
            key=lambda point: point.z,
        )
        direction = (high - low).normalized()

        plan = Vector((direction.x, direction.y, 0.0))
        if plan.length < _PLANAR_EPS:
            continue  # a vertical arris is not a rake
        plan.normalize()
        across = plan.cross(UP)
        interior = face.normal.cross(Vector(trims.face_edge_direction(edge, face)))
        if across.dot(interior) < 0.0:
            across = -across
        along = across.cross(UP)

        # The rake, in the frame: no across component (it lies in the gable
        # plane), rising by its own pitch. Its `along` component is what keeps
        # the extrusion oblique rather than parallel to the profile plane.
        rake = (0.0, direction.dot(UP), direction.dot(along))
        found.append(
            trims.VergeRun(
                origin=low,
                across=across,
                along=along,
                rake=rake,
                length=(high - low).length,
            )
        )
    return found


def roof_bmesh(roof):
    """Build the roof solid from its overhang polygon and gable flags."""

    bm = bmesh.new()
    corners = [
        bm.verts.new((x, y, roof["base_z"]))
        for x, y in roof["overhang_boundary"]
    ]
    bm.verts.ensure_lookup_table()
    angle_layer = bm.edges.layers.float.new("BBIM_gable_roof_angles")
    gables = set(roof["gable_indices"])
    total = len(corners)
    for index in range(total):
        edge = bm.edges.new((corners[index], corners[(index + 1) % total]))
        # Bonsai reads a right angle on a footprint edge as "make this a gable".
        edge[angle_layer] = math.pi / 2 if index in gables else 0.0
    generate_hipped_roof_bmesh(
        bm,
        "ANGLE",
        0.0,
        roof["thickness"],
        math.radians(roof["angle"]),
        math.radians(roof["rafter_edge_angle"]),
        mutate_current_bmesh=True,
    )
    return bm


def roof_role_mesh(solid, roof):
    """Convert one closed roof solid into Top, Ceiling, and Side face roles."""

    solid.normal_update()
    solid.verts.index_update()
    pitch = math.radians(roof["angle"])
    boundary = roof["overhang_boundary"]
    signed_area = sum(
        start[0] * end[1] - end[0] * start[1]
        for start, end in zip(boundary, boundary[1:] + boundary[:1])
    )
    outward_sign = 1.0 if signed_area > 0.0 else -1.0
    expected_planes = []
    for index, (start, end) in enumerate(
        zip(boundary, boundary[1:] + boundary[:1])
    ):
        if index in roof["gable_indices"]:
            continue
        dx, dy = end[0] - start[0], end[1] - start[1]
        length = math.hypot(dx, dy)
        outward = (dy * outward_sign / length, -dx * outward_sign / length)
        expected_planes.append(
            (
                Vector(
                    (
                        outward[0] * math.sin(pitch),
                        outward[1] * math.sin(pitch),
                        math.cos(pitch),
                    )
                ),
                Vector((start[0], start[1], roof["base_z"])),
            )
        )
    vertices = [tuple(vertex.co) for vertex in solid.verts]
    faces = []
    slots = []
    for face in solid.faces:
        faces.append([vertex.index for vertex in face.verts])
        normal = face.normal.normalized()
        if any(
            (normal - expected).length <= _PLANAR_EPS
            and all(
                abs(expected.dot(vertex.co - anchor)) <= _PLANAR_EPS
                for vertex in face.verts
            )
            for expected, anchor in expected_planes
        ):
            slots.append("top")
        elif any(
            (normal + expected).length <= _PLANAR_EPS
            and all(
                abs(
                    expected.dot(vertex.co - anchor) + roof["thickness"]
                ) <= _PLANAR_EPS
                for vertex in face.verts
            )
            for expected, anchor in expected_planes
        ):
            slots.append("ceiling")
        else:
            slots.append("side")
    missing = {"top", "ceiling", "side"} - set(slots)
    if missing:
        raise RuntimeError(
            f"{roof['key']} has no {', '.join(sorted(missing))} roof faces"
        )
    return vertices, faces, [], slots


def roof_clipping_bmesh(solid, termination):
    """Extract one roof surface, oriented downward for wall clipping."""

    solid.normal_update()
    clipping = bmesh.new()
    vertex_map = {}
    for face in solid.faces:
        normal = face.normal.normalized()
        if termination == "UNDERSIDE" and normal.z >= -0.5:
            continue
        if termination == "TOP_SURFACE" and normal.z <= 0.5:
            continue
        vertices = []
        for vertex in face.verts:
            mapped = vertex_map.get(vertex.index)
            if mapped is None:
                mapped = clipping.verts.new(vertex.co)
                vertex_map[vertex.index] = mapped
            vertices.append(mapped)
        clipping_face = clipping.faces.new(vertices)
        clipping_face.normal_update()
        if clipping_face.normal.z > 0.0:
            clipping_face.normal_flip()
    if not clipping.faces:
        clipping.free()
        surface = (
            "downward-facing underside"
            if termination == "UNDERSIDE"
            else "upward-facing top surface"
        )
        raise RuntimeError(f"the relating roof has no {surface}")
    return clipping


def slab_clipping_bmesh(surfaces):
    """Build downward-oriented slab clipping planes in project coordinates."""

    clipping = bmesh.new()
    for boundary, height in surfaces:
        vertices = [clipping.verts.new((x, y, height)) for x, y in boundary]
        face = clipping.faces.new(vertices)
        face.normal_update()
        if face.normal.z > 0.0:
            face.normal_flip()
    return clipping


def slab_clipping_surfaces(slab, wall, termination):
    """Select slab surfaces whose plan union fully covers this wall."""

    surfaces = (
        [(
            slab["boundary"],
            slab["base_z"]
            + (slab["thickness"] if termination == "TOP_SURFACE" else 0.0),
        )]
        if slab["boundary"] is not None
        else [
            (
                tier["boundary"],
                tier["base_z"]
                + (tier["height"] if termination == "TOP_SURFACE" else 0.0),
            )
            for tier in slab["tiers"]
        ]
    )
    wall_shape = shapely.Polygon(wall["footprint"])
    applicable = [
        (boundary, height, shapely.Polygon(boundary))
        for boundary, height in surfaces
        if height > wall["base_z"] + _PLANAR_EPS
        and shapely.Polygon(boundary).intersection(wall_shape).area
        > _PLANAR_EPS * _PLANAR_EPS
    ]
    coverage = shapely.unary_union(
        [surface[2] for surface in applicable]
    ).buffer(_PLANAR_EPS) if applicable else shapely.Polygon()
    if not coverage.covers(wall_shape):
        raise RuntimeError(
            f"{slab['key']} must cover {wall['key']} completely and have "
            "its selected termination surface above the wall base"
        )
    return [(boundary, height) for boundary, height, _ in applicable]


def generator_kwargs(settings, declared):
    """Keep only what IfcOpenShell's generator declares it accepts."""

    allowed = {field.name for field in dataclasses.fields(settings)}
    return {
        name: value
        for name, value in declared.items()
        # An unset optional is what the generator's own default already is,
        # so leaving it out and passing None mean the same thing to it.
        if name in allowed and value is not None
    }


def snake(name):
    """`LiningToPanelOffsetX` -> `lining_to_panel_offset_x`.

    Bonsai's own window and door tools read their parameters out of the
    `BBIM_Window` and `BBIM_Door` psets in snake case, while IFC and
    IfcOpenShell's generators name the same quantities in the schema's case.
    Converting mechanically is what keeps one declared value from having to be
    written out twice and drifting.
    """

    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def axis_placement(model, location, axis=None, ref_direction=None):
    """An `IfcAxis2Placement3D`, with its two optional direction vectors."""

    def direction(vector):
        return model.create_entity(
            "IfcDirection", DirectionRatios=[float(value) for value in vector]
        )

    return model.create_entity(
        "IfcAxis2Placement3D",
        Location=model.create_entity(
            "IfcCartesianPoint",
            Coordinates=[float(value) for value in location],
        ),
        Axis=direction(axis) if axis is not None else None,
        RefDirection=direction(ref_direction) if ref_direction is not None else None,
    )


def extruded_rectangle(
    model, context, x_dim, y_dim, depth, location, axis=None, ref_direction=None
):
    """A rectangle swept into a solid: what an opening should be made of.

    An opening is a box, and IFC has a word for a box - a rectangle profile
    swept along an axis. Written as a face set instead it still cuts the same
    hole, but its width, height and depth stop being readable numbers and
    become a coordinate list a consumer has to bound-box to recover. It is
    also what Bonsai's own `generate_opening_from_filling` writes.
    """

    return model.create_entity(
        "IfcShapeRepresentation",
        ContextOfItems=context,
        RepresentationIdentifier="Body",
        RepresentationType="SweptSolid",
        Items=[
            model.create_entity(
                "IfcExtrudedAreaSolid",
                SweptArea=model.create_entity(
                    "IfcRectangleProfileDef",
                    ProfileType="AREA",
                    XDim=x_dim,
                    YDim=y_dim,
                ),
                Position=axis_placement(model, location, axis, ref_direction),
                ExtrudedDirection=model.create_entity(
                    "IfcDirection", DirectionRatios=(0.0, 0.0, 1.0)
                ),
                Depth=depth,
            )
        ],
    )


def extruded_xz_polygon(model, context, outline, depth):
    """An arbitrary elevation outline swept through a wall along local Y.

    ``outline`` is expressed in the filling element's XZ plane: X runs along
    the host wall and Z runs up.  IFC profiles are two-dimensional, so those
    coordinates become the profile's local XY while its placement maps local
    Y back onto world Z.  The profile starts half a depth behind the filling
    plane and sweeps the full depth forwards, reaching both wall faces.
    """

    points = [[float(x), float(z)] for x, z in outline]
    if len(points) < 3:
        raise ValueError("an extruded XZ polygon needs at least three points")
    if points[0] == points[-1]:
        points.pop()
    if len(points) < 3:
        raise ValueError("an extruded XZ polygon needs at least three points")
    curve = model.create_entity(
        "IfcIndexedPolyCurve",
        Points=model.create_entity("IfcCartesianPointList2D", CoordList=points),
        Segments=[
            model.createIfcLineIndex(tuple(range(1, len(points) + 1)) + (1,))
        ],
        SelfIntersect=False,
    )
    profile = model.create_entity(
        "IfcArbitraryClosedProfileDef",
        ProfileType="AREA",
        OuterCurve=curve,
    )
    solid = model.create_entity(
        "IfcExtrudedAreaSolid",
        SweptArea=profile,
        Position=axis_placement(
            model,
            (0.0, -depth / 2.0, 0.0),
            axis=(0.0, -1.0, 0.0),
            ref_direction=(1.0, 0.0, 0.0),
        ),
        # The placement's local Z points towards world -Y, so a local -Z
        # extrusion runs forwards through the wall in world +Y.
        ExtrudedDirection=model.create_entity(
            "IfcDirection", DirectionRatios=(0.0, 0.0, -1.0)
        ),
        Depth=depth,
    )
    return model.create_entity(
        "IfcShapeRepresentation",
        ContextOfItems=context,
        RepresentationIdentifier="Body",
        RepresentationType="SweptSolid",
        Items=[solid],
    )


def split_by_role(mesh):
    """Group a mesh's faces by the material role named for each.

    A roof or procedure says which role owns each face; IFC says the same
    thing with an `IfcShapeAspect` per part. Splitting the mesh accordingly is
    what lets one BIM element carry all of its materials itself.

    Every part keeps the whole vertex list and indexes into it, rather than
    carrying a compacted one of its own: `add_mesh_representation` reads its
    vertices as a rectangular array, so parts of differing vertex counts are
    not something it can take. Unreferenced points in a face set are legal,
    and at the size of a window the duplication is a few dozen coordinates.

    Roles are returned title-cased, because that is the name the shape aspect
    and its material constituent share.
    """

    _, faces, _, slots = mesh
    grouped = {}
    for face, role in zip(faces, slots):
        grouped.setdefault(role, []).append(list(face))
    return [(role.title(), grouped[role]) for role in sorted(grouped)]


def assign_role_split_body(model, context, entity, mesh, materials_by_role):
    """Give `entity` a body built from a role-split mesh: one representation,
    one shape aspect per role the mesh names, and every declared material
    bound to its aspect - the shared shape roofs, composed windows, and
    railings need, since each carries more than one material on one product.

    `materials_by_role` is already keyed by the exact aspect name
    (`split_by_role`'s own `role.title()` casing) - the same contract
    `roof_payload`, `opening_payload`, and `railing_payload` already produce.

    A role the caller left undeclared falls back to whichever material was
    declared first, rather than arriving unstyled - what Bonsai's own window
    tool does.
    """

    parts = split_by_role(mesh)
    frame_verts = [list(vertex) for vertex in mesh[0]]
    entity.Representation = model.create_entity(
        "IfcProductDefinitionShape", Representations=[]
    )
    representation = ifc_api.geometry.add_mesh_representation(
        model,
        context=context,
        vertices=[frame_verts] * len(parts),
        faces=[part[1] for part in parts],
    )
    ifc_api.geometry.assign_representation(
        model, product=entity, representation=representation
    )
    for index, (role, _) in enumerate(parts):
        ifc_api.geometry.add_shape_aspect(
            model,
            role,
            items=[representation.Items[index]],
            representation=representation,
            part_of_product=entity.Representation,
        )
    if materials_by_role:
        declared = {
            role: materials[material_key]
            for role, material_key in materials_by_role.items()
        }
        fallback = next(iter(declared.values()))
        ifc_api.material.set_shape_aspect_constituents(
            model,
            element=entity,
            context=context,
            materials={role: declared.get(role, fallback) for role, _ in parts},
        )


def placement_matrix(angle, position):
    """A world matrix turned about Z, at an already-resolved world position.

    The compiler solves both, because a `NEGATIVE` opening is a half turn plus
    a move to the opposite corner and that is arithmetic, not geometry.
    """

    matrix = np.eye(4)
    matrix[0, 0] = math.cos(angle)
    matrix[0, 1] = -math.sin(angle)
    matrix[1, 0] = math.sin(angle)
    matrix[1, 1] = math.cos(angle)
    matrix[:3, 3] = position
    return matrix


def stable_guid(key):
    value = uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"bonsai-building-author:{BUILD_NAME}:{key}",
    )
    return ifcopenshell.guid.compress(value.hex)


def extensions_for(relating_key):
    return [
        item
        for item in EXTEND_TO_STRUCTURE
        if item["relating_element"] == relating_key
    ]


def apply_extension(relating_entity, extension, clipping):
    """Resolve one wall against its declared structure surface."""

    wall_entity = entities[extension["related_element"]]
    tool.Model.clip_wall_to_slab(wall_entity, clipping)
    body = ifcopenshell.util.representation.get_representation(
        wall_entity, "Model", "Body", "MODEL_VIEW"
    )
    boolean = next(
        (
            item
            for item in body.Items
            if item.is_a("IfcBooleanResult")
        ),
        None,
    ) if body else None
    if not body or not ifc_api.geometry.validate_type(
        model,
        representation=body,
        preferred_item=boolean,
    ):
        raise RuntimeError(
            f"could not validate the clipped body of "
            f"{extension['related_element']}"
        )

    common_data = ifcopenshell.util.element.get_pset(
        wall_entity, "Pset_WallCommon"
    )
    common = (
        model.by_id(common_data["id"])
        if common_data
        else ifc_api.pset.add_pset(
            model, product=wall_entity, name="Pset_WallCommon"
        )
    )
    ifc_api.pset.edit_pset(
        model,
        pset=common,
        properties={"ExtendToStructure": True},
    )

    relationship = ifc_api.geometry.connect_element(
        model,
        relating_element=relating_entity,
        related_element=wall_entity,
        description="TOP",
    )
    relationship.GlobalId = stable_guid(extension["key"])


def root_entity(model, operation, ifc_class):
    entity = ifc_api.root.create_entity(
        model,
        ifc_class=ifc_class,
        name=operation["parameters"]["name"],
    )
    entity.GlobalId = stable_guid(operation["key"])
    if hasattr(entity, "Tag"):
        entity.Tag = operation["key"]
    return entity


def add_layer_set(operation, ifc_class):
    """Build the type entity and `IfcMaterialLayerSet` a wall or slab type
    carries. The layer set lives on the type either way; only the occurrence
    that assigns it decides which axis it stacks along.
    """

    parameters = operation["parameters"]
    entity = root_entity(model, operation, ifc_class)
    entity.PredefinedType = parameters["predefined_type"]
    layer_set = ifc_api.material.add_material_set(
        model,
        name=parameters["name"],
        set_type="IfcMaterialLayerSet",
    )
    for layer in parameters["layers"]:
        material_layer = ifc_api.material.add_layer(
            model,
            layer_set=layer_set,
            material=materials[layer["material"]],
        )
        attributes = {
            "LayerThickness": layer["thickness"],
            "Priority": layer["priority"],
        }
        for attribute, value in (
            ("Name", layer["name"]),
            ("Category", layer["category"]),
            ("IsVentilated", layer["is_ventilated"]),
        ):
            if value is not None:
                attributes[attribute] = value
        ifc_api.material.edit_layer(
            model,
            layer=material_layer,
            attributes=attributes,
        )
    ifc_api.material.assign_material(
        model,
        products=[entity],
        type="IfcMaterialLayerSet",
        material=layer_set,
    )
    return entity, layer_set


IfcStore.purge()
model = ifc_api.project.create_file(version="IFC4")
tool.Ifc.set(model)

entities = {}
materials = {}
layer_sets = {}
window_types = {}

project_operation = next(
    operation for operation in OPERATIONS if operation["kind"] == "project"
)
project_entity = root_entity(model, project_operation, "IfcProject")
entities[project_operation["key"]] = project_entity

length_unit = ifc_api.unit.add_si_unit(model, unit_type="LENGTHUNIT")
area_unit = ifc_api.unit.add_si_unit(model, unit_type="AREAUNIT")
volume_unit = ifc_api.unit.add_si_unit(model, unit_type="VOLUMEUNIT")
ifc_api.unit.assign_unit(
    model,
    units=[length_unit, area_unit, volume_unit],
)

model_context = ifc_api.context.add_context(model, context_type="Model")
body_context = ifc_api.context.add_context(
    model,
    context_type="Model",
    context_identifier="Body",
    target_view="MODEL_VIEW",
    parent=model_context,
)
# A wall's reference line lives in Plan/Axis/GRAPH_VIEW. Everything that reads
# a wall - the layer set usage, the corner solver, Bonsai's own wall tools -
# measures from it, so the context is created whether or not walls follow.
plan_context = ifc_api.context.add_context(model, context_type="Plan")
axis_context = ifc_api.context.add_context(
    model,
    context_type="Plan",
    context_identifier="Axis",
    target_view="GRAPH_VIEW",
    parent=plan_context,
)

spatial_settings = {
    "site": ("IfcSite", "project"),
    "building": ("IfcBuilding", "site"),
    "storey": ("IfcBuildingStorey", "building"),
}
for kind in ("site", "building", "storey"):
    ifc_class, parent_role = spatial_settings[kind]
    for operation in (
        item for item in OPERATIONS if item["kind"] == kind
    ):
        entity = root_entity(model, operation, ifc_class)
        if kind == "storey":
            entity.Elevation = operation["parameters"]["elevation"]
        parent = entities[operation["references"][parent_role]]
        ifc_api.aggregate.assign_object(
            model,
            products=[entity],
            relating_object=parent,
        )
        matrix = np.eye(4)
        if kind == "storey":
            matrix[2, 3] = operation["parameters"]["elevation"]
        ifc_api.geometry.edit_object_placement(
            model,
            product=entity,
            matrix=matrix,
            is_si=True,
        )
        entities[operation["key"]] = entity

for operation in (
    item for item in OPERATIONS if item["kind"] == "material"
):
    parameters = operation["parameters"]
    material = ifc_api.material.add_material(
        model,
        name=parameters["ifc_name"],
        category=parameters["category"],
    )
    color = parameters["base_color"]
    style = ifc_api.style.add_style(
        model,
        name=f"BA::{operation['key']}",
    )
    ifc_api.style.add_surface_style(
        model,
        style=style,
        ifc_class="IfcSurfaceStyleShading",
        attributes={
            "SurfaceColour": {
                "Name": None,
                "Red": color[0],
                "Green": color[1],
                "Blue": color[2],
            },
            "Transparency": 1.0 - parameters["alpha"],
        },
    )
    ifc_api.style.assign_material_style(
        model,
        material=material,
        style=style,
        context=body_context,
    )
    materials[operation["key"]] = material

# A wall type carries the layer set; each wall occurrence carries a usage that
# places that same set against its reference line. Stating the layers once, on
# the type, is why a wall never restates its own thickness.
for operation in (
    item for item in OPERATIONS if item["kind"] == "wall-type"
):
    entity, layer_set = add_layer_set(operation, "IfcWallType")
    entities[operation["key"]] = entity
    layer_sets[operation["key"]] = layer_set

# A slab type carries the same kind of layer set as a wall type, stacked
# along the occurrence's AXIS3 instead of AXIS2 - across its depth rather
# than across its thickness.
for operation in (
    item for item in OPERATIONS if item["kind"] == "slab-type"
):
    entity, layer_set = add_layer_set(operation, "IfcSlabType")
    entities[operation["key"]] = entity
    layer_sets[operation["key"]] = layer_set

wall_operations = {
    operation["key"]: operation
    for operation in OPERATIONS
    if operation["kind"] == "wall"
}
for wall in WALLS["walls"]:
    operation = wall_operations[wall["key"]]
    start, end = wall["start"], wall["end"]
    delta_x = end[0] - start[0]
    delta_y = end[1] - start[1]
    angle = math.atan2(delta_y, delta_x)

    entity = root_entity(model, operation, "IfcWall")
    ifc_api.type.assign_type(
        model,
        related_objects=[entity],
        relating_type=entities[wall["wall_type"]],
    )
    # assign_type copies the type's layer set onto the occurrence as a usage,
    # which is the association IFC wants; the offset and sense still have to
    # say where that set sits relative to this wall's reference line.
    usage = ifcopenshell.util.element.get_material(entity)
    if usage is None or not usage.is_a("IfcMaterialLayerSetUsage"):
        usage = ifc_api.material.assign_material(
            model,
            products=[entity],
            type="IfcMaterialLayerSetUsage",
            material=layer_sets[wall["wall_type"]],
        )
        usage = ifcopenshell.util.element.get_material(entity)
    ifc_api.material.edit_layer_usage(
        model,
        usage=usage,
        attributes={
            # AXIS2 is the only value IFC allows for a wall: the layers stack
            # across the wall, not along or up it.
            "LayerSetDirection": "AXIS2",
            "DirectionSense": wall["direction_sense"],
            "OffsetFromReferenceLine": wall["offset_from_reference_line"],
        },
    )

    matrix = np.eye(4)
    matrix[0, 0] = math.cos(angle)
    matrix[0, 1] = -math.sin(angle)
    matrix[1, 0] = math.sin(angle)
    matrix[1, 1] = math.cos(angle)
    matrix[:3, 3] = (start[0], start[1], wall["base_z"])
    ifc_api.geometry.edit_object_placement(
        model,
        product=entity,
        matrix=matrix,
        is_si=True,
    )
    # The reference line, in wall-local coordinates where it runs along +X.
    ifc_api.geometry.assign_representation(
        model,
        product=entity,
        representation=ifc_api.geometry.add_axis_representation(
            model,
            context=axis_context,
            axis=((0.0, 0.0), (math.hypot(delta_x, delta_y), 0.0)),
        ),
    )
    ifc_api.spatial.assign_container(
        model,
        products=[entity],
        relating_structure=entities[wall["storey"]],
    )
    entities[wall["key"]] = entity

# Junctions before bodies: the body of a wall is a function of its
# connections, so every connection has to exist before any wall regenerates.
for junction in WALLS["junctions"]:
    ifc_api.geometry.connect_path(
        model,
        relating_element=entities[junction["relating"]],
        related_element=entities[junction["related"]],
        relating_connection=junction["relating_connection"],
        related_connection=junction["related_connection"],
    )

for wall in WALLS["walls"]:
    # IfcOpenShell owns the corner: it reads the layer priorities and the
    # connection types and produces the mitres, butts, and notches. The skill
    # supplies the declaration and stays out of the geometry.
    ifc_api.geometry.regenerate_wall_representation(
        model,
        wall=entities[wall["key"]],
        length=math.hypot(
            wall["end"][0] - wall["start"][0],
            wall["end"][1] - wall["start"][1],
        ),
        height=wall["height"],
    )

# A corner window's own two openings each void only their own host, so
# neither ever reaches the mitre `connect_path`/`regenerate_wall_representation`
# just resolved between the two walls above. The same cutter geometry clears
# both walls, but IFC4's singular `VoidsElements` inverse requires a separate
# opening occurrence for each host.
for corner in CORNER_OPENINGS:
    size = corner["size"]
    representation = extruded_rectangle(
        model,
        body_context,
        x_dim=size["along"],
        y_dim=size["through"],
        depth=size["height"],
        location=(0.0, 0.0, 0.0),
    )
    for host_key in (corner["wall_a"], corner["wall_b"]):
        opening_key = f"{corner['key']}.opening.{host_key}"
        opening = ifc_api.root.create_entity(
            model,
            ifc_class="IfcOpeningElement",
            name=f"{corner['name']} Opening - {host_key}",
            predefined_type="OPENING",
        )
        opening.GlobalId = stable_guid(opening_key)
        opening.Tag = opening_key
        ifc_api.geometry.assign_representation(
            model, product=opening, representation=representation
        )
        relation = ifc_api.feature.add_feature(
            model, feature=opening, element=entities[host_key]
        )
        relation.GlobalId = stable_guid(f"{corner['key']}.voids.{host_key}")
        # Set the host first: edit_object_placement converts this common
        # world-space cutter frame into each host's own relative placement.
        ifc_api.geometry.edit_object_placement(
            model,
            product=opening,
            matrix=placement_matrix(corner["angle"], corner["position"]),
            is_si=True,
        )
        entities[opening_key] = opening

# A virtual element is placed exactly like a wall's reference line - the same
# rotation onto its axis, the same storey container - but carries no layer
# set and no body: IFC's own answer to a boundary with nothing built there.
for operation in (
    item for item in OPERATIONS if item["kind"] == "virtual-element"
):
    parameters = operation["parameters"]
    start, end = parameters["axis"]
    delta_x = end[0] - start[0]
    delta_y = end[1] - start[1]
    angle = math.atan2(delta_y, delta_x)
    storey = entities[operation["references"]["storey"]]

    entity = root_entity(model, operation, "IfcVirtualElement")

    matrix = np.eye(4)
    matrix[0, 0] = math.cos(angle)
    matrix[0, 1] = -math.sin(angle)
    matrix[1, 0] = math.sin(angle)
    matrix[1, 1] = math.cos(angle)
    matrix[:3, 3] = (start[0], start[1], storey.Elevation)
    ifc_api.geometry.edit_object_placement(
        model, product=entity, matrix=matrix, is_si=True
    )
    ifc_api.geometry.assign_representation(
        model,
        product=entity,
        representation=ifc_api.geometry.add_axis_representation(
            model,
            context=axis_context,
            axis=((0.0, 0.0), (math.hypot(delta_x, delta_y), 0.0)),
        ),
    )
    ifc_api.spatial.assign_container(
        model, products=[entity], relating_structure=storey
    )
    entities[operation["key"]] = entity

for slab in SLABS:
    entity = ifc_api.root.create_entity(
        model,
        ifc_class="IfcSlab",
        name=slab["name"],
        predefined_type=slab["predefined_type"],
    )
    entity.GlobalId = stable_guid(slab["key"])
    entity.Tag = slab["key"]

    matrix = np.eye(4)
    matrix[2, 3] = slab["base_z"]
    ifc_api.geometry.edit_object_placement(
        model, product=entity, matrix=matrix, is_si=True
    )

    if slab["tiers"]:
        # Tiers have different profiles, so they are not a layer set - they
        # are one body of several extrusions, and one material for all of
        # them. `Items` is a set, so several swept solids in a single
        # SweptSolid representation is exactly what the schema allows.
        entity.Representation = model.create_entity(
            "IfcProductDefinitionShape",
            Representations=[
                model.create_entity(
                    "IfcShapeRepresentation",
                    ContextOfItems=body_context,
                    RepresentationIdentifier="Body",
                    RepresentationType="SweptSolid",
                    Items=[
                        model.create_entity(
                            "IfcExtrudedAreaSolid",
                            SweptArea=model.create_entity(
                                "IfcArbitraryClosedProfileDef",
                                ProfileType="AREA",
                                OuterCurve=model.create_entity(
                                    "IfcPolyline",
                                    Points=[
                                        model.create_entity(
                                            "IfcCartesianPoint",
                                            Coordinates=[float(x), float(y)],
                                        )
                                        for x, y in (
                                            tier["boundary"] + tier["boundary"][:1]
                                        )
                                    ],
                                ),
                            ),
                            # Each tier is placed at its own elevation
                            # relative to the slab's own base, which the
                            # compiler already stacked.
                            Position=axis_placement(
                                model, (0.0, 0.0, tier["base_z"] - slab["base_z"])
                            ),
                            ExtrudedDirection=model.create_entity(
                                "IfcDirection", DirectionRatios=(0.0, 0.0, 1.0)
                            ),
                            Depth=tier["height"],
                        )
                        for tier in slab["tiers"]
                    ],
                )
            ],
        )
        ifc_api.material.assign_material(
            model,
            products=[entity],
            type="IfcMaterial",
            material=materials[slab["material"]],
        )
    else:
        ifc_api.type.assign_type(
            model,
            related_objects=[entity],
            relating_type=entities[slab["slab_type"]],
        )
        # A slab's depth comes from its extrusion, not a positioned layer set
        # the way a wall's AXIS2 usage is - AXIS3 only has to say which axis
        # the layers split across on import.
        usage = ifcopenshell.util.element.get_material(entity)
        if usage is None or not usage.is_a("IfcMaterialLayerSetUsage"):
            usage = ifc_api.material.assign_material(
                model,
                products=[entity],
                type="IfcMaterialLayerSetUsage",
                material=layer_sets[slab["slab_type"]],
            )
            usage = ifcopenshell.util.element.get_material(entity)
        usage.LayerSetDirection = "AXIS3"

        representation = ifc_api.geometry.add_slab_representation(
            model,
            context=body_context,
            depth=slab["thickness"],
            polyline=[tuple(point) for point in slab["boundary"]],
        )
        ifc_api.geometry.assign_representation(
            model, product=entity, representation=representation
        )
        # Written so a script-authored slab stays editable by Bonsai's own
        # slab tool, exactly as BBIM_Roof does for a script-authored roof. A
        # tiered slab gets none: its body is not what that tool regenerates,
        # and claiming otherwise would invite it to flatten the tiers.
        pset = ifc_api.pset.add_pset(
            model, product=entity, name="EPset_Parametric"
        )
        ifc_api.pset.edit_pset(
            model, pset=pset, properties={"Engine": "Bonsai.DumbLayer3"}
        )

    ifc_api.spatial.assign_container(
        model, products=[entity], relating_structure=entities[slab["storey"]]
    )
    entities[slab["key"]] = entity
    walls_by_key = {wall["key"]: wall for wall in WALLS["walls"]}
    for extension in extensions_for(slab["key"]):
        wall = walls_by_key[extension["related_element"]]
        surfaces = slab_clipping_surfaces(
            slab, wall, extension["termination"]
        )
        clipping = slab_clipping_bmesh(surfaces)
        try:
            apply_extension(entity, extension, clipping)
        finally:
            clipping.free()

for railing in RAILINGS:
    start, end = railing["start"], railing["end"]
    delta_x = end[0] - start[0]
    delta_y = end[1] - start[1]
    length = math.hypot(delta_x, delta_y)
    angle = math.atan2(delta_y, delta_x)

    # The chosen profile's own design, in the path's own local frame - X
    # along the run, Y across it, Z up from the run's own base - the same
    # frame a roof window's procedure builds in before being placed on its
    # roof face.
    mesh = railings.profile(railing["profile"]).geometry(
        length,
        railing["height"],
        start_post=railing["start_post"],
        end_post=railing["end_post"],
    )

    entity = ifc_api.root.create_entity(
        model,
        ifc_class="IfcRailing",
        name=railing["name"],
        predefined_type=railing["predefined_type"],
    )
    entity.GlobalId = stable_guid(railing["key"])
    entity.Tag = railing["key"]
    if railing["object_type"] is not None:
        entity.ObjectType = railing["object_type"]

    # One shape aspect per part the chosen profile's mesh named - Post, Rail
    # and Infill for a guardrail; Shoe and Glazing for a balustrade; Post and
    # Infill for a fence - so the one product can carry every material its
    # design actually has, exactly as a window carries its Lining, Framing
    # and Glazing.
    assign_role_split_body(model, body_context, entity, mesh, railing["materials"])

    ifc_api.geometry.edit_object_placement(
        model,
        product=entity,
        matrix=placement_matrix(angle, (start[0], start[1], railing["base_z"])),
        is_si=True,
    )
    ifc_api.spatial.assign_container(
        model, products=[entity], relating_structure=entities[railing["storey"]]
    )

    pset = ifc_api.pset.add_pset(model, product=entity, name="Pset_RailingCommon")
    ifc_api.pset.edit_pset(model, pset=pset, properties={"Height": railing["height"]})

    entities[railing["key"]] = entity

for gate in GATES:
    # The declaration path is the clear passage. Each product procedure adds
    # its measured support posts outside local X=0..OverallWidth, preserving
    # the IFC distinction between opening width and installed assembly width.
    mesh = railings.gate_profile(gate["profile"]).geometry(
        gate["passage_width"], gate["height"], gate["leaves"]
    )
    entity = ifc_api.root.create_entity(
        model,
        ifc_class="IfcDoor",
        name=gate["name"],
        predefined_type="GATE",
    )
    entity.GlobalId = stable_guid(gate["key"])
    entity.Tag = gate["key"]
    entity.OverallWidth = gate["passage_width"]
    entity.OverallHeight = gate["height"]
    entity.OperationType = gate["operation_type"]

    assign_role_split_body(model, body_context, entity, mesh, gate["materials"])
    ifc_api.geometry.edit_object_placement(
        model,
        product=entity,
        matrix=placement_matrix(gate["angle"], gate["position"]),
        is_si=True,
    )
    ifc_api.spatial.assign_container(
        model, products=[entity], relating_structure=entities[gate["storey"]]
    )

    pset = ifc_api.pset.add_pset(model, product=entity, name="Pset_DoorCommon")
    ifc_api.pset.edit_pset(model, pset=pset, properties={"IsExternal": True})

    # Deliberately no opening, IfcRelFillsElement, or BBIM_Door. A boundary
    # gate is a free-standing IfcDoor(GATE), and this custom product mesh is
    # not the lining/leaf body Bonsai's stock door generator would recreate.
    entities[gate["key"]] = entity


def section_profile(model, name, ring):
    """A gutter's own section, as an `IfcArbitraryClosedProfileDef`.

    `gutters.py` states a section as `(u up, v toward the building)`, which
    reads like a manufacturer's drawing. The profile plane an extrusion
    sweeps is placed with its own X up and its Y across, and that Y comes out
    of the cross product pointing *away* from the building - so `v` is
    negated here, once, at the single seam between the two frames rather than
    inside the procedure that has no business knowing about IFC placements.
    """

    return model.create_entity(
        "IfcArbitraryClosedProfileDef",
        ProfileType="AREA",
        ProfileName=name,
        OuterCurve=model.create_entity(
            "IfcPolyline",
            Points=[
                model.create_entity(
                    "IfcCartesianPoint", Coordinates=[float(u), float(-v)]
                )
                for u, v in ring
            ],
        ),
    )


def mitre_half_space(model, normal, at_x):
    """A vertical half-space cutting at 45 degrees in plan, in the run's own frame.

    Stated in the **object** frame, not the swept solid's `Position` frame:
    `IfcHalfSpaceSolid` is resolved against the representation's own
    coordinates, so a plane written in the extrusion's frame silently cuts
    nothing - no error, just an unclipped solid. The run's direction
    therefore has to live in the element's `ObjectPlacement`, which is what
    also keeps this normal purely local.
    """

    return model.create_entity(
        "IfcHalfSpaceSolid",
        BaseSurface=model.create_entity(
            "IfcPlane",
            Position=axis_placement(
                model,
                (at_x, 0.0, 0.0),
                axis=(normal[0], normal[1], 0.0),
                ref_direction=(0.0, 0.0, 1.0),
            ),
        ),
        AgreementFlag=False,
    )


def gutter_body(model, context, profile_entity, length, overrun, ends):
    """One run swept along itself, then cut back at whichever ends mitre.

    The extrusion overruns both ends so a mitre plane has material to cut;
    stopping it exactly on the corner leaves the cut coplanar with the end
    face and the boolean nothing to resolve. An end that stop-ends instead is
    not cut at all - the overrun is simply not applied there.
    """

    start_overrun = overrun if ends["start"]["kind"] == "mitre" else 0.0
    end_overrun = overrun if ends["end"]["kind"] == "mitre" else 0.0
    solid = model.create_entity(
        "IfcExtrudedAreaSolid",
        SweptArea=profile_entity,
        Position=axis_placement(
            model,
            (-start_overrun, 0.0, 0.0),
            axis=(1.0, 0.0, 0.0),
            ref_direction=(0.0, 0.0, 1.0),
        ),
        ExtrudedDirection=model.create_entity(
            "IfcDirection", DirectionRatios=(0.0, 0.0, 1.0)
        ),
        Depth=start_overrun + length + end_overrun,
    )
    representation_type = "SweptSolid"
    for name, at_x in (("start", 0.0), ("end", length)):
        end = ends[name]
        if end["kind"] != "mitre":
            continue
        solid = model.create_entity(
            "IfcBooleanClippingResult",
            Operator="DIFFERENCE",
            FirstOperand=solid,
            SecondOperand=mitre_half_space(model, end["normal"], at_x),
        )
        representation_type = "Clipping"
    return model.create_entity(
        "IfcShapeRepresentation",
        ContextOfItems=context,
        RepresentationIdentifier="Body",
        RepresentationType=representation_type,
        Items=[solid],
    )


def swept_pipe(model, context, points, pipe, bend_radius):
    """A hollow pipe swept along a path, round or rectangular.

    A round one is an `IfcSweptDiskSolid`: `InnerRadius` bores it for free,
    which is why it is one solid and not a difference of two. A rectangular
    one is an `IfcRectangleHollowProfileDef` - which carries `XDim`, `YDim`
    and `WallThickness` as readable numbers - swept with a **fixed
    reference**, because a profile has an orientation a disk does not.

    That reference is local X, along the gutter the pipe hangs from. Every
    segment of a downspout's path lies in the local Y-Z plane, so local X is
    perpendicular to every tangent on it - which is exactly what the schema
    demands, since a `FixedReference` parallel to the tangent anywhere along
    the directrix is invalid. Using global Z here would be that mistake: the
    pipe's own straight run is vertical.

    `StartParam` and `EndParam` are omitted because a polyline is already a
    bounded curve, which is what the schema's `DirectrixBounded` rule asks
    for - supplying them would mean restating a parameterisation that
    differs between the two curve types.

    A zero `bend_radius` leaves the path a plain polyline, whose corners
    IfcOpenShell mitres at half angle - what a folded sheet elbow looks
    like. A positive one replaces each interior corner with a real arc.
    """

    def point_list(coordinates):
        return [
            model.create_entity(
                "IfcCartesianPoint", Coordinates=[float(v) for v in point]
            )
            for point in coordinates
        ]

    if bend_radius <= 0.0:
        directrix = model.create_entity("IfcPolyline", Points=point_list(points))
    else:
        filleted, arcs = _fillet_path(points, bend_radius)
        segments = []
        cursor = 1
        for entry_index, middle_index, exit_index in arcs:
            # `_fillet_path` reuses a point rather than repeating it, so a
            # fillet starting exactly where the last one ended leaves nothing
            # to draw a line across.
            if entry_index > cursor:
                segments.append(
                    model.create_entity("IfcLineIndex", [cursor, entry_index])
                )
            segments.append(
                model.create_entity(
                    "IfcArcIndex", [entry_index, middle_index, exit_index]
                )
            )
            cursor = exit_index
        if cursor < len(filleted):
            segments.append(
                model.create_entity("IfcLineIndex", [cursor, len(filleted)])
            )
        directrix = model.create_entity(
            "IfcIndexedPolyCurve",
            Points=model.create_entity(
                "IfcCartesianPointList3D",
                CoordList=[[float(v) for v in point] for point in filleted],
            ),
            Segments=segments,
            SelfIntersect=False,
        )
    if pipe["shape"] == "round":
        item = model.create_entity(
            "IfcSweptDiskSolid",
            Directrix=directrix,
            Radius=pipe["radius"],
            InnerRadius=pipe["inner_radius"],
        )
    else:
        item = model.create_entity(
            "IfcFixedReferenceSweptAreaSolid",
            SweptArea=model.create_entity(
                "IfcRectangleHollowProfileDef",
                ProfileType="AREA",
                ProfileName=f"RHS_{pipe['x']}x{pipe['y']}",
                XDim=pipe["x"],
                YDim=pipe["y"],
                WallThickness=pipe["wall"],
                InnerFilletRadius=pipe["fillet"],
                OuterFilletRadius=pipe["fillet"],
            ),
            Position=axis_placement(model, (0.0, 0.0, 0.0)),
            Directrix=directrix,
            FixedReference=model.create_entity(
                "IfcDirection", DirectionRatios=(1.0, 0.0, 0.0)
            ),
        )
    return model.create_entity(
        "IfcShapeRepresentation",
        ContextOfItems=context,
        RepresentationIdentifier="Body",
        RepresentationType="AdvancedSweptSolid",
        Items=[item],
    )


def _unit(delta):
    span = math.sqrt(sum(value * value for value in delta))
    return [value / span for value in delta], span


def _fillet_path(points, setback):
    """Replace each interior corner with a real tangent arc.

    `setback` is how far back along each leg the arc starts, clamped to half
    the shorter leg so two fillets on one short leg cannot overrun each other
    - which is exactly what a swan neck does, its middle leg being only
    `standoff * sqrt(2)` long.

    The arc's midpoint has to lie **on** the arc, not merely between its ends:
    a point picked by averaging is collinear often enough that the kernel
    rejects the whole curve, which is a shape failure naming only the product.
    For a fillet set back `d` along legs meeting at angle `theta`, the radius
    is `d * tan(theta / 2)` and the centre sits `d / cos(theta / 2)` from the
    corner along the bisector, so the arc's midpoint is that distance less the
    radius.

    Returns the point list and the 1-based index of each arc's first point,
    which is the indexing `IfcIndexedPolyCurve` segments use.
    """

    filleted = [points[0]]
    arcs = []

    def push(point):
        """Append a point unless it repeats the last one, and return its
        1-based index either way.

        Two fillets on one short leg are both clamped to half of it, so they
        meet exactly at its midpoint - a smooth, valid path, but one whose
        two tangent points are the same coordinate. Appending both leaves a
        zero-length line between them, which the kernel rejects as a whole
        curve. Comparing indices does not catch it; comparing coordinates
        does.
        """

        if math.dist(point, filleted[-1]) <= 1e-9:
            return len(filleted)
        filleted.append(point)
        return len(filleted)

    for index in range(1, len(points) - 1):
        before, corner, after = points[index - 1], points[index], points[index + 1]
        to_before, span_before = _unit(
            [before[axis] - corner[axis] for axis in range(3)]
        )
        to_after, span_after = _unit(
            [after[axis] - corner[axis] for axis in range(3)]
        )
        distance = min(setback, span_before / 2.0, span_after / 2.0)
        cosine = max(-1.0, min(1.0, sum(
            to_before[axis] * to_after[axis] for axis in range(3)
        )))
        half = math.acos(cosine) / 2.0
        bisector, _ = _unit(
            [to_before[axis] + to_after[axis] for axis in range(3)]
        )
        radius = distance * math.tan(half)
        to_middle = distance / math.cos(half) - radius
        entry = tuple(
            corner[axis] + to_before[axis] * distance for axis in range(3)
        )
        middle = tuple(
            corner[axis] + bisector[axis] * to_middle for axis in range(3)
        )
        exit_ = tuple(
            corner[axis] + to_after[axis] * distance for axis in range(3)
        )
        arcs.append((push(entry), push(middle), push(exit_)))
    push(points[-1])
    return filleted, arcs


# Every gutter, downspout, outlet and stop-end joins one RAINWATER system, so
# the file answers "what drains this roof" as a group rather than as a naming
# convention over loose elements. Created only when something drains.
rainwater_system = None
if GUTTERS:
    # `add_system` takes only the class - name and predefined type are set
    # on the entity afterwards rather than passed through.
    rainwater_system = ifc_api.system.add_system(
        model, ifc_class="IfcDistributionSystem"
    )
    rainwater_system.Name = "Rainwater"
    rainwater_system.PredefinedType = "RAINWATER"

for gutter in GUTTERS:
    design = gutters.profile(gutter["profile"])
    nominal, thickness = gutter["nominal_size"], gutter["thickness"]
    ring = design.ring(nominal, thickness)
    projection = design.projection(nominal)
    # Where a downspout hangs from, already resolved in the run's own frame.
    # This is all a downspout ever learns from its gutter. Read by name: as a
    # positional pair these two were transposed here, which a half-round hides
    # (its sole's up and across are the same number) and a box gutter does not.
    sole_u = gutter["drop_point"]["up"]
    sole_v = gutter["drop_point"]["across"]
    section = section_profile(model, f"{gutter['profile']}.{nominal}", ring)
    # A stop-end is a filled plate, so it gets its own profile. Extruding the
    # sheet ring instead yields an annulus - a hollow slice of the run, flush
    # against its own end face, closing nothing.
    plate_profile = section_profile(
        model, f"{gutter['profile']}.{nominal}.plate", design.plate(nominal)
    )
    placement = placement_matrix(
        gutter["angle"],
        (gutter["start"][0], gutter["start"][1], gutter["base_z"]),
    )
    drains = []

    entity = ifc_api.root.create_entity(
        model,
        ifc_class="IfcPipeSegment",
        name=gutter["name"],
        predefined_type="GUTTER",
    )
    entity.GlobalId = stable_guid(gutter["key"])
    entity.Tag = gutter["key"]
    entity.Representation = model.create_entity(
        "IfcProductDefinitionShape",
        Representations=[
            gutter_body(
                model,
                body_context,
                section,
                gutter["length"],
                projection * gutters.MITRE_OVERRUN,
                gutter["ends"],
            )
        ],
    )
    ifc_api.geometry.edit_object_placement(
        model, product=entity, matrix=placement, is_si=True
    )
    ifc_api.spatial.assign_container(
        model, products=[entity], relating_structure=entities[gutter["storey"]]
    )
    if gutter["material"]:
        ifc_api.material.assign_material(
            model,
            products=[entity],
            type="IfcMaterial",
            material=materials[gutter["material"]],
        )
    pset = ifc_api.pset.add_pset(
        model, product=entity, name="Pset_PipeSegmentTypeCommon"
    )
    ifc_api.pset.edit_pset(
        model, pset=pset, properties={"NominalDiameter": nominal}
    )
    entities[gutter["key"]] = entity
    drains.append(entity)

    # A free end is closed by a plate of the run's own section - the same
    # filled section, extruded a sheet's thickness. IfcPipeFittingTypeEnum has
    # no value for a closure (ENTRY and EXIT both name flow the stop-end does
    # not carry), so it is USERDEFINED with ObjectType saying what it is, the
    # same choice a sill makes against IfcBuildingElementPart.
    for name, at_x, facing in (("start", 0.0, -1.0), ("end", gutter["length"], 1.0)):
        if gutter["ends"][name]["kind"] != "stop_end":
            continue
        plate = ifc_api.root.create_entity(
            model,
            ifc_class="IfcPipeFitting",
            name=f"{gutter['name']}.{name}-stop",
            predefined_type="USERDEFINED",
        )
        plate.GlobalId = stable_guid(f"{gutter['key']}.{name}-stop")
        plate.Tag = f"{gutter['key']}.{name}-stop"
        plate.ObjectType = "StopEnd"
        plate.Representation = model.create_entity(
            "IfcProductDefinitionShape",
            Representations=[
                model.create_entity(
                    "IfcShapeRepresentation",
                    ContextOfItems=body_context,
                    RepresentationIdentifier="Body",
                    RepresentationType="SweptSolid",
                    Items=[
                        model.create_entity(
                            "IfcExtrudedAreaSolid",
                            SweptArea=plate_profile,
                            Position=axis_placement(
                                model,
                                (at_x + facing * thickness, 0.0, 0.0),
                                axis=(1.0, 0.0, 0.0),
                                ref_direction=(0.0, 0.0, 1.0),
                            ),
                            ExtrudedDirection=model.create_entity(
                                "IfcDirection", DirectionRatios=(0.0, 0.0, 1.0)
                            ),
                            Depth=thickness,
                        )
                    ],
                )
            ],
        )
        ifc_api.geometry.edit_object_placement(
            model, product=plate, matrix=placement, is_si=True
        )
        ifc_api.spatial.assign_container(
            model, products=[plate], relating_structure=entities[gutter["storey"]]
        )
        if gutter["material"]:
            ifc_api.material.assign_material(
                model,
                products=[plate],
                type="IfcMaterial",
                material=materials[gutter["material"]],
            )
        entities[plate.Tag] = plate
        drains.append(plate)

    for spout in gutter["downspouts"]:
        section = spout["pipe"]
        # Already solved, in the gutter's own frame: X along the run, Y toward
        # the building, Z up from its sole. A `shoe` termination carries one
        # extra point, kicked outboard - nothing here needs to know which.
        path = [tuple(point) for point in spout["path"]]
        segment = ifc_api.root.create_entity(
            model,
            ifc_class="IfcPipeSegment",
            name=spout["name"],
            predefined_type="RIGIDSEGMENT",
        )
        segment.GlobalId = stable_guid(spout["key"])
        segment.Tag = spout["key"]
        segment.Representation = model.create_entity(
            "IfcProductDefinitionShape",
            Representations=[
                swept_pipe(
                    model, body_context, path, section, spout["bend_radius"]
                )
            ],
        )
        # Placed along the run rather than in the world: `along` is measured
        # on the gutter, so the pipe stays put when the roof moves. The drop
        # point is used as resolved - the section frame and an object
        # placement share the same sense of "across", and flipping it here
        # (as the profile plane genuinely needs) puts the pipe on the far
        # side of its own gutter, catching nothing.
        ifc_api.geometry.edit_object_placement(
            model,
            product=segment,
            matrix=placement
            @ placement_matrix(0.0, (spout["along"], sole_v, sole_u)),
            is_si=True,
        )
        ifc_api.spatial.assign_container(
            model, products=[segment], relating_structure=entities[gutter["storey"]]
        )
        if spout["material"]:
            ifc_api.material.assign_material(
                model,
                products=[segment],
                type="IfcMaterial",
                material=materials[spout["material"]],
            )
        pipe_pset = ifc_api.pset.add_pset(
            model, product=segment, name="Pset_PipeSegmentTypeCommon"
        )
        # `NominalDiameter` is the schema's word and it is a diameter, so a
        # rectangular pipe states its across-width under it rather than
        # inventing a property no consumer reads.
        if section["shape"] == "round":
            sizes = {
                "NominalDiameter": section["radius"] * 2.0,
                "InnerDiameter": section["inner_radius"] * 2.0,
            }
        else:
            sizes = {
                "NominalDiameter": section["x"],
                "InnerDiameter": section["x"] - 2.0 * section["wall"],
            }
        ifc_api.pset.edit_pset(model, pset=pipe_pset, properties=sizes)
        entities[spout["key"]] = segment
        drains.append(segment)

    if rainwater_system is not None:
        ifc_api.system.assign_system(
            model, products=drains, system=rainwater_system
        )

def add_spaces():
    """Create spaces only after native wall joins and top clipping are final.

    Opening subtraction is disabled by the resolver: an opening never
    enlarges a room or its main floor; its separate covering owns that area.
    """

    regions = space_geometry.resolve_space_regions(model, SPACES, entities)
    for storey_spaces in SPACES:
        storey_key = storey_spaces["storey"]
        for space in storey_spaces["spaces"]:
            region = regions[space["key"]]
            if region.interiors:
                raise RuntimeError(
                    f"space '{space['key']}': interior-ring profiles are not "
                    "supported by the current space extrusion"
                )
            boundary = list(region.exterior.coords)[:-1]

            entity = ifc_api.root.create_entity(
                model,
                ifc_class="IfcSpace",
                name=space["name"],
                predefined_type=space["predefined_type"],
            )
            entity.GlobalId = stable_guid(space["key"])
            if hasattr(entity, "Tag"):
                entity.Tag = space["key"]

            matrix = np.eye(4)
            matrix[2, 3] = space["base_z"]
            ifc_api.geometry.edit_object_placement(
                model, product=entity, matrix=matrix, is_si=True
            )
            representation = ifc_api.geometry.add_slab_representation(
                model,
                context=body_context,
                depth=space["height"],
                polyline=boundary + [boundary[0]],
            )
            ifc_api.geometry.assign_representation(
                model, product=entity, representation=representation
            )
            # A space is spatial structure, so it is aggregated under its
            # storey rather than contained as a physical element.
            ifc_api.aggregate.assign_object(
                model, products=[entity], relating_object=entities[storey_key]
            )
            entities[space["key"]] = entity
    return regions


def add_floor_covering(item, boundary):
    """Create one physical finish occurrence and contain it in its room."""

    entity = ifc_api.root.create_entity(
        model,
        ifc_class="IfcCovering",
        name=item["name"],
        predefined_type=item["predefined_type"],
    )
    entity.GlobalId = stable_guid(item["key"])
    if hasattr(entity, "Tag"):
        entity.Tag = item["key"]
    matrix = np.eye(4)
    matrix[2, 3] = item["base_z"]
    ifc_api.geometry.edit_object_placement(
        model, product=entity, matrix=matrix, is_si=True
    )
    representation = ifc_api.geometry.add_slab_representation(
        model,
        context=body_context,
        depth=item["thickness"],
        # An IFC area profile must close explicitly. Relying on geometry
        # repair can collapse the 2 mm strip at a virtual room boundary.
        polyline=boundary + [boundary[0]],
    )
    ifc_api.geometry.assign_representation(
        model, product=entity, representation=representation
    )
    ifc_api.material.assign_material(
        model,
        products=[entity],
        type="IfcMaterial",
        material=materials[item["material"]],
    )
    # A covering is an element contained in the room it finishes. It is not
    # aggregated into the IfcSpace or into another covering occurrence.
    ifc_api.spatial.assign_container(
        model,
        products=[entity],
        relating_structure=entities[item["space"]],
    )
    entities[item["key"]] = entity


# A window or door type carries the section as IFC's own predefined property
# sets, which is also where IfcOpenShell's generators read it from. Stating it
# once, on the type, is why an occurrence declares only its overall size.
opening_types = {}
for operation in (
    item
    for item in OPERATIONS
    if item["kind"] in ("window-type", "door-type")
):
    parameters = operation["parameters"]
    is_window = operation["kind"] == "window-type"
    entity = root_entity(
        model, operation, "IfcWindowType" if is_window else "IfcDoorType"
    )
    entity.PredefinedType = parameters["predefined_type"]
    if is_window:
        entity.PartitioningType = parameters["partitioning_type"]
    else:
        entity.OperationType = parameters["operation_type"]

    property_sets = []
    declared = [
        (
            "IfcWindowLiningProperties" if is_window else "IfcDoorLiningProperties",
            "Lining",
            f"{operation['key']}.lining",
            parameters["lining"],
        )
    ]
    panels = parameters["panels"] if is_window else [parameters["panel"]]
    for index, panel in enumerate(panels):
        declared.append(
            (
                "IfcWindowPanelProperties" if is_window else "IfcDoorPanelProperties",
                f"Panel {index}",
                f"{operation['key']}.panel.{index}",
                panel,
            )
        )
    for ifc_class, pset_name, guid_key, attributes in declared:
        pset_entity = model.create_entity(
            ifc_class, GlobalId=stable_guid(guid_key), Name=pset_name
        )
        for attribute, value in attributes.items():
            # A glazed door leaf's own framing is an input to IfcOpenShell's
            # generator with no attribute on IfcDoorPanelProperties, so the
            # schema decides what the property set is allowed to carry.
            if hasattr(pset_entity, attribute):
                setattr(pset_entity, attribute, value)
        property_sets.append(pset_entity)
    entity.HasPropertySets = property_sets
    if is_window and parameters.get("assembly"):
        # The Body is authoritative: standard scalar bands cannot describe
        # an independent bottom track and two different sash depth positions.
        entity.ParameterTakesPrecedence = False
        assembly_pset = ifc_api.pset.add_pset(model, product=entity, name="BA_WindowAssembly")
        assembly_pset.GlobalId = stable_guid(f"{operation['key']}.assembly")
        ifc_api.pset.edit_pset(model, pset=assembly_pset, properties={
            "Kind": parameters["assembly"]["kind"],
            "Version": 1,
            "LengthUnit": "METRE",
            "Data": model.createIfcText(json.dumps(parameters["assembly"], sort_keys=True)),
        })
    entities[operation["key"]] = entity
    opening_types[operation["key"]] = parameters

# Composed windows keep the same IFC type/occurrence split as stock windows,
# but their section is interpreted by the building script instead of
# IfcOpenShell's rectangular panel generator.  USERDEFINED is the schema's
# explicit escape hatch for this non-standard partitioning.
for operation in (
    item for item in OPERATIONS if item["kind"] == "composed-window-type"
):
    entity = root_entity(model, operation, "IfcWindowType")
    entity.PredefinedType = "WINDOW"
    entity.PartitioningType = "USERDEFINED"
    entity.UserDefinedPartitioningType = "COMPOSED_GLAZING"
    entities[operation["key"]] = entity

for opening in OPENINGS:
    is_window = opening["kind"] == "window"
    type_parameters = opening_types[opening["type"]]

    # The void first: an IfcOpeningElement spanning the wall, subtracted by
    # IfcRelVoidsElement, which is the schema's own boolean. Its placement has
    # X along the wall, Y through it and Z up, so the reveal is a rectangle in
    # XZ swept along Y - the axes the profile below is oriented to.
    # Sized as the placement is oriented: X along the wall, Y through it, Z up.
    size = opening["opening_size"]
    void = ifc_api.root.create_entity(
        model,
        ifc_class="IfcOpeningElement",
        name=f"{opening['name']} Opening",
        predefined_type="OPENING",
    )
    void.GlobalId = stable_guid(f"{opening['key']}.opening")
    ifc_api.geometry.assign_representation(
        model,
        product=void,
        representation=extruded_rectangle(
            model,
            body_context,
            x_dim=size["width"],
            y_dim=size["height"],
            depth=size["through"],
            location=(0.0, -size["through"] / 2.0, 0.0),
            axis=(0.0, 1.0, 0.0),
            ref_direction=(1.0, 0.0, 0.0),
        ),
    )
    ifc_api.geometry.edit_object_placement(
        model,
        product=void,
        matrix=placement_matrix(
            opening["opening_angle"], opening["opening_position"]
        ),
        is_si=True,
    )
    ifc_api.feature.add_feature(model, feature=void, element=entities[opening["wall"]])

    entity = ifc_api.root.create_entity(
        model,
        ifc_class="IfcWindow" if is_window else "IfcDoor",
        name=opening["name"],
        predefined_type=type_parameters["predefined_type"],
    )
    entity.GlobalId = stable_guid(opening["key"])
    entity.Tag = opening["key"]
    entity.OverallWidth = opening["overall_width"]
    entity.OverallHeight = opening["overall_height"]
    if is_window:
        entity.PartitioningType = type_parameters["partitioning_type"]
    else:
        entity.OperationType = type_parameters["operation_type"]
    ifc_api.type.assign_type(
        model,
        related_objects=[entity],
        relating_type=entities[opening["type"]],
        # Each occurrence builds its own body at its own size; do not map the
        # type's.
        should_map_representations=False,
    )
    ifc_api.geometry.edit_object_placement(
        model,
        product=entity,
        matrix=placement_matrix(opening["angle"], opening["position"]),
        is_si=True,
    )

    # Shape aspects hang off the product's shape, so the container has to
    # exist before the generator runs - otherwise the Lining, Framing and
    # Glazing parts are built but left unnamed, and nothing can be painted
    # separately.
    entity.Representation = model.create_entity(
        "IfcProductDefinitionShape", Representations=[]
    )
    if is_window and type_parameters.get("assembly"):
        representation = window_assemblies.add_lift_slide_representation(
            model, context=body_context,
            overall_height=opening["overall_height"], overall_width=opening["overall_width"],
            assembly={k: v for k, v in type_parameters["assembly"].items() if k != "kind"},
            part_of_product=entity.Representation,
            lining_offset=opening["lining"]["LiningOffset"],
        )
    elif is_window:
        representation = ifc_api.geometry.add_window_representation(
            model,
            context=body_context,
            overall_height=opening["overall_height"],
            overall_width=opening["overall_width"],
            partition_type=type_parameters["partitioning_type"],
            lining_properties=generator_kwargs(
                WindowLiningProperties, opening["lining"]
            ),
            panel_properties=[
                generator_kwargs(WindowPanelProperties, panel)
                for panel in type_parameters["panels"]
            ],
            part_of_product=entity.Representation,
        )
    else:
        representation = ifc_api.geometry.add_door_representation(
            model,
            context=body_context,
            overall_height=opening["overall_height"],
            overall_width=opening["overall_width"],
            operation_type=type_parameters["operation_type"],
            lining_properties=generator_kwargs(
                DoorLiningProperties, opening["lining"]
            ),
            panel_properties=generator_kwargs(
                DoorPanelProperties, type_parameters["panel"]
            ),
            part_of_product=entity.Representation,
        )
    ifc_api.geometry.assign_representation(
        model, product=entity, representation=representation
    )

    # assign_type leaves the occurrence's PredefinedType to be inherited, but
    # a reader that never resolves the type then sees a window of no kind, so
    # it is stated on both.
    entity.PredefinedType = type_parameters["predefined_type"]

    # One material per shape aspect the generator actually named. A solid door
    # leaf has no Glazing aspect, so giving it a glazing constituent would
    # describe a part the element does not have. Roles the script left
    # undeclared fall back to a declared one rather than arriving unstyled,
    # which is what Bonsai's own window tool does.
    aspects = [
        aspect.Name for aspect in (entity.Representation.HasShapeAspects or [])
    ]
    if opening["materials"] and aspects:
        fallback = next(iter(opening["materials"].values()))
        ifc_api.material.set_shape_aspect_constituents(
            model,
            element=entity,
            context=body_context,
            materials={
                role: materials[opening["materials"].get(role, fallback)]
                for role in aspects
            },
        )
    ifc_api.spatial.assign_container(
        model, products=[entity], relating_structure=entities[opening["storey"]]
    )
    # IfcRelFillsElement: the element fills the void it was cut for.
    ifc_api.feature.add_filling(model, opening=void, element=entity)

    pset = ifc_api.pset.add_pset(
        model,
        product=entity,
        name="Pset_WindowCommon" if is_window else "Pset_DoorCommon",
    )
    ifc_api.pset.edit_pset(
        model, pset=pset, properties={"IsExternal": opening["is_external"]}
    )

    # Bonsai keeps a window or door re-editable through a BBIM pset holding
    # the same parameters its own tool writes, exactly as BBIM_Roof does for a
    # roof. Writing it is what makes a script-authored opening adjustable with
    # the window and door tools instead of arriving as dead geometry.
    if is_window and type_parameters.get("assembly"):
        # No BBIM_Window: stock regeneration would replace the HST track with
        # an ordinary four-sided lining. Script rebuilds retain the assembly.
        entities[opening["key"]] = entity
        continue
    lining_data = {snake(name): value for name, value in opening["lining"].items()}
    if is_window:
        panels = type_parameters["panels"]
        panel_data = {
            "frame_depth": [panel["FrameDepth"] for panel in panels] + [0.0] * (3 - len(panels)),
            "frame_thickness": [panel["FrameThickness"] for panel in panels] + [0.0] * (3 - len(panels)),
        }
        bbim_data = {
            "window_type": type_parameters["partitioning_type"],
            "overall_height": opening["overall_height"],
            "overall_width": opening["overall_width"],
            "lining_properties": lining_data,
            "panel_properties": panel_data,
        }
    else:
        panel = type_parameters["panel"]
        bbim_data = {
            "door_type": type_parameters["operation_type"],
            "overall_height": opening["overall_height"],
            "overall_width": opening["overall_width"],
            "lining_properties": lining_data,
            # Bonsai names IFC's normalised PanelWidth after what it is.
            "panel_properties": {
                "panel_depth": panel["PanelDepth"],
                "panel_width_ratio": panel["PanelWidth"],
                "frame_depth": panel["FrameDepth"],
                "frame_thickness": panel["FrameThickness"],
            },
        }
    bbim = ifc_api.pset.add_pset(
        model,
        product=entity,
        name="BBIM_Window" if is_window else "BBIM_Door",
    )
    ifc_api.pset.edit_pset(
        model,
        pset=bbim,
        properties={"Data": model.createIfcText(json.dumps(bbim_data))},
    )
    entities[opening["key"]] = entity

# A composed window is still one wall filling in IFC.  Its rectangles and
# triangles are authoring pieces inside one IfcWindow body, not child windows,
# and their connected exterior makes one readable polygonal wall opening.
for window in COMPOSED_WINDOWS:
    void = ifc_api.root.create_entity(
        model,
        ifc_class="IfcOpeningElement",
        name=f"{window['name']} Opening",
        predefined_type="OPENING",
    )
    void.GlobalId = stable_guid(f"{window['key']}.opening")
    ifc_api.geometry.assign_representation(
        model,
        product=void,
        representation=extruded_xz_polygon(
            model,
            body_context,
            window["opening_outline"],
            window["opening_through"],
        ),
    )
    ifc_api.geometry.edit_object_placement(
        model,
        product=void,
        matrix=placement_matrix(window["angle"], window["opening_position"]),
        is_si=True,
    )
    ifc_api.feature.add_feature(
        model, feature=void, element=entities[window["wall"]]
    )

    entity = ifc_api.root.create_entity(
        model,
        ifc_class="IfcWindow",
        name=window["name"],
        predefined_type="WINDOW",
    )
    entity.GlobalId = stable_guid(window["key"])
    entity.Tag = window["key"]
    entity.OverallWidth = window["overall_width"]
    entity.OverallHeight = window["overall_height"]
    entity.PartitioningType = "USERDEFINED"
    entity.UserDefinedPartitioningType = "COMPOSED_GLAZING"
    ifc_api.type.assign_type(
        model,
        related_objects=[entity],
        relating_type=entities[window["type"]],
        # Each occurrence has its own declared composition and dimensions.
        should_map_representations=False,
    )
    # Keep the occurrence legible to consumers that do not resolve its type,
    # matching the stock window path above.
    entity.PredefinedType = "WINDOW"
    ifc_api.geometry.edit_object_placement(
        model,
        product=entity,
        matrix=placement_matrix(window["angle"], window["position"]),
        is_si=True,
    )

    mesh = composed_windows.composed_window_mesh(
        window["pieces"],
        window["dividers"],
        profile_width=window["profile_width"],
        profile_depth=window["profile_depth"],
        glazing_thickness=window["glazing_thickness"],
    )
    assign_role_split_body(
        model,
        body_context,
        entity,
        mesh,
        {role.title(): key for role, key in window["materials"].items()},
    )
    ifc_api.spatial.assign_container(
        model, products=[entity], relating_structure=entities[window["storey"]]
    )
    ifc_api.feature.add_filling(model, opening=void, element=entity)

    pset = ifc_api.pset.add_pset(
        model,
        product=entity,
        name="Pset_WindowCommon",
    )
    ifc_api.pset.edit_pset(
        model, pset=pset, properties={"IsExternal": window["is_external"]}
    )
    # Deliberately no BBIM_Window: Bonsai's stock modifier can only recreate
    # its predefined rectangular panel schemas.  The building script remains
    # the authoritative parametric definition for this custom composition.
    entities[window["key"]] = entity

for operation in (
    item for item in OPERATIONS if item["kind"] == "extrusion"
):
    parameters = operation["parameters"]
    width, depth = parameters["size"]
    profile = model.create_entity(
        "IfcRectangleProfileDef",
        ProfileType="AREA",
        XDim=width,
        YDim=depth,
    )
    entity = root_entity(model, operation, parameters["ifc_class"])
    representation = ifc_api.geometry.add_profile_representation(
        model,
        context=body_context,
        profile=profile,
        depth=parameters["height"],
    )
    ifc_api.geometry.assign_representation(
        model,
        product=entity,
        representation=representation,
    )
    storey = entities[operation["references"]["storey"]]
    ifc_api.spatial.assign_container(
        model,
        products=[entity],
        relating_structure=storey,
    )
    position = parameters["position"]
    matrix = np.eye(4)
    matrix[:3, 3] = (
        position[0],
        position[1],
        float(storey.Elevation or 0.0) + position[2],
    )
    ifc_api.geometry.edit_object_placement(
        model,
        product=entity,
        matrix=matrix,
        is_si=True,
    )
    material_key = operation["references"].get("material")
    if material_key:
        ifc_api.material.assign_material(
            model,
            products=[entity],
            type="IfcMaterial",
            material=materials[material_key],
        )
    entities[operation["key"]] = entity

for sill in SILLS:
    window_entity = entities[sill["window"]]
    verts, faces, uvs, slots = sills.standard_sill_mesh(
        sill["width"], sill["depth"], sill["thickness"],
        corner=sill["corner"], corner_reach=sill["corner_reach"],
    )
    entity = ifc_api.root.create_entity(
        model,
        ifc_class="IfcBuildingElementPart",
        name=sill["name"],
        predefined_type="USERDEFINED",
    )
    entity.GlobalId = stable_guid(sill["key"])
    entity.Tag = sill["key"]
    entity.ObjectType = "Sill"
    representation = ifc_api.geometry.add_mesh_representation(
        model,
        context=body_context,
        vertices=[[list(vertex) for vertex in verts]],
        faces=[[list(face) for face in faces]],
    )
    ifc_api.geometry.assign_representation(
        model, product=entity, representation=representation
    )
    ifc_api.geometry.edit_object_placement(
        model,
        product=entity,
        matrix=placement_matrix(sill["angle"], sill["position"]),
        is_si=True,
    )
    material_key = sill["material"]
    if material_key:
        ifc_api.material.assign_material(
            model,
            products=[entity],
            type="IfcMaterial",
            material=materials[material_key],
        )
    # Aggregated onto the window it serves rather than contained in the
    # storey directly - IFC allows a product exactly one place in the
    # spatial decomposition tree, so this also removes any container
    # assignment `assign_object` would otherwise conflict with.
    ifc_api.aggregate.assign_object(
        model, products=[entity], relating_object=window_entity
    )
    entities[sill["key"]] = entity

for roof in ROOFS:
    storey = entities[roof["storey"]]

    bm = roof_bmesh(roof)
    mesh = roof_role_mesh(bm, roof)

    entity = ifc_api.root.create_entity(
        model,
        ifc_class="IfcRoof",
        name=roof["name"],
        predefined_type=roof["predefined_type"],
    )
    entity.GlobalId = stable_guid(roof["key"])
    entity.Tag = roof["key"]

    assign_role_split_body(
        model,
        body_context,
        entity,
        mesh,
        roof["materials"],
    )
    # The skeleton solves the roof in world coordinates, so its placement is
    # the identity - but a product carrying a shape representation must still
    # have one, which is IfcProduct.PlacementForShapeRepresentation.
    ifc_api.geometry.edit_object_placement(
        model, product=entity, matrix=np.eye(4), is_si=True
    )
    ifc_api.spatial.assign_container(
        model,
        products=[entity],
        relating_structure=storey,
    )
    entities[roof["key"]] = entity

    # Bonsai keeps its roofs re-editable through a BBIM_Roof pset holding the
    # footprint and the generation parameters. Writing it means a roof this
    # script authored can be opened and adjusted with Bonsai's own roof tool
    # rather than arriving as dead geometry. Safe to write because
    # `skeleton.require_supported` has already refused anything Bonsai's
    # unweighted skeleton would regenerate differently.
    angle_radians = math.radians(roof["angle"])
    gables = set(roof["gable_indices"])
    corner_count = len(roof["overhang_boundary"])
    roof_data = {
        "roof_type": "HIP/GABLE ROOF",
        "generation_method": "ANGLE",
        "roof_thickness": roof["thickness"],
        "rafter_edge_angle": math.radians(roof["rafter_edge_angle"]),
        "angle": angle_radians,
        "percentage": math.tan(angle_radians) * 100.0,
        "path_data": {
            "verts": [
                [x, y, roof["base_z"]] for x, y in roof["overhang_boundary"]
            ],
            "edges": [
                [index, (index + 1) % corner_count]
                for index in range(corner_count)
            ],
            "gable_roof_angles": [
                math.pi / 2 if index in gables else 0.0
                for index in range(corner_count)
            ],
        },
    }
    pset = ifc_api.pset.add_pset(model, product=entity, name="BBIM_Roof")
    ifc_api.pset.edit_pset(
        model,
        pset=pset,
        properties={"Data": model.createIfcText(json.dumps(roof_data))},
    )

    extensions = extensions_for(roof["key"])
    for extension in extensions:
        clipping = roof_clipping_bmesh(bm, extension["termination"])
        try:
            apply_extension(entity, extension, clipping)
        finally:
            clipping.free()
    bm.free()

    # Everything that covers this roof, gathered so the file carries one
    # IfcRelCoversBldgElements naming all of them rather than one relationship
    # per covering - the schema's RelatedCoverings is a set for exactly this,
    # and a consumer asking what covers the roof should get one answer.
    roof_coverings = []

    # A tile covering is a building element, not a rendering flourish: IFC has
    # IfcCovering with PredefinedType ROOFING for exactly this. Leaving it out
    # would make the IFC and the GLB disagree about what the roof is.
    if roof["covering"]:
        solid = roof_bmesh(roof)
        solid.normal_update()
        tile_verts, _, _, _ = tiles.profile(roof["covering"]).geometry()
        thickness = max(v[2] for v in tile_verts) - min(v[2] for v in tile_verts)
        shell_verts, shell_faces = covering_shell(solid, thickness)
        solid.free()

        covering = ifc_api.root.create_entity(
            model,
            ifc_class="IfcCovering",
            name=f"{roof['name']} Covering",
            predefined_type="ROOFING",
        )
        covering.GlobalId = stable_guid(f"{roof['key']}.covering")
        covering.Tag = f"{roof['key']}.covering"
        ifc_api.geometry.assign_representation(
            model,
            product=covering,
            representation=ifc_api.geometry.add_mesh_representation(
                model,
                context=body_context,
                vertices=[shell_verts],
                faces=[shell_faces],
            ),
        )
        ifc_api.geometry.edit_object_placement(
            model, product=covering, matrix=np.eye(4), is_si=True
        )
        ifc_api.spatial.assign_container(
            model, products=[covering], relating_structure=storey
        )
        if roof["covering_material"]:
            ifc_api.material.assign_material(
                model,
                products=[covering],
                type="IfcMaterial",
                material=materials[roof["covering_material"]],
            )
        entities[f"{roof['key']}.covering"] = covering
        roof_coverings.append(covering)

    # A verge trim runs along the roof's raking free edges. Which edges those
    # are is never stated: `trims.edge_kind` reads it off the solid, so a roof
    # with no gable grows none without anyone saying so, and a boundary that
    # changes shape moves them without anyone editing a list.
    #
    # The IFC body remains authoritative. Presentation may offset only an
    # exposed, wall-competing face slightly outward without altering this body.
    if roof["verge_trim"]:
        section = roof["verge_trim_section"]
        centre = roof["verge_trim_centre"]
        solid = roof_bmesh(roof)
        runs = verge_runs(solid)
        solid.free()
        for index, run in enumerate(runs):
            trim = ifc_api.root.create_entity(
                model,
                ifc_class="IfcCovering",
                name=f"{roof['name']} Verge {index}",
                # IfcCoveringTypeEnum has no value for a verge trim - the
                # buildingSMART thread asking for a flashing died unresolved -
                # so it is USERDEFINED with ObjectType saying what it is, the
                # same choice a gutter's stop-end and a window sill both make.
                predefined_type="USERDEFINED",
            )
            trim.GlobalId = stable_guid(f"{roof['key']}.verge.{index}")
            trim.Tag = f"{roof['key']}.verge.{index}"
            trim.ObjectType = "Flashing"
            trim.Representation = model.create_entity(
                "IfcProductDefinitionShape",
                Representations=[
                    model.create_entity(
                        "IfcShapeRepresentation",
                        ContextOfItems=body_context,
                        RepresentationIdentifier="Body",
                        RepresentationType="SweptSolid",
                        Items=[
                            model.create_entity(
                                "IfcExtrudedAreaSolid",
                                # A plain rectangle, so XDim and YDim stay
                                # readable numbers instead of a coordinate
                                # list a consumer has to bound-box.
                                SweptArea=model.create_entity(
                                    "IfcRectangleProfileDef",
                                    ProfileType="AREA",
                                    ProfileName=roof["verge_trim"],
                                    XDim=section["thickness"],
                                    YDim=section["height"],
                                    Position=model.create_entity(
                                        "IfcAxis2Placement2D",
                                        Location=model.create_entity(
                                            "IfcCartesianPoint",
                                            Coordinates=[
                                                float(centre[0]),
                                                float(centre[1]),
                                            ],
                                        ),
                                    ),
                                ),
                                # The profile plane is the frame's own XY -
                                # across and up - so the section stands
                                # vertical and its own Y is world vertical.
                                Position=axis_placement(
                                    model,
                                    (0.0, 0.0, 0.0),
                                    axis=(0.0, 0.0, 1.0),
                                    ref_direction=(1.0, 0.0, 0.0),
                                ),
                                # Skew to that plane: this is an **oblique**
                                # extrusion, and deliberately so. A sweep is a
                                # translation, so every profile edge stays
                                # parallel to itself - the board leans with the
                                # rake while its vertical edges stay vertical.
                                # A section swept perpendicular to the rake
                                # instead rotates the board about its own run.
                                ExtrudedDirection=model.create_entity(
                                    "IfcDirection",
                                    DirectionRatios=[float(v) for v in run.rake],
                                ),
                                Depth=run.length,
                            )
                        ],
                    )
                ],
            )
            # Built column by column rather than through `placement_matrix`,
            # which only turns a run in plan. The middle column is `UP`
            # literally, not a value carried from the run: it is world
            # vertical for every verge there will ever be, and that is what
            # keeps the board upright however the rake pitches.
            ifc_api.geometry.edit_object_placement(
                model,
                product=trim,
                matrix=np.array(
                    [
                        [run.across.x, UP.x, run.along.x, run.origin.x],
                        [run.across.y, UP.y, run.along.y, run.origin.y],
                        [run.across.z, UP.z, run.along.z, run.origin.z],
                        [0.0, 0.0, 0.0, 1.0],
                    ]
                ),
                is_si=True,
            )
            ifc_api.spatial.assign_container(
                model, products=[trim], relating_structure=storey
            )
            if roof["verge_trim_material"]:
                ifc_api.material.assign_material(
                    model,
                    products=[trim],
                    type="IfcMaterial",
                    material=materials[roof["verge_trim_material"]],
                )
            entities[trim.Tag] = trim
            roof_coverings.append(trim)

    if roof_coverings:
        model.create_entity(
            "IfcRelCoversBldgElements",
            GlobalId=stable_guid(f"{roof['key']}.covers"),
            RelatingBuildingElement=entity,
            RelatedCoverings=roof_coverings,
        )

    if roof["roof_windows"]:
        solid = roof_bmesh(roof)
        solid.normal_update()
        frames = face_frames(solid, roof["overhang_boundary"])
        for window in roof["roof_windows"]:
            frame = frames.get(window["edge"])
            if frame is None:
                raise RuntimeError(
                    f"{window['key']} is hosted on edge {window['edge']} of "
                    f"{roof['key']}, but no roof face rises from that edge"
                )

            # The roof face's own frame: X across the eave, Y up the slope, Z
            # normal to the plane, origin at the window's centre on it. Giving
            # both the opening and the window this placement is what lets each
            # carry geometry in its own coordinates rather than in world ones.
            origin, eave, up_slope, normal = frame
            centre = (
                origin
                + eave * window["along"]
                + up_slope * window["up_slope"]
            )
            face_matrix = np.eye(4)
            face_matrix[:3, 0] = eave
            face_matrix[:3, 1] = up_slope
            face_matrix[:3, 2] = normal
            face_matrix[:3, 3] = centre

            reach = roof["thickness"] + 0.5
            opening = ifc_api.root.create_entity(
                model,
                ifc_class="IfcOpeningElement",
                name=f"{window['name']} Opening",
                predefined_type="OPENING",
            )
            opening.GlobalId = stable_guid(f"{window['key']}.opening")
            ifc_api.geometry.assign_representation(
                model,
                product=opening,
                representation=extruded_rectangle(
                    model,
                    body_context,
                    x_dim=window["width"],
                    y_dim=window["height"],
                    depth=2.0 * reach,
                    location=(0.0, 0.0, -reach),
                ),
            )
            ifc_api.geometry.edit_object_placement(
                model, product=opening, matrix=face_matrix, is_si=True
            )
            # IfcRelVoidsElement: the schema's own boolean subtraction.
            ifc_api.feature.add_feature(model, feature=opening, element=entity)

            window_entity = ifc_api.root.create_entity(
                model,
                ifc_class="IfcWindow",
                name=window["name"],
                predefined_type="SKYLIGHT",
            )
            window_entity.GlobalId = stable_guid(window["key"])
            window_entity.Tag = window["key"]

            # `profile` is the script's word for "these windows are the same
            # product". IFC already has that: IfcWindowType plus
            # IfcRelDefinesByType. Reusing it means two identical skylights
            # read as two occurrences of one type, not two unrelated objects.
            type_key = (
                f"{window['profile']}:{window['width']}x{window['height']}"
            )
            window_type = window_types.get(type_key)
            if window_type is None:
                window_type = ifc_api.root.create_entity(
                    model,
                    ifc_class="IfcWindowType",
                    name=type_key,
                    predefined_type="SKYLIGHT",
                )
                window_type.GlobalId = stable_guid(f"type:{type_key}")
                window_type.Tag = window["profile"]
                window_types[type_key] = window_type
            ifc_api.type.assign_type(
                model,
                related_objects=[window_entity],
                relating_type=window_type,
                # Each occurrence carries its own body; do not overwrite it.
                should_map_representations=False,
            )

            ifc_api.geometry.edit_object_placement(
                model, product=window_entity, matrix=face_matrix, is_si=True
            )

            # One item per role the procedure named, each named by a shape
            # aspect, so the BIM element carries its frame and its pane
            # separately - the same shared wiring a railing's parts get.
            # Before this it was one item with one material, and the
            # presentation had to build a second, BIM-less copy beside it
            # just to hold the two.
            profile = roof_windows.profile(window["profile"])
            mesh = profile.geometry(window["width"], window["height"])
            assign_role_split_body(
                model, body_context, window_entity, mesh,
                # roof_payload keys a window's roles in lower case; every
                # aspect name is title-cased, so the lookup has to be too.
                {role.title(): key for role, key in window["materials"].items()},
            )
            ifc_api.spatial.assign_container(
                model, products=[window_entity], relating_structure=storey
            )
            # IfcRelFillsElement: the window fills the void it was cut for.
            ifc_api.feature.add_filling(
                model, opening=opening, element=window_entity
            )
            entities[window["key"]] = window_entity
        solid.free()

# Roof/slab clipping has now resolved native wall bodies. Read those bodies
# with opening subtraction disabled, never pre-join axis rectangles or live
# Blender bounds, and use each identical polygon for its room and main floor.
space_regions = add_spaces()
for covering in COVERINGS["main"]:
    region = space_regions[covering["space"]]
    add_floor_covering(covering, list(region.exterior.coords)[:-1])

for threshold in COVERINGS["thresholds"]:
    patch = shapely.Polygon(threshold["boundary"])
    room = space_regions[threshold["space"]]
    if not space_geometry.threshold_is_adjacent(room, patch):
        raise RuntimeError(
            f"{threshold['source']} threshold_space "
            f"'{threshold['space']}' is not adjacent to its opening"
        )
    add_floor_covering(threshold, threshold["boundary"])

# Exterior areas have an explicit FootPrint rather than an invented room
# volume. IFC owns the boundary; presentation derives a horizontal surface.
if TURFS:
    footprint_context = ifc_api.context.add_context(
        model, context_type="Plan", context_identifier="FootPrint",
        target_view="PLAN_VIEW", parent=plan_context)
for turf in TURFS:
    params = turf["parameters"]
    boundary = params["boundary"]
    entity = root_entity(model, turf, "IfcSpace")
    entity.PredefinedType = "USERDEFINED"
    entity.ObjectType = "Turf"
    ifc_api.aggregate.assign_object(model, products=[entity],
                                   relating_object=entities[turf["references"]["site"]])
    matrix = np.eye(4)
    matrix[2, 3] = params["elevation"]
    ifc_api.geometry.edit_object_placement(model, product=entity, matrix=matrix, is_si=True)
    curve = model.create_entity("IfcPolyline", Points=[
        model.create_entity("IfcCartesianPoint", Coordinates=tuple(float(v) for v in point))
        for point in boundary + [boundary[0]]])
    representation = model.create_entity("IfcShapeRepresentation",
        ContextOfItems=footprint_context, RepresentationIdentifier="FootPrint",
        RepresentationType="Curve2D", Items=[curve])
    ifc_api.geometry.assign_representation(model, product=entity, representation=representation)
    common = ifc_api.pset.add_pset(model, product=entity, name="Pset_SpaceCommon")
    ifc_api.pset.edit_pset(model, pset=common, properties={"IsExternal": True})
    authoring = ifc_api.pset.add_pset(model, product=entity, name="BBAM_Landscape")
    ifc_api.pset.edit_pset(model, pset=authoring, properties={
        "SemanticId": turf["key"], "Role": "turf", "Version": 1})
    area = abs(sum(p[0]*boundary[(i+1)%len(boundary)][1]
                   - boundary[(i+1)%len(boundary)][0]*p[1]
                   for i, p in enumerate(boundary))) / 2
    quantities = ifc_api.pset.add_qto(model, product=entity, name="Qto_SpaceBaseQuantities")
    ifc_api.pset.edit_qto(model, qto=quantities, properties={"NetFloorArea": area})
    entities[turf["key"]] = entity


print(
    {
        "schema": model.schema,
        "turfs": [turf["key"] for turf in TURFS],
        "project": project_entity.Name,
        "roofs": [roof["key"] for roof in ROOFS],
        "slabs": [slab["key"] for slab in SLABS],
        "railings": [railing["key"] for railing in RAILINGS],
        "gates": [gate["key"] for gate in GATES],
        "spaces": [
            space["key"]
            for storey_spaces in SPACES
            for space in storey_spaces["spaces"]
        ],
        "coverings": [
            item["key"]
            for group in (COVERINGS["main"], COVERINGS["thresholds"])
            for item in group
        ],
        "openings": [opening["key"] for opening in OPENINGS],
        "composed_windows": [window["key"] for window in COMPOSED_WINDOWS],
        "sills": [sill["key"] for sill in SILLS],
        "corner_openings": [corner["key"] for corner in CORNER_OPENINGS],
        "extended_to_structure": [
            item["related_element"] for item in EXTEND_TO_STRUCTURE
        ],
        "ifc_roots": len(model.by_type("IfcRoot")),
        "products": {
            ifc_class: len(model.by_type(ifc_class))
            for ifc_class in sorted(
                {entity.is_a() for entity in model.by_type("IfcProduct")}
            )
        },
    }
)
