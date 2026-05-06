#!/usr/bin/env python3
"""Render bounded virtual-camera motion from a still image."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from moviepy import VideoClip
from PIL import Image


OUTPUT_FORMATS = {
    "vertical": (1080, 1920),
    "9:16": (1080, 1920),
    "9x16": (1080, 1920),
    "portrait": (1080, 1920),
    "landscape": (1920, 1080),
    "16:9": (1920, 1080),
    "16x9": (1920, 1080),
}
MOTION_TYPES = {"push-in", "pull-back", "pan-left", "pan-right", "pan-up", "pan-down", "diagonal-drift", "swipe-in"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


def parse_crop(value: str | None) -> tuple[float, float, float, float] | None:
    if not value:
        return None
    parts = [float(part.strip()) for part in value.split(",")]
    if len(parts) != 4:
        raise ValueError("crop boxes must be x,y,width,height")
    x, y, width, height = parts
    if width <= 0 or height <= 0:
        raise ValueError("crop width and height must be positive")
    return (x, y, width, height)


def validate_box(box: tuple[float, float, float, float], image_size: tuple[int, int], output_size: tuple[int, int]) -> None:
    image_w, image_h = image_size
    out_w, out_h = output_size
    x, y, width, height = box
    if x < 0 or y < 0 or x + width > image_w or y + height > image_h:
        raise ValueError(f"crop box {box} goes outside image bounds {image_size}")
    if abs((width / height) - (out_w / out_h)) > 0.02:
        raise ValueError(f"crop box aspect ratio must match output aspect {out_w}:{out_h}")


def cover_crop_box(image_size: tuple[int, int], output_size: tuple[int, int], scale: float) -> tuple[float, float, float, float]:
    image_w, image_h = image_size
    out_w, out_h = output_size
    if image_w < out_w * 0.75 or image_h < out_h * 0.75:
        raise ValueError(f"source image {image_w}x{image_h} is too small for {out_w}x{out_h} still motion")
    aspect = out_w / out_h
    if image_w / image_h > aspect:
        crop_h = image_h * scale
        crop_w = crop_h * aspect
    else:
        crop_w = image_w * scale
        crop_h = crop_w / aspect
    if crop_w > image_w or crop_h > image_h:
        raise ValueError("requested motion crop exceeds image bounds")
    x = (image_w - crop_w) / 2
    y = (image_h - crop_h) / 2
    return (x, y, crop_w, crop_h)


def motion_crop_boxes(image_size: tuple[int, int], output_size: tuple[int, int], motion_type: str) -> tuple[tuple[float, float, float, float], tuple[float, float, float, float]]:
    base = cover_crop_box(image_size, output_size, 1.0)
    moving = cover_crop_box(image_size, output_size, 0.84)
    image_w, image_h = image_size
    x, y, width, height = moving
    max_x = image_w - width
    max_y = image_h - height

    if motion_type == "push-in":
        return base, moving
    if motion_type == "pull-back":
        return moving, base
    if motion_type == "pan-left":
        return (max_x, y, width, height), (0, y, width, height)
    if motion_type == "pan-right":
        return (0, y, width, height), (max_x, y, width, height)
    if motion_type == "pan-up":
        return (x, max_y, width, height), (x, 0, width, height)
    if motion_type == "pan-down":
        return (x, 0, width, height), (x, max_y, width, height)
    if motion_type == "diagonal-drift":
        return (0, 0, width, height), (max_x, max_y, width, height)
    if motion_type == "swipe-in":
        return (0, y, width, height), (max_x, y, width, height)
    raise ValueError(f"unsupported motion type: {motion_type}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render subtle bounded motion from a still image.")
    parser.add_argument("--image", required=True, help="Input still image.")
    parser.add_argument("--output", required=True, help="Output MP4.")
    parser.add_argument("--duration", type=float, required=True, help="Clip duration in seconds.")
    parser.add_argument("--format", default="vertical", choices=tuple(OUTPUT_FORMATS), help="Output format.")
    parser.add_argument("--motion", default="push-in", choices=tuple(sorted(MOTION_TYPES)), help="Motion type.")
    parser.add_argument("--start-crop", help="Optional x,y,width,height start crop.")
    parser.add_argument("--end-crop", help="Optional x,y,width,height end crop.")
    parser.add_argument("--fps", type=int, default=30)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    image_path = Path(args.image).resolve()
    output_path = Path(args.output).resolve()
    if not image_path.exists() or not image_path.is_file():
        raise FileNotFoundError(f"image not found: {image_path}")
    if image_path.suffix.lower() not in IMAGE_EXTENSIONS:
        raise ValueError(f"unsupported still image extension: {image_path.suffix}")
    if args.duration <= 0:
        raise ValueError("duration must be positive")

    output_size = OUTPUT_FORMATS[args.format]
    image = Image.open(image_path).convert("RGB")
    start_crop = parse_crop(args.start_crop)
    end_crop = parse_crop(args.end_crop)
    if start_crop or end_crop:
        if not start_crop or not end_crop:
            raise ValueError("start-crop and end-crop must be provided together")
        validate_box(start_crop, image.size, output_size)
        validate_box(end_crop, image.size, output_size)
        start_box, end_box = start_crop, end_crop
    else:
        start_box, end_box = motion_crop_boxes(image.size, output_size, args.motion)

    def make_frame(t: float):
        progress = max(0.0, min(1.0, t / args.duration))
        eased = progress * progress * (3 - 2 * progress)
        box = tuple(start_box[i] + (end_box[i] - start_box[i]) * eased for i in range(4))
        left, top, width, height = box
        crop = image.crop((int(round(left)), int(round(top)), int(round(left + width)), int(round(top + height))))
        resized = crop.resize(output_size, Image.Resampling.LANCZOS)
        return np.array(resized)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    clip = VideoClip(make_frame, duration=args.duration)
    clip.write_videofile(str(output_path), fps=args.fps, codec="libx264", audio=False)
    manifest = {
        "input_image": str(image_path),
        "output": str(output_path),
        "duration_seconds": args.duration,
        "format": args.format,
        "output_size": output_size,
        "motion": args.motion,
        "start_crop": start_box,
        "end_crop": end_box,
    }
    manifest_path = output_path.with_suffix(".motion.json")
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Saved still motion: {output_path}")
    print(f"Wrote motion manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
