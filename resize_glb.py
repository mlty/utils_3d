#!/usr/bin/env python3
"""Compress GLB files with Blender texture resizing and Draco mesh compression."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import math
from pathlib import Path


DEFAULT_BLENDER = "/Applications/Blender.app/Contents/MacOS/Blender"


def parse_args(argv: list[str]) -> argparse.Namespace:
	parser = argparse.ArgumentParser(
		description="Resize embedded textures and export a smaller Draco-compressed GLB."
	)
	parser.add_argument("input", type=Path, help="Input .glb path")
	parser.add_argument("output", type=Path, nargs="?", help="Output .glb path")
	parser.add_argument("--max-texture-size", type=int, default=2048)
	parser.add_argument("--draco-level", type=int, default=8)
	parser.add_argument("--position-quantization", type=int, default=14)
	parser.add_argument("--normal-quantization", type=int, default=10)
	parser.add_argument("--texcoord-quantization", type=int, default=12)
	parser.add_argument("--no-draco", action="store_true", help="Disable Draco for maximum viewer compatibility")
	parser.add_argument("--decimate-ratio", type=float, default=1.0, help="Optional mesh decimation ratio, e.g. 0.6")
	parser.add_argument("--planar-angle-degrees", type=float, default=0.0, help="Remove near-coplanar faces before ratio decimation")
	parser.add_argument("--image-format", choices=("AUTO", "JPEG", "NONE"), default="JPEG")
	parser.add_argument("--blender", default=os.environ.get("BLENDER", DEFAULT_BLENDER))
	parser.add_argument("--in-blender", action="store_true", help=argparse.SUPPRESS)
	return parser.parse_args(argv)


def default_output_path(input_path: Path, max_texture_size: int) -> Path:
	return input_path.with_name(f"{input_path.stem}_compressed_{max_texture_size}.glb")


def run_with_blender(args: argparse.Namespace) -> int:
	blender = shutil.which(args.blender) or args.blender
	if not Path(blender).exists():
		raise SystemExit(f"Blender not found: {args.blender}")

	output = args.output or default_output_path(args.input, args.max_texture_size)
	cmd = [
		blender,
		"--background",
		"--python",
		str(Path(__file__).resolve()),
		"--",
		str(args.input),
		str(output),
		"--max-texture-size",
		str(args.max_texture_size),
		"--draco-level",
		str(args.draco_level),
		"--position-quantization",
		str(args.position_quantization),
		"--normal-quantization",
		str(args.normal_quantization),
		"--texcoord-quantization",
		str(args.texcoord_quantization),
		*( ["--no-draco"] if args.no_draco else [] ),
		"--decimate-ratio",
		str(args.decimate_ratio),
		"--planar-angle-degrees",
		str(args.planar_angle_degrees),
		"--image-format",
		args.image_format,
		"--in-blender",
	]
	return subprocess.call(cmd)


def blender_main(args: argparse.Namespace) -> None:
	import bpy  # type: ignore[import-not-found]

	input_path = args.input.expanduser().resolve()
	output_path = (args.output or default_output_path(input_path, args.max_texture_size)).expanduser().resolve()
	output_path.parent.mkdir(parents=True, exist_ok=True)

	bpy.ops.object.select_all(action="SELECT")
	bpy.ops.object.delete()

	bpy.ops.import_scene.gltf(filepath=str(input_path))

	if not 0 < args.decimate_ratio <= 1:
		raise ValueError("--decimate-ratio must be greater than 0 and less than or equal to 1")
	if args.planar_angle_degrees < 0:
		raise ValueError("--planar-angle-degrees must be greater than or equal to 0")
	if args.planar_angle_degrees > 0:
		for obj in bpy.context.scene.objects:
			if obj.type != "MESH":
				continue
			modifier = obj.modifiers.new("resize_glb_planar_decimate", "DECIMATE")
			modifier.decimate_type = "DISSOLVE"
			modifier.angle_limit = math.radians(args.planar_angle_degrees)
			bpy.context.view_layer.objects.active = obj
			obj.select_set(True)
			bpy.ops.object.modifier_apply(modifier=modifier.name)
			obj.select_set(False)
	if args.decimate_ratio < 1:
		for obj in bpy.context.scene.objects:
			if obj.type != "MESH":
				continue
			modifier = obj.modifiers.new("resize_glb_decimate", "DECIMATE")
			modifier.ratio = args.decimate_ratio
			bpy.context.view_layer.objects.active = obj
			obj.select_set(True)
			bpy.ops.object.modifier_apply(modifier=modifier.name)
			obj.select_set(False)

	with tempfile.TemporaryDirectory(prefix="resize_glb_") as temp_dir:
		temp_dir_path = Path(temp_dir)
		resized_images = []
		for image in list(bpy.data.images):
			if image.size[0] <= 0 or image.size[1] <= 0:
				continue
			max_side = max(image.size)
			if max_side <= args.max_texture_size:
				continue
			scale = args.max_texture_size / max_side
			width = max(1, round(image.size[0] * scale))
			height = max(1, round(image.size[1] * scale))
			image.scale(width, height)

			temp_image_path = temp_dir_path / f"{len(resized_images):03d}_{image.name}.png"
			image.save_render(str(temp_image_path))
			replacement = bpy.data.images.load(str(temp_image_path))
			replacement.colorspace_settings.name = image.colorspace_settings.name
			resized_images.append((image, replacement))

		for original, replacement in resized_images:
			for material in bpy.data.materials:
				if not material.node_tree:
					continue
				for node in material.node_tree.nodes:
					if getattr(node, "image", None) == original:
						node.image = replacement

		bpy.context.scene.render.image_settings.file_format = "JPEG"
		bpy.context.scene.render.image_settings.quality = 82

		bpy.ops.export_scene.gltf(
			filepath=str(output_path),
			export_format="GLB",
			export_image_format=args.image_format,
			export_draco_mesh_compression_enable=not args.no_draco,
			export_draco_mesh_compression_level=args.draco_level,
			export_draco_position_quantization=args.position_quantization,
			export_draco_normal_quantization=args.normal_quantization,
			export_draco_texcoord_quantization=args.texcoord_quantization,
			export_animations=False,
		)

	input_mb = input_path.stat().st_size / 1024 / 1024
	output_mb = output_path.stat().st_size / 1024 / 1024
	print(f"Wrote {output_path}")
	print(f"Size: {input_mb:.2f} MB -> {output_mb:.2f} MB")


def main(argv: list[str] | None = None) -> int:
	if argv is None:
		raw_args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else sys.argv[1:]
	else:
		raw_args = argv
	args = parse_args(raw_args)
	if args.in_blender:
		blender_main(args)
		return 0
	return run_with_blender(args)


if __name__ == "__main__":
	raise SystemExit(main())
