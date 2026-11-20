#!/usr/bin/env python3
"""Filter ObjaverseXL assets from text captions with rules plus ghc-api review."""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


DEFAULT_INPUT_CSVS = [
    "/Users/mlty/Downloads/ObjaverseXL_github.csv",
    "/Users/mlty/Downloads/ObjaverseXL_sketchfab.csv",
]

RULE_OUTPUT_FIELDS = [
    "asset_id",
    "source_csv",
    "row_index",
    "sha256",
    "file_identifier",
    "aesthetic_score",
    "text_status",
    "rule_decision",
    "asset_category",
    "training_value_score",
    "risk_score",
    "risk_tags",
    "positive_tags",
    "llm_needed",
    "rule_reasons",
    "caption_text",
]

LLM_OUTPUT_FIELDS = [
    "asset_id",
    "status",
    "source_csv",
    "row_index",
    "sha256",
    "file_identifier",
    "aesthetic_score",
    "rule_decision",
    "rule_risk_tags",
    "llm_decision",
    "asset_category",
    "bad_for_3d_training",
    "rock_stone_irregular_surface",
    "broken_or_damaged",
    "flat_floor_wall_plane",
    "scene_or_environment",
    "clean_object_candidate",
    "training_value_score",
    "confidence",
    "reasons",
    "error",
]

RISK_PATTERNS = {
    "rock_stone_irregular": re.compile(
        r"\b(rock|rocks|stone|stones|boulder|boulders|cliff|cliffs|cave|caves|"
        r"mountain|mountains|terrain|pebble|pebbles|rubble|gravel|crag|craggy|"
        r"geode|crystal|crystals|ore|asteroid|meteorite|lava|volcanic)\b",
        re.IGNORECASE,
    ),
    "flat_floor_wall_plane": re.compile(
        r"\b(floor|floors|ground|plane|flat|wall|walls|ceiling|tile|tiles|road|"
        r"street|pavement|surface|platform|slab|panel|paneling|sidewalk|asphalt)\b",
        re.IGNORECASE,
    ),
    "broken_damaged_fragment": re.compile(
        r"\b(broken|damaged|destroyed|ruined|ruins|debris|fragment|fragments|"
        r"shattered|cracked|wreck|wrecked|scrap|collapsed|dilapidated)\b",
        re.IGNORECASE,
    ),
    "scene_environment": re.compile(
        r"\b(scene|environment|landscape|diorama|level|map|forest|desert|island|"
        r"beach|valley|canyon|field|garden|room|interior|exterior)\b",
        re.IGNORECASE,
    ),
}

POSITIVE_PATTERNS = {
    "character_creature": re.compile(
        r"\b(character|creature|humanoid|human|person|warrior|soldier|robot|alien|"
        r"animal|monster|dragon|dog|cat|bird|fish|horse|zombie|statue|figurine)\b",
        re.IGNORECASE,
    ),
    "vehicle_machine": re.compile(
        r"\b(vehicle|car|truck|tank|spaceship|ship|aircraft|plane|helicopter|"
        r"motorcycle|bike|robotic|machine|mech|drone|train)\b",
        re.IGNORECASE,
    ),
    "object_prop": re.compile(
        r"\b(prop|object|tool|weapon|sword|gun|furniture|chair|table|door|chest|"
        r"lamp|vase|instrument|equipment|armor|helmet|book|toy|booth|sign)\b",
        re.IGNORECASE,
    ),
    "architecture_part": re.compile(
        r"\b(building|house|tower|bridge|temple|castle|arch|column|window|stairs|"
        r"staircase|gate|fence|roof|facade)\b",
        re.IGNORECASE,
    ),
}


@dataclass
class RuleResult:
    asset_id: str
    source_csv: str
    row_index: int
    sha256: str
    file_identifier: str
    aesthetic_score: str
    caption_text: str
    text_status: str
    rule_decision: str
    asset_category: str
    training_value_score: int
    risk_score: int
    risk_tags: List[str]
    positive_tags: List[str]
    llm_needed: bool
    rule_reasons: List[str]


