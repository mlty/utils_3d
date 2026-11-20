#!/usr/bin/env python3
"""Audit post-removal metadata for residual low-quality training assets."""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Iterator


DEFAULT_INPUTS = {
    "tex": Path("/Users/mlty/Downloads/metadata_tex_remove.csv"),
    "github": Path("/Users/mlty/Downloads/metadata_github_remove.csv"),
    "sket": Path("/Users/mlty/Downloads/metadata_sket_remove.csv"),
    "cg": Path("/Users/mlty/Downloads/metadata_cg_remove.csv"),
    "step1x": Path("/Users/mlty/Downloads/metadata_step1x_remove.csv"),
}
DEFAULT_REFERENCES = {
    "github": Path("/Users/mlty/Downloads/ObjaverseXL_github.csv"),
    "sket": Path("/Users/mlty/Downloads/ObjaverseXL_sketchfab.csv"),
    "tex_metadata": Path("/Users/mlty/Downloads/metadata.json"),
    "tex_caption": Path("/Users/mlty/Downloads/caption.json"),
    "step1x_github": Path("/Users/mlty/Downloads/objaverse_xl_github_url_480k.json"),
    "step1x_objaverse": Path("/Users/mlty/Downloads/objaverse_320k.json"),
}
OUTPUT_FIELDS = (
    "dataset", "source_row", "sha256", "local_path", "file_identifier",
    "decision", "reasons", "aesthetic_score", "face_count", "max_texture",
    "voxel_blocks", "reference_matched", "text_evidence",
)

REJECT_PATTERNS = tuple(
    (reason, re.compile(pattern, re.IGNORECASE))
    for reason, pattern in {
        "explicit_ai_generated": r"\b(ai[-_ ]generated|generated[-_ ]by[-_ ]ai|generative[-_ ]ai|text[-_ ]to[-_ ]3d|meshy(?:\.ai)?|tripo(?:3d)?|dreamfusion|shap-e)\b|人工智能生成|ai生成",
        "scan_photogrammetry": r"\b(photogrammetr(?:y|ic)|3d[-_ ]?scan(?:ned)?|reality[-_ ]capture|laser[-_ ]scan)\b|摄影测量|扫描模型",
        "broken_fragment": r"\b(broken|damaged|destroyed|ruins?|wrecked|debris|fragment(?:ed|s)?|shards?|rubble|incomplete[-_ ]model|missing[-_ ]parts?)\b|破损|损坏|废墟|残片|碎片|残缺",
        "flat_or_proxy": r"\b(flat[-_ ]plane|ground[-_ ]plane|background[-_ ]plane|collision[-_ ]mesh|collider|proxy[-_ ]mesh|placeholder|dummy[-_ ]model)\b|碰撞体|占位模型",
    }.items()
)
REVIEW_PATTERNS = tuple(
    (reason, re.compile(pattern, re.IGNORECASE))
    for reason, pattern in {
        "test_or_sample_asset": r"(?:^|[/_. -])(test|tests|testing|sample|example|demo|tutorial|temp|tmp|backup)(?:[/_. -]|$)|测试模型|示例模型",
        "terrain_or_rock": r"\b(terrain|rock|rocks|stone|boulder|cliff|cave|gravel|asteroid)\b|地形|岩石|石头|洞穴",
        "lod_or_optimized": r"(?:^|[/_. -])lod[0-9_ -]*(?:[/_. -]|$)|\b(low[-_ ]poly|lowpoly|decimat(?:ed|ion))\b|低模",
        "body_part": r"\b(body[-_ ]part|head[-_ ]only|hand[-_ ]only|single[-_ ]tooth|anatomy[-_ ]part)\b|人体部位|单独头部",
        "billboard_or_sprite": r"\b(billboard|sprite)\b|广告牌模型",
    }.items()
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=Path(__file__).with_name("removed_metadata_analysis"))
    parser.add_argument("--limit", type=int, default=0, help="Maximum rows per target CSV; 0 analyzes all rows")
    parser.add_argument("--low-aesthetic", type=float, default=4.5)
    parser.add_argument("--very-low-faces", type=int, default=150)
    parser.add_argument("--small-texture", type=int, default=256)
    parser.add_argument("--very-low-blocks", type=int, default=128)
    return parser.parse_args()


def parse_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return " ".join(normalize_text(item) for item in value)
    return str(value).replace("_", " ").strip()


def parse_caption(value: str) -> str:
    if not value:
        return ""
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return value
    return normalize_text(parsed)


def asset_uuid(path: str) -> str:
    stem = Path(path).stem
    stem = re.sub(r"_1024$", "", stem, flags=re.IGNORECASE)
    match = re.search(r"[0-9a-f]{32}", stem, re.IGNORECASE)
    return match.group(0).lower() if match else ""


def iter_csv(path: Path, limit: int = 0) -> Iterator[tuple[int, dict[str, str]]]:
    with path.open(encoding="utf-8-sig", errors="replace", newline="") as handle:
        reader = csv.DictReader(handle)
        for row_number, row in enumerate(reader, start=1):
            if limit and row_number > limit:
                break
            yield row_number, row


