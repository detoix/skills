"""Minimal executable building-as-code example."""

import math

from building_author import (
    Building,
    building,
    corner_opening,
    covering,
    door,
    downspout,
    driveway_gate,
    extend_to_structure,
    fence,
    gate_fence_connections,
    gutter,
    layer,
    material,
    project,
    pedestrian_gate,
    railing,
    roof,
    roof_edge,
    roof_window,
    site,
    slab,
    slab_type,
    space,
    storey,
    virtual_element,
    wall,
    wall_type,
    window,
    window_lining,
    window_panel,
    window_sill,
    window_type,
)
from building_author import gutters
from building_author.materials import (
    anthracite_aluminium,
    glass,
    herringbone_wood,
    opening_frame,
    roof_tile,
    stucco,
    window_frame,
)
from building_author.openings import (
    casement_window_type,
    fixed_window_type,
    panel_door_type,
)

model = Building("minimal-house")

project(model, "demo-project", name="Minimal House Project")
site(model, "plot", project="demo-project", name="Demo Site")
building(model, "house", site="plot", name="Minimal House")
storey(model, "ground", building="house", name="Ground Floor", elevation=0.0)
storey(model, "attic", building="house", name="Attic", elevation=3.0)

stucco(model, "stucco.white")
roof_tile(model, "tile.terracotta")
herringbone_wood(model, "timber.decking")
herringbone_wood(model, "timber.flooring")
window_frame(model, "frame.metal")
opening_frame(model, "frame.joinery")
glass(model, "glazing")
anthracite_aluminium(model, "fence.aluminium")

# Material layers for this demonstration model.
material(model, "plaster.internal", ifc_name="Gypsum plaster", category="plaster", base_color=(0.90, 0.90, 0.88), roughness=0.9)
material(model, "block.aac", ifc_name="Aerated concrete block", category="masonry", base_color=(0.75, 0.75, 0.72), roughness=0.9)
material(model, "insulation.eps", ifc_name="EPS insulation", category="insulation", base_color=(0.95, 0.93, 0.70), roughness=0.95)
material(model, "brick", ifc_name="Clay brick", category="masonry", base_color=(0.70, 0.40, 0.32), roughness=0.9)
material(model, "concrete", ifc_name="Concrete", category="concrete", base_color=(0.72, 0.71, 0.68), roughness=0.85)
material(model, "screed", ifc_name="Cement screed", category="screed", base_color=(0.78, 0.76, 0.72), roughness=0.8)
material(model, "tile.outdoor", ifc_name="Outdoor porcelain tile", category="tile", base_color=(0.65, 0.63, 0.58), roughness=0.55)
material(model, "tile.ceramic", ifc_name="Indoor ceramic tile", category="tile", base_color=(0.72, 0.74, 0.73), roughness=0.38)
material(model, "stone.sill", ifc_name="Precast concrete sill", category="concrete", base_color=(0.80, 0.79, 0.75), roughness=0.6)
material(model, "metal.zinc", ifc_name="Titanium zinc", category="metal", base_color=(0.62, 0.64, 0.66), metallic=0.9, roughness=0.35)
material(model, "insulation.xps", ifc_name="XPS insulation", category="insulation", base_color=(0.55, 0.72, 0.80), roughness=0.9)
material(model, "plinth.render", ifc_name="Plinth render", category="plaster", base_color=(0.34, 0.34, 0.33), roughness=0.85)

