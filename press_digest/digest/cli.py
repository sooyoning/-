"""명령행 진입점.  python -m digest --help"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import store
from .extract_api import DEFAULT_MODEL, SYSTEM, extract_pdf
from .pdf_pages import guess_date, parse_page_range, read_pages, render_tiles
from .report import build_cumulative_html, build_cumulative_xlsx, build_daily_docx
from .schema import ROOT, load_categories, normalize_record, category_names

OUT = ROOT / "output"
WORK = ROOT / "work"


def _rebuild_cumulative(cats, base) -> None:
    recs = store.load_all(base)
    h = build_cumulative_html(recs, cats, OUT / "cumulative" / "index.html")
    x = build_cumulative_xlsx(recs, cats, OUT / "cumulative" / "누적정리.xlsx")
    print(f"누적 {len(recs)}건 → {h}\n             → {x}")


def _daily(cats, base, date, min_rel=None) -> None:
    p = build_daily_docx(store.load_day(date, base), date, cats, OUT / "daily" / f"{date}.docx", min_rel)
    print(f"일일 보고서 → {p}")


def cmd_process(a) -> int:
    cats = load_categories(a.categories)
    pages = read_pages(a.pdf)
    date = guess_date(a.pdf, pages, a.date)
    wanted = set(parse_page_range(a.pages, len(pages)))
    # 날짜·면 헤더가 없는 페이지(표지 등)는 기사 페이지가 아니므로 제외
    targets = [p for p in pages if p.page in wanted and p.headers]
    skipped = [p.page for p in pages if p.page in wanted and not p.headers]
    print(f"{a.pdf.name}: 기준일 {date}, 기사 페이지 {len(targets)}개 (제외: {skipped or '없음'})")

    if a.engine == "manual":
        d = WORK / date
        (d / "pages").mkdir(parents=True, exist_ok=True)
        for p in targets:
            for i, jpg in enumerate(render_tiles(a.pdf, p.page), start=1):
                (d / "pages" / f"p{p.page:02d}_{i}.jpg").write_bytes(jpg)
        (d / "INSTRUCTIONS.md").write_text(
            f"# {date} 수기(manual) 정리 지침\n\n`pages/` 의 이미지를 페이지별(pNN_1, pNN_2 = 위·아래 타일)로 읽고 "
            f"`records.json` 에 아래 형식의 배열을 작성한 뒤 다음을 실행하세요.\n\n"
            f"    python -m digest ingest work/{date}/records.json --date {date}\n\n"
            f"## 필드\n각 원소: media, title, page_label, pdf_page, category, sub_categories[], issue, relevance, "
            f"facts[], situation, stances[{{group,actor,position}}], implications, notes\n"
            f"분야 후보: {', '.join(category_names(cats))}\n\n## 작성 원칙\n{SYSTEM}\n", encoding="utf-8")
        print(f"이미지 {len(list((d / 'pages').iterdir()))}장과 지침을 {d} 에 만들었습니다.")
        return 0

    recs, failed = extract_pdf(a.pdf, targets, date, cats, model=a.model, workers=a.workers)
    new, upd = store.upsert(recs, date, a.data)
    print(f"저장: 신규 {new}건, 갱신 {upd}건" + (f" · 실패 페이지 {failed} (재실행: --pages {','.join(map(str, failed))})" if failed else ""))
    if not a.no_report:
        _daily(cats, a.data, date, a.min_relevance)
        _rebuild_cumulative(cats, a.data)
    return 1 if failed else 0


def cmd_ingest(a) -> int:
    cats = load_categories(a.categories)
    names = category_names(cats)
    raw = json.loads(a.json.read_text(encoding="utf-8"))
    by_date: dict[str, list[dict]] = {}
    for r in raw:
        date = r.get("date") or a.date
        if not date:
            print("date 가 없는 레코드가 있습니다. --date 를 지정하세요.", file=sys.stderr)
            return 2
        by_date.setdefault(date, []).append(normalize_record(r, date, names, source=a.json.name))
    for date, recs in sorted(by_date.items()):
        new, upd = store.upsert(recs, date, a.data)
        print(f"{date}: 신규 {new}건, 갱신 {upd}건")
        if not a.no_report:
            _daily(cats, a.data, date)
    if not a.no_report:
        _rebuild_cumulative(cats, a.data)
    return 0


def cmd_report(a) -> int:
    cats = load_categories(a.categories)
    if a.date:
        _daily(cats, a.data, a.date, a.min_relevance)
    if a.cumulative or not a.date:
        _rebuild_cumulative(cats, a.data)
    return 0


def cmd_list(a) -> int:
    rows = store.query(store.load_all(a.data), category=a.category, since=a.since, until=a.until,
                       q=a.q, issue=a.issue, media=a.media, min_relevance=a.min_relevance)
    for r in rows:
        print(f"{r['date']} | {r['category']} | {r['media']} | {r['title']}"
              + (f" | 이슈:{r['issue']}" if r["issue"] else ""))
    print(f"-- {len(rows)}건")
    return 0


def cmd_categories(a) -> int:
    for c in load_categories(a.categories):
        print(f"{c['name']}: {c['desc']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="digest", description="신문기사 주요내용 PDF → 핵심 정리·누적·소관분야별 보고서")
    ap.add_argument("--data", type=Path, default=store.DEFAULT_DIR, help="일자별 JSON 저장 폴더")
    ap.add_argument("--categories", type=Path, default=None, help="분류표 JSON (기본 categories.json)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("process", help="PDF 1개 처리 (추출→저장→보고서)")
    p.add_argument("pdf", type=Path)
    p.add_argument("--date", help="YYYY-MM-DD (기본: 페이지 헤더/파일명에서 추정)")
    p.add_argument("--pages", help="예: 2-20,25 (기본 전체)")
    p.add_argument("--engine", choices=["api", "manual"], default="api",
                   help="api: Claude API 자동 추출 / manual: 이미지·지침만 만들고 직접(또는 Claude Code로) 작성")
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--min-relevance", choices=["보통", "높음"], help="일일 보고서에서 낮은 관련도 기사 제외")
    p.add_argument("--no-report", action="store_true")
    p.set_defaults(fn=cmd_process)

    p = sub.add_parser("ingest", help="수기/외부에서 만든 records.json 적재")
    p.add_argument("json", type=Path)
    p.add_argument("--date")
    p.add_argument("--no-report", action="store_true")
    p.set_defaults(fn=cmd_ingest)

    p = sub.add_parser("report", help="보고서만 다시 생성")
    p.add_argument("--date", help="일일 DOCX 생성 대상일")
    p.add_argument("--cumulative", action="store_true", help="누적 HTML/XLSX 생성")
    p.add_argument("--min-relevance", choices=["보통", "높음"])
    p.set_defaults(fn=cmd_report)

    p = sub.add_parser("list", help="누적 검색")
    for f in ("category", "since", "until", "q", "issue", "media"):
        p.add_argument(f"--{f}")
    p.add_argument("--min-relevance", choices=["낮음", "보통", "높음"])
    p.set_defaults(fn=cmd_list)

    p = sub.add_parser("categories", help="소관분야 분류표 보기")
    p.set_defaults(fn=cmd_categories)

    a = ap.parse_args(argv)
    return a.fn(a)
