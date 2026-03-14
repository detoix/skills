#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: optimize_glb.sh -i <input.glb> [-o <output.glb>] [-d <degrees>] [-r <decimate_ratio>] [-s <pre_simplify_ratio>] [-t <timeout_secs>] [-T <texture>] [-N <normal_map>] [-b <blender_binary>] [-f]

  -i  Input GLB file (required)
  -o  Output GLB file (default: <input>_processed.glb)
  -d  Limited Dissolve angle in degrees (default: 5)
  -r  Decimate ratio 0.0-1.0 (default: 0.5)
  -s  Pre-simplify ratio via gltf-transform before Blender
  -t  Blender timeout in seconds (default: 60)
  -T  Diffuse texture path assigned to Base Color
  -N  Normal map path assigned through a Normal Map node
  -b  Blender binary path (default: blender)
  -f  Use Flatpak Blender (flatpak run org.blender.Blender)
  -h  Show this help
EOF
  exit 1
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Error: required command not found: $1" >&2
    exit 1
  fi
}

INPUT=""
OUTPUT=""
DEGREES=5
RATIO=0.5
PRE_SIMPLIFY=""
BLENDER_TIMEOUT=60
BLENDER="blender"
USE_FLATPAK=0
TEXTURE=""
NORMAL=""

while getopts "i:o:d:r:s:t:T:N:b:fh" opt; do
  case "$opt" in
    i) INPUT="$OPTARG" ;;
    o) OUTPUT="$OPTARG" ;;
    d) DEGREES="$OPTARG" ;;
    r) RATIO="$OPTARG" ;;
    s) PRE_SIMPLIFY="$OPTARG" ;;
    t) BLENDER_TIMEOUT="$OPTARG" ;;
    T) TEXTURE="$(realpath "$OPTARG")" ;;
    N) NORMAL="$(realpath "$OPTARG")" ;;
    b) BLENDER="$OPTARG" ;;
    f) USE_FLATPAK=1 ;;
    h) usage ;;
    *) usage ;;
  esac
done

if [[ -z "$INPUT" ]]; then
  echo "Error: input file is required." >&2
  usage
fi

require_cmd realpath
require_cmd mktemp
require_cmd timeout
require_cmd npx

if [[ $USE_FLATPAK -eq 1 ]]; then
  require_cmd flatpak
  BLENDER_CMD=(flatpak run --filesystem=/tmp org.blender.Blender)
else
  if ! command -v "$BLENDER" >/dev/null 2>&1; then
    echo "Error: Blender binary not found: $BLENDER" >&2
    exit 1
  fi
  BLENDER_CMD=("$BLENDER")
fi

INPUT="$(realpath "$INPUT")"

if [[ ! -f "$INPUT" ]]; then
  echo "Error: input file does not exist: $INPUT" >&2
  exit 1
fi

if [[ "${INPUT##*.}" != "glb" ]]; then
  echo "Error: input must be a .glb file: $INPUT" >&2
  exit 1
fi

if [[ -z "$OUTPUT" ]]; then
  BASENAME="$(basename "$INPUT" .glb)"
  OUTPUT="$(dirname "$INPUT")/${BASENAME}_processed.glb"
fi
OUTPUT="$(realpath -m "$OUTPUT")"

TMP_DIR="$(mktemp -d)"
BLENDER_SCRIPT="$TMP_DIR/blender_process.py"
PRE_SIMPLIFIED="$TMP_DIR/pre_simplified.glb"
INTERMEDIATE="$TMP_DIR/intermediate_raw.glb"
cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

BLENDER_INPUT="$INPUT"
if [[ -n "$PRE_SIMPLIFY" ]]; then
  echo "==> Pre-simplifying with gltf-transform (ratio=${PRE_SIMPLIFY})..."
  npx --yes @gltf-transform/cli simplify "$INPUT" "$PRE_SIMPLIFIED" --ratio "$PRE_SIMPLIFY" --error 0.01
  BLENDER_INPUT="$PRE_SIMPLIFIED"
fi

cat >"$BLENDER_SCRIPT" <<PYEOF
import bpy
import math
import sys