wall_type(model, "ext.470", name="External Wall 470", predefined_type="SOLIDWALL", layers=[
    layer("plaster.internal", 0.010, priority=10, category="Inner finish", name="Internal Plaster"),
    layer("block.aac", 0.250, priority=90, category="LoadBearing", name="Aerated Concrete"),
    layer("insulation.eps", 0.200, priority=20, category="Insulation", name="EPS"),
    layer("stucco.white", 0.010, priority=10, category="Outer finish", name="External Render"),
])
wall_type(model, "int.120", name="Partition 120", predefined_type="PARTITIONING", layers=[
    layer("plaster.internal", 0.010, priority=10, category="Inner finish", name="Plaster"),
    layer("brick", 0.100, priority=60, category="LoadBearing", name="Brick"),
    layer("plaster.internal", 0.010, priority=10, category="Inner finish", name="Plaster"),
])
# The base course, 30 mm thinner than the wall it carries. Both runs centre on
# the same reference line, so that difference is what sets the plinth face back
# 15 mm on each side; there is no recess to state separately.
wall_type(model, "plinth.440", name="Plinth 440", predefined_type="SOLIDWALL", layers=[
    layer("concrete", 0.250, priority=90, category="LoadBearing", name="Foundation Concrete"),
    layer("insulation.xps", 0.180, priority=20, category="Insulation", name="XPS"),
    layer("plinth.render", 0.010, priority=10, category="Outer finish", name="Plinth Render"),
])
slab_type(model, "floor.200", name="Ground Floor Slab 200", predefined_type="BASESLAB", layers=[
    layer("concrete", 0.150, priority=90, category="LoadBearing", name="Structural Slab"),
    layer("screed", 0.050, priority=10, category="Finish", name="Screed"),
])
# `FLOOR`, not `BASESLAB`: neither deck bears on the ground the way the house's
# own ground slab does - the terrace floats above the ground on its own base,
# and the balcony cantilevers off the east gable wall.
slab_type(model, "balcony.floor", name="Balcony Slab 180", predefined_type="FLOOR", layers=[
    layer("concrete", 0.150, priority=90, category="LoadBearing", name="Structural Slab"),
    layer("tile.outdoor", 0.030, priority=10, category="Finish", name="Outdoor Tile"),
])

# `base_offset` is where the slab's own AXIS3 extrusion starts, not where its
# top ends up - declared as the negative of the type's total thickness so the
# top lands flush with the ground storey, the way the walls above expect.
slab(model, "ground-slab", storey="ground", slab_type="floor.200", boundary=[(0.0, 0.0), (8.0, 0.0), (8.0, 6.0), (0.0, 6.0)], base_offset=-0.200, name="Ground Slab")

# The wooden terrace stands off the north wall, in the garden the roof's own
# overhang shelters closest to the house. Its own base_offset is the negative
# of terrace.wood's total thickness, the same rule as ground-slab above - the
# usual case, so its top meets the garden door's threshold flush.
# One slab, one material, two tiers. Plinth-high, so its deck lands flush
# with the ground storey and the garden door's threshold, and it steps down
# once on the way to the garden. Every footprint is stated: the lower tier
# reaches 0.30 further on the three open edges and stays flush against the
# north wall, which is the edge the house is on.
# The north wall's axis is y = 6.0 and ext.470 is centred on it, so its render
# face - and the plinth's, which is 30 mm thinner - is half a thickness out.
# A deck butts that face, not the axis it is drawn from.
NORTH_FACE = 6.0 + 0.470 / 2
TERRACE_DECK = [(1.5, NORTH_FACE), (6.5, NORTH_FACE), (6.5, 9.5), (1.5, 9.5)]
TERRACE_STEP = [(1.2, NORTH_FACE), (6.8, NORTH_FACE), (6.8, 9.8), (1.2, 9.8)]
slab(model, "terrace", storey="ground", predefined_type="FLOOR", material="timber.decking",
     tiers=[(TERRACE_STEP, 0.150), (TERRACE_DECK, 0.150)],
     base_offset=-0.300, name="Terrace")

# The balcony cantilevers off the east gable wall, at the attic floor's own
# elevation - its boundary starts flush at x=8.0, the gable wall's own face,
# and its base_offset is balcony.floor's total thickness, so its top meets
# the balcony door's threshold flush the same way.
slab(model, "balcony", storey="attic", slab_type="balcony.floor", boundary=[(8.0, 1.5), (9.2, 1.5), (9.2, 4.5), (8.0, 4.5)], base_offset=-0.180, name="Balcony")

