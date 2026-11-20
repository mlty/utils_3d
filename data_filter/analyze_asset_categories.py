#!/usr/bin/env python3
"""Classify retained and excluded assets into approximate semantic categories."""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterator


DATASETS = ("tex", "github", "sket", "cg", "step1x")
CATEGORY_PATTERNS = {
    "human_character": r"\b(character|human|person|man|woman|boy|girl|warrior|soldier|knight|zombie|humanoid|avatar|npc|people|farmer|doctor|nurse|pirate|ninja|wizard|robot character)\b|人物|角色|人形|士兵|战士",
    "animal_creature": r"\b(animal|creature|monster|dragon|dog|cat|bird|fish|horse|cow|pig|sheep|goat|bear|wolf|rabbit|frog|insect|dinosaur|shark|whale|snake|spider|alien|beast)\b|动物|怪物|龙|猫|狗|鸟|鱼",
    "vehicle_transport": r"\b(car|truck|vehicle|tank|ship|boat|aircraft|airplane|helicopter|motorcycle|motorbike|bicycle|bike|train|spaceship|bus|van|scooter|tractor|trailer|submarine|rocket)\b|汽车|车辆|飞机|船|摩托|自行车|火车",
    "furniture_home": r"\b(furniture|chair|armchair|stool|bench|sofa|couch|bed|cabinet|desk|shelf|bookshelf|bookcase|wardrobe|dresser|nightstand|table|cupboard|mattress|crib|drawer)\b|家具|椅子|沙发|桌子|床|柜子|书架",
    "architecture_building": r"\b(building|house|tower|bridge|temple|castle|church|hut|cabin|warehouse|station|shop|facade|roof|door|window|stairs|gate|fence|column|arch|balcony|monument)\b|建筑|房屋|塔|桥|寺庙|城堡|门|窗",
    "weapon_military": r"\b(sword|gun|rifle|pistol|weapon|axe|bow|shield|cannon|missile|knife|dagger|grenade|shotgun|spear|hammer weapon|ammunition|ammo|turret)\b|武器|剑|枪|刀|盾|导弹",
    "machine_tool_industrial": r"\b(machine|equipment|engine|robot|mech|drill|hammer|factory|industrial|generator|crane|excavator|tool|gear|mechanical|appliance|device)\b|机器|设备|工具|机器人|工业",
    "electronics_device": r"\b(computer|laptop|phone|smartphone|camera|television|monitor|console|speaker|keyboard|mouse|headphone|microphone|radio|screen|printer|electronic)\b|电脑|手机|相机|电视|显示器|电子",
    "food_drink_tableware": r"\b(food|fruit|vegetable|cake|bread|burger|pizza|meat|bottle|cup|plate|bowl|glass|tableware|drink|can|jar|apple|banana|strawberry|carrot|mushroom|meal)\b|食物|水果|蔬菜|蛋糕|面包|瓶|杯|碗|盘",
    "clothing_accessory": r"\b(clothing|shirt|dress|coat|shoe|boot|hat|helmet|armor|bag|watch|jewelry|glove|pants|trousers|skirt|jacket|outfit|backpack|mask|costume)\b|服装|衣服|鞋|帽|头盔|盔甲|包|首饰",
    "nature_plant": r"\b(tree|plant|flower|forest|bush|grass|leaf|leaves|cactus|palm|vegetation|crop|log|branch|mushroom|coral)\b|树|植物|花|草|灌木|仙人掌",
    "lighting_fixture": r"\b(lamp|lantern|chandelier|light fixture|streetlight|sconce|ceiling light|floor light|lampshade)\b|灯|灯笼|吊灯|路灯",
    "container_packaging": r"\b(container|box|crate|barrel|package|packaging|basket|chest|bin|bucket|case|suitcase|pot|vase|tankard)\b|容器|箱子|盒子|桶|篮子|罐子|花瓶",
    "musical_instrument": r"\b(guitar|piano|drum|violin|trumpet|instrument|ukulele|saxophone|flute|microphone|bongo)\b|乐器|吉他|钢琴|鼓|小提琴",
    "sports_game_toy": r"\b(toy|game|dice|chess|puzzle|ball|football|basketball|golf|skateboard|playground|arcade|doll|lego|figurine)\b|玩具|游戏|棋|球|拼图|玩偶",
    "decorative_art": r"\b(decoration|ornament|artwork|painting|frame|sign|emblem|fountain|clock|candle|trophy|gift|podium|pedestal)\b|装饰|艺术品|画|标志|喷泉|钟|奖杯",
}
COMPILED = {category: re.compile(pattern, re.IGNORECASE) for category, pattern in CATEGORY_PATTERNS.items()}
PRIORITY = tuple(CATEGORY_PATTERNS)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--analysis-dir", type=Path,
        default=Path(__file__).with_name("removed_metadata_analysis"),
    )
    parser.add_argument(
        "--semantic-exclusions", type=Path,
        default=Path(__file__).with_name("precision_semantic_filter") / "exclusion_candidates.csv",
    )
    parser.add_argument(
        "--out-dir", type=Path,
        default=Path(__file__).with_name("asset_category_analysis"),
    )
    return parser.parse_args()


def iter_rows(path: Path) -> Iterator[dict[str, str]]:
    for filename in ("reject_candidates.csv", "review_candidates.csv", "keep_candidates.csv"):
        with (path / filename).open(encoding="utf-8-sig", errors="replace", newline="") as handle:
            yield from csv.DictReader(handle)


