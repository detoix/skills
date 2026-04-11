#!/usr/bin/env bash
# Dual-platform GLB optimization script (Linux/macOS and Windows Git Bash).
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: optimize_glb.sh -i <input.glb> [-o <output.glb>] [-d <degrees>] [-r <decimate_ratio>] [-s <pre_simplify_ratio>] [-t <timeout_secs>] [-T <texture>] [-N <normal_map>] [-b <blender_binary>] [-f] [-h] 

  -i  Input GLB file (required)
  -o  Output GLB file (default: <input>_processed.glb)
  -d  Limited Dissolve angle in degrees (default: 5)
  -r  Decimate ratio 0.0-1.0 (default: 0.5)
  -s  Pre-simplify ratio via gltf-transform before Blender
  -t  Blender timeout in seconds (default: 120)
  -T  Diffuse texture path
  -N  Normal map path
  -b  Blender binary path
  -f  Use Flatpak Blender (Linux only)
  -h  Show this help
EOF
  exit 1
}

# Detect OS
IS_WIN=false
if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" ]]; then
  IS_WIN=true
fi

# Helper to normalize paths for Blender (handles Windows cygpath if needed)
to_blender_path() {
  if $IS_WIN; then
    cygpath -w "$1"
  else
    echo "$1"
  fi
}

INPUT=""
OUTPUT=""
DEGREES=5
RATIO=0.5
PRE_SIMPLIFY=""
BLENDER_TIMEOUT=120
BLENDER="blender"
USE_FLATPAK=false
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
    f) USE_FLATPAK=true ;;
    h) usage ;;
    *) usage ;;
  esac
done

if [[ -z "$INPUT" ]]; then
  echo "Error: input file is required." >&2
  usage
fi

if $USE_FLATPAK; then
  BLENDER="flatpak run org.blender.Blender"
fi

INPUT="$(realpath "$INPUT")"
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

# Paths for the Blender Python script
B_INPUT="$(to_blender_path "$BLENDER_INPUT")"
B_OUTPUT="$(to_blender_path "$INTERMEDIATE")"
B_TEXTURE=""
B_NORMAL=""
[[ -n "$TEXTURE" ]] && B_TEXTURE="$(to_blender_path "$TEXTURE")"
[[ -n "$NORMAL"  ]] && B_NORMAL="$(to_blender_path "$NORMAL")"

# Generate Blender Python script
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
bpy.ops.import_scene.gltf(filepath=r"${B_INPUT}")

meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
if not meshes:
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
    
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=66.0, island_margin=0.02)
    bpy.ops.object.mode_set(mode="OBJECT")

if texture_path or normal_path:
    mat = bpy.data.materials.new(name="Material")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    bsdf = nodes.get("Principled BSDF")
    
    if texture_path:
        tex = nodes.new("ShaderNodeTexImage")
        tex.image = bpy.data.images.load(texture_path)
        links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    
    if normal_path:
        nor_tex = nodes.new("ShaderNodeTexImage")
        nor_tex.image = bpy.data.images.load(normal_path)
        nor_tex.image.colorspace_settings.name = "Non-Color"
        nor_map = nodes.new("ShaderNodeNormalMap")
        links.new(nor_tex.outputs["Color"], nor_map.inputs["Color"])
        links.new(nor_map.outputs["Normal"], bsdf.inputs["Normal"])

    for obj in meshes:
        obj.data.materials.clear()
        obj.data.materials.append(mat)

bpy.ops.export_scene.gltf(filepath=output, export_format="GLB")
PYEOF

B_SCRIPT="$(to_blender_path "$BLENDER_SCRIPT")"

echo "==> Running Blender..."
timeout "$BLENDER_TIMEOUT" $BLENDER --background --python "$B_SCRIPT" -- "$DEGREES" "$RATIO" "$B_OUTPUT" "$B_TEXTURE" "$B_NORMAL"

echo "==> Finalizing with Draco compression..."
npx --yes @gltf-transform/cli optimize "$INTERMEDIATE" "$OUTPUT" --compress draco

echo "Done: $OUTPUT"

