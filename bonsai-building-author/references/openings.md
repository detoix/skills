# Windows and Doors

Declare an opening against its **host wall's reference line**, and let the
compiler resolve the void, the placement, and the lining geometry.

## Declaration

```python
casement_window_type(model, "wt.casement")          # or state your own section
panel_door_type(model, "dt.entrance", operation_type="SINGLE_SWING_LEFT")

window(model, "south-window", wall="south-wall", window_type="wt.casement",
       along=5.2, sill_height=0.90, overall_width=1.60, overall_height=1.40,
       lining_material="frame.joinery", framing_material="frame.joinery",
       glazing_material="glazing")

door(model, "front-door", wall="south-wall", door_type="dt.entrance",
     along=1.4, overall_width=1.00, overall_height=2.10, is_external=True,
     direction_sense="NEGATIVE",
     lining_material="frame.joinery", framing_material="frame.joinery")
```

`along` measures from the wall's reference line **start** to the **centre** of
the opening; `sill_height` measures from that wall's own base, not the storey.
Positioning against the declared reference line rather than world coordinates
is what keeps an opening on its wall when the wall moves - the same reason a
roof window is hosted on a declared boundary edge.

A door sits on the floor and has no sill; `base_offset` raises one for the rare
case that it does.

Each opening owns its key namespace (`<opening>.opening`).

### Sliding glazing is still a window

Use `sliding_window()` when the source identifies a sliding glazed unit as a
window. It is a semantic wrapper around `window()` and therefore emits an
ordinary `IfcWindow`, not a door with a window-like appearance. The type still
owns how its panels operate:

`OperationType` is semantic metadata, not a request for different frame
geometry. The stock generator's slider declaration below retains a common
lining and centre mullion; it is **not** an HST lift-slide assembly.

```python
from building_author.openings import sliding_window

window_type(model, "wt.slider", partitioning_type="DOUBLE_PANEL_VERTICAL",
            lining=window_lining(depth=0.08, thickness=0.06,
                                 mullion_thickness=0.06),
            panels=[
                window_panel(frame_depth=0.08, frame_thickness=0.07,
                             operation_type="SLIDINGHORIZONTAL",
                             position="LEFT"),
                window_panel(frame_depth=0.08, frame_thickness=0.07,
                             operation_type="SLIDINGHORIZONTAL",
                             position="RIGHT"),
            ])

sliding_window(model, "terrace-slider", wall="north-wall",
               window_type="wt.slider", along=3.0, sill_height=0.0,
               overall_width=3.00, overall_height=2.30,
               lining_material="frame.joinery",
               framing_material="frame.joinery",
               glazing_material="glazing", name="Terrace Sliding Window")
```

`sill_height=0.0` describes floor-level glazing. Neither that zero sill nor a
passable panel changes its IFC class; use `door()` only when the source says it
is a door.

### Balcony frame or HST track

Choose the assembly from the reference, not merely from a zero sill height:

```python
from building_author.openings import balcony_window_type, lift_slide_window_type

balcony_window_type(model, "wt.balcony", hinge_side="LEFT")
lift_slide_window_type(model, "wt.hst", sliding_side="LEFT")
```

Both are ordinary reusable `window-type` declarations and their occurrences
use `window()` (or `sliding_window()` for HST). The balcony recipe uses the
stock generator: a normal four-sided outer frame and sash. The HST recipe
adds `assembly={"kind": "LIFT_SLIDE", ...}` to that same core declaration:
head/jamb frame, independent low threshold and two rails, two sash depth
positions, and overlapping meeting stiles with interlock lips. There is no
full-depth central mullion. LEFT/RIGHT follows local X elevation; the sliding
sash occupies the inner (+Y) track, transformed by `direction_sense` normally.

The HST frame helper is IfcOpenShell's
`create_ifc_window_frame_simple`; its other sections use `ShapeBuilder`
profiles/extrusions. No Bonsai or IfcOpenShell source is changed or copied.
Separate lining, framing and glazing remain native IFC swept solids with the
normal material roles, not GLB-only geometry. The type stores the complete
metre-valued recipe in `BA_WindowAssembly` and sets
`ParameterTakesPrecedence=False`: its explicit Body is authoritative where
IFC's scalar lining/panel parameters cannot describe per-edge sections and
two tracks. It deliberately has **no `BBIM_Window`**; regenerate it from the
building script, not Bonsai's stock window editor, which would lose this layout.

