"""Presentation phase, executed in Blender through `execute_blender_code`.

Runs after the IFC reload. The host injects `bpy` and `get_ifc_file()`.
`compile_blender` replaces the three placeholder constants below with real
literals; every other line runs exactly as written here.
"""

import json
import math
import sys

import bmesh
from mathutils import Matrix, Vector

from bonsai.bim.module.model.roof import generate_hipped_roof_bmesh


OPERATIONS = json.loads("@@OPERATIONS@@")
MATERIAL_TARGETS = json.loads("@@MATERIAL_TARGETS@@")
TURFS = json.loads("@@TURFS@@")
ROOFS = json.loads("@@ROOFS@@")
WALLS_WITH_OPENINGS = json.loads("@@WALLS_WITH_OPENINGS@@")
PACKAGE_ROOT = "@@PACKAGE_ROOT@@"
BLEND_PATH = "@@BLEND_PATH@@"

# The tile layout is the tested pure-Python implementation rather than a copy
# inlined here, so `scripts/tests/` covers exactly the code that runs.
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
from building_author import caps, tiles, trims  # noqa: E402
from building_author.flashing_clearance import flashing_render_clearances  # noqa: E402
from building_author.roof_recess import roof_wall_recess  # noqa: E402

UP = Vector((0.0, 0.0, 1.0))
_PLANAR_EPS = 1e-6

ifc_file = get_ifc_file()
for obj in list(bpy.context.scene.objects):
    try:
        definition_id = obj.BIMObjectProperties.ifc_definition_id
    except Exception:
        definition_id = 0
    if not definition_id:
        bpy.data.objects.remove(obj, do_unlink=True)

# The rebuild owns the scene, so drop what a previous run left behind rather
# than letting it pile up across reruns.
for mesh in list(bpy.data.meshes):
    if mesh.name.startswith("BA::") and not mesh.users:
        bpy.data.meshes.remove(mesh)

objects = {}
for obj in bpy.context.scene.objects:
    try:
        definition_id = obj.BIMObjectProperties.ifc_definition_id
    except Exception:
        continue
    if not definition_id:
        continue
    try:
        entity = ifc_file.by_id(definition_id)
    except Exception:
        continue
    key = getattr(entity, "Tag", None)
    if key:
        objects[key] = obj
        obj["building_author_key"] = key

# `add_feature`, in the IFC phase, only ever writes the `IfcRelVoidsElement`
# relationship - it never touches a Blender mesh, and the IFC phase's own
# `regenerate_wall_representation` pass runs once, before any opening
# exists, and only ever resolves corners. Nothing else there forces a wall's
# Blender object back in sync with the voids it now carries, so a wall can
# reach this reload still looking unopened even though its IFC data is
# correct. This runs first, before any material or tile work reads the
# scene, so nothing downstream can work from a wall that still looks unopened.
walls_to_recalculate = []
# Include host-only openings created by a project's IFC completion batch.
# Derive the authoritative host set rather than requiring source-string edits.
opening_hosts = set(WALLS_WITH_OPENINGS)
for wall_entity in ifc_file.by_type("IfcWall"):
    if wall_entity.HasOpenings and getattr(wall_entity, "Tag", None):
        opening_hosts.add(wall_entity.Tag)
for key in sorted(opening_hosts):
    obj = objects.get(key)
    if obj is None or obj.type != "MESH":
        raise RuntimeError(
            f"a wall with openings is missing from Blender: {key}"
        )
    walls_to_recalculate.append(obj)
if walls_to_recalculate:
    bpy.ops.object.select_all(action="DESELECT")
    for obj in walls_to_recalculate:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = walls_to_recalculate[0]
    bpy.ops.bim.recalculate_wall()
    bpy.ops.object.select_all(action="DESELECT")

