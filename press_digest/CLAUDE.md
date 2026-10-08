# press_digest — 일일 PDF 업로드 처리 지침

사용자가 「신문기사 주요 내용」 PDF(금융위 대변인실 스크랩)를 올리면 **API 키 없이 Claude가 직접 읽고** 정리한다.
(자동화·API 연동은 사용자가 불필요하다고 했음 — `--engine api` 는 쓰지 말 것.)

## 처리 절차
1. 헤더 확인·기준일 추정: `python -m digest process <pdf> --engine manual` → `work/<날짜>/pages/` 에 위·아래 타일 이미지, `INSTRUCTIONS.md` 생성.
   (PDF 텍스트에는 날짜·면 헤더만 있고 본문은 이미지다. 표지·만평·인사/부고란은 정책 정보가 없어 제외.)
2. 페이지를 읽는다. 빠르게 훑을 땐 PDF를 Read(pages 범위, 최대 20쪽)로 보고, **숫자가 빽빽한 기사는 타일 이미지로 재확인**한다.
3. 기사별 레코드를 `work/<날짜>/records.json` 에 작성한다(필드·원칙은 `digest/extract_api.py` 의 SYSTEM 프롬프트와 `INSTRUCTIONS.md` 따름).
   - 한 기사가 두 쪽에 걸치면(제목 없는 이어짐 쪽) 한 레코드로 합친다.
   - 분류는 `categories.json`, 같은 사건은 같은 `issue` 문자열로 묶는다(누적 이슈별 보기에 쓰임).
   - 수치는 기사 그대로. 불확실하면 `[판독불확실]`. 시사점은 기사 근거 범위의 의견으로 사실관계와 분리.
4. 적재·보고서: `python -m digest ingest work/<날짜>/records.json --date <날짜>` → `output/daily/<날짜>.docx`, `output/cumulative/index.html`, `output/cumulative/누적정리.xlsx` 갱신.
5. 사용자에게: 건수·분야 분포, 눈여겨볼 이슈, 판독불확실 항목, 산출물 파일을 전달한다. 산출물은 `SendUserFile`로 보낸다.

## 주의
- `data/records`, `output`, `work`, `*.pdf` 는 `.gitignore` 대상(언론사 저작물). 커밋하지 않는다.
- 같은 날짜 재처리는 (일자+매체+제목) 기준 덮어쓰기라 안전하다.
- 소관분야 분류표 변경 요청은 `categories.json` 만 고치면 된다.