def number(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def categories(text: str) -> tuple[str, list[str]]:
    scores = {category: len(pattern.findall(text)) for category, pattern in COMPILED.items()}
    labels = [category for category in PRIORITY if scores[category] > 0]
    if not labels:
        return "other_unknown", []
    primary = max(labels, key=lambda category: (scores[category], -PRIORITY.index(category)))
    return primary, labels


def threshold_passes(row: dict[str, str]) -> bool:
    blocks = number(row.get("voxel_blocks", ""))
    if blocks is None or not 2_000 <= blocks <= 30_000:
        return False
    score = number(row.get("aesthetic_score", ""))
    if score is not None and score < 5.0:
        return False
    faces = number(row.get("face_count", ""))
    return faces is None or 1_000 <= faces <= 1_000_000


def rate(count: int, total: int) -> str:
    return f"{count / total:.2%}" if total else "0.00%"


def report(summary: dict[str, object]) -> str:
    lines = [
        "# 3D 资产类别分布", "",
        "分类基于路径和 caption 关键词，是近似统计；主类别互斥可相加，多标签统计不可相加。", "",
        "## 总体", "",
        "| 数据源 | 最终保留 | 已删除 | 保留未知率 |", "| --- | ---: | ---: | ---: |",
    ]
    for dataset in DATASETS:
        stats = summary["datasets"][dataset]
        retained = stats["outcomes"].get("retained", 0)
        unknown = stats["primary_by_outcome"].get("retained", {}).get("other_unknown", 0)
        lines.append(f"| {dataset} | {retained:,} | {stats['outcomes'].get('semantic_delete', 0) + stats['outcomes'].get('threshold_delete', 0):,} | {rate(unknown, retained)} |")

    for dataset in DATASETS:
        stats = summary["datasets"][dataset]
        lines.extend(["", f"## {dataset}", "", "### 最终保留主类别", "",
                      "| 类别 | 数量 | 保留占比 |", "| --- | ---: | ---: |"])
        retained = stats["outcomes"].get("retained", 0)
        for category, count in stats["primary_by_outcome"].get("retained", {}).items():
            lines.append(f"| `{category}` | {count:,} | {rate(count, retained)} |")
        lines.extend(["", "### 删除主类别", "", "| 类别 | 语义删除 | 阈值删除 | 删除合计 |", "| --- | ---: | ---: | ---: |"])
        semantic = stats["primary_by_outcome"].get("semantic_delete", {})
        threshold = stats["primary_by_outcome"].get("threshold_delete", {})
        all_categories = Counter(semantic) + Counter(threshold)
        for category, total in all_categories.most_common():
            lines.append(f"| `{category}` | {semantic.get(category, 0):,} | {threshold.get(category, 0):,} | {total:,} |")

    lines.extend(["", "## 限制", "",
                  "- `other_unknown` 不代表无类别，只表示当前文本没有稳定关键词。",
                  "- 一个模型可能同时是人物、武器和服装；主类别只取关键词命中最多的一类。",
                  "- TexVerse/GitHub/Sketchfab 的文本覆盖较好；CG 和 Step1X 主要依赖路径，未知率预计更高。",
                  "- 精确类别和类别平衡应使用图片或多视角渲染模型复核。"])
    return "\n".join(lines) + "\n"


def main() -> int:
    args = parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    with args.semantic_exclusions.open(encoding="utf-8-sig", errors="replace", newline="") as handle:
        semantic_keys = {(row["dataset"], row["source_row"]) for row in csv.DictReader(handle)}

    outcomes: dict[str, Counter[str]] = defaultdict(Counter)
    primary_counts: dict[str, dict[str, Counter[str]]] = defaultdict(lambda: defaultdict(Counter))
    multilabel_counts: dict[str, dict[str, Counter[str]]] = defaultdict(lambda: defaultdict(Counter))
    output_path = args.out_dir / "asset_categories.csv"
    fields = ("dataset", "source_row", "sha256", "outcome", "primary_category", "all_categories", "local_path")
    with output_path.open("w", encoding="utf-8-sig", newline="") as output_handle:
        writer = csv.DictWriter(output_handle, fieldnames=fields)
        writer.writeheader()
        for row in iter_rows(args.analysis_dir):
            dataset = row["dataset"]
            key = (dataset, row["source_row"])
            if key in semantic_keys:
                outcome = "semantic_delete"
            elif not threshold_passes(row):
                outcome = "threshold_delete"
            else:
                outcome = "retained"
            primary, labels = categories(f"{row['local_path']} {row['file_identifier']} {row['text_evidence']}")
            outcomes[dataset][outcome] += 1
            primary_counts[dataset][outcome][primary] += 1
            multilabel_counts[dataset][outcome].update(labels)
            writer.writerow({
                "dataset": dataset,
                "source_row": row["source_row"],
                "sha256": row["sha256"],
                "outcome": outcome,
                "primary_category": primary,
                "all_categories": ";".join(labels),
                "local_path": row["local_path"],
            })

    summary = {"datasets": {}}
    for dataset in DATASETS:
        summary["datasets"][dataset] = {
            "outcomes": dict(outcomes[dataset]),
            "primary_by_outcome": {
                outcome: dict(counter.most_common()) for outcome, counter in primary_counts[dataset].items()
            },
            "multilabel_by_outcome": {
                outcome: dict(counter.most_common()) for outcome, counter in multilabel_counts[dataset].items()
            },
        }
    (args.out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.out_dir / "summary.md").write_text(report(summary), encoding="utf-8")
    print(json.dumps({dataset: summary["datasets"][dataset]["outcomes"] for dataset in DATASETS}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())