def normalize_ghc_chat_url(raw_url: Optional[str]) -> str:
    url = (raw_url or "http://localhost:8313").rstrip("/")
    if url.endswith("/chat/completions"):
        return url
    if url.endswith("/responses"):
        return url.removesuffix("/responses") + "/chat/completions"
    if url.endswith("/v1"):
        return url + "/chat/completions"
    return url + "/v1/chat/completions"


def normalize_ghc_responses_url(raw_url: Optional[str]) -> str:
    url = (raw_url or "http://localhost:8313").rstrip("/")
    if url.endswith("/responses"):
        return url
    if url.endswith("/chat/completions"):
        return url.removesuffix("/chat/completions") + "/responses"
    if url.endswith("/v1"):
        return url + "/responses"
    return url + "/v1/responses"


def normalize_model_name(model: str) -> str:
    model_aliases = {
        "gpt5.5": "gpt-5.5",
        "gpt_5.5": "gpt-5.5",
    }
    return model_aliases.get(model, model)


def choose_api_mode(args: argparse.Namespace) -> str:
    if args.api_mode != "auto":
        return args.api_mode
    model = normalize_model_name(args.model).lower()
    raw_url = (args.ghc_api_url or "").rstrip("/")
    if raw_url.endswith("/responses") or model.startswith("gpt-5"):
        return "responses"
    return "chat"


def parse_float(value: str) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def clamp(value: int, min_value: int = 0, max_value: int = 100) -> int:
    return max(min_value, min(max_value, value))


def compact_list(value: Any) -> str:
    if isinstance(value, list):
        return "; ".join(str(item) for item in value)
    if value is None:
        return ""
    return str(value)


def parse_caption_text(raw_captions: str) -> Tuple[str, str]:
    text = (raw_captions or "").strip()
    if not text:
        return "", "empty"
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return text, "raw_text"
    if isinstance(parsed, list):
        return " ".join(str(item) for item in parsed if str(item).strip()), "ok"
    if isinstance(parsed, str):
        return parsed, "ok"
    return json.dumps(parsed, ensure_ascii=False), "ok"


def make_asset_id(source_csv: str, row_index: int, sha256: str) -> str:
    source_name = Path(source_csv).stem.replace("ObjaverseXL_", "")
    sha_prefix = sha256[:12] if sha256 else "no_sha"
    return f"{source_name}:{row_index}:{sha_prefix}"


def choose_asset_category(risk_tags: Sequence[str], positive_tags: Sequence[str]) -> str:
    if positive_tags:
        return positive_tags[0]
    if "rock_stone_irregular" in risk_tags:
        return "nature_rock_stone_terrain"
    if "flat_floor_wall_plane" in risk_tags:
        return "flat_surface_or_structure"
    if "broken_damaged_fragment" in risk_tags:
        return "damaged_fragment_debris"
    if "scene_environment" in risk_tags:
        return "scene_environment"
    return "unknown"