def iter_json_items(path: Path) -> Iterable[tuple[str, Any]]:
    try:
        import ijson
    except ImportError as error:
        raise RuntimeError("Large reference JSON files require ijson: pip install ijson") from error
    with path.open("rb") as handle:
        yield from ijson.kvitems(handle, "")


def collect_target_keys(
    inputs: dict[str, Path], limit: int
) -> tuple[dict[str, set[str]], set[str], set[str]]:
    hashes: dict[str, set[str]] = {name: set() for name in inputs}
    tex_ids: set[str] = set()
    step1x_ids: set[str] = set()
    for dataset, path in inputs.items():
        for _, row in iter_csv(path, limit):
            sha256 = row.get("sha256", "").lower()
            if sha256:
                hashes[dataset].add(sha256)
            if dataset == "tex":
                identifier = asset_uuid(row.get("local_path", ""))
                if identifier:
                    tex_ids.add(identifier)
            elif dataset == "step1x":
                identifier = asset_uuid(row.get("local_path", ""))
                if identifier:
                    step1x_ids.add(identifier)
    return hashes, tex_ids, step1x_ids


def load_objaverse_csv(path: Path, wanted: set[str]) -> dict[str, dict[str, str]]:
    matched: dict[str, dict[str, str]] = {}
    for _, row in iter_csv(path):
        sha256 = row.get("sha256", "").lower()
        if sha256 in wanted:
            matched[sha256] = row
    return matched


def load_json_matches(path: Path, wanted: set[str]) -> dict[str, Any]:
    matched: dict[str, Any] = {}
    for key, value in iter_json_items(path):
        normalized = key.lower()
        if normalized in wanted:
            matched[normalized] = value
    return matched


def load_step1x_objaverse_ids(path: Path, wanted_ids: set[str]) -> set[str]:
    with path.open(encoding="utf-8") as handle:
        values = json.load(handle)
    return {identifier for value in values if (identifier := asset_uuid(str(value))) in wanted_ids}


def prepare_references(
    hashes: dict[str, set[str]], tex_ids: set[str], step1x_ids: set[str], references: dict[str, Path]
) -> dict[str, Any]:
    return {
        "github": load_objaverse_csv(references["github"], hashes["github"]),
        "sket": load_objaverse_csv(references["sket"], hashes["sket"]),
        "tex_metadata": load_json_matches(references["tex_metadata"], tex_ids),
        "tex_caption": load_json_matches(references["tex_caption"], tex_ids),
        "step1x_github": load_json_matches(references["step1x_github"], hashes["step1x"]),
        "step1x_objaverse": load_step1x_objaverse_ids(references["step1x_objaverse"], step1x_ids),
    }


def enrich_row(dataset: str, row: dict[str, str], references: dict[str, Any]) -> dict[str, Any]:
    sha256 = row.get("sha256", "").lower()
    result: dict[str, Any] = {
        "file_identifier": row.get("file_identifier", ""),
        "caption": parse_caption(row.get("captions", "")),
        "aesthetic_score": parse_number(row.get("aesthetic_score")),
        "face_count": None,
        "max_texture": None,
        "reference_matched": False,
    }
    if dataset in {"github", "sket"}:
        reference = references[dataset].get(sha256)
        if reference:
            result.update(
                file_identifier=reference.get("file_identifier", result["file_identifier"]),
                caption=parse_caption(reference.get("captions", "")),
                aesthetic_score=parse_number(reference.get("aesthetic_score")),
                reference_matched=True,
            )
    elif dataset == "tex":
        identifier = asset_uuid(row.get("local_path", ""))
        metadata = references["tex_metadata"].get(identifier, {})
        caption = references["tex_caption"].get(identifier, "")
        if metadata or caption:
            result.update(
                file_identifier=identifier,
                caption=normalize_text(caption),
                face_count=parse_number(metadata.get("faceCount")),
                max_texture=parse_number(metadata.get("max_texture")),
                metadata_text=" ".join(normalize_text(metadata.get(field)) for field in ("name", "description", "tags", "categories")),
                reference_matched=True,
            )
    elif dataset == "step1x":
        github_url = references["step1x_github"].get(sha256, "")
        identifier = asset_uuid(row.get("local_path", ""))
        if github_url:
            result.update(file_identifier=github_url, reference_matched=True)
        elif identifier in references["step1x_objaverse"]:
            result.update(file_identifier=identifier, reference_matched=True)
    return result


