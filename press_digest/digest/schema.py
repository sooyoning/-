"""기사 레코드 스키마, 분류표 로딩, 정규화."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CATEGORIES = ROOT / "categories.json"

# 입장(stance) 주체 구분 — 일일 보고서에서 이 순서로 정렬된다.
STANCE_GROUPS = [
    "금융위", "금감원", "정부·타부처", "국회", "수사기관",
    "금융회사", "소비자·시민단체", "전문가·학계", "기타",
]
RELEVANCE = ["높음", "보통", "낮음"]  # 금융위·금감원 소관 정책과의 관련도
FALLBACK_CATEGORY = "기타·타부처"


def load_categories(path: Path | str | None = None) -> list[dict]:
    data = json.loads(Path(path or DEFAULT_CATEGORIES).read_text(encoding="utf-8"))
    cats = data["categories"]
    if FALLBACK_CATEGORY not in [c["name"] for c in cats]:
        cats.append({"name": FALLBACK_CATEGORY, "desc": "위 분류에 맞지 않는 기사"})
    return cats


def category_names(cats: list[dict]) -> list[str]:
    return [c["name"] for c in cats]


def _norm_title(title: str) -> str:
    return re.sub(r"[\s\W_]+", "", title or "").lower()


def make_id(date: str, media: str, title: str) -> str:
    key = f"{date}|{_norm_title(media)}|{_norm_title(title)}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


def response_schema(cat_names: list[str]) -> dict:
    """Claude structured output(JSON Schema). 모든 필드 required, additionalProperties=false."""
    s = {"type": "string"}
    article = {
        "type": "object",
        "properties": {
            "media": s,
            "title": s,
            "page_label": s,
            "continues_previous": {"type": "boolean"},
            "category": {"type": "string", "enum": cat_names},
            "sub_categories": {"type": "array", "items": {"type": "string", "enum": cat_names}},
            "issue": s,
            "relevance": {"type": "string", "enum": RELEVANCE},
            "facts": {"type": "array", "items": s},
            "situation": s,
            "stances": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "group": {"type": "string", "enum": STANCE_GROUPS},
                        "actor": s,
                        "position": s,
                    },
                    "required": ["group", "actor", "position"],
                    "additionalProperties": False,
                },
            },
            "implications": s,
            "notes": s,
        },
        "required": [
            "media", "title", "page_label", "continues_previous", "category",
            "sub_categories", "issue", "relevance", "facts", "situation",
            "stances", "implications", "notes",
        ],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {"articles": {"type": "array", "items": article}},
        "required": ["articles"],
        "additionalProperties": False,
    }


def _clean(x) -> str:
    return re.sub(r"[ \t]+", " ", str(x or "")).strip()


def normalize_record(raw: dict, date: str, cat_names: list[str], pdf_page: int | None = None,
                     source: str = "") -> dict:
    """모델/수기 입력을 저장 포맷으로 정규화한다. 분류표에 없는 분야는 '기타·타부처'."""
    cat = _clean(raw.get("category"))
    if cat not in cat_names:
        cat = FALLBACK_CATEGORY
    subs = [c for c in (raw.get("sub_categories") or []) if c in cat_names and c != cat]
    rel = _clean(raw.get("relevance")) or "보통"
    if rel not in RELEVANCE:
        rel = "보통"
    stances = []
    for st in raw.get("stances") or []:
        grp = _clean(st.get("group")) if isinstance(st, dict) else ""
        if grp not in STANCE_GROUPS:
            grp = "기타"
        if isinstance(st, dict) and _clean(st.get("position")):
            stances.append({"group": grp, "actor": _clean(st.get("actor")),
                            "position": _clean(st.get("position"))})
    media, title = _clean(raw.get("media")), _clean(raw.get("title"))
    return {
        "id": make_id(date, media, title),
        "date": date,
        "media": media,
        "title": title,
        "page_label": _clean(raw.get("page_label")),
        "pdf_page": raw.get("pdf_page", pdf_page),
        "category": cat,
        "sub_categories": subs,
        "issue": _clean(raw.get("issue")),
        "relevance": rel,
        "facts": [_clean(f) for f in raw.get("facts") or [] if _clean(f)],
        "situation": _clean(raw.get("situation")),
        "stances": stances,
        "implications": _clean(raw.get("implications")),
        "notes": _clean(raw.get("notes")),
        "source": source or raw.get("source", ""),
    }