def classify_by_rules(source_csv: str, row_index: int, row: Dict[str, str], text_max_chars: int) -> RuleResult:
    sha256 = row.get("sha256", "")
    file_identifier = row.get("file_identifier", "")
    aesthetic_score = row.get("aesthetic_score", "")
    caption_text, text_status = parse_caption_text(row.get("captions", ""))
    searchable_text = f"{caption_text} {file_identifier}"
    risk_tags = [tag for tag, pattern in RISK_PATTERNS.items() if pattern.search(searchable_text)]
    positive_tags = [tag for tag, pattern in POSITIVE_PATTERNS.items() if pattern.search(searchable_text)]
    score = parse_float(aesthetic_score)

    risk_score = 0
    if "rock_stone_irregular" in risk_tags:
        risk_score += 35
    if "flat_floor_wall_plane" in risk_tags:
        risk_score += 30
    if "broken_damaged_fragment" in risk_tags:
        risk_score += 30
    if "scene_environment" in risk_tags:
        risk_score += 20
    if text_status == "empty":
        risk_score += 25

    training_value_score = 50
    if score is not None:
        if score >= 6.5:
            training_value_score += 10
        elif score >= 5.5:
            training_value_score += 5
        elif score < 4.5:
            training_value_score -= 10
    if positive_tags:
        training_value_score += 20
    if len(positive_tags) >= 2:
        training_value_score += 5
    training_value_score -= risk_score
    if risk_tags and positive_tags:
        training_value_score += 10
    training_value_score = clamp(training_value_score)
    risk_score = clamp(risk_score)

    reasons: List[str] = []
    if text_status == "empty":
        rule_decision = "review"
        reasons.append("captions empty; text-only judgment is unavailable")
    elif risk_score >= 65 and not positive_tags:
        rule_decision = "reject"
        reasons.append("strong risk signals with no clear reusable object signal")
    elif risk_tags and positive_tags:
        rule_decision = "review"
        reasons.append("mixed risk and useful-object signals need LLM review")
    elif risk_score >= 35:
        rule_decision = "review"
        reasons.append("risk keywords indicate possible mesh-training mismatch")
    elif positive_tags and training_value_score >= 60:
        rule_decision = "keep"
        reasons.append("clear reusable object/category signal and low text risk")
    else:
        rule_decision = "review"
        reasons.append("insufficient positive object evidence")

    if risk_tags:
        reasons.append("risk_tags=" + ",".join(risk_tags))
    if positive_tags:
        reasons.append("positive_tags=" + ",".join(positive_tags))

    llm_needed = text_status != "empty" and (rule_decision != "keep" or bool(risk_tags))
    truncated_text = caption_text[:text_max_chars] if text_max_chars > 0 else caption_text
    return RuleResult(
        asset_id=make_asset_id(source_csv, row_index, sha256),
        source_csv=source_csv,
        row_index=row_index,
        sha256=sha256,
        file_identifier=file_identifier,
        aesthetic_score=aesthetic_score,
        caption_text=truncated_text,
        text_status=text_status,
        rule_decision=rule_decision,
        asset_category=choose_asset_category(risk_tags, positive_tags),
        training_value_score=training_value_score,
        risk_score=risk_score,
        risk_tags=risk_tags,
        positive_tags=positive_tags,
        llm_needed=llm_needed,
        rule_reasons=reasons,
    )


def rule_result_to_row(result: RuleResult) -> Dict[str, Any]:
    return {
        "asset_id": result.asset_id,
        "source_csv": result.source_csv,
        "row_index": result.row_index,
        "sha256": result.sha256,
        "file_identifier": result.file_identifier,
        "aesthetic_score": result.aesthetic_score,
        "text_status": result.text_status,
        "rule_decision": result.rule_decision,
        "asset_category": result.asset_category,
        "training_value_score": result.training_value_score,
        "risk_score": result.risk_score,
        "risk_tags": ";".join(result.risk_tags),
        "positive_tags": ";".join(result.positive_tags),
        "llm_needed": "yes" if result.llm_needed else "no",
        "rule_reasons": "; ".join(result.rule_reasons),
        "caption_text": result.caption_text,
    }


def iter_rule_results(args: argparse.Namespace) -> Iterable[RuleResult]:
    total_seen = 0
    for source_csv in args.input_csvs:
        csv_path = Path(source_csv)
        with csv_path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
            reader = csv.DictReader(handle)
            for row_index, row in enumerate(reader, start=1):
                if args.limit and total_seen >= args.limit:
                    return
                total_seen += 1
                yield classify_by_rules(str(csv_path), row_index, row, args.text_max_chars)


def should_send_to_llm(result: RuleResult, args: argparse.Namespace) -> bool:
    if not result.llm_needed:
        return False
    if args.llm_scope == "review":
        return result.rule_decision == "review"
    if args.llm_scope == "reject":
        return result.rule_decision == "reject"
    if args.llm_scope == "risk":
        return bool(result.risk_tags)
    return result.rule_decision in {"review", "reject"} or bool(result.risk_tags)


