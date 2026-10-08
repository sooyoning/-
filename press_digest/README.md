# 신문기사 주요내용 PDF 자동 정리 (press_digest)

금융위 대변인실 「신문기사 주요 내용」 PDF를 매일 올리면 기사별로 아래 순서로 정리하고, 누적 저장해 **소관분야별·이슈별**로 다시 볼 수 있게 합니다.

> **일자 – 매체명 – 제목 – 사실관계(수치 명시) – 상황 – 금융위·금감원 등 및 이해관계자 입장 – 시사점**  (+ 소관분야·이슈·관련도)

## 한눈에 보는 흐름

```
PDF ──► 페이지별 이미지(위·아래 타일, 200dpi) ──► Claude 비전 추출(구조화 JSON)
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
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...     # 또는 `ant auth login`
```

## 매일 사용법

```bash
# 1) PDF 처리: 추출 → 저장 → 일일 DOCX → 누적 HTML/XLSX 갱신
python -m digest process ~/Downloads/보도자료_261009.pdf
#    날짜는 PDF 헤더(없으면 파일명 yymmdd)에서 자동 인식, --date 로 지정 가능
#    일부 페이지만: --pages 2-20   |  낮은 관련도 기사 제외: --min-relevance 보통

# 2) 누적에서 찾기
python -m digest list --category 가계부채·여신관리 --since 2026-10-01
python -m digest list --q 요구불 --min-relevance 높음
python -m digest list --issue "AI 연쇄 해킹"

# 3) 보고서만 다시 만들기
python -m digest report --date 2026-10-08
python -m digest report --cumulative
```

- 같은 날 PDF를 다시 처리해도 (일자+매체+제목)이 같으면 **덮어쓰기**라 중복되지 않습니다.
- 페이지 단위로 실패를 격리합니다. 실패 페이지는 `--pages 번호`로 재실행하세요.
- 한 기사가 두 쪽에 걸쳐 제목 없이 이어지면 같은 매체의 직전 기사에 자동 병합합니다(`notes`에 기록).

## API 키 없이 쓰기 (Claude Code 등으로 직접 정리)

```bash
python -m digest process 보도자료_261009.pdf --engine manual   # work/날짜/ 에 이미지+지침 생성
# → 이미지를 읽고 work/날짜/records.json 작성(Claude Code에 "work/날짜 지침대로 정리해줘")
python -m digest ingest work/2026-10-09/records.json --date 2026-10-09
```

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
