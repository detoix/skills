# Runtime Preflight

Check capabilities rather than dependency versions. Run this preflight at the
start of every task that will inspect, change, render, or export Blender or IFC
state. Declaring and validating a script locally does not require a live
runtime.

## Resolve the requirements

For runtime execution, always require:

- A callable `bonsai-mcp` toolset.
- A live Blender connection that can run read-only Blender code.
- Bonsai and IfcOpenShell facilities that can run read-only IFC code.

Require only when the task needs them:

- Blender glTF export capability for a Three.js GLB deliverable.
- A Three.js test environment for interactive presentation verification.
- Texture, asset, image, PDF, or other source-processing facilities.
- Additional capabilities required by the completed building script.
  A lift-slide window assembly requires the callable upstream
  `create_ifc_window_frame_simple` helper, `ShapeBuilder` profile/extrusion
  methods and shape-aspect API. Probe those capabilities, not a version pin;
  do not patch a missing generator into the third-party installation.

An open IFC project is task state, not an installed dependency. Report the
absence of a required project separately.

## Probe without mutation

Probe in this order:

1. Confirm that the required Bonsai MCP query and execution tools are
   discoverable.
2. Call a lightweight query to distinguish a live bridge from configured but
   disconnected tooling.
3. Confirm through read-only Blender execution that `bpy` and any
   task-required Blender capability are available.
4. Confirm through read-only IFC execution that Bonsai/IfcOpenShell facilities
   required by the task are available.
5. Run any operation-specific read-only probes required by the script.

Do not create objects, edit IFC data, save files, install packages, start
servers, or change configuration during the preflight.

## Classify the result

- `ready`: the capability probe succeeded.
- `disconnected`: the dependency appears installed or configured, but its
  process, bridge, add-on, or connection is unavailable.
- `missing`: the executable, add-on, module, tool, or package is not present.
- `unknown`: the probe was inconclusive.

Do not treat a connection failure as proof that a dependency is missing.

## Handle unmet requirements

For `disconnected`, state what needs to be started or connected and ask the
user to do so. Do not reinstall it.

For `missing` or installation-related `unknown`, stop runtime-dependent work
and ask one concise question:

> The runtime preflight found these missing capabilities: [list]. Would you
> like me to install or configure them?

Do not include dependency versions in the question or bake version pins into
the skill. If the user authorizes installation, select currently compatible
components at that time and verify them by capability after installation.

If the user declines, continue only with work that does not require the
missing capabilities, such as planning or reviewing existing text.