def write_rule_outputs(args: argparse.Namespace, out_dir: Path) -> Tuple[List[RuleResult], Dict[str, Any]]:
    out_dir.mkdir(parents=True, exist_ok=True)
    rule_results_path = out_dir / "rule_prefilter_results.csv"
    llm_candidates_path = out_dir / "llm_candidates.csv"
    keep_path = out_dir / "rule_keep_candidates.csv"
    review_path = out_dir / "rule_review_candidates.csv"
    reject_path = out_dir / "rule_reject_candidates.csv"

    counters: Counter[str] = Counter()
    risk_counter: Counter[str] = Counter()
    positive_counter: Counter[str] = Counter()
    llm_candidates: List[RuleResult] = []

    with (
        rule_results_path.open("w", encoding="utf-8", newline="") as rule_handle,
        llm_candidates_path.open("w", encoding="utf-8", newline="") as llm_handle,
        keep_path.open("w", encoding="utf-8", newline="") as keep_handle,
        review_path.open("w", encoding="utf-8", newline="") as review_handle,
        reject_path.open("w", encoding="utf-8", newline="") as reject_handle,
    ):
        rule_writer = csv.DictWriter(rule_handle, fieldnames=RULE_OUTPUT_FIELDS)
        llm_writer = csv.DictWriter(llm_handle, fieldnames=RULE_OUTPUT_FIELDS)
        keep_writer = csv.DictWriter(keep_handle, fieldnames=RULE_OUTPUT_FIELDS)
        review_writer = csv.DictWriter(review_handle, fieldnames=RULE_OUTPUT_FIELDS)
        reject_writer = csv.DictWriter(reject_handle, fieldnames=RULE_OUTPUT_FIELDS)
        for writer in (rule_writer, llm_writer, keep_writer, review_writer, reject_writer):
            writer.writeheader()

        for result in iter_rule_results(args):
            counters["total"] += 1
            counters[f"text_status:{result.text_status}"] += 1
            counters[f"rule_decision:{result.rule_decision}"] += 1
            counters[f"asset_category:{result.asset_category}"] += 1
            for tag in result.risk_tags:
                risk_counter[tag] += 1
            for tag in result.positive_tags:
                positive_counter[tag] += 1
            row = rule_result_to_row(result)
            rule_writer.writerow(row)
            if result.rule_decision == "keep":
                keep_writer.writerow(row)
            elif result.rule_decision == "reject":
                reject_writer.writerow(row)
            else:
                review_writer.writerow(row)
            if should_send_to_llm(result, args):
                if not args.llm_limit or len(llm_candidates) < args.llm_limit:
                    llm_candidates.append(result)
                    llm_writer.writerow(row)

            if args.progress_every and counters["total"] % args.progress_every == 0:
                print(f"rule prefilter scanned {counters['total']} rows", flush=True)

    summary = {
        "input_csvs": args.input_csvs,
        "total": counters["total"],
        "counters": dict(counters),
        "risk_tags": dict(risk_counter),
        "positive_tags": dict(positive_counter),
        "llm_candidates": len(llm_candidates),
        "outputs": {
            "rule_prefilter_results": str(rule_results_path),
            "llm_candidates": str(llm_candidates_path),
            "rule_keep_candidates": str(keep_path),
            "rule_review_candidates": str(review_path),
            "rule_reject_candidates": str(reject_path),
        },
    }
    with (out_dir / "rule_summary.json").open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2)
    write_markdown_summary(out_dir / "summary.md", summary, llm_summary=None)
    return llm_candidates, summary


