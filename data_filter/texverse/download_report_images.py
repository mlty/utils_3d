#!/usr/bin/env python3
"""Download report thumbnails and build a local HTML gallery."""

from __future__ import annotations

import argparse
import csv
import html
import json
import mimetypes
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional, Sequence


def download_image(index: int, row: Dict[str, str], out_dir: Path, timeout_sec: int, retries: int) -> Dict[str, str]:
	asset_id = row.get("asset_id", "unknown")
	result = {"asset_id": asset_id, "filename": "", "status": "failed", "error": ""}
	url = row.get("thumbnail_url", "")
	if not url:
		result["error"] = "missing thumbnail_url"
		return result
	for attempt in range(retries + 1):
		try:
			request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
			with urllib.request.urlopen(request, timeout=timeout_sec) as response:
				content = response.read()
				extension = mimetypes.guess_extension(response.headers.get_content_type()) or ".jpg"
			filename = f"{index:04d}_{asset_id}{extension}"
			(out_dir / filename).write_bytes(content)
			result.update({"filename": filename, "status": "ok", "error": ""})
			return result
		except Exception as exc:
			result["error"] = f"{type(exc).__name__}: {exc}"
			if isinstance(exc, urllib.error.HTTPError) and exc.code < 500 and exc.code != 429:
				break
			if attempt < retries:
				time.sleep(min(2**attempt, 4))
	try:
		api_request = urllib.request.Request(
			f"https://api.sketchfab.com/v3/models/{asset_id}",
			headers={"User-Agent": "Mozilla/5.0"},
		)
		with urllib.request.urlopen(api_request, timeout=timeout_sec) as response:
			model = json.loads(response.read().decode("utf-8"))
		fallback_urls = [
			image.get("url", "") for image in model.get("thumbnails", {}).get("images", [])
			if isinstance(image, dict) and image.get("url")
		]
		for fallback_url in fallback_urls:
			try:
				request = urllib.request.Request(fallback_url, headers={"User-Agent": "Mozilla/5.0"})
				with urllib.request.urlopen(request, timeout=timeout_sec) as response:
					content = response.read()
					extension = mimetypes.guess_extension(response.headers.get_content_type()) or ".jpg"
				filename = f"{index:04d}_{asset_id}{extension}"
				(out_dir / filename).write_bytes(content)
				result.update({"filename": filename, "status": "ok", "error": ""})
				return result
			except Exception:
				continue
	except Exception as exc:
		result["error"] += f"; fallback failed: {type(exc).__name__}: {exc}"
	return result


def write_gallery(rows: List[Dict[str, str]], downloads: Dict[str, Dict[str, str]], out_dir: Path) -> None:
	cards: List[str] = []
	for row in rows:
		asset_id = row.get("asset_id", "")
		download = downloads[asset_id]
		if download["status"] == "ok":
			media = f'<img src="{html.escape(download["filename"])}" loading="lazy" alt="{html.escape(asset_id)}">'
		else:
			media = f'<div class="missing">下载失败<br>{html.escape(download["error"])}</div>'
		cards.append(
			f'<article>{media}<div class="body"><strong>{html.escape(row.get("name") or asset_id)}</strong>'
			f'<code>{html.escape(asset_id)}</code><p>{html.escape(row.get("reason", ""))}</p>'
			f'<small>{html.escape(row.get("quality_issues", ""))}</small></div></article>'
		)
	page = """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Reject Images</title>
<style>body{margin:0;padding:24px;background:#f4f3ef;color:#202420;font-family:Georgia,"Noto Serif SC",serif}h1{margin:0 0 20px}.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:16px}article{overflow:hidden;border:1px solid #c9c8c1;border-radius:6px;background:#fff}img,.missing{display:block;width:100%;aspect-ratio:16/9;object-fit:contain;background:#deddd7}.missing{display:grid;place-items:center;color:#8b2e23}.body{padding:14px}.body strong,.body code{display:block}.body code{margin-top:5px;color:#68706a;font-size:11px}.body p{font-size:14px;line-height:1.5}.body small{color:#8b2e23}</style>
</head><body>"""
	page += f'<h1>Reject Images ({len(rows)})</h1><main class="grid">{"".join(cards)}</main></body></html>'
	(out_dir / "index.html").write_text(page, encoding="utf-8")


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument("csv_path", type=Path)
	parser.add_argument("--out-dir", type=Path)
	parser.add_argument("--workers", type=int, default=16)
	parser.add_argument("--timeout-sec", type=int, default=60)
	parser.add_argument("--retries", type=int, default=2)
	return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
	args = parse_args(argv)
	out_dir = args.out_dir or args.csv_path.parent / f"{args.csv_path.stem}_images"
	out_dir.mkdir(parents=True, exist_ok=True)
	with args.csv_path.open(encoding="utf-8", newline="") as handle:
		rows = list(csv.DictReader(handle))
	downloads: Dict[str, Dict[str, str]] = {}
	with ThreadPoolExecutor(max_workers=max(args.workers, 1)) as executor:
		futures = [
			executor.submit(download_image, index, row, out_dir, args.timeout_sec, args.retries)
			for index, row in enumerate(rows, 1)
		]
		for future in as_completed(futures):
			result = future.result()
			downloads[result["asset_id"]] = result
	with (out_dir / "manifest.csv").open("w", encoding="utf-8", newline="") as handle:
		writer = csv.DictWriter(handle, fieldnames=["asset_id", "filename", "status", "error"])
		writer.writeheader()
		writer.writerows(downloads[row.get("asset_id", "")] for row in rows)
	write_gallery(rows, downloads, out_dir)
	failures = sum(result["status"] != "ok" for result in downloads.values())
	print(f"images={len(rows)} downloaded={len(rows) - failures} failures={failures} output={out_dir}")
	return 1 if failures else 0


if __name__ == "__main__":
	raise SystemExit(main())
