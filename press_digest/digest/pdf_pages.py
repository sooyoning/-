"""PDF 페이지 처리: 헤더(날짜·면) 파싱, 날짜 추정, 판독용 이미지 타일 렌더링."""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber

# 예) "2026년 10월 8일 목요일 B02면 경제 금융"
HEADER_RE = re.compile(
    r"(?P<y>\d{4})년\s*(?P<m>\d{1,2})월\s*(?P<d>\d{1,2})일\s*[월화수목금토일]요일\s*(?P<rest>[^\n]*)"
)


@dataclass
class PageInfo:
    page: int                      # 1부터 시작하는 PDF 페이지 번호
    headers: list[str] = field(default_factory=list)   # 예: ["B02면 경제"]
    dates: list[str] = field(default_factory=list)     # YYYY-MM-DD


def read_pages(pdf_path: Path | str) -> list[PageInfo]:
    pages: list[PageInfo] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            info = PageInfo(page=i)
            for m in HEADER_RE.finditer(page.extract_text() or ""):
                info.dates.append(f"{int(m['y']):04d}-{int(m['m']):02d}-{int(m['d']):02d}")
                info.headers.append(m["rest"].strip())
            pages.append(info)
    return pages


def guess_date(pdf_path: Path | str, pages: list[PageInfo], override: str | None = None) -> str:
    """우선순위: --date > 페이지 헤더 최빈값 > 파일명 yymmdd."""
    if override:
        return override
    counts: dict[str, int] = {}
    for p in pages:
        for d in p.dates:
            counts[d] = counts.get(d, 0) + 1
    if counts:
        return max(counts, key=counts.get)
    m = re.search(r"(?<!\d)(\d{2})(\d{2})(\d{2})(?!\d)", Path(pdf_path).stem)
    if m:
        return f"20{m[1]}-{m[2]}-{m[3]}"
    raise ValueError("날짜를 알 수 없습니다. --date YYYY-MM-DD 로 지정하세요.")


def parse_page_range(spec: str | None, total: int) -> list[int]:
    if not spec:
        return list(range(1, total + 1))
    out: list[int] = []
    for part in spec.split(","):
        a, _, b = part.strip().partition("-")
        lo, hi = int(a), int(b or a)
        out.extend(range(lo, min(hi, total) + 1))
    return sorted(set(out))


def render_tiles(pdf_path: Path | str, page_no: int, dpi: int = 200, tiles: int = 2,
                 overlap: float = 0.08, quality: int = 88) -> list[bytes]:
    """페이지를 위·아래(겹침 포함)로 나눠 JPEG 바이트로 반환한다.

    신문 지면은 글씨가 작아서 한 장으로 보내면 API 쪽 축소로 수치가 뭉개진다.
    타일로 나누면 숫자 판독 정확도가 올라간다.
    """
    with pdfplumber.open(str(pdf_path)) as pdf:
        img = pdf.pages[page_no - 1].to_image(resolution=dpi).original.convert("RGB")
    w, h = img.size
    out: list[bytes] = []
    step = h / tiles
    for t in range(tiles):
        top = max(0, int(t * step - overlap * h)) if t else 0
        bottom = min(h, int((t + 1) * step + overlap * h)) if t < tiles - 1 else h
        buf = io.BytesIO()
        img.crop((0, top, w, bottom)).save(buf, "JPEG", quality=quality)
        out.append(buf.getvalue())
    return out