def apply_pbr(blender_material, parameters):
    """Build the flat fallback and retain any on-demand agent recipe pointer."""

    blender_material.use_nodes = True
    nodes = blender_material.node_tree.nodes
    links = blender_material.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    principled = nodes.new("ShaderNodeBsdfPrincipled")
    links.new(principled.outputs["BSDF"], output.inputs["Surface"])
    color = parameters["base_color"]
    alpha = parameters["alpha"]
    principled.inputs["Base Color"].default_value = (*color, 1.0)
    principled.inputs["Roughness"].default_value = parameters["roughness"]
    principled.inputs["Metallic"].default_value = parameters["metallic"]
    principled.inputs["Alpha"].default_value = alpha
    principled.inputs["IOR"].default_value = parameters["ior"]
    blender_material.diffuse_color = (*color, alpha)
    if hasattr(blender_material, "use_backface_culling"):
        blender_material.use_backface_culling = not parameters.get(
            "double_sided", True
        )
    recipe = parameters.get("material_recipe")
    property_name = "building_author_material_recipe"
    if recipe is None:
        if property_name in blender_material:
            del blender_material[property_name]
    else:
        blender_material[property_name] = recipe
    # Set both branches explicitly. A material datablock can survive a rebuild;
    # without the opaque branch, changing a once-transparent finish to alpha 1
    # leaves Blender (and therefore a GLB export) in blend mode.
    if hasattr(blender_material, "blend_method"):
        blender_material.blend_method = "BLEND" if alpha < 1.0 else "OPAQUE"
    if hasattr(blender_material, "surface_render_method"):
        blender_material.surface_render_method = (
            "BLENDED" if alpha < 1.0 else "DITHERED"
        )
    return blender_material


def material_style_name(candidate):
    """Resolve a current IFC style, whose numeric ID alone is not an identity."""

    properties = getattr(candidate, "BIMStyleProperties", None)
    style_id = getattr(properties, "ifc_definition_id", 0) or 0
    if not style_id:
        return None
    try:
        style = ifc_file.by_id(style_id)
    except Exception:
        return None
    return getattr(style, "Name", None) if style.is_a("IfcSurfaceStyle") else None


def material_matches_key(candidate, material_key):
    """Recognize a semantic tag or Bonsai's style name with Blender suffix."""

    recorded = candidate.get("building_author_material_key")
    if recorded is not None:
        return recorded == material_key
    name = candidate.name
    expected = f"BA::{material_key}"
    if name == expected:
        return True
    base, separator, suffix = name.rpartition(".")
    return bool(separator and base == expected and suffix.isdigit())


def imported_materials(material_key):
    """The Blender materials Bonsai built for one IFC material's style.

    A wall's layers arrive already split into per-layer slots carrying these,
    so a layered element is only as good as they are. The IFC phase gives each
    surface style the semantic material key, because display names may repeat.
    A prior IFC's datablock can survive reload with a recycled numeric style
    ID, so its semantic key/name must agree with the current style too.
    """

    found = []
    for candidate in bpy.data.materials:
        if (material_style_name(candidate) == f"BA::{material_key}"
                and material_matches_key(candidate, material_key)):
            found.append(candidate)
    return found


def fallback_material(material_key):
    """Reuse this build's material without adopting another style's binding."""

    for candidate in bpy.data.materials:
        properties = getattr(candidate, "BIMStyleProperties", None)
        if (candidate.get("building_author_material_key") == material_key
                and not getattr(properties, "ifc_definition_id", 0)):
            return candidate
    name = f"BA::{material_key}"
    candidate = bpy.data.materials.get(name)
    if candidate is not None:
        properties = getattr(candidate, "BIMStyleProperties", None)
        style_id = getattr(properties, "ifc_definition_id", 0) or 0
        if (not material_matches_key(candidate, material_key)
                or (style_id and material_style_name(candidate) != name)):
            candidate = None
    if candidate is None:
        # Blender chooses a suffix if an old datablock owns the display name.
        # Keep that datablock and its binding intact; retain the actual object.
        candidate = bpy.data.materials.new(name)
    candidate["building_author_material_key"] = material_key
    return candidate


resolved_materials = {}
for operation in (
    item for item in OPERATIONS if item["kind"] == "pbr-material"
):
    material_key = operation["references"]["target"]
    parameters = operation["parameters"]
    blender_material = fallback_material(material_key)
    resolved_materials[material_key] = blender_material
    apply_pbr(blender_material, parameters)

    # Bonsai's import already assigned its own flat material wherever IFC says
    # this material belongs, per layer on a layered wall. Upgrading those in
    # place is what gives a wall's layers real PBR without reassigning slots
    # the IFC has already worked out.
    for existing in imported_materials(material_key):
        existing["building_author_material_key"] = material_key
        apply_pbr(existing, parameters)

    for target_key in MATERIAL_TARGETS.get(material_key, []):
        target = objects.get(target_key)
        if target is None or target.type != "MESH":
            raise RuntimeError(
                f"presentation target is missing from Blender: {target_key}"
            )
        target.data.materials.clear()
        target.data.materials.append(blender_material)

