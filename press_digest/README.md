# 신문기사 주요내용 PDF 자동 정리 (press_digest)

금융위 대변인실 「신문기사 주요 내용」 PDF를 매일 올리면 기사별로 아래 순서로 정리하고, 누적 저장해 **소관분야별·이슈별**로 다시 볼 수 있게 합니다.

> **일자 – 매체명 – 제목 – 사실관계(수치 명시) – 상황 – 금융위·금감원 등 및 이해관계자 입장 – 시사점**  (+ 소관분야·이슈·관련도)

## 한눈에 보는 흐름

```
PDF ──► 페이지별 이미지(위·아래 타일, 200dpi) ──► Claude가 직접 판독해 기사별 JSON 작성
   └─ 날짜·면은 PDF 텍스트 헤더에서 확정                    │ 이어진 기사 자동 병합
                                                            ▼
                         data/records/YYYY-MM-DD.json  (일자별 원본, 재처리 시 덮어쓰기)
                                                            │
        ┌───────────────────────────────┬───────────────────┴─────────────┐
        ▼                               ▼                                 ▼
 output/daily/날짜.docx          output/cumulative/index.html      output/cumulative/누적정리.xlsx
 (소관분야별 표, 요청 순서)      (분야·이슈·기간·매체·검색 필터)    (전체 + 분야별 시트, 필터)
```

PDF 본문은 **전부 이미지**(텍스트 레이어에는 날짜·면 헤더만 있음)라서 OCR/비전 모델이 필요합니다. 그래서 신문 지면을 위·아래로 나눠 확대한 이미지를 Claude에 보내 숫자 판독 정확도를 높였습니다.

## 설치

```bash
cd press_digest
pip install -r requirements.txt     # pdfplumber, python-docx, openpyxl (anthropic 은 api 엔진 쓸 때만)
```

## 매일 사용법 (업로드 방식)

1. 그날 PDF를 Claude Code 대화에 올리고 "오늘 것 정리해줘"라고 하면 됩니다.
2. Claude가 지침(`CLAUDE.md`)대로 페이지를 읽어 기사별 레코드를 만들고 아래 명령으로 적재합니다.
   ```bash
   python -m digest process 보도자료_261009.pdf --engine manual      # 이미지·지침 준비 (날짜 자동 인식)
   python -m digest ingest work/2026-10-09/records.json --date 2026-10-09   # 적재 + 일일 DOCX + 누적 HTML/XLSX
   ```
3. 결과: `output/daily/날짜.docx`(소관분야별 표), `output/cumulative/index.html`(누적·필터·이슈별 보기), `output/cumulative/누적정리.xlsx`.

누적 조회·재생성은 API 키 없이 로컬에서 됩니다.

```bash
python -m digest list --category 가계부채·여신관리 --since 2026-10-01
python -m digest list --q 요구불 --min-relevance 높음
python -m digest list --issue "AI 연쇄 해킹"
python -m digest report --date 2026-10-08 --min-relevance 보통    # 일일 보고서만 재생성(낮은 관련도 제외)
python -m digest report --cumulative                               # 누적 HTML/XLSX 재생성
```

- 같은 날 PDF를 다시 처리해도 (일자+매체+제목)이 같으면 **덮어쓰기**라 중복되지 않습니다.
- 한 기사가 두 쪽에 걸치면 한 레코드로 합칩니다.
- 만평·인사/부고란은 정책 정보가 없어 제외합니다.

> 참고: `--engine api`(Claude API 자동 추출)도 구현·테스트돼 있으나 사용자가 자동화를 원하지 않아 기본 흐름에서 뺐습니다. 설치: `pip install -r requirements.txt`.

## 웹 페이지에서 직접 업로드 (API 키 없이)

`web/index.html`은 claude.ai에 **Artifact로 게시**해서 쓰는 단일 페이지입니다. 게시된 Artifact는 보는 사람의 Claude 계정으로 Claude를 호출할 수 있어(`sample`, 이미지 전달 포함) 키가 필요 없습니다.

- 정리하기: PDF 업로드 → 브라우저에서 쪽별 이미지 분할 → Claude가 기사별로 정리 → 저장소(`db`)에 누적
- 누적 보기: 분야·이슈·일자별 보기, 필터·검색, 엑셀/HTML 보고서/JSON 백업 저장(`downloads`)
- 로컬 파일로 열면 Claude 호출이 되지 않아 `output/cumulative/index.html`(조회 전용)과 다릅니다.
- 소관분야 기준은 `web/index.html` 상단 `CATS`를 고치고 같은 경로로 다시 게시하면 바뀝니다.
- 테스트: 목(mock) 런타임으로 실제 PDF 59쪽을 끝까지 돌려 확인(정상·실패·한도초과 후 재개). 실제 claude.ai 런타임에서의 첫 호출은 사용자가 허용 창을 눌러야 합니다.

## 소관분야 분류 바꾸기

`categories.json`의 `name`/`desc`를 수정·추가하면 됩니다(`python -m digest categories`로 확인). `desc`가 모델의 분류 기준입니다.
기사는 **주 분야 1개 + 관련 분야**, 그리고 같은 사건을 묶는 **이슈명**을 가집니다. HTML에서 `소관분야별 / 이슈별(시간순) / 일자별` 보기를 전환할 수 있습니다.
금융위 국·과 단위(예: 금융정책국·금융산업국·자본시장국·금융소비자국)로 나누고 싶으면 그 이름으로 분류표를 바꾸세요.

## 정확도·운영 메모

- **수치는 기사 원문 그대로**, 글씨가 불분명하면 `[판독불확실]`로 표시하도록 지시합니다. 보고용으로 쓰기 전 핵심 수치는 원문 대조를 권장합니다.
- **시사점은 기사 근거 범위의 해석(의견)**이며 사실관계 칸과 분리돼 있습니다.
- 모델은 기본 `claude-opus-5-5`(환경변수 `PRESS_DIGEST_MODEL`로 변경). 비용을 줄이려면 `claude-sonnet-5-5`로 바꿔 품질을 비교해 보세요.
- `data/records`, `output`, `work`, `*.pdf`는 `.gitignore`로 제외했습니다(언론사 저작물 포함 가능). 팀 공유 시 `output/cumulative/index.html` 한 파일만 전달하면 됩니다.
- `samples/2026-10-08.sample.json`은 실제 PDF(2026.10.8 조간) 일부 13건을 정리한 예시입니다:
  `python -m digest ingest samples/2026-10-08.sample.json --date 2026-10-08`

## 테스트

```bash
python -m unittest discover -s tests -v
PRESS_DIGEST_TEST_PDF=/경로/보도자료.pdf python -m unittest discover -s tests -v   # 실제 PDF 통합 테스트 포함
```