# The footprint is walked anticlockwise, which puts the interior on the left of
# every wall. NEGATIVE then stacks the layers leftwards from the reference
# line, so the layer declared first lands inside and the render lands outside.
wall(model, "south-wall", storey="ground", wall_type="ext.470", axis=((0.0, 0.0), (8.0, 0.0)), height=3.0, direction_sense="NEGATIVE")
wall(model, "east-wall", storey="ground", wall_type="ext.470", axis=((8.0, 0.0), (8.0, 6.0)), height=3.0, direction_sense="NEGATIVE")
wall(model, "north-wall", storey="ground", wall_type="ext.470", axis=((8.0, 6.0), (0.0, 6.0)), height=3.0, direction_sense="NEGATIVE")
wall(model, "west-wall", storey="ground", wall_type="ext.470", axis=((0.0, 6.0), (0.0, 0.0)), height=3.0, direction_sense="NEGATIVE")
wall(model, "east-gable", storey="attic", wall_type="ext.470", axis=((8.0, 0.0), (8.0, 6.0)), height=3.5, direction_sense="NEGATIVE", name="East Gable Wall")
wall(model, "west-gable", storey="attic", wall_type="ext.470", axis=((0.0, 6.0), (0.0, 0.0)), height=3.5, direction_sense="NEGATIVE", name="West Gable Wall")
# Ends on the south wall's path, not at a corner: an ATPATH junction.
wall(model, "partition", storey="ground", wall_type="int.120", axis=((4.5, 0.0), (4.5, 4.0)), height=3.0)
# The partition stops short of the north wall on purpose: this closes the gap
# between its open end and the north wall with no physical construction, so
# the bedroom and the living room stay two spaces either side of a threshold
# that is only ever open.
virtual_element(model, "partition.divider", storey="ground", axis=((4.5, 4.0), (4.5, 6.0)))

# The house meets the ground on a 300 mm plinth: the same four axes again,
# dropped below the storey datum, so grade sits at -0.300 and the ground slab
# rings inside it. Each run corners with its neighbours and with nothing above
# it, because stacking on a shared axis is not a junction. A building that
# starts at grade instead simply omits these four lines.
wall(model, "south-plinth", storey="ground", wall_type="plinth.440", axis=((0.0, 0.0), (8.0, 0.0)), height=0.30, base_offset=-0.30, direction_sense="NEGATIVE")
wall(model, "east-plinth", storey="ground", wall_type="plinth.440", axis=((8.0, 0.0), (8.0, 6.0)), height=0.30, base_offset=-0.30, direction_sense="NEGATIVE")
wall(model, "north-plinth", storey="ground", wall_type="plinth.440", axis=((8.0, 6.0), (0.0, 6.0)), height=0.30, base_offset=-0.30, direction_sense="NEGATIVE")
wall(model, "west-plinth", storey="ground", wall_type="plinth.440", axis=((0.0, 6.0), (0.0, 0.0)), height=0.30, base_offset=-0.30, direction_sense="NEGATIVE")

casement_window_type(model, "wt.casement")
fixed_window_type(model, "wt.fixed")
panel_door_type(model, "dt.entrance", operation_type="SINGLE_SWING_LEFT")
panel_door_type(model, "dt.internal", operation_type="SINGLE_SWING_RIGHT")
# A second recipe, stated rather than reused, for the flush corner window
# below: same section as `wt.fixed`, but `offset` moves `LiningOffset` off
# the wall's own centred position - 0.235 (the wall's half-thickness) minus
# 0.04 (half this lining's own 0.08 depth) - so the lining's outer face
# sits flush with the wall's own outer face instead of buried in its middle.
# Negative, not positive: local +Y is the interior face on a wall drawn this
# project's own way (the footprint walked anticlockwise), the same fact
# that decides a sill's mitre sign - a positive offset would push the
# lining flush with the inside of the wall instead of the outside.
window_type(model, "wt.flush", name="Flush Window", predefined_type="WINDOW",
            partitioning_type="SINGLE_PANEL",
            lining=window_lining(depth=0.08, thickness=0.06,
                                 to_panel_offset_x=0.04, to_panel_offset_y=0.025,
                                 offset=-0.195),
            panels=[window_panel(frame_depth=0.08, frame_thickness=0.07,
                                 operation_type="FIXEDCASEMENT")])