def temporary_object(source, name):
    """Wrap a bmesh in a scene object, because modifiers need a real object."""

    mesh = bpy.data.meshes.new(name)
    source.to_mesh(mesh)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def crop_to_face(field_object, face, name, reach=1.0):
    """Crop one face's tile field to that face, returning the result mesh.

    A boolean intersect against a prism spanning the face along its normal.
    Boolean is the only crop this file performs: it is correct for faces that
    are not convex, which a reflex corner in the roof boundary produces, and
    it is the same operation roof openings will need. Bisecting edge by edge
    would be far faster but is only valid on convex regions, so keeping it as
    well would mean a second path exercised rarely and trusted wrongly.

    This runs per face rather than once per roof because tiles from adjacent
    faces overlap along ridges, hips and valleys, and each face wants cropping
    to its own plane. The result is closed, so cut tiles are capped rather
    than left open.

    It does **not** run per face to give the solver input that does not
    self-intersect, which is what this said for a long time. Within a single
    face the field self-intersects anyway - every unit laps the course below
    it - so that was never achievable by splitting the work up, and the
    `use_self` flag below is what actually handles it.
    """

    normal = face.normal.normalized()
    prism = bmesh.new()
    below = [prism.verts.new(vert.co - normal * reach) for vert in face.verts]
    above = [prism.verts.new(vert.co + normal * reach) for vert in face.verts]
    prism.verts.ensure_lookup_table()
    count = len(below)
    prism.faces.new(list(reversed(below)))
    prism.faces.new(above)
    for index in range(count):
        following = (index + 1) % count
        prism.faces.new(
            [
                below[index],
                below[following],
                above[following],
                above[index],
            ]
        )
    # Make the solid consistently outward-facing rather than trusting the
    # face's winding: an inside-out cutter makes INTERSECT return nothing.
    bmesh.ops.recalc_face_normals(prism, faces=prism.faces[:])
    prism.normal_update()
    # A face may be concave, so do not hand the solver an n-gon cap.
    bmesh.ops.triangulate(prism, faces=prism.faces[:])
    cutter = temporary_object(prism, f"{name}.cutter")
    prism.free()

    modifier = field_object.modifiers.new("crop", "BOOLEAN")
    modifier.operation = "INTERSECT"
    modifier.object = cutter
    modifier.solver = "EXACT"
    # The field self-intersects: every unit laps the course below it, and a
    # pantile's rolls interpenetrate their neighbours besides. EXACT assumes
    # operands that do not, and given ones that do it returns **nothing** -
    # no error, no warning, an empty mesh and a roof with no covering.
    #
    # Cropping per face was already justified by keeping *adjacent faces'*
    # fields apart, which is a different overlap and does not help with this
    # one. `tile.clay` survives because a plain box tilted onto its own lap
    # barely interpenetrates; `tile.celtic` and `tile.standing_seam` never
    # rendered once until this flag was set.
    modifier.use_self = True

    depsgraph = bpy.context.evaluated_depsgraph_get()
    mesh = bpy.data.meshes.new_from_object(
        field_object.evaluated_get(depsgraph)
    )
    mesh.name = name

    # A boolean that eats its whole input is the failure this function is
    # most likely to hit and the one hardest to see: the covering simply is
    # not there, and every later stage runs happily on nothing.
    if len(mesh.vertices) == 0:
        raise RuntimeError(
            f"cropping {name} returned an empty mesh from a field of "
            f"{len(field_object.data.vertices)} vertices; the EXACT boolean "
            "rejected it rather than trimming it"
        )

    field_mesh = field_object.data
    cutter_mesh = cutter.data
    bpy.data.objects.remove(field_object, do_unlink=True)
    bpy.data.objects.remove(cutter, do_unlink=True)
    bpy.data.meshes.remove(field_mesh)
    bpy.data.meshes.remove(cutter_mesh)
    return mesh