Default 174 mm frame depth, 77 mm sash depth, 48 mm frame band and approximately
95 mm sash face follow the published
[ALUPROF MB-77HS envelope dimensions](https://aluprof.com/files/downloads/MB-77HS_A3_EN.pdf).
The 10 mm base, 5 mm rails, 87 mm track spacing, 50 mm meeting overlap,
20 mm interlocks, 2 mm sealing clearance, 24 mm glazing and 3 mm glazing bite
are exposed, simplified recipe assumptions. This is not an exact manufacturer
section, fabrication model or certified accessible threshold. The helper's
keyword parameters allow an evidenced project section to replace them; code
validates physical fit and derives matching IFC panel metadata.

`sill_height` always places the physical assembly bottom; `OverallHeight`
includes its full body. Nothing is silently buried below zero. Coordinate
recesses and adjacent floor/plinth construction explicitly with the project.
The HST type currently **rejects `threshold_space`**, whose full-wall flooring
patch would compete with the track: finish regions must stop at the actual
joinery interfaces, not run across it. The track is already part of the window;
do not add a separate door threshold or projecting window sill to imitate it.
See `scripts/example_window_assemblies.py` for an isolated comparison fixture.

## Stating your own section

```python
window_type(model, "wt.tall", partitioning_type="TRIPLE_PANEL_VERTICAL",
            lining=window_lining(depth=0.08, thickness=0.06,
                                 mullion_thickness=0.06,
                                 to_panel_offset_x=0.04,
                                 to_panel_offset_y=0.025),
            panels=[window_panel(frame_depth=0.08, frame_thickness=0.07,
                                 operation_type="FIXEDCASEMENT")] * 3)
```

The **type** carries the section, the **occurrence** carries only its overall
size and its materials. That is where IFC puts them, so a section is stated
once and two windows of one type cannot drift apart.

## Composed glazing

Use the composed path when a window is a connected assembly of simple panes
that the stock rectangular partition schemas cannot express:

```python
composed_window_type(model, "wt.gable", profile_width=0.08,
                     profile_depth=0.08, glazing_thickness=0.024)

pieces = [
    window_rectangle(0, 0, 2.2, 0.9,
                     profile_edges=("left", "bottom"), pane="left"),
    window_triangle((0, .9), (2.2, .9), (2.2, 2.0),
                    profile_edges=("skew",), pane="left"),
]
composed_window(model, "gable-light", wall="gable",
                window_type="wt.gable", along=2.2, sill_height=2.3,
                pieces=pieces, dividers=[])
```

Rectangles default to profiles on `bottom`, `right`, `top`, and `left`, but
any subset—including none—is valid. Triangles likewise accept `base`,
`vertical`, and `skew`. Giving touching pieces the same `pane` joins their
glazing, so a rectangle with no top profile plus a triangle with only a skew
profile becomes one trapezoid without a false horizontal seam. Explicit
`window_divider()` declarations add mullions or transoms independently of
piece boundaries.

One connected composition becomes one `IfcWindow` and one arbitrary-profile
`IfcOpeningElement`, with `Framing` and `Glazing` shape aspects. Its type uses
`PartitioningType=USERDEFINED`. It deliberately carries no `BBIM_Window`:
Bonsai's stock editor can only regenerate its predefined rectangular panel
layouts, so the building script remains authoritative for this geometry.

The host wall's storey controls placement and IFC containment, not height.
A composed window may extend above that storey or cross a storey boundary;
neither validation nor compilation clips its `OverallHeight`.

## What maps to what in IFC

| declaration | IFC |
| --- | --- |
| `window(...)` / `door(...)` | `IfcWindow` / `IfcDoor`, `OverallWidth`, `OverallHeight` |
| its opening | `IfcOpeningElement` + `IfcRelVoidsElement` + `IfcRelFillsElement` |
| `window_type(...)` / `door_type(...)` | `IfcWindowType` / `IfcDoorType` + `IfcRelDefinesByType` |
| `partitioning_type=` / `operation_type=` | `PartitioningType` / `OperationType` |
| `window_lining(...)` / `door_lining(...)` | `IfcWindowLiningProperties` / `IfcDoorLiningProperties` |
| `window_panel(...)` / `door_panel(...)` | `IfcWindowPanelProperties` / `IfcDoorPanelProperties` |
| `*_material=` | `IfcMaterialConstituentSet`, one constituent per shape aspect |
| `direction_sense=` | the element's `ObjectPlacement`, turned about Z |
| `is_external=` | `Pset_WindowCommon` / `Pset_DoorCommon` |
| the stock resolved section | the `BBIM_Window` / `BBIM_Door` pset |
| a lift-slide `assembly` | authoritative swept-solid Body + `BA_WindowAssembly` on its type |

The lining and panel property sets hang off the type's `HasPropertySets`
directly - they are `IfcPreDefinedPropertySet`s, so they need no
`IfcRelDefinesByProperties`.

## Who does what

**Stock window and door bodies are IfcOpenShell's**, through
`ifcopenshell.api.geometry.add_window_representation` and
`add_door_representation`: real swept solids for lining, mullion, transom,
sashes, leaf and glazing, driven by the declared lining and panel properties.
This is the same split roofs already use - Bonsai solves the roof solid, the
skill supplies the declaration - and it is why an opening arrives as a
**parametric Bonsai element** rather than dead geometry.

Those generators emit `IfcShapeAspect`s named `Lining`, `Framing` and
`Glazing`. Those names *are* the material roles: they become the
`IfcMaterialConstituentSet` constituent names through
`ifcopenshell.api.material.set_shape_aspect_constituents`, which is also what
gives Bonsai per-part material slots on import. Only the aspects an element
actually has are given constituents - a solid door leaf has no `Glazing`, so
giving it a glazing material would describe a part it does not have.

**Writing `BBIM_Window` / `BBIM_Door` is what keeps the element editable** by
Bonsai's own window and door tools, exactly as `BBIM_Roof` does for a roof. It
holds the same parameters in the snake case those tools read, converted
mechanically from the schema's case so one declared value is never written out
twice.

**The hardware is theirs too.** `add_door_representation` builds the lever and
mirrors it onto both faces of the leaf, inside the `Framing` shape aspect, so
a door needs none from the skill - adding one would put a third handle on a
door that has two. `add_window_representation` builds no handle, and a window
here goes without rather than carrying a procedure for one part.

## The four states of a door

A door is hung on one stile or the other, and swings one way or the other.
IFC splits those across two places, so the script does too:

| state | carried by |
| --- | --- |
| hung left / right | `IfcDoorType.OperationType` - `SINGLE_SWING_LEFT` vs `..._RIGHT` |
| swings toward / away | the **object placement**, turned half a turn about Z |

There is no schema attribute for the swing. IFC reads the operation type in
the element's own frame, so turning the element is what reverses it - which is
exactly what Bonsai's `bim.toggle_door_swing` does, flipping the object and
swapping `LEFT`/`RIGHT` as two separate motions.

`direction_sense` is that placement, stated in the `IfcDirectionSenseEnum` a
wall already uses for its layers. `NEGATIVE` turns the opening about its own
height and starts it from the opposite corner, so it still fills the same
hole. Windows take it too: a window is not symmetric through the wall, since
its sash stands proud on one face and its reveal is deeper on the other.

The cutter never turns with it - it is a box about its own centre, so a half
turn would be a no-op.

## Through the wall

IFC has **no relationship binding an opening to a material layer**. It has two
things instead, and the script uses both:

- `IfcOpeningElement` is a boolean solid, so what it cuts is decided by its
  shape. `PredefinedType` separates `OPENING` from `RECESS`, but by geometry,
  not by naming a layer.
- `LiningOffset` on the lining properties is a **length** through the wall.

So a window set against one layer of a buildup is that offset, measured. The
lining starts centred in the wall's total thickness, and `lining_offset` moves
it from there. The wall type's layer thicknesses are what tell you the number;
nothing in IFC will state it for you.

## Offsets are ratios, thicknesses are lengths

`FirstMullionOffset`, `SecondMullionOffset`, `FirstTransomOffset` and
`SecondTransomOffset` are `IfcNormalisedRatioMeasure` in IFC4 - **fractions of
the window**, not distances. IfcOpenShell's generator and Bonsai's props both
want the distance instead. The declaration states the ratio, which is what
lets one type serve every size it is built at, and the compiler multiplies by
each occurrence's overall width or height.

Left unstated, a division splits the window evenly: one mullion halves it, two
make thirds. A division the partitioning does not have carries no offset at
all rather than a zero, because a zero offset is a panel of zero width - which
surfaces as an index error inside the shape builder with nothing naming the
window. `validate()` refuses these by name instead:

- a mullioned or transomed partitioning with that thickness left at zero
- offsets out of order, or outside `(0, 1)`
- a panel count that disagrees with the partitioning
- a window too narrow for its own divisions and framing

`CasingThickness`, `CasingDepth` and `ThresholdDepth` are
`IfcPositiveLengthMeasure`, so a door without them leaves them **unset** rather
than zero - zero is not a length the schema allows.

## The void

One `IfcOpeningElement` per opening: an `IfcRectangleProfileDef` of the
opening's width and height, swept along the element's Y through the wall. IFC
has a word for a box and this is it - written as a face set instead it cuts
the same hole, but its width, height and depth stop being readable numbers and
become a coordinate list a consumer has to bound-box. It is also what Bonsai's
own `generate_opening_from_filling` writes.

It reaches `OPENING_REACH` past each wall face, because a cutter that stops
exactly on the face leaves coplanar surfaces for the boolean to resolve, which
is where slivers come from. A door on the floor drops the same reach below the
wall base for the same reason; a raised door stops at its own base.

The lining is centred in the wall's thickness, measured from the wall's real
centre - which is its layer-set offset plus half its thickness, not its
reference line. `LiningOffset` then shifts it from there.

## The floor area under an opening belongs to one space

The horizontal finish under a floor-level opening is not part of either room
body and is not the door lining's `ThresholdDepth`. It is one separate
`IfcCovering(FLOORING)`: the opening width across the host wall's exact plan
footprint, without the extra `OPENING_REACH` used only to make the void boolean
robust. Do not change either adjacent `IfcSpace` or merge the patch into either
room's main flooring covering.

`threshold_space` is the required opening-occurrence argument whenever the
opening receives this finish patch. It names the one adjacent room that owns
the patch:

```python
door(model, "bedroom-door", wall="partition", door_type="dt.internal",
     along=2.1, overall_width=0.90, overall_height=2.10,
     threshold_space="hall")
```

This patch is not an exterior joinery track or a recess detail. HST assemblies
reject it; see the installation boundary above.

Compilation validates that the named space is on the same storey, is
floor-level at the opening, is actually adjacent to it, and has exactly one
main flooring covering. It creates
`<opening>.threshold-flooring`, spatially contains it directly in that space,
and inherits the main covering's material, type, thickness and material
recipe at that covering's own elevation, raised by `THRESHOLD_RISE` - the
patch spans the host wall's footprint, where a plinth tops out at the same
datum, and a finished face landing exactly on it shimmers. The threshold
patch remains its own `IfcCovering` occurrence;
it is not aggregated into the main one. Its geometry may sit at the space
boundary because IFC spatial containment is a semantic hierarchy, not a
geometric clipping operation.

Never infer `threshold_space` from `direction_sense`, the door swing, the host
wall direction, room names, or finish materials. Never halve the patch at the
wall centreline, duplicate it into both rooms, or leave it without a spatial
container. The same explicit owner is required for a floor-level opening
represented only by a virtual boundary; in that case `threshold_space` belongs
on `virtual_element()` instead. See [spaces.md](spaces.md).

## The void is not the same as visible

`ifcopenshell.api.feature.add_feature`, called once per opening, only ever
writes the `IfcRelVoidsElement` relationship - the schema fact that this
opening voids that wall. It does not cut anything into a Blender mesh, and
it does not ask the host wall to regenerate. A window or door can be
declared correctly, its wall's IFC data can be entirely correct, and the
wall can still reach the live scene looking unopened, because nothing in
the IFC phase forces it back in sync once its voids exist - see
[walls.md](walls.md) for where that sync actually happens
(`bim.recalculate_wall`, run automatically per wall in the presentation
phase). This is a host-wall concern, not something an opening declares or
needs to know about.

## Sills

```python
window_sill(model, "south-window.sill", window="south-window",
            horn=0.05, projection=0.04, thickness=0.03, material="stone")
```

`add_window_representation` builds lining, panels and glazing but nothing
that projects past the wall face, and the schema agrees: `IfcWindowLiningProperties`
has one `LiningThickness` and one `LiningDepth` for all four sides of the
reveal, with no attribute for a sill the way a door gets `ThresholdDepth`.
So a sill that reads as a sill - wider than the opening by `horn` on each
side, projecting past the wall by `projection` on each face - is this
skill's to build, not IfcOpenShell's.

It states no `along` or `sill_height` of its own; both already live on the
`window=` it names, and it sits at that window's own sill line, spanning the
wall's full thickness rather than the window's own, usually narrower, lining
depth - a sill sheds water off the wall, not off the frame.

Its top face is raised `SILL_RISE` above that sill line, not placed exactly
on it. The wall's own opening void has its bottom face exactly there too -
both driven by the same `sill_height` - so left alone the sill and the
wall's own cut reveal are two independent, coincident, overlapping faces at
the same height: the same z-fighting `OPENING_REACH` already exists to
avoid on the wall's own cut, solved the same way, a small deliberate
overlap into the wall rather than an exact match nothing can resolve
consistently.

IFC has no entity for a sill either. `IfcBuildingElementPart` is the closest
fit - a functional part of a larger element - with `PredefinedType` left
`USERDEFINED` since none of the enumeration's few values name one, and
`ObjectType` stating "Sill" instead. It is aggregated onto its window with
`IfcRelAggregates` rather than stood beside it as its own occurrence: a sill
without its window is meaningless the way a chimney or a railing is not, and
IFC allows a product exactly one place in the spatial decomposition tree, so
aggregating it removes any storey containment it might otherwise carry
instead of conflicting with one. Its placement is solved relative to the
window's own placement as a consequence, the same convenience the roof
window's frame gets from being built in its roof face's own frame.

### Corner windows

Use `corner_window()` to state the complete glazed assembly explicitly. It
composes two ordinary windows with the one `corner_opening()` declaration needed to
clear the wall mitre; it adds no new compiler operation:

```python
from building_author.openings import corner_window

north_window, west_window = corner_window(
    model, "corner-window",
    walls=("north-wall", "west-wall"),
    window_types=("wt.fixed", "wt.fixed"),
    along=(7.40, 0.60),
    sill_height=0.90,
    overall_widths=(1.20, 1.20),
    overall_height=1.40,
    lining_material="frame.joinery",
    framing_material="frame.joinery",
    glazing_material="glazing",
    name="Corner Window",
)
```

The ordered pairs map index-for-index: the first wall, type, `along`, width,
and direction describe `<key>.0`; the second set describes `<key>.1`. The
corner opening declaration is `<key>.opening`, and the function returns the
two window IDs.
Keep `along` explicit. A centred frame can end at the walls' shared reference
point, while a flush box frame needs a deliberate setback or overlap based on
its lining depth and offset; the helper must not invent that junction. A
supplied `name` is a display-name base: the legs append their wall keys and the
corner opening declaration appends `Corner Opening`.

Two windows meeting at a building corner each get their own sill, and each
one's plain rectangle stops `horn` short of that corner the same way it does
everywhere else - which leaves a real unfilled square exactly where the two
should meet, not a rounding error. Sills remain separate declarations because
their reach and exterior-side sign depend on the two wall buildups and the
chosen frame setback:

```python
window_sill(model, "corner-window.0.sill", window=north_window,
            horn=0.05, projection=0.05, thickness=0.03, material="stone",
            corner="end", corner_reach=-0.235)
window_sill(model, "corner-window.1.sill", window=west_window,
            horn=0.05, projection=0.05, thickness=0.03, material="stone",
            corner="start", corner_reach=-0.235)
```

`corner` names which end of *this* sill (`"start"` or `"end"`, `along`'s own
vocabulary) faces the corner; `corner_reach` pushes that end's Y = +depth/2
corner outward by that much, or its Y = -depth/2 corner if `corner_reach` is
negative - `sills.py` is never told which physical side of the wall is
which, so the sign is how a script states it.

The *other* corner at that same end does not stay put - it shrinks back by
`depth - corner_reach`, along the same axis the push moves on, turning the
end into a trapezoid rather than a rectangle with one corner dragged out.
That keeps this sill's own mitre at exactly 45 degrees to its own X and Y,
whatever `corner_reach` turns out to be: the along-axis span from the
shrunk corner to the pushed one is `corner_reach + (depth - corner_reach) =
depth`, matching the across-axis span between them, which is always `depth`
by construction. A window on the wall around the corner, cutting its own
sill's mitre the same way from its own depth, produces a diagonal at the
same 45 degrees - and two 45-degree lines through perpendicular walls are
themselves parallel, so the two sills' mitres coincide as one line without
either ever being told the other's numbers, even when the two walls are
different thicknesses or the windows sit off-centre in them.

`corner_reach` itself still has to close the *whole* gap on that side, not
just the other wall's own share of it: how far short of *this* wall's own
true corner the sill's un-mitred edge already sits - `horn` eats into
whatever margin the window itself was set back by, so it is rarely zero,
and a window sitting exactly at the corner (see below) puts that edge
slightly *past* it - plus how far past that point the other wall's own
sill still projects, its half-thickness plus its own projection.
`corner_reach=-0.235` above is `corner-window.0`'s own edge sitting exactly
at the true corner (0 short of it, `horn` already carrying it 0.05 past), so
only `west-wall`'s half-thickness plus its own projection, less that 0.05,
remains to close: 0.235 + 0.05 - 0.05 = 0.235.

Getting the sign right is reading `sills.py`'s own local frame off the
wall's axis, the same reasoning `direction_sense` already asks for: local Y
is 90 degrees anticlockwise of the wall's own start-to-end direction, so it
points into the interior on any wall drawn the way this project's own
examples are, walking the footprint anticlockwise. A sill's mitre wants the
*exterior* corner, so on such a wall that is the negative-Y corner -
`corner_reach` negative - not the positive one.

Whether written directly or emitted by `corner_window()`, the two windows are
separate declarations. For a centred frame they are positioned exactly at the
point the two walls' own reference lines meet - both the wall's endpoint and
the touchpoint the windows should meet at, not two different things to
reconcile. Flush frames are the explicit-offset case described above.

### What actually clears the corner

Positioning the windows there is not what removes the wall material at
that corner. Each window's own opening voids only its own host, so it
never reaches the solid the two walls still mitre between themselves -
`junctions.py` resolving any two coincident endpoints the ordinary way,
untouched by either window. Reaching one opening past its own wall's
endpoint to try to clear it anyway means guessing how far that mitre
actually extended - short, and a sliver of wall remains; long, and the
cutter starts removing wall that was never meant to move.

```python
corner_opening(model, "north-window.corner", walls=("north-wall", "west-wall"),
                base=0.90, height=1.40)
```

That low-level call is the third declaration `corner_window()` already emits;
do not add a second copy when using the helper.

IFC4's `IfcOpeningElement.VoidsElements` is a singular inverse: each opening
occurrence voids one host through one `IfcRelVoidsElement`. `corner_opening`
therefore emits two opening occurrences with the same cutter geometry,
each placed relative to its own wall. Their semantic keys are
`<corner-key>.opening.<wall-key>`; opening and relationship GUIDs derive from
the corner key and host key. The cutter is sized through each wall by that
wall's own declared thickness and along it by the other wall's, the most
either wall's own mitre with the other could
ever occupy, not by how far a cutter happened to reach. `base` and
`height` are the same vertical span `sill_height` and `overall_height`
already state on the two windows meeting there. Neither wall is touched -
both keep the axis, length and corner mitre they were declared with.

The compiler calls `ifcopenshell.api.feature.add_feature` once for each
occurrence, then assigns its world placement through
`geometry.edit_object_placement`, which resolves the host-relative transform.

### Inspect the corner assembly

The author chooses the two windows' `along` positions, lining offsets, and
sill mitres from the reference and the actual sections. The corner cutter
clears the host walls; it does not solve the frame junction or sill placement.
Before accepting a corner window:

- Inspect a horizontal section through the glazing. Check how the two frame
  sections meet, including their depth and offsets; confirm the intended
  contact or overlap without a projecting frame stub or an unintended gap.
- Inspect the host cuts in both walls, including the mitred corner. Confirm
  that the opening is clear and that surrounding wall material remains.
- Check the sills' exterior projections, mitred ends, and heights together.
- Inspect exterior and interior close-ups, plus the section, in the finished
  Blender scene and exported GLB when delivered. A distant view and a valid
  IFC relationship do not establish a correct visible junction.

## Preset values

The tests pin these window, door and material presets.

| Quantity | Value |
| --- | --- |
| Window lining band / depth | 0.06 / 0.08 m |
| Window mullion | 0.09 m |
| Window sash band / depth | 0.07 / 0.08 m |
| Door lining band / depth | 0.10 / 0.14 m |
| Door leaf | 0.035 m |
| Frame base colour | (0.947, 0.947, 0.947) |
| Glazing | (0.8, 0.8, 0.8), metallic 0.5, alpha 0.5 |

The lining keeps its declared thickness when the opening dimensions change.