# `along` measures from the wall's own reference line start, so a window stays
# on its wall when the wall moves. The south wall runs (0,0) to (8,0).
# The footprint is walked anticlockwise, so a wall's +Y is its inward face.
# NEGATIVE turns the door about its own height to open the other way; with
# SINGLE_SWING_LEFT that is the fourth of the four states IFC can express.
door(model, "front-door", wall="south-wall", door_type="dt.entrance", along=1.4, overall_width=1.00, overall_height=2.10, direction_sense="NEGATIVE", lining_material="frame.joinery", framing_material="frame.joinery", is_external=True, name="Front Door")
window(model, "south-window", wall="south-wall", window_type="wt.casement", along=5.2, sill_height=0.90, overall_width=1.60, overall_height=1.40, lining_material="frame.joinery", framing_material="frame.joinery", glazing_material="glazing", name="Living Room Window")
window(model, "east-window", wall="east-wall", window_type="wt.fixed", along=3.0, sill_height=1.20, overall_width=0.90, overall_height=1.10, lining_material="frame.joinery", framing_material="frame.joinery", glazing_material="glazing", name="Stair Light")
# The north wall runs (8,6) to (0,6), so along=3.0 lands at x=5.0 - centred
# under the terrace's own span, x=1.5..6.5.
door(model, "garden-door", wall="north-wall", door_type="dt.entrance", along=3.0, overall_width=1.00, overall_height=2.10, lining_material="frame.joinery", framing_material="frame.joinery", is_external=True, name="Garden Door")
# The east gable wall runs (8,0) to (8,6), so along=3.0 lands at y=3.0 -
# centred under the balcony's own span, y=1.5..4.5.
door(model, "balcony-door", wall="east-gable", door_type="dt.entrance", along=3.0, overall_width=1.00, overall_height=2.10, lining_material="frame.joinery", framing_material="frame.joinery", is_external=True, name="Balcony Door")
# The finish through this opening is a separate covering occurrence rather
# than a bridge merged into either room finish. `threshold_space` selects its
# sole spatial owner; all finish data is inherited from that room's covering.
door(model, "bedroom-door", wall="partition", door_type="dt.internal", along=2.7, overall_width=0.90, overall_height=2.10, lining_material="frame.joinery", framing_material="frame.joinery", threshold_space="bedroom", name="Bedroom Door")

# A projecting sill under each ordinary window: wider than its opening by
# `horn`, proud of the wall face by `projection`, an `IfcBuildingElementPart`
# aggregated onto the window it serves rather than a second copy of the
# frame's own reveal.
window_sill(model, "south-window.sill", window="south-window", horn=0.05, projection=0.05, thickness=0.03, material="stone.sill", name="Living Room Window Sill")
window_sill(model, "east-window.sill", window="east-window", horn=0.04, projection=0.05, thickness=0.03, material="stone.sill", name="Stair Light Sill")

# A corner window: two fixed lights on adjacent walls, meeting at the
# north-west corner (0, 6). Each window's own opening only ever voids its
# own host, so it never reaches the solid the two walls still mitre
# between themselves there - `corner_opening` below is what actually clears
# that, sized from both walls' own declared thickness rather than guessed.
# The north wall runs (8,6) to (0,6), so along=7.4 puts this window's far
# edge exactly at along=8, the wall's own end; the west wall runs (0,6) to
# (0,0), so along=0.6 puts its near edge exactly at along=0, the wall's own
# start - the same point.
window(model, "corner-window.north", wall="north-wall", window_type="wt.fixed", along=7.40, sill_height=0.90, overall_width=1.20, overall_height=1.40, lining_material="frame.joinery", framing_material="frame.joinery", glazing_material="glazing", name="Corner Window - North")
window(model, "corner-window.west", wall="west-wall", window_type="wt.fixed", along=0.60, sill_height=0.90, overall_width=1.20, overall_height=1.40, lining_material="frame.joinery", framing_material="frame.joinery", glazing_material="glazing", name="Corner Window - West")
# Neither wall is touched - both keep the axis, length and corner mitre
# they were declared with above. This corner cut uses a separate IFC opening
# occurrence per host, sharing cutter geometry sized through each wall by
# that wall's own thickness and along
# it by the other wall's - the most either wall's own mitre with the other
# could ever occupy - not by how far a single-wall opening happened to
# reach. `base`/`height` match the two windows' own sill_height/height.
corner_opening(model, "corner-window.opening", walls=("north-wall", "west-wall"), base=0.90, height=1.40)

# Each sill mitres toward the other: `corner="end"` on the north sill and
# `corner="start"` on the west sill each name the end of their own wall that
# faces (0, 6). Both windows now touch that point exactly, so each sill's
# own un-mitred edge is only its own `horn` past it (0.05 m); `corner_reach`
# still has to reach the other wall's own sill extent from there - its
# half-thickness plus its own projection, less the 0.05 m horn already
# covers: 0.235 + 0.05 - 0.05 = 0.235 m on both sides here, since the two
# windows are detailed identically. Both walls are drawn as part of the
# footprint's own anticlockwise walk, so local Y is interior and the sill's
# exterior corner - the one that actually needs to wrap - is the negative
# one.
window_sill(model, "corner-window.north.sill", window="corner-window.north", horn=0.05, projection=0.05, thickness=0.03, material="stone.sill", corner="end", corner_reach=-0.235, name="Corner Window Sill - North")
window_sill(model, "corner-window.west.sill", window="corner-window.west", horn=0.05, projection=0.05, thickness=0.03, material="stone.sill", corner="start", corner_reach=-0.235, name="Corner Window Sill - West")

