"""일자별 JSON 저장소. data/records/YYYY-MM-DD.json 이 원본(source of truth)이다."""
from __future__ import annotations

import json
from pathlib import Path

from .schema import ROOT

DEFAULT_DIR = ROOT / "data" / "records"


def _path(date: str, base: Path) -> Path:
    return base / f"{date}.json"


def load_day(date: str, base: Path = DEFAULT_DIR) -> list[dict]:
    p = _path(date, base)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []


def load_all(base: Path = DEFAULT_DIR) -> list[dict]:
    out: list[dict] = []
    for p in sorted(base.glob("????-??-??.json")):
        out.extend(json.loads(p.read_text(encoding="utf-8")))
    return out


def upsert(records: list[dict], date: str, base: Path = DEFAULT_DIR) -> tuple[int, int]:
    """같은 id(일자+매체+제목)는 덮어쓰고 나머지는 추가. 반환: (신규, 갱신)."""
    base.mkdir(parents=True, exist_ok=True)
    existing = {r["id"]: r for r in load_day(date, base)}
    new = upd = 0
    for r in records:
        if r["id"] in existing:
            upd += 1
        else:
            new += 1
        existing[r["id"]] = r
    ordered = sorted(existing.values(), key=lambda r: (r.get("pdf_page") or 0, r["media"]))
    _path(date, base).write_text(json.dumps(ordered, ensure_ascii=False, indent=2), encoding="utf-8")
    return new, upd


def query(records: list[dict], *, category: str | None = None, since: str | None = None,
          until: str | None = None, q: str | None = None, issue: str | None = None,
          media: str | None = None, min_relevance: str | None = None) -> list[dict]:
    rank = {"낮음": 0, "보통": 1, "높음": 2}
    out = []
    for r in records:
        if category and category not in [r["category"], *r["sub_categories"]]:
            continue
        if since and r["date"] < since or until and r["date"] > until:
            continue
        if issue and issue not in r["issue"]:
            continue
        if media and media not in r["media"]:
            continue
        if min_relevance and rank[r["relevance"]] < rank[min_relevance]:
            continue
        if q:
            blob = " ".join([r["title"], r["situation"], r["implications"], r["issue"],
                             *r["facts"], *(s["position"] + s["actor"] for s in r["stances"])])
            if q not in blob:
                continue
        out.append(r)
    return sorted(out, key=lambda r: (r["date"], r["category"], r["media"]), reverse=True)
