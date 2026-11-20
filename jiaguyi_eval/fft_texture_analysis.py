#!/usr/bin/env python3
"""Rank texture images by FFT signals useful for AI-texture triage."""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import numpy as np
from PIL import Image


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def classify_texture_usage(image_path: str) -> str:
    name = Path(image_path).name.lower()
    normal_markers = ("normal", "nmap", "_nor", "-nor", "bump")
    packed_markers = ("rough", "metal", "metallic", "spec", "gloss", "occlusion", "_ao", "orm", "arm")
    color_markers = ("basecolor", "base_color", "diffuse", "albedo", "color", "colour", "_col", "-col")
    if any(marker in name for marker in normal_markers):
        return "normal_like"
    if any(marker in name for marker in packed_markers):
        return "packed_or_material_like"
    if any(marker in name for marker in color_markers):
        return "color_like"
    return "unknown"


def resize_filter() -> int:
    try:
        return Image.Resampling.LANCZOS
    except AttributeError:
        return Image.LANCZOS


def load_gray_image(image_path: str, size: int) -> np.ndarray:
    with Image.open(image_path) as image:
        gray_image = image.convert("L").resize((size, size), resize_filter())
    array = np.asarray(gray_image, dtype=np.float32) / 255.0
    array -= float(array.mean())
    stddev = float(array.std())
    if stddev > 1e-6:
        array /= stddev
    return array


def radial_profile(power: np.ndarray, radius: np.ndarray, bins: int) -> np.ndarray:
    edges = np.linspace(0.0, float(radius.max()), bins + 1)
    indexes = np.digitize(radius.ravel(), edges) - 1
    values = power.ravel()
    profile = np.zeros(bins, dtype=np.float64)
    counts = np.zeros(bins, dtype=np.float64)
    valid = (indexes >= 0) & (indexes < bins)
    np.add.at(profile, indexes[valid], values[valid])
    np.add.at(counts, indexes[valid], 1.0)
    counts[counts == 0] = 1.0
    return profile / counts


def fft_metrics(
    image_path: str,
    size: int,
    low_radius: float,
    high_radius: float,
    radial_bins: int,
) -> Dict[str, Any]:
    array = load_gray_image(image_path, size)
    window = np.outer(np.hanning(size), np.hanning(size)).astype(np.float32)
    spectrum = np.fft.fftshift(np.fft.fft2(array * window))
    power = np.abs(spectrum) ** 2

    frequencies = np.fft.fftshift(np.fft.fftfreq(size))
    freq_x, freq_y = np.meshgrid(frequencies, frequencies)
    radius = np.sqrt(freq_x**2 + freq_y**2)

    analysis_mask = radius >= low_radius
    high_mask = radius >= high_radius
    total_power = float(power[analysis_mask].sum())
    if total_power <= 0:
        return {
            "fft_error": "zero_power",
            "high_freq_ratio": 0.0,
            "spectral_entropy": 0.0,
            "spectral_flatness": 0.0,
            "periodicity_score": 0.0,
            "fft_ai_score": 0.0,
        }

    analysis_power = power[analysis_mask].astype(np.float64)
    probabilities = analysis_power / total_power
    entropy = -float(np.sum(probabilities * np.log2(probabilities + 1e-18)))
    spectral_entropy = entropy / math.log2(max(len(probabilities), 2))
    spectral_flatness = float(np.exp(np.mean(np.log(analysis_power + 1e-12))) / (np.mean(analysis_power) + 1e-12))
    high_freq_ratio = float(power[high_mask].sum() / total_power)

    profile = radial_profile(power, radius, radial_bins)
    bin_centers = np.linspace(0.0, float(radius.max()), radial_bins, endpoint=False)
    mid_profile = profile[(bin_centers >= low_radius) & (bin_centers <= 0.50)]
    mid_profile = mid_profile[mid_profile > 0]
    if len(mid_profile):
        periodicity_score = float(np.max(mid_profile) / (np.median(mid_profile) + 1e-12))
    else:
        periodicity_score = 0.0

    fft_ai_score = high_freq_ratio * spectral_entropy * spectral_flatness / math.log2(2.0 + periodicity_score)
    return {
        "high_freq_ratio": round(high_freq_ratio, 6),
        "spectral_entropy": round(spectral_entropy, 6),
        "spectral_flatness": round(spectral_flatness, 6),
        "periodicity_score": round(periodicity_score, 6),
        "fft_ai_score": round(fft_ai_score, 6),
    }