def cap_runs(bm):
    """Every ridge and hip of a roof solid, as a placed run.

    `trims.edge_kind` does the classifying, exactly as `verge_runs` in the IFC
    phase does; this only harvests what a cap needs off the bmesh and turns
    the answer into a frame. Which edges these are is never declared: an
    arris where two roof faces fold away from each other is a fact about the
    solid, so a shed roof yields none and every hip of a hipped roof yields
    one without anyone listing them.

    Two things differ from a verge run, and both come from a cap sitting on
    the **bisector** of its two faces rather than against one of them:

    - ``up`` is carried rather than assumed. A verge board's up is world
      vertical for every run there will ever be; a cap's is world vertical
      only on a ridge.
    - ``cosine`` comes back with it. One dot product against either face
      normal yields both how high the cap sits and how steeply its skirt has
      to fall, so nothing downstream measures the roof a second time.

    The run points **downhill**, so each piece laps the one below it. On a
    ridge that is level and the ordering is only there to be stable.
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
        normal_b = face_b.normal.normalized()
        kind = trims.edge_kind_from_bmesh(edge)
        if kind not in (trims.RIDGE, trims.HIP):
            continue

        # A bmesh edge has no direction of its own, so order the ends rather
        # than trusting their storage order - height first, then position, so
        # a level ridge still lands the same way on every run of the build.
        high, low = sorted(
            (edge.verts[0].co.copy(), edge.verts[1].co.copy()),
            key=lambda point: (point.z, point.x, point.y),
            reverse=True,
        )
        along = (low - high).normalized()
        up = UP - along * UP.dot(along)
        if up.length < _PLANAR_EPS:
            continue  # a vertical arris has no bisector to sit on
        up.normalize()
        found.append(
            caps.CapRun(
                origin=high,
                # `up x along`, so the frame is right-handed by construction
                # and no vert or face order can flip the cap over.
                across=up.cross(along),
                up=up,
                along=along,
                length=(low - high).length,
                # Both faces give the same answer on a roof of one pitch,
                # which is the only kind `skeleton.require_supported` allows.
                # The larger of the two is the shallower fold, so a solver
                # rounding error can only seat the cap slightly high.
                cosine=max(up.dot(normal_a), up.dot(normal_b)),
            )
        )
    return found


def face_frames(bm, boundary):
    """Map each boundary edge index to the frame of the face rising from it.

    Roof windows are declared against a boundary edge, because edges are
    declared while faces are skeleton output whose numbering shifts.
    """

    frames = {}
    for face in bm.faces:
        normal = face.normal.normalized()
        if normal.z <= _PLANAR_EPS:
            continue
        origin, eave, up_slope = face_frame(face)
        # The verts sitting at v = 0 are the ones on the eave; their midpoint
        # is what identifies which declared boundary edge this face rises from.
        on_eave = [
            vert.co
            for vert in face.verts
            if abs((vert.co - origin).dot(up_slope)) < 1e-4
        ]
        eave_mid = (
            sum(on_eave, Vector()) / len(on_eave) if on_eave else origin.copy()
        )
        best, best_distance = None, None
        for index in range(len(boundary)):
            a = Vector((*boundary[index], 0.0))
            b = Vector((*boundary[(index + 1) % len(boundary)], 0.0))
            span = b - a
            length = span.length
            if length < _PLANAR_EPS:
                continue
            point = Vector((eave_mid.x, eave_mid.y, 0.0))
            t = max(0.0, min(1.0, (point - a).dot(span) / (length * length)))
            distance = (point - (a + span * t)).length
            if best_distance is None or distance < best_distance:
                best, best_distance = index, distance
        if best is not None:
            frames[best] = (origin, eave, up_slope, normal)
    return frames


def window_solid(frame, window, reach, name):
    """Build the opening box as a scene object, ready to cut with."""

    origin, eave, up_slope, normal = frame
    centre = origin + eave * window["along"] + up_slope * window["up_slope"]
    half_width = window["width"] / 2.0
    half_height = window["height"] / 2.0

    box = bmesh.new()
    made = []
    for depth in (-reach, reach):
        for sign_x, sign_y in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
            made.append(
                box.verts.new(
                    centre
                    + eave * (sign_x * half_width)
                    + up_slope * (sign_y * half_height)
                    + normal * depth
                )
            )
    box.verts.ensure_lookup_table()
    box.faces.new([made[3], made[2], made[1], made[0]])
    box.faces.new([made[4], made[5], made[6], made[7]])
    for index in range(4):
        following = (index + 1) % 4
        box.faces.new(
            [made[index], made[following], made[4 + following], made[4 + index]]
        )
    bmesh.ops.recalc_face_normals(box, faces=box.faces[:])
    obj = temporary_object(box, name)
    box.free()
    return obj, centre


def subtract_window(host, frame, window, name):
    """Cut one roof window out of the covering, returning the new mesh."""

    cutter, _ = window_solid(frame, window, 1.0, f"{name}.{window['key']}.cut")
    modifier = host.modifiers.new("opening", "BOOLEAN")
    modifier.operation = "DIFFERENCE"
    modifier.object = cutter
    modifier.solver = "EXACT"
    # Same reason as the crop: by now the covering carries a lapping field
    # and its caps, which overlap each other by design.
    modifier.use_self = True

    depsgraph = bpy.context.evaluated_depsgraph_get()
    result = bpy.data.meshes.new_from_object(host.evaluated_get(depsgraph))
    result.name = name

    host_mesh = host.data
    cutter_mesh = cutter.data
    bpy.data.objects.remove(host, do_unlink=True)
    bpy.data.objects.remove(cutter, do_unlink=True)
    bpy.data.meshes.remove(host_mesh)
    bpy.data.meshes.remove(cutter_mesh)
    return result


def face_frame(face):
    """Anchor a roof face's ``(u, v)`` frame on its eave.

    Returns ``(origin, eave, up_slope)`` with the origin on the face's lowest
    horizontal edge, so ``v = 0`` is the eave and courses march up the slope
    from there - the way tiles are actually laid. Anchoring anywhere else
    makes the layout's `floor()` snapping land at an arbitrary offset, leaving
    a partial course at the eave instead of at the ridge where trim hides it.
    """

    normal = face.normal.normalized()
    verts = [vert.co for vert in face.verts]

    eave_edge = None
    lowest = None
    for index in range(len(verts)):
        start = verts[index]
        end = verts[(index + 1) % len(verts)]
        if abs(start.z - end.z) > _PLANAR_EPS:
            continue  # not a horizontal edge, so not an eave
        height = (start.z + end.z) / 2.0
        if lowest is None or height < lowest:
            lowest = height
            eave_edge = (start.copy(), end.copy())

    if eave_edge is None:
        # No horizontal edge at all: fall back to the plane's own horizontal.
        direction = normal.cross(UP)
        if direction.length < _PLANAR_EPS:
            direction = Vector((1.0, 0.0, 0.0))
        eave_edge = (min(verts, key=lambda co: co.z).copy(), None)
        eave = direction.normalized()
    else:
        eave = (eave_edge[1] - eave_edge[0]).normalized()

    up_slope = normal.cross(eave)
    if up_slope.z < 0.0:
        # Flip both so the frame stays right-handed and v still runs uphill.
        eave = -eave
        up_slope = -up_slope
        if eave_edge[1] is not None:
            eave_edge = (eave_edge[1], eave_edge[0])
    return eave_edge[0], eave, up_slope.normalized()


tile_operations = {
    operation["references"]["target"]: operation["parameters"]
    for operation in OPERATIONS
    if operation["kind"] == "roof-tiles"
}
tile_materials = {
    operation["references"]["target"]: operation["references"].get("material")
    for operation in OPERATIONS
    if operation["kind"] == "roof-tiles"
}

tile_counts = {}
for roof in ROOFS:
    parameters = tile_operations.get(roof["key"])
    if parameters is None:
        continue

    profile = tiles.profile(parameters["profile"])

    # Rebuild the same solid the IFC phase did. The skeleton is deterministic,
    # so the faces tiled here are the faces that were exported.
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
    bm.normal_update()

    tile_verts, tile_faces, tile_uvs, _ = profile.geometry()

    # Tile and crop one face at a time, then merge. Tiles from adjacent faces
    # overlap along ridges, hips and valleys, and that overlap would make the
    # field self-intersecting - which the boolean solver cannot take.
    covering = bmesh.new()
    covering.loops.layers.uv.new("UVMap")  # so merged faces keep their UVs
    placed = 0

    for index, face in enumerate(bm.faces):
        normal = face.normal.normalized()
        if normal.z <= _PLANAR_EPS:
            continue  # underside, eave cut, or gable wall
        origin, eave, up_slope = face_frame(face)
        outline = [
            (
                (vert.co - origin).dot(eave),
                (vert.co - origin).dot(up_slope),
            )
            for vert in face.verts
        ]

        field = bmesh.new()
        field_uv = field.loops.layers.uv.new("UVMap")
        count = 0
        for u, v in tiles.centres(outline, profile, roof["covering_stagger"]):
            # A non-lapping field rides a sub-millimetre clearance above the
            # face plane, stepped course by course: without it the crop's
            # boolean is handed exact coplanar coincidences it can silently
            # resolve into a hole. See `tiles.course_clearance`.
            position = (
                origin + eave * u + up_slope * v
                + normal * tiles.course_clearance(v, profile)
            )
            placement = Matrix(
                (
                    (eave.x, up_slope.x, normal.x, position.x),
                    (eave.y, up_slope.y, normal.y, position.y),
                    (eave.z, up_slope.z, normal.z, position.z),
                    (0.0, 0.0, 0.0, 1.0),
                )
            )
            made = [
                field.verts.new(placement @ Vector(vertex))
                for vertex in tile_verts
            ]
            for corners, corner_uvs in zip(tile_faces, tile_uvs):
                built = field.faces.new([made[slot] for slot in corners])
                for loop, uv in zip(built.loops, corner_uvs):
                    loop[field_uv].uv = uv
            count += 1
        if not count:
            field.free()
            continue

        name = f"BA::{roof['key']}.face{index}"
        field_object = temporary_object(field, name)
        field.free()
        cropped = crop_to_face(field_object, face, name)
        covering.from_mesh(cropped)
        bpy.data.meshes.remove(cropped)
        placed += count

    # Cap every ridge and hip, into the same mesh. A cap is not cropped: it
    # closes the join between two fields that were each cropped flush to the
    # arris, so it has to oversail that arris rather than stop at it.
    #
    # Adjacent runs overlap where a hip meets the ridge. The cap barrels
    # conceal the junction.
    #
    # This lands before the roof windows are subtracted, so a window reaching
    # a ridge cuts its cap too. Lapping caps inside the boolean is safe for
    # the reason lapping tiles already are: the field has been handing the
    # solver self-intersecting input since the first roof.
    cap = caps.profile(parameters["cap"]) if parameters.get("cap") else None
    capped = 0
    if cap is not None:
        # Fetched fresh rather than kept from before the crop: `from_mesh`
        # invalidates a layer reference taken earlier, and a stale one writes
        # UVs into freed memory rather than raising.
        covering_uv = covering.loops.layers.uv.verify()
        envelope = profile.envelope()
        for run in cap_runs(bm):
            # Both numbers come from the covering: how high it reaches, and
            # how far it drops back between those highs. The first seats the
            # cap, the second shapes the skirt that closes over the drop.
            seat = caps.seating(
                envelope, run.cosine, cap.foot, profile.relief
            )
            spacing = caps.spacing(run.length, cap)
            cap_verts, cap_faces, cap_uvs, _ = cap.geometry(seat, spacing.piece)
            for station in spacing.stations:
                position = run.origin + run.along * station
                placement = Matrix(
                    (
                        (run.across.x, run.up.x, run.along.x, position.x),
                        (run.across.y, run.up.y, run.along.y, position.y),
                        (run.across.z, run.up.z, run.along.z, position.z),
                        (0.0, 0.0, 0.0, 1.0),
                    )
                )
                made = [
                    covering.verts.new(placement @ Vector(vertex))
                    for vertex in cap_verts
                ]
                for corners, corner_uvs in zip(cap_faces, cap_uvs):
                    built = covering.faces.new([made[slot] for slot in corners])
                    for loop, uv in zip(built.loops, corner_uvs):
                        loop[covering_uv].uv = uv
                capped += 1

    # Punch the roof windows out of the covering with the same boxes that
    # void the IFC roof, so the hole in the tiles matches the hole in the BIM.
    openings = []
    if roof["roof_windows"]:
        frames = face_frames(bm, roof["overhang_boundary"])
        for window in roof["roof_windows"]:
            frame = frames.get(window["edge"])
            if frame is None:
                raise RuntimeError(
                    f"{window['key']} is hosted on edge {window['edge']} of "
                    f"{roof['key']}, but no roof face rises from that edge"
                )
            openings.append((window, frame))

    bm.free()

    mesh = bpy.data.meshes.new(f"BA::{roof['key']}.covering")
    covering.to_mesh(mesh)
    covering.free()

    for window, frame in openings:
        holder = bpy.data.objects.new(f"BA::{window['key']}.host", mesh)
        bpy.context.scene.collection.objects.link(holder)
        mesh = subtract_window(holder, frame, window,
                               f"BA::{roof['key']}.covering")

    material_key = tile_materials.get(roof["key"])
    if material_key:
        blender_material = resolved_materials.get(material_key)
        if blender_material is not None:
            # `new_from_object` on a boolean-evaluated object hands back a
            # mesh carrying one empty material slot, while every face keeps
            # material_index 0. Appending the tile would land it in slot 1
            # and leave the whole field rendering with no material, so an
            # empty slot is filled instead of skipped.
            if mesh.materials and mesh.materials[0] is None:
                mesh.materials[0] = blender_material
            else:
                mesh.materials.append(blender_material)

    # The covering is an IfcCovering(ROOFING) created in the IFC phase, so
    # swap the tile field onto that element rather than making a second,
    # BIM-less object beside it.
    covering_key = f"{roof['key']}.covering"
    obj = objects.get(covering_key)
    if obj is None:
        raise RuntimeError(
            f"{covering_key} was not found in Blender; the IFC phase should "
            "have created an IfcCovering for this roof"
        )
    previous = obj.data
    obj.data = mesh
    if previous.users == 0:
        bpy.data.meshes.remove(previous)

    # Bonsai imports the skylight's IFC shape aspects as separate frame and
    # glazing slots on the same object.
    tile_counts[roof["key"]] = {
        "tiles": placed,
        "caps": capped,
        "verts": len(mesh.vertices),
        "polys": len(mesh.polygons),
    }

# Render-only roof-body relief. The original mesh coordinates, IFC body,
# roof parameters, tiles and caps stay untouched. A non-applied modifier
# carries the evaluated displacement into Blender rendering and GLB export.
def world_mesh(obj):
    return (
        [tuple(obj.matrix_world @ v.co) for v in obj.data.vertices],
        [tuple(p.vertices) for p in obj.data.polygons],
    )


def apply_render_displacements(obj, deltas, report, *, modifier_name,
                               attribute_name, group_name, report_key):
    """Replace a presentation offset without changing source vertices or IFC."""

    existing = obj.modifiers.get(modifier_name)
    if existing:
        obj.modifiers.remove(existing)
    if obj.data.users > 1:
        obj.data = obj.data.copy()
    if not report["moved_vertices"]:
        stale_attribute = obj.data.attributes.get(attribute_name)
        if stale_attribute:
            obj.data.attributes.remove(stale_attribute)
        if report_key in obj:
            del obj[report_key]
        return
    attribute = obj.data.attributes.get(attribute_name)
    if attribute is None:
        attribute = obj.data.attributes.new(attribute_name, "FLOAT_VECTOR", "POINT")
    inverse = obj.matrix_world.to_3x3().inverted()
    for item, delta in zip(attribute.data, deltas):
        item.vector = inverse @ Vector(delta)
    group = bpy.data.node_groups.get(group_name)
    if group is None:
        group = bpy.data.node_groups.new(group_name, "GeometryNodeTree")
        group.interface.new_socket(name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
        group.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
        source = group.nodes.new("NodeGroupInput")
        target = group.nodes.new("NodeGroupOutput")
        offset = group.nodes.new("GeometryNodeInputNamedAttribute")
        offset.data_type = "FLOAT_VECTOR"
        offset.inputs["Name"].default_value = attribute_name
        position = group.nodes.new("GeometryNodeSetPosition")
        group.links.new(source.outputs["Geometry"], position.inputs["Geometry"])
        group.links.new(offset.outputs["Attribute"], position.inputs["Offset"])
        group.links.new(position.outputs["Geometry"], target.inputs["Geometry"])
    modifier = obj.modifiers.new(modifier_name, "NODES")
    modifier.node_group = group
    obj[report_key] = json.dumps(report, sort_keys=True)


# Read each source wall mesh once. Both contact passes use this cached data;
# neither evaluates the same wall repeatedly through Blender's dependency graph.
wall_meshes = [world_mesh(obj) for obj in objects.values()
               if obj.type == "MESH"
               and ifc_file.by_id(obj.BIMObjectProperties.ifc_definition_id).is_a("IfcWall")]
recess_reports = {}
for roof in ROOFS:
    obj = objects.get(roof["key"])
    if obj is None or obj.type != "MESH":
        continue
    deltas, report = roof_wall_recess(*world_mesh(obj), wall_meshes)
    recess_reports[roof["key"]] = report
    apply_render_displacements(
        obj, deltas, report, modifier_name="BA::Roof render recess",
        attribute_name="ba_roof_render_recess",
        group_name="BA::Roof render recess graph",
        report_key="building_author_roof_recess",
    )

flashing_reports = {}
for roof in ROOFS:
    prefix = f"{roof['key']}.verge."
    flashing_meshes = {}
    for key, obj in sorted(objects.items()):
        if (obj.type != "MESH" or not key.startswith(prefix)
                or not key[len(prefix):].isdigit()):
            continue
        entity = ifc_file.by_id(obj.BIMObjectProperties.ifc_definition_id)
        if not entity.is_a("IfcCovering") or entity.ObjectType != "Flashing":
            continue
        # The generated section's local X points inboard. Transform the outer
        # plane's normal, including any object rotation or nonuniform scale.
        outward = (obj.matrix_world.to_3x3().inverted().transposed()
                   @ Vector((-1.0, 0.0, 0.0))).normalized()
        flashing_meshes[key] = (*world_mesh(obj), tuple(outward))
    if not flashing_meshes:
        continue
    # A board is flush with its roof's gable plane by construction, so the
    # roof body and its covering are coplanar competitors alongside the walls.
    roof_meshes = [world_mesh(objects[key])
                   for key in (roof["key"], roof["key"] + ".covering")
                   if key in objects and objects[key].type == "MESH"]
    for key, (deltas, report) in flashing_render_clearances(
            flashing_meshes, wall_meshes + roof_meshes).items():
        flashing_reports[key] = report
        apply_render_displacements(
            objects[key], deltas, report,
            modifier_name="BA::Flashing render clearance",
            attribute_name="ba_flashing_render_clearance",
            group_name="BA::Flashing render clearance graph",
            report_key="building_author_flashing_clearance",
        )

# The IFC space may import as a curve or be omitted by the importer. Resolve
# it by its persisted semantic property, never by its display name or Tag.
from ifcopenshell.util.element import get_pset
from ifcopenshell.util.placement import get_local_placement
from mathutils.geometry import tessellate_polygon
for turf in TURFS:
    matches = [entity for entity in ifc_file.by_type("IfcSpace")
               if get_pset(entity, "BBAM_Landscape", "SemanticId") == turf["key"]]
    if len(matches) != 1:
        raise RuntimeError(f"Expected one IFC turf space for {turf['key']}")
    entity = matches[0]
    representation = next(rep for rep in entity.Representation.Representations
                          if rep.RepresentationIdentifier == "FootPrint")
    coords = [tuple(point.Coordinates) for point in representation.Items[0].Points][:-1]
    vertices = [Vector((x, y, 0)) for x, y in coords]
    triangles = tessellate_polygon([vertices])
    indices = {tuple(vertex): index for index, vertex in enumerate(vertices)}
    faces = [tuple(v if isinstance(v, int) else indices[tuple(v)]
                   for v in triangle) for triangle in triangles]
    mesh = bpy.data.meshes.new("BA::" + turf["key"])
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    uv = mesh.uv_layers.new(name="UVMap")
    for loop in mesh.loops:
        uv.data[loop.index].uv = coords[loop.vertex_index]
    obj = bpy.data.objects.new(turf["parameters"]["name"], mesh)
    bpy.context.scene.collection.objects.link(obj)
    obj.matrix_world = Matrix(get_local_placement(entity.ObjectPlacement).tolist())
    obj["building_author_key"] = turf["key"]
    obj["landscape"] = {"version": 1, "id": turf["key"], "role": "turf",
                        "ifcGlobalId": entity.GlobalId}
    mat = bpy.data.materials.get("BA::Turf") or bpy.data.materials.new("BA::Turf")
    mat.use_nodes = True
    mat.diffuse_color = (0.12, 0.23, 0.055, 1)
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = mat.diffuse_color
    bsdf.inputs["Roughness"].default_value = 0.95
    mesh.materials.append(mat)
    objects[turf["key"]] = obj

bpy.ops.object.select_all(action="DESELECT")
built_objects = [obj for obj in objects.values() if obj.type == "MESH"]
for obj in built_objects:
    obj.select_set(True)
if built_objects:
    bpy.context.view_layer.objects.active = built_objects[0]

bpy.ops.wm.save_as_mainfile(filepath=BLEND_PATH)
print(
    {
        "blend_path": BLEND_PATH,
        "ifc_objects": len(objects),
        "mesh_objects": len(built_objects),
        "presentation_operations": len(OPERATIONS),
        "tiles": tile_counts,
    }
)