args = sys.argv[sys.argv.index("--") + 1:]
degrees = float(args[0])
ratio = float(args[1])
output = args[2]
texture_path = args[3] if len(args) > 3 and args[3] else ""
normal_path = args[4] if len(args) > 4 and args[4] else ""

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath="${BLENDER_INPUT}")

bpy.ops.object.select_all(action="DESELECT")
meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
for obj in meshes:
    obj.select_set(True)

if not meshes:
    print("ERROR: No mesh objects found in the GLB file.")
    sys.exit(1)

bpy.context.view_layer.objects.active = meshes[0]
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.mesh.dissolve_limited(angle_limit=math.radians(degrees))
bpy.ops.object.mode_set(mode="OBJECT")

for obj in meshes:
    bpy.context.view_layer.objects.active = obj
    modifier = obj.modifiers.new(name="Decimate", type="DECIMATE")
    modifier.ratio = ratio
    bpy.ops.object.modifier_apply(modifier=modifier.name)

for obj in meshes:
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.cube_project(cube_size=1.0)
    bpy.ops.object.mode_set(mode="OBJECT")

if texture_path or normal_path:
    material = bpy.data.materials.new(name="Material")
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()

    output_node = nodes.new("ShaderNodeOutputMaterial")
    output_node.location = (400, 0)

    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (0, 0)
    links.new(bsdf.outputs["BSDF"], output_node.inputs["Surface"])

    if texture_path:
        tex_node = nodes.new("ShaderNodeTexImage")
        tex_node.location = (-500, 200)
        tex_node.image = bpy.data.images.load(texture_path)
        links.new(tex_node.outputs["Color"], bsdf.inputs["Base Color"])

    if normal_path:
        normal_tex = nodes.new("ShaderNodeTexImage")
        normal_tex.location = (-700, -200)
        normal_tex.image = bpy.data.images.load(normal_path)
        normal_tex.image.colorspace_settings.name = "Non-Color"

        normal_map = nodes.new("ShaderNodeNormalMap")
        normal_map.location = (-300, -200)
        links.new(normal_tex.outputs["Color"], normal_map.inputs["Color"])
        links.new(normal_map.outputs["Normal"], bsdf.inputs["Normal"])

    for obj in meshes:
        obj.data.materials.clear()
        obj.data.materials.append(material)

bpy.ops.object.select_all(action="SELECT")
bpy.ops.export_scene.gltf(
    filepath=output,
    export_format="GLB",
    use_selection=False,
    export_apply=True,
)

print(f"Exported to {output}")
PYEOF

echo "==> Running Blender (limited dissolve=${DEGREES} deg, decimate ratio=${RATIO}, timeout=${BLENDER_TIMEOUT}s)..."
set +e
timeout "$BLENDER_TIMEOUT" "${BLENDER_CMD[@]}" --background --python "$BLENDER_SCRIPT" -- "$DEGREES" "$RATIO" "$INTERMEDIATE" "$TEXTURE" "$NORMAL"
EXIT_CODE=$?
set -e
if [[ $EXIT_CODE -ne 0 ]]; then
  if [[ $EXIT_CODE -eq 124 ]]; then
    echo "Error: Blender timed out after ${BLENDER_TIMEOUT}s. Try pre-simplifying first with -s 0.25." >&2
  else
    echo "Error: Blender exited with code $EXIT_CODE. Check the logs above." >&2
  fi
  exit 1
fi

if [[ ! -f "$INTERMEDIATE" ]]; then
  echo "Error: Blender did not produce output. Check the logs above." >&2
  exit 1
fi

echo "==> Running gltf-transform optimize with Draco compression..."
npx --yes @gltf-transform/cli optimize "$INTERMEDIATE" "$OUTPUT" --compress draco

ORIG_SIZE=$(du -h "$INPUT" | cut -f1)
FINAL_SIZE=$(du -h "$OUTPUT" | cut -f1)

echo ""
echo "Done"
echo "  Input:  $INPUT ($ORIG_SIZE)"
echo "  Output: $OUTPUT ($FINAL_SIZE)"