def build_llm_prompt(batch: Sequence[RuleResult]) -> str:
    items = []
    for result in batch:
        items.append(
            {
                "id": result.asset_id,
                "sha256": result.sha256,
                "file_identifier": result.file_identifier,
                "aesthetic_score": result.aesthetic_score,
                "rule_decision": result.rule_decision,
                "rule_risk_tags": result.risk_tags,
                "rule_positive_tags": result.positive_tags,
                "caption": result.caption_text,
            }
        )
    return (
        "你是3D训练数据筛选专家。只根据每个资产的文本描述和URL路径判断它是否适合用于学习可复用mesh。\n"
        "重点识别并剔除：石头/岩石/地形等表面粗糙不规则资产；破损、废墟、碎片、残骸；平面、地板、墙面、道路、纯环境场景。\n"
        "优先保留：角色、动物、车辆、机器、家具、工具、道具、建筑部件等形体明确、可复用、对mesh学习有价值的单体资产。\n"
        "只返回JSON，不要Markdown。返回格式必须是：\n"
        "{\"items\":[{\"id\":\"...\",\"decision\":\"keep|review|reject\","
        "\"asset_category\":\"...\",\"bad_for_3d_training\":\"yes|no|uncertain\","
        "\"rock_stone_irregular_surface\":\"yes|no|uncertain\","
        "\"broken_or_damaged\":\"yes|no|uncertain\","
        "\"flat_floor_wall_plane\":\"yes|no|uncertain\","
        "\"scene_or_environment\":\"yes|no|uncertain\","
        "\"clean_object_candidate\":\"yes|no|uncertain\","
        "\"training_value_score\":0,\"confidence\":0.0,\"reasons\":[\"...\"]}]}\n"
        "training_value_score 取0到100，reject通常低于40，keep通常高于60。\n"
        "待判断资产JSON：\n"
        + json.dumps(items, ensure_ascii=False)
    )


def extract_json_object(text: str) -> Dict[str, Any]:
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
        if isinstance(parsed, list):
            return {"items": parsed}
        return {"raw": parsed}
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise
        parsed = json.loads(match.group(0))
        return parsed if isinstance(parsed, dict) else {"raw": parsed}


def extract_response_text(response_json: Dict[str, Any]) -> str:
    if isinstance(response_json.get("output_text"), str):
        return response_json["output_text"]
    choices = response_json.get("choices")
    if isinstance(choices, list) and choices:
        message = choices[0].get("message", {}) if isinstance(choices[0], dict) else {}
        content = message.get("content", "") if isinstance(message, dict) else ""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "".join(str(item.get("text", "")) for item in content if isinstance(item, dict))
    output = response_json.get("output")
    if isinstance(output, list):
        parts: List[str] = []
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content", [])
            if isinstance(content, list):
                for part in content:
                    if not isinstance(part, dict):
                        continue
                    text = part.get("text") or part.get("output_text")
                    if isinstance(text, str):
                        parts.append(text)
        if parts:
            return "".join(parts)
    return ""


def make_chat_payload(batch: Sequence[RuleResult], args: argparse.Namespace) -> Dict[str, Any]:
    return {
        "model": normalize_model_name(args.model),
        "messages": [{"role": "user", "content": build_llm_prompt(batch)}],
        "temperature": args.temperature,
        "response_format": {"type": "json_object"},
    }


def make_responses_payload(batch: Sequence[RuleResult], args: argparse.Namespace) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "model": normalize_model_name(args.model),
        "input": build_llm_prompt(batch),
    }
    if not normalize_model_name(args.model).lower().startswith("gpt-5"):
        payload["temperature"] = args.temperature
    return payload


def post_json(api_url: str, payload: Dict[str, Any], headers: Dict[str, str], timeout_sec: int) -> Dict[str, Any]:
    request = urllib.request.Request(api_url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=timeout_sec) as response:
        return json.loads(response.read().decode("utf-8"))


def call_ghc_api_with_mode(batch: Sequence[RuleResult], args: argparse.Namespace, api_mode: str) -> Dict[str, Any]:
    headers = {"Content-Type": "application/json"}
    api_key = os.environ.get(args.ghc_api_key_env, "")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    if api_mode == "responses":
        api_url = normalize_ghc_responses_url(args.ghc_api_url)
        payload = make_responses_payload(batch, args)
    else:
        api_url = normalize_ghc_chat_url(args.ghc_api_url)
        payload = make_chat_payload(batch, args)

    try:
        response_json = post_json(api_url, payload, headers, args.timeout_sec)
        content_text = extract_response_text(response_json)
        parsed = extract_json_object(content_text)
        return {"status": "ok", "api_mode": api_mode, "items": parsed.get("items", []), "raw_response": response_json}
    except urllib.error.HTTPError as exc:
        error_text = exc.read().decode("utf-8", errors="replace")[-2000:]
        return {"status": "failed", "api_mode": api_mode, "items": [], "error": f"HTTP {exc.code}: {error_text}"}
    except Exception as exc:
        return {"status": "failed", "api_mode": api_mode, "items": [], "error": str(exc)}


