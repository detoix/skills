"""Compare conventional balcony joinery with left/right HST assemblies.

The balcony type reuses the pack's measured 80 mm casement section. HST uses
the pack's published ALUPROF MB-77HS envelope dimensions, with its explicitly
documented generic rail, threshold and sealing approximations; this is a
section comparison, not a certified manufacturer product model.

All dimensions are metres. Each window's complete body starts at floor datum
z=0 and ends at z=2.3. The conventional bottom frame and the HST threshold are
joinery within that height. No part is implicitly embedded below the floor;
no floor covering, threshold_space patch or slab is declared. LEFT/RIGHT is
the type's local-X elevation convention, with the moving HST sash on +Y.

Import make_model() to validate or compile an isolated fixture. Execution of
the generated phases belongs to Bonsai MCP; importing this file does not open
Blender, replace a scene or write any files.
"""

from building_author import (
    Building,
    building,
    layer,
    material,
    project,
    site,
    storey,
    wall,
    wall_type,
    window,
)
from building_author.materials import glass
from building_author.openings import balcony_window_type, lift_slide_window_type


def make_model(output_dir=None):
    """Return three independently hosted window samples as one Building."""
    model = Building("window-assemblies", output_dir=output_dir)
    project(model, "project", name="Balcony and HST Window Comparison")
    site(model, "site", project="project", name="Isolated Comparison Fixture")
    building(model, "comparison", site="site", name="Three Window Assemblies")
    storey(model, "ground", building="comparison", name="Floor Datum ±0.00", elevation=0.0)

    # Linear RGB appearance choices for readable section comparison.
    material(model, "frame.charcoal", ifc_name="Charcoal coated window profiles",
             category="joinery", base_color=(0.032, 0.040, 0.047),
             roughness=0.38, metallic=0.0)
    material(model, "wall.warm", ifc_name="Warm light comparison wall",
             category="masonry", base_color=(0.80, 0.77, 0.70), roughness=0.88)
    glass(model, "glazing")
    wall_type(model, "wt.sample", name="Homogeneous 300 mm sample wall",
              predefined_type="SOLIDWALL",
              layers=[layer("wall.warm", 0.30, priority=50,
                            category="Comparison wall", name="Sample wall body")])

    # A one-metre separation prevents inferred wall junctions between samples.
    # Every wall runs along +X, so both HST handings share one elevation frame.
    wall(model, "wall.balcony", storey="ground", wall_type="wt.sample",
         axis=((0.0, 0.0), (4.0, 0.0)), height=2.80,
         direction_sense="NEGATIVE", name="Conventional Balcony Sample")
    wall(model, "wall.hst.left", storey="ground", wall_type="wt.sample",
         axis=((5.0, 0.0), (9.0, 0.0)), height=2.80,
         direction_sense="NEGATIVE", name="HST Left-Moving Sample")
    wall(model, "wall.hst.right", storey="ground", wall_type="wt.sample",
         axis=((10.0, 0.0), (14.0, 0.0)), height=2.80,
         direction_sense="NEGATIVE", name="HST Right-Moving Sample")

    balcony_window_type(model, "wt.balcony", hinge_side="LEFT")
    lift_slide_window_type(model, "wt.hst.left", sliding_side="LEFT")
    lift_slide_window_type(model, "wt.hst.right", sliding_side="RIGHT")

    window(model, "balcony", wall="wall.balcony", window_type="wt.balcony",
           along=2.0, sill_height=0.0, overall_width=1.20, overall_height=2.30,
           direction_sense="POSITIVE", lining_material="frame.charcoal",
           framing_material="frame.charcoal", glazing_material="glazing",
           name="Conventional Balcony Window — 1.20 × 2.30 m")
    window(model, "hst.left", wall="wall.hst.left", window_type="wt.hst.left",
           along=2.0, sill_height=0.0, overall_width=2.80, overall_height=2.30,
           direction_sense="POSITIVE", lining_material="frame.charcoal",
           framing_material="frame.charcoal", glazing_material="glazing",
           name="HST Window — Left Moving — 2.80 × 2.30 m")
    window(model, "hst.right", wall="wall.hst.right", window_type="wt.hst.right",
           along=2.0, sill_height=0.0, overall_width=2.80, overall_height=2.30,
           direction_sense="POSITIVE", lining_material="frame.charcoal",
           framing_material="frame.charcoal", glazing_material="glazing",
           name="HST Window — Right Moving — 2.80 × 2.30 m")
    return model


if __name__ == "__main__":
    model = make_model()
    print("# --- IFC phase: run in an isolated Bonsai MCP fixture session ---")
    print(model.ifc_source())
    print("# --- presentation phase: run after that fixture's IFC reload ---")
    print(model.blender_source())