def read_csv(path: Path) -> List[Dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: Sequence[Dict[str, Any]], fieldnames: Sequence[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="FFT texture triage for image_0 candidate textures.")
    parser.add_argument("--input-csv", required=True, help="CSV containing texture image paths.")
    parser.add_argument("--out", required=True, help="Output report directory.")
    parser.add_argument("--image-path-column", default="image0_path", help="Column holding image file paths.")
    parser.add_argument("--sample-size", type=int, default=50, help="Top N ranked rows to export as sample.")
    parser.add_argument("--size", type=int, default=512, help="Square image size for FFT.")
    parser.add_argument("--low-radius", type=float, default=0.03, help="Ignore DC/very low frequency radius below this value.")
    parser.add_argument("--high-radius", type=float, default=0.30, help="High-frequency radius threshold.")
    parser.add_argument("--radial-bins", type=int, default=96, help="Number of radial FFT bins.")
    parser.add_argument(
        "--sample-usage",
        choices=("color_like", "unknown", "normal_like", "packed_or_material_like", "all"),
        default="color_like",
        help="Texture usage bucket to use for the top sample export.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    input_path = Path(args.input_csv)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = read_csv(input_path)
    output_rows: List[Dict[str, Any]] = []
    for row in rows:
        image_path = row.get(args.image_path_column, "")
        output = dict(row)
        output["fft_image_path"] = image_path
        output["fft_texture_usage"] = classify_texture_usage(image_path)
        try:
            output.update(fft_metrics(image_path, args.size, args.low_radius, args.high_radius, args.radial_bins))
        except Exception as exc:
            output["fft_error"] = str(exc)
            output.update(
                {
                    "high_freq_ratio": 0.0,
                    "spectral_entropy": 0.0,
                    "spectral_flatness": 0.0,
                    "periodicity_score": 0.0,
                    "fft_ai_score": 0.0,
                }
            )
        output_rows.append(output)

    output_rows.sort(key=lambda item: safe_float(item.get("fft_ai_score")), reverse=True)
    if args.sample_usage == "all":
        sample_candidates = output_rows
    else:
        sample_candidates = [row for row in output_rows if row.get("fft_texture_usage") == args.sample_usage]
    sample_rows = sample_candidates[: max(args.sample_size, 0)]

    preferred_fields = [
        "path",
        "relative_path",
        "folder",
        "imgs_image_count",
        "image0_max_fill_rate",
        "image0_file_name",
        "image0_path",
        "high_freq_ratio",
        "spectral_entropy",
        "spectral_flatness",
        "periodicity_score",
        "fft_ai_score",
        "fft_texture_usage",
        "texture_issue_types",
        "flagged_textures",
        "face_count",
        "lod",
        "status",
        "fft_error",
    ]
    extra_fields = [field for row in output_rows for field in row.keys() if field not in preferred_fields]
    fieldnames = preferred_fields + sorted(set(extra_fields))
    write_csv(out_dir / "image0_fft_ranked_assets.csv", output_rows, fieldnames)
    write_csv(out_dir / "image0_fft_sample_50.csv", sample_rows, fieldnames)
    with (out_dir / "image0_fft_sample_50_paths.txt").open("w", encoding="utf-8") as handle:
        for row in sample_rows:
            handle.write(str(row.get("path", "")) + "\n")

    score_bins: Counter[str] = Counter()
    high_ratio_bins: Counter[str] = Counter()
    for row in output_rows:
        score = safe_float(row.get("fft_ai_score"))
        high_ratio = safe_float(row.get("high_freq_ratio"))
        score_bins[f"{math.floor(score * 10) / 10:.1f}-{math.floor(score * 10) / 10 + 0.1:.1f}"] += 1
        high_ratio_bins[f"{math.floor(high_ratio * 10) / 10:.1f}-{math.floor(high_ratio * 10) / 10 + 0.1:.1f}"] += 1

    summary = {
        "input_csv": str(input_path),
        "image_path_column": args.image_path_column,
        "row_count": len(output_rows),
        "sample_count": len(sample_rows),
        "sample_usage": args.sample_usage,
        "sample_candidate_count": len(sample_candidates),
        "size": args.size,
        "low_radius": args.low_radius,
        "high_radius": args.high_radius,
        "score_definition": "high_freq_ratio * spectral_entropy * spectral_flatness / log2(2 + periodicity_score)",
        "texture_usage_counts": dict(Counter(str(row.get("fft_texture_usage", "")) for row in output_rows).most_common()),
        "score_bins": dict(sorted(score_bins.items())),
        "high_freq_ratio_bins": dict(sorted(high_ratio_bins.items())),
        "top_folder_counts": dict(Counter(str(row.get("folder", "")) for row in sample_rows).most_common()),
    }
    with (out_dir / "summary.json").open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")

    lines = [
        "# Image_0 FFT Texture Analysis",
        "",
        f"- input: `{input_path}`",
        f"- rows analyzed: {len(output_rows)}",
        f"- sample count: {len(sample_rows)}",
        f"- sample usage filter: `{args.sample_usage}` ({len(sample_candidates)} candidates)",
        f"- FFT image size: {args.size}",
        f"- high-frequency radius: >= {args.high_radius}",
        "- rank score: `high_freq_ratio * spectral_entropy * spectral_flatness / log2(2 + periodicity_score)`",
        "",
        "## Interpretation",
        "",
        "- Higher `high_freq_ratio`: dense fine detail / noise-like texture energy.",
        "- Higher `spectral_entropy`: power spread across many frequencies.",
        "- Higher `spectral_flatness`: less peaky, more noise-like spectrum.",
        "- Lower `periodicity_score`: weaker obvious repeated/tile frequency peaks.",
        "- The default sample excludes normal/roughness-like maps because they naturally contain strong high-frequency signals.",
        "",
        "## Files",
        "",
        "- `image0_fft_ranked_assets.csv`",
        "- `image0_fft_sample_50.csv`",
        "- `image0_fft_sample_50_paths.txt`",
    ]
    (out_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    print(f"out_dir {out_dir}")
    for row in sample_rows[:10]:
        print(row.get("fft_ai_score"), row.get("high_freq_ratio"), row.get("periodicity_score"), row.get("path"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())