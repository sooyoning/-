"""Claude 비전 API로 지면 이미지 → 기사별 구조화 레코드."""
from __future__ import annotations

import base64
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

from .pdf_pages import PageInfo, render_tiles
from .schema import STANCE_GROUPS, normalize_record, response_schema

DEFAULT_MODEL = os.environ.get("PRESS_DIGEST_MODEL", "claude-opus-5-5")

SYSTEM = """당신은 금융위원회 대변인실의 '신문기사 주요 내용' 스크랩을 정리하는 정책 분석 보조자입니다.
입력은 신문 지면 한 페이지를 위·아래로 나눈 이미지입니다(두 이미지는 경계 부분이 겹칩니다).
페이지에는 기사가 1건 또는 여러 건 있을 수 있습니다. 기사마다 레코드 1건을 만드세요.

작성 원칙
- 기사에 없는 내용은 절대 만들지 마세요. 수치는 숫자·단위·기준시점·출처(예: '국민의힘 ○○○ 의원실 자료')를 기사 그대로 옮깁니다.
  도표·그래프의 수치도 읽을 수 있는 범위에서 facts에 포함합니다. 글씨가 흐려 확신이 없으면 값 뒤에 '[판독불확실]'을 붙이세요.
- media: 지면 상단 제호(예: 매일경제, 한겨레). page_label: 날짜 줄의 면 정보(예: 'A06면 종합').
- title: 기사 대제목 그대로. 헤드라인 없이 앞 기사의 이어지는 본문·그래픽만 있는 조각이면
  continues_previous=true, title은 빈 문자열로 두고 같은 형식으로 내용만 채웁니다.
- facts: 사실관계 핵심을 3~8개 항목으로. 각 항목은 한 문장, 금액·비율·건수·기간·날짜·주체를 명시.
- situation: 사건의 경과와 현재 쟁점을 1~3문장으로.
- stances: 금융위·금감원·정부·국회·금융회사·소비자단체·전문가가 기사에서 밝힌 입장/발언. group은 주어진 구분 중 선택,
  actor는 기사에 나온 표기 그대로('금융위 관계자', '신한은행' 등), position은 입장 요약. 기사에 없으면 빈 배열.
- implications: 금융위·금감원 소관 부서 관점의 시사점(후속 정책·감독 과제·리스크)을 1~3문장. 기사 근거 범위 안에서의 해석이며 사실과 섞지 마세요.
- category/sub_categories: 주어진 소관분야 목록에서만 선택. issue: 같은 사건·정책을 묶을 수 있는 짧은 이슈명(예: 'AI 연쇄 해킹 사고').
- relevance: 금융위·금감원 소관 정책과의 관련도(높음/보통/낮음). 인물동정·칼럼 등은 '낮음'.
- notes: 판독 한계·특이사항(없으면 빈 문자열).
금융과 무관한 기사도 레코드는 만들되 relevance를 '낮음'으로 하세요. 응답은 JSON 스키마를 따릅니다."""


def _user_content(page: PageInfo, tiles: list[bytes], cats: list[dict]) -> list[dict]:
    cat_text = "\n".join(f"- {c['name']}: {c['desc']}" for c in cats)
    hint = (
        f"PDF {page.page}페이지. 텍스트 레이어로 읽은 날짜·면 헤더: {page.headers or '없음'}\n\n"
        f"[소관분야 목록]\n{cat_text}\n\n[입장 주체 구분] {', '.join(STANCE_GROUPS)}"
    )
    content: list[dict] = [{"type": "text", "text": hint}]
    for i, jpg in enumerate(tiles, start=1):
        content.append({"type": "text", "text": f"이미지 {i}/{len(tiles)}"})
        content.append({"type": "image", "source": {
            "type": "base64", "media_type": "image/jpeg",
            "data": base64.standard_b64encode(jpg).decode("ascii")}})
    content.append({"type": "text", "text": "이 페이지의 모든 기사를 JSON으로 정리하세요."})
    return content


def extract_page(client, pdf_path, page: PageInfo, cats: list[dict], model: str,
                 dpi: int = 200) -> list[dict]:
    cat_names = [c["name"] for c in cats]
    tiles = render_tiles(pdf_path, page.page, dpi=dpi)
    resp = client.messages.create(
        model=model,
        max_tokens=16000,
        system=SYSTEM,
        messages=[{"role": "user", "content": _user_content(page, tiles, cats)}],
        # Opus 5.5 는 강제 tool_choice 불가 → 구조화 출력(JSON Schema)을 사용한다.
        output_config={"effort": "medium",
                       "format": {"type": "json_schema", "schema": response_schema(cat_names)}},
    )
    if resp.stop_reason in ("refusal", "max_tokens"):
        raise RuntimeError(f"p.{page.page}: stop_reason={resp.stop_reason}")
    text = next(b.text for b in resp.content if b.type == "text")
    arts = json.loads(text)["articles"]
    for a in arts:
        a["pdf_page"] = page.page
    return arts


def merge_continuations(per_page: list[tuple[int, list[dict]]]) -> list[dict]:
    """헤드라인 없는 이어짐 조각(continues_previous)을 직전 같은 매체 기사에 합친다."""
    merged: list[dict] = []
    for _, arts in sorted(per_page, key=lambda t: t[0]):
        for a in arts:
            prev = next((m for m in reversed(merged) if m["media"] == a["media"]), None)
            if a.get("continues_previous") and prev is not None:
                prev["facts"] = prev["facts"] + [f for f in a["facts"] if f not in prev["facts"]]
                prev["stances"] = prev["stances"] + a["stances"]
                for k in ("situation", "implications"):
                    if not prev[k]:
                        prev[k] = a[k]
                prev["notes"] = " ".join(x for x in (prev["notes"], a["notes"],
                                                     f"p.{a['pdf_page']} 이어짐 병합") if x)
            else:
                merged.append(dict(a))
    return merged


def extract_pdf(pdf_path, pages: list[PageInfo], date: str, cats: list[dict], *,
                model: str = DEFAULT_MODEL, workers: int = 4, client=None,
                log: Callable[[str], None] = print) -> tuple[list[dict], list[int]]:
    """반환: (정규화된 레코드, 실패한 PDF 페이지 번호)."""
    if client is None:
        import anthropic
        client = anthropic.Anthropic()  # ANTHROPIC_API_KEY 또는 `ant auth login` 프로필 사용
    cat_names = [c["name"] for c in cats]
    results: list[tuple[int, list[dict]]] = []
    failed: list[int] = []

    def work(p: PageInfo):
        try:
            return p.page, extract_page(client, pdf_path, p, cats, model), None
        except Exception as e:  # noqa: BLE001 - 페이지 단위로 격리해 계속 진행
            return p.page, [], e

    with ThreadPoolExecutor(max_workers=workers) as ex:
        for page_no, arts, err in ex.map(work, pages):
            if err:
                failed.append(page_no)
                log(f"  ✗ p.{page_no} 실패: {err}")
            else:
                results.append((page_no, arts))
                log(f"  ✓ p.{page_no}: 기사 {len(arts)}건")
    merged = merge_continuations(results)
    return [normalize_record(a, date, cat_names, source=Path(str(pdf_path)).name) for a in merged], failed