# A second corner window, at the south-east corner (8, 0), on `wt.flush`
# instead of `wt.fixed` - proving the same declarations work whether the
# glazing sits centred in the wall or pushed flush to its outer face. But
# `along` is *not* the same 7.4/0.6 the centred pair uses, and not simply
# "reach as far as the exterior face reaches" either - that was tried and
# overlapped by the window's own full frame depth: each window's generated
# frame is a plain box, with no mitre this skill can cut into it the way
# it can a sill, so pushing both frames all the way to the shared corner
# point made them interpenetrate. Nor is touching them exactly right - an
# exact edge-to-edge match is the same coincident-face risk `CLEARANCE`
# and `SILL_RISE` already exist to avoid elsewhere, just not yet named
# here. So each frame reaches to the *other* window's own fixed depth
# face - x = 8.13 for south, y = -0.13 for east, neither dependent on the
# other's own along - plus the same 0.004 m deliberate overlap: along =
# (8.13 + 0.004) - 0.6 = 7.534, along = 0.6 + (-0.13 - 0.004) = 0.466.
window(model, "corner-window.south", wall="south-wall", window_type="wt.flush", along=7.534, sill_height=0.90, overall_width=1.20, overall_height=1.40, lining_material="frame.joinery", framing_material="frame.joinery", glazing_material="glazing", name="Corner Window - South")
window(model, "corner-window.east", wall="east-wall", window_type="wt.flush", along=0.466, sill_height=0.90, overall_width=1.20, overall_height=1.40, lining_material="frame.joinery", framing_material="frame.joinery", glazing_material="glazing", name="Corner Window - East")
corner_opening(model, "corner-window.opening.2", walls=("south-wall", "east-wall"), base=0.90, height=1.40)
# The sill still needs its own mitre, recomputed for these along values:
# each sill's own un-mitred near corner now sits short of its target by
# 0.101 m, so corner_reach=-0.101 on both, closing that gap the same
# trapezoid way the centred pair's sills do.
window_sill(model, "corner-window.south.sill", window="corner-window.south", horn=0.05, projection=0.05, thickness=0.03, material="stone.sill", corner="end", corner_reach=-0.101, name="Corner Window Sill - South")
window_sill(model, "corner-window.east.sill", window="corner-window.east", horn=0.05, projection=0.05, thickness=0.03, material="stone.sill", corner="start", corner_reach=-0.101, name="Corner Window Sill - East")

# `verge_trim` runs an upright board along the verges. Which edges those are
# is not stated here and could not be: a verge is where a sloping face meets
# something that is not roof surface, and the two `defines_slope=False` lines
# below are already what makes the solid produce those edges. Declaring the
# profile is the whole of it - four runs follow, two per gable, and a roof
# hipped at both ends would grow none from the same line. Its section is the
# catalogued 170 x 80; how high its lip sits is the one thing left unstated,
# because the compiler derives that from `tile.clay`'s own relief.
roof(model, "main-roof", storey="attic", boundary=[(0.0, 0.0), (8.0, 0.0), (8.0, 6.0), (0.0, 6.0)], angle=40.0, thickness=0.30, top_material="concrete", ceiling_material="plaster.internal", side_material="stucco.white", base_offset=0.0, overhang=0.4, covering="tile.clay", covering_material="tile.terracotta", verge_trim="verge.standard", verge_trim_material="metal.zinc", name="Main Roof")
roof_edge(model, "main-roof", 1, defines_slope=False)
roof_edge(model, "main-roof", 3, defines_slope=False)
roof_window(model, "skylight", roof="main-roof", edge=0, along=4.0, up_slope=1.5, width=0.94, height=1.40, material="frame.metal", glazing="glazing", name="Skylight")
extend_to_structure(model, "east-gable.top", relating_element="main-roof", related_element="east-gable", termination="TOP_SURFACE")
extend_to_structure(model, "west-gable.top", relating_element="main-roof", related_element="west-gable", termination="TOP_SURFACE")