def call_ghc_api(batch: Sequence[RuleResult], args: argparse.Namespace) -> Dict[str, Any]:
    api_mode = choose_api_mode(args)
    response = call_ghc_api_with_mode(batch, args, api_mode)
    error = str(response.get("error", ""))
    if args.api_mode == "auto" and api_mode == "chat" and "unsupported_api_for_model" in error:
        return call_ghc_api_with_mode(batch, args, "responses")
    return response


def chunked(items: Sequence[RuleResult], batch_size: int) -> Iterable[List[RuleResult]]:
    size = max(batch_size, 1)
    for start in range(0, len(items), size):
        yield list(items[start : start + size])


def llm_item_to_row(result: RuleResult, status: str, item: Dict[str, Any], error: str = "") -> Dict[str, Any]:
    return {
        "asset_id": result.asset_id,
        "status": status,
        "source_csv": result.source_csv,
        "row_index": result.row_index,
        "sha256": result.sha256,
        "file_identifier": result.file_identifier,
        "aesthetic_score": result.aesthetic_score,
        "rule_decision": result.rule_decision,
        "rule_risk_tags": ";".join(result.risk_tags),
        "llm_decision": item.get("decision", ""),
        "asset_category": item.get("asset_category", ""),
        "bad_for_3d_training": item.get("bad_for_3d_training", ""),
        "rock_stone_irregular_surface": item.get("rock_stone_irregular_surface", ""),
        "broken_or_damaged": item.get("broken_or_damaged", ""),
        "flat_floor_wall_plane": item.get("flat_floor_wall_plane", ""),
        "scene_or_environment": item.get("scene_or_environment", ""),
        "clean_object_candidate": item.get("clean_object_candidate", ""),
        "training_value_score": item.get("training_value_score", ""),
        "confidence": item.get("confidence", ""),
        "reasons": compact_list(item.get("reasons")),
        "error": error,
    }


def read_existing_llm_asset_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    asset_ids: set[str] = set()
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            asset_id = str(row.get("asset_id", ""))
            decision = str(row.get("llm_decision", ""))
            if asset_id and row.get("status") == "ok" and decision in {"keep", "review", "reject"}:
                asset_ids.add(asset_id)
    return asset_ids