def classify(
    row: dict[str, str], enriched: dict[str, Any], args: argparse.Namespace
) -> tuple[str, list[str], str, float | None]:
    searchable = " ".join(
        filter(None, (
            row.get("local_path", ""), enriched.get("file_identifier", ""),
            enriched.get("caption", ""), enriched.get("metadata_text", ""),
        ))
    )
    reject_reasons = [reason for reason, pattern in REJECT_PATTERNS if pattern.search(searchable)]
    review_reasons = [reason for reason, pattern in REVIEW_PATTERNS if pattern.search(searchable)]
    aesthetic = enriched.get("aesthetic_score")
    face_count = enriched.get("face_count")
    max_texture = enriched.get("max_texture")
    blocks = parse_number(row.get("64_15_occ4_num_blocks") or row.get("64_15_occ8_num_blocks"))
    if aesthetic is not None and aesthetic < args.low_aesthetic:
        review_reasons.append("low_aesthetic_score")
    if face_count is not None and face_count <= args.very_low_faces:
        review_reasons.append("very_low_face_count")
    if max_texture is not None and 0 < max_texture < args.small_texture:
        review_reasons.append("small_max_texture")
    if blocks is not None and blocks <= args.very_low_blocks:
        review_reasons.append("very_low_voxel_blocks")
    reasons = reject_reasons + review_reasons
    decision = "reject" if reject_reasons else "review" if review_reasons else "keep"
    evidence = re.sub(r"\s+", " ", searchable).strip()[:500]
    return decision, reasons, evidence, blocks


def write_report(out_dir: Path, summary: dict[str, Any]) -> None:
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# Remove 后数据质量复核", "", "## 汇总", ""]
    lines.extend([
        "| 数据集 | 总数 | Reject | Review | Keep | 参考数据匹配率 |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ])
    for dataset, stats in summary["datasets"].items():
        total = stats["total"]
        matched_rate = stats["reference_matched"] / total if total else 0
        lines.append(
            f"| {dataset} | {total:,} | {stats['decisions'].get('reject', 0):,} | "
            f"{stats['decisions'].get('review', 0):,} | {stats['decisions'].get('keep', 0):,} | {matched_rate:.2%} |"
        )
    lines.extend(["", "## 原因分布", ""])
    for reason, count in summary["reason_distribution"].items():
        lines.append(f"- `{reason}`: {count:,}")
    lines.extend(["", "## 各数据源原因", ""])
    for dataset, stats in summary["datasets"].items():
        lines.append(f"### {dataset}")
        lines.append("")
        for reason, count in stats["reasons"].items():
            lines.append(f"- `{reason}`: {count:,}")
        if not stats["reasons"]:
            lines.append("- 无规则命中")
        lines.append("")
    lines.extend([
        "", "## 使用建议", "",
        "- `reject_candidates.csv` 仅包含高置信文本风险，建议抽样确认后删除。",
        "- `review_candidates.csv` 是弱信号或数值异常，不应直接删除。",
        "- `keep` 表示当前元数据规则未发现风险，不代表模型已通过视觉质量检查。",
        "- 下一步应对 Reject 全量和 Review 分层抽样进行多视角渲染复核。",
    ])
    (out_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    inputs = DEFAULT_INPUTS
    args.out_dir.mkdir(parents=True, exist_ok=True)
    hashes, tex_ids, step1x_ids = collect_target_keys(inputs, args.limit)
    references = prepare_references(hashes, tex_ids, step1x_ids, DEFAULT_REFERENCES)
    summary: dict[str, Any] = {
        "thresholds": {
            "low_aesthetic": args.low_aesthetic,
            "very_low_faces": args.very_low_faces,
            "small_texture": args.small_texture,
            "very_low_blocks": args.very_low_blocks,
        },
        "datasets": {},
        "reason_distribution": {},
    }
    reason_counts: Counter[str] = Counter()
    output_handles = {
        decision: (args.out_dir / f"{decision}_candidates.csv").open("w", encoding="utf-8-sig", newline="")
        for decision in ("reject", "review", "keep")
    }
    try:
        writers = {decision: csv.DictWriter(handle, fieldnames=OUTPUT_FIELDS) for decision, handle in output_handles.items()}
        for writer in writers.values():
            writer.writeheader()
        for dataset, path in inputs.items():
            decisions: Counter[str] = Counter()
            dataset_reasons: Counter[str] = Counter()
            matched = 0
            total = 0
            for source_row, row in iter_csv(path, args.limit):
                total += 1
                enriched = enrich_row(dataset, row, references)
                decision, reasons, evidence, blocks = classify(row, enriched, args)
                decisions[decision] += 1
                matched += int(enriched["reference_matched"])
                reason_counts.update(reasons)
                dataset_reasons.update(reasons)
                writers[decision].writerow({
                    "dataset": dataset,
                    "source_row": source_row,
                    "sha256": row.get("sha256", ""),
                    "local_path": row.get("local_path", ""),
                    "file_identifier": enriched.get("file_identifier", ""),
                    "decision": decision,
                    "reasons": ";".join(reasons),
                    "aesthetic_score": enriched.get("aesthetic_score") if enriched.get("aesthetic_score") is not None else "",
                    "face_count": enriched.get("face_count") if enriched.get("face_count") is not None else "",
                    "max_texture": enriched.get("max_texture") if enriched.get("max_texture") is not None else "",
                    "voxel_blocks": blocks if blocks is not None else "",
                    "reference_matched": enriched["reference_matched"],
                    "text_evidence": evidence,
                })
            summary["datasets"][dataset] = {
                "total": total,
                "reference_matched": matched,
                "decisions": dict(decisions),
                "reasons": dict(dataset_reasons.most_common()),
            }
    finally:
        for handle in output_handles.values():
            handle.close()
    summary["reason_distribution"] = dict(reason_counts.most_common())
    write_report(args.out_dir, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())