# Gutters hang on the two eaves. Edges 1 and 3 are gables and carry none, so
# each run stop-ends rather than mitreing into nothing - derived from which
# edges were declared, not stated. A run hangs just under its roof's drip edge
# without being told to; that is the one thing it asks its roof.
gutter(model, "main-roof.eave.south", roof="main-roof", edge=0, profile="gutter.half_round", nominal_size=0.125, material="metal.zinc", name="South Gutter")
gutter(model, "main-roof.eave.north", roof="main-roof", edge=2, profile="gutter.box", nominal_size=0.125, material="metal.zinc", name="North Gutter")

# `standoff` and `length` are stated, not derived: how far back a pipe reaches
# depends on the wall it is fixed to, and how far it falls on the ground, and
# neither the downspout nor its gutter knows either. That is the authoring
# agent's arithmetic - but it is arithmetic over declared numbers, not
# constants measured off a built model, so it follows if the roof or the wall
# type ever change. `drop` is NOT stated: how far a pipe must fall before it
# can swan back under the overhang belongs to the gutter's own roof, so the
# compiler derives it.
HALF_ROUND = gutters.profile("gutter.half_round")
BOX = gutters.profile("gutter.box")
GUTTER_SIZE = 0.125

EAVE_Z = 3.0                                            # attic elevation + the roof's base_offset
SOUTH_SOLE_Z = EAVE_Z - gutters.sole_below_eave(HALF_ROUND, GUTTER_SIZE)
NORTH_SOLE_Z = EAVE_Z - gutters.sole_below_eave(BOX, GUTTER_SIZE)
SHOE_FALL = gutters.SHOE_LENGTH * math.cos(math.radians(gutters.SHOE_ANGLE))

# Across: the sole hangs `overhang` plus its own half width outboard of the
# wall axis; the render face is half the wall's own thickness out from it. A
# pipe wants its centre one radius plus a working gap short of that face, so
# the two shapes want slightly different standoffs - which is the whole reason
# this is stated rather than derived inside a downspout that knows no wall.
WALL_FACE = 0.470 / 2                                   # ext.470, centred on its axis
SOLE_OUT = 0.4 - HALF_ROUND.sole(GUTTER_SIZE).across     # overhang + half the gutter
CLEAR = 0.02
SOUTH_STANDOFF = SOLE_OUT - WALL_FACE - 0.100 / 2 - CLEAR
NORTH_STANDOFF = SOLE_OUT - WALL_FACE - 0.080 / 2 - CLEAR

# South: round pipe with shoes, discharging onto splash blocks clear of the plinth.
for number, along in enumerate((0.7, 8.1)):
    downspout(model, f"main-roof.eave.south.ds.{number}", gutter="main-roof.eave.south", along=along, profile="downspout.round", nominal_size=0.100, length=SOUTH_SOLE_Z - 0.12 - SHOE_FALL, termination="shoe", standoff=SOUTH_STANDOFF, bend_radius=0.08, material="metal.zinc", name=f"South Downspout {number + 1}")

# North: square pipe stopping square over gullies set directly below.
for number, along in enumerate((0.7, 8.1)):
    downspout(model, f"main-roof.eave.north.ds.{number}", gutter="main-roof.eave.north", along=along, profile="downspout.rectangular", nominal_size=0.080, length=NORTH_SOLE_Z - 0.10, termination="straight", standoff=NORTH_STANDOFF, bend_radius=0.08, material="metal.zinc", name=f"North Downspout {number + 1}")

# The street boundary is one matching Horizon 020 family: mostly opaque
# aluminium fence runs, a two-leaf driveway gate, and the smaller one-leaf
# pedestrian gate (also called a wicket, or `furtka` in Polish). Gate paths
# state clear passage; each gate procedure owns the support posts outside that
# path. Adjacent fence paths therefore end on those post centres and suppress
# their own terminal post, avoiding coincident solids in IFC and GLB.
#
# Grade is 300 mm below the ground-storey datum, matching the plinth above, so
# the complete boundary uses the same -0.300 base offset instead of floating at
# finished-floor level. The 1.32 m height is one of Horizon's published 120 mm
# increments, and both gate widths are made-to-measure sizes the product family
# supports.
STREET_Y = -3.0
STREET_FENCE_PROFILE = "fence.horizontal-slat"
STREET_FENCE_HEIGHT = 1.32
STREET_BASE = -0.300
WICKET_CLEAR = ((0.9, STREET_Y), (1.9, STREET_Y))
DRIVEWAY_CLEAR = ((4.2, STREET_Y), (7.2, STREET_Y))