def run_llm_review(candidates: Sequence[RuleResult], args: argparse.Namespace, out_dir: Path) -> Dict[str, Any]:
    jsonl_path = out_dir / "llm_results.jsonl"
    csv_path = out_dir / "llm_results.csv"
    final_keep_path = out_dir / "llm_keep.csv"
    final_review_path = out_dir / "llm_review.csv"
    final_reject_path = out_dir / "llm_reject.csv"
    existing_asset_ids = read_existing_llm_asset_ids(jsonl_path) if args.resume else set()
    remaining_candidates = [result for result in candidates if result.asset_id not in existing_asset_ids]
    batches = list(chunked(remaining_candidates, args.batch_size))
    counters: Counter[str] = Counter()
    started = time.time()
    if existing_asset_ids:
        print(f"resume enabled: skipping {len(existing_asset_ids)} existing LLM result rows", flush=True)

    open_mode = "a" if args.resume else "w"
    with jsonl_path.open(open_mode, encoding="utf-8") as jsonl_handle:
        with ThreadPoolExecutor(max_workers=max(args.workers, 1)) as executor:
            future_to_batch = {executor.submit(call_ghc_api, batch, args): batch for batch in batches}
            for finished_batches, future in enumerate(as_completed(future_to_batch), start=1):
                batch = future_to_batch[future]
                response = future.result()
                items_by_id = {
                    str(item.get("id", "")): item for item in response.get("items", []) if isinstance(item, dict)
                }
                if response.get("status") != "ok":
                    for result in batch:
                        row = llm_item_to_row(result, "failed", {}, str(response.get("error", "")))
                        jsonl_handle.write(json.dumps(row, ensure_ascii=False) + "\n")
                        counters["failed"] += 1
                    jsonl_handle.flush()
                else:
                    for result in batch:
                        item = items_by_id.get(result.asset_id, {})
                        status = "ok" if item else "missing_llm_item"
                        row = llm_item_to_row(result, status, item, "" if item else "LLM response omitted this asset_id")
                        jsonl_handle.write(json.dumps(row, ensure_ascii=False) + "\n")
                        counters[status] += 1
                    jsonl_handle.flush()

                elapsed = max(time.time() - started, 0.001)
                done_assets = sum(counters.values())
                print(
                    f"llm batches {finished_batches}/{len(batches)} assets={done_assets}/{len(remaining_candidates)} "
                    f"rate={done_assets / elapsed:.2f}/s",
                    flush=True,
                )

    raw_rows = read_jsonl_rows(jsonl_path)
    rows = read_jsonl_rows_deduped(jsonl_path)
    rows_by_decision: Dict[str, List[Dict[str, Any]]] = {"keep": [], "review": [], "reject": []}
    for row in rows:
        decision = str(row.get("llm_decision", ""))
        if decision in rows_by_decision:
            rows_by_decision[decision].append(row)
    write_csv(csv_path, LLM_OUTPUT_FIELDS, rows)
    write_csv(final_keep_path, LLM_OUTPUT_FIELDS, rows_by_decision["keep"])
    write_csv(final_review_path, LLM_OUTPUT_FIELDS, rows_by_decision["review"])
    write_csv(final_reject_path, LLM_OUTPUT_FIELDS, rows_by_decision["reject"])
    summary = {
        "llm_candidates": len(candidates),
        "skipped_existing": len(existing_asset_ids),
        "remaining_candidates_started": len(remaining_candidates),
        "raw_result_rows": len(raw_rows),
        "deduped_result_rows": len(rows),
        "duplicate_result_rows": len(raw_rows) - len(rows),
        "batch_size": args.batch_size,
        "workers": args.workers,
        "model": normalize_model_name(args.model),
        "api_mode": choose_api_mode(args),
        "elapsed_sec": round(time.time() - started, 2),
        "counters": dict(counters),
        "decision_counts": dict(Counter(str(row.get("llm_decision", "")) for row in rows)),
        "outputs": {
            "llm_results_jsonl": str(jsonl_path),
            "llm_results_csv": str(csv_path),
            "llm_keep": str(final_keep_path),
            "llm_review": str(final_review_path),
            "llm_reject": str(final_reject_path),
        },
    }
    with (out_dir / "llm_summary.json").open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2)
    return summary


def read_jsonl_rows(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return rows


def read_jsonl_rows_deduped(path: Path) -> List[Dict[str, Any]]:
    rows_by_asset_id: Dict[str, Dict[str, Any]] = {}
    anonymous_rows: List[Dict[str, Any]] = []
    for row in read_jsonl_rows(path):
        asset_id = str(row.get("asset_id", ""))
        if asset_id:
            rows_by_asset_id[asset_id] = row
        else:
            anonymous_rows.append(row)
    return list(rows_by_asset_id.values()) + anonymous_rows


def write_csv(path: Path, fieldnames: Sequence[str], rows: Sequence[Dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_markdown_summary(path: Path, rule_summary: Dict[str, Any], llm_summary: Optional[Dict[str, Any]]) -> None:
    lines = [
        "# ObjaverseXL Text Filter Summary",
        "",
        "## Rule Prefilter",
        "",
        f"- total rows: {rule_summary.get('total', 0)}",
        f"- llm candidates: {rule_summary.get('llm_candidates', 0)}",
        "",
        "### Counters",
        "",
    ]
    for key, value in sorted(rule_summary.get("counters", {}).items()):
        lines.append(f"- {key}: {value}")
    lines.extend(["", "### Risk Tags", ""])
    for key, value in sorted(rule_summary.get("risk_tags", {}).items()):
        lines.append(f"- {key}: {value}")
    if llm_summary:
        lines.extend(["", "## LLM Review", ""])
        lines.append(f"- model: {llm_summary.get('model', '')}")
        lines.append(f"- candidates: {llm_summary.get('llm_candidates', 0)}")
        lines.append(f"- elapsed_sec: {llm_summary.get('elapsed_sec', 0)}")
        lines.append("")
        lines.append("### LLM Decisions")
        lines.append("")
        for key, value in sorted(llm_summary.get("decision_counts", {}).items()):
            lines.append(f"- {key or 'blank'}: {value}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def validate_inputs(paths: Sequence[str]) -> None:
    missing = [path for path in paths if not Path(path).exists()]
    if missing:
        raise FileNotFoundError("missing input CSV(s): " + ", ".join(missing))


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Filter ObjaverseXL assets from captions with rules plus ghc-api.")
    parser.add_argument("input_csvs", nargs="*", default=DEFAULT_INPUT_CSVS, help="ObjaverseXL CSV files to scan.")
    parser.add_argument("--out-dir", default="data_filter/objaverse_text_filter_report", help="Output report directory.")
    parser.add_argument("--ghc-api-url", default=os.environ.get("GHC_API_URL") or os.environ.get("GHC_API_BASE_URL") or "http://localhost:8313", help="ghc-api base URL, /chat/completions URL, or /responses URL.")
    parser.add_argument("--ghc-api-key-env", default="GHC_API_KEY", help="Environment variable containing ghc-api key.")
    parser.add_argument("--model", default=os.environ.get("GHC_API_MODEL", "gpt-5.5"), help="LLM model name. Default: gpt-5.5")
    parser.add_argument("--api-mode", choices=["auto", "chat", "responses"], default="auto", help="ghc-api endpoint mode. Auto uses /responses for gpt-5.x models. Default: auto")
    parser.add_argument("--workers", type=int, default=4, help="Concurrent ghc-api requests. Default: 4")
    parser.add_argument("--batch-size", type=int, default=30, help="Assets per ghc-api request. Default: 30")
    parser.add_argument("--timeout-sec", type=int, default=180, help="HTTP timeout for one request. Default: 180")
    parser.add_argument("--temperature", type=float, default=0.0, help="LLM temperature. Default: 0")
    parser.add_argument("--llm-scope", choices=["candidates", "review", "reject", "risk"], default="candidates", help="Which rule-prefilter rows should be sent to LLM.")
    parser.add_argument("--llm-limit", type=int, default=0, help="Maximum LLM candidates to review. Use 0 for no limit.")
    parser.add_argument("--resume", action="store_true", help="Resume LLM review by skipping asset_id values already present in llm_results.jsonl.")
    parser.add_argument("--rules-only", action="store_true", help="Only run rule prefilter; do not call ghc-api.")
    parser.add_argument("--limit", type=int, default=0, help="Maximum rows to scan across all CSVs. Use 0 for all rows.")
    parser.add_argument("--text-max-chars", type=int, default=900, help="Maximum caption characters written/sent per asset. Default: 900")
    parser.add_argument("--progress-every", type=int, default=50000, help="Print rule progress every N scanned rows. Use 0 to disable.")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    validate_inputs(args.input_csvs)
    out_dir = Path(args.out_dir)
    started = time.time()
    candidates, rule_summary = write_rule_outputs(args, out_dir)
    llm_summary = None
    if not args.rules_only and candidates:
        llm_summary = run_llm_review(candidates, args, out_dir)
    write_markdown_summary(out_dir / "summary.md", rule_summary, llm_summary)
    print(f"finished in {time.time() - started:.1f}s -> {out_dir}", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        raise SystemExit(130)