WICKET_CONNECTIONS = gate_fence_connections(
    WICKET_CLEAR, height=STREET_FENCE_HEIGHT,
    profile=STREET_FENCE_PROFILE, leaves=1,
)
DRIVEWAY_CONNECTIONS = gate_fence_connections(
    DRIVEWAY_CLEAR, height=STREET_FENCE_HEIGHT,
    profile=STREET_FENCE_PROFILE, leaves=2,
)

pedestrian_gate(
    model, "boundary.street.wicket", storey="ground", path=WICKET_CLEAR,
    height=STREET_FENCE_HEIGHT, profile=STREET_FENCE_PROFILE,
    base_offset=STREET_BASE, material="fence.aluminium",
    name="Street Pedestrian Gate",
)
driveway_gate(
    model, "boundary.street.driveway", storey="ground", path=DRIVEWAY_CLEAR,
    height=STREET_FENCE_HEIGHT, profile=STREET_FENCE_PROFILE,
    base_offset=STREET_BASE, material="fence.aluminium",
    name="Street Driveway Gate",
)
fence(
    model, "boundary.street.west", storey="ground",
    path=((-2.0, STREET_Y), WICKET_CONNECTIONS[0]),
    height=STREET_FENCE_HEIGHT, profile=STREET_FENCE_PROFILE,
    base_offset=STREET_BASE, material="fence.aluminium", end_post=False,
    name="Street Fence - West",
)
fence(
    model, "boundary.street.middle", storey="ground",
    path=(WICKET_CONNECTIONS[1], DRIVEWAY_CONNECTIONS[0]),
    height=STREET_FENCE_HEIGHT, profile=STREET_FENCE_PROFILE,
    base_offset=STREET_BASE, material="fence.aluminium",
    start_post=False, end_post=False, name="Street Fence - Middle",
)
fence(
    model, "boundary.street.east", storey="ground",
    path=(DRIVEWAY_CONNECTIONS[1], (10.0, STREET_Y)),
    height=STREET_FENCE_HEIGHT, profile=STREET_FENCE_PROFILE,
    base_offset=STREET_BASE, material="fence.aluminium", start_post=False,
    name="Street Fence - East",
)

# The terrace itself is unguarded - a ground-level deck, low enough off the
# garden that this example gives it none. The balcony is guarded on its three
# edges open to the air - not the edge against the east gable wall, where the
# balcony door already is - each straight run its own declaration, none
# mitring another's end posts, on the steel tube-and-cable profile.
railing(model, "balcony.rail.outer", storey="attic", path=((9.2, 1.5), (9.2, 4.5)), height=1.0, profile="guardrail.steel", post_material="frame.metal", rail_material="frame.metal", infill_material="frame.metal", name="Balcony Railing - Outer")
railing(model, "balcony.rail.south", storey="attic", path=((8.0, 1.5), (9.2, 1.5)), height=1.0, profile="guardrail.steel", post_material="frame.metal", rail_material="frame.metal", infill_material="frame.metal", name="Balcony Railing - South")
railing(model, "balcony.rail.north", storey="attic", path=((9.2, 4.5), (8.0, 4.5)), height=1.0, profile="guardrail.steel", post_material="frame.metal", rail_material="frame.metal", infill_material="frame.metal", name="Balcony Railing - North")

# `at` is a point inside the intended room, not its shape: compilation
# encloses the partition wall and its virtual_element divider into two
# regions and assigns each space the one region containing its point.
space(model, "bedroom", storey="ground", at=(2.0, 2.0), height=2.5, name="Bedroom")
space(model, "living-room", storey="ground", at=(6.0, 3.0), height=2.5, name="Living Room")
# These have no boundary or elevation arguments: each footprint is exactly its
# resolved room and each finish top lands on that room's base datum. The door's
# threshold patch inherits the bedroom's herringbone finish and 15 mm depth.
covering(model, "bedroom.flooring", space="bedroom", material="timber.flooring", thickness=0.015, name="Bedroom Herringbone Flooring")
covering(model, "living-room.flooring", space="living-room", material="tile.ceramic", thickness=0.012, name="Living Room Ceramic Flooring")


if __name__ == "__main__":
    print("# --- IFC phase: run through Bonsai MCP IFC execution ---")
    print(model.ifc_source())
    print("# --- presentation phase: run after the IFC reload ---")
    print(model.blender_source())
