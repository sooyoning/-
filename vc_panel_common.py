"""
vc_panel_common.py — Session 4A/4B 공용 패널 빌더 및 생존편의 진단 유틸리티
IREF-D-26-01562

- 기업 식별자: corp_code -> firm
- 상장 코호트 연도: lyear
- 산업 분류: industry_sector (없으면 industry)
- 시변 통제변수(TV6): mkt_log, rev_log, growrev, om_scaled, cr_log, d2e_log
"""

import pandas as pd

FIRM_ID_RAW = "corp_code"
COHORT_YEAR = "lyear"
REL_YEAR = "rel"

INDUSTRY_CANDIDATES = ["industry_sector", "industry"]
ATTRITION_CANDIDATES = ["attrition_flag", "sample_status"]

TV6 = ["mkt_log", "rev_log", "growrev", "om_scaled", "cr_log", "d2e_log"]


def _resolve(df, candidates, label):
    for cand in candidates:
        if cand in df.columns:
            return cand
    raise KeyError(f"{label} 변수({candidates})를 데이터에서 찾을 수 없습니다.")


def build_panel(path="vc_korea_final_panel.csv"):
    """기업-연차 unbalanced 패널 로드 및 컬럼명 표준화.

    표준화 결과:
      - corp_code -> firm
      - industry_sector / industry -> industry_sector
      - cal / year: 패널 시간 인덱스로 사용할 연도 변수
        (없으면 lyear + rel 로 생성)
    """
    df = pd.read_csv(path)

    if FIRM_ID_RAW in df.columns:
        df = df.rename(columns={FIRM_ID_RAW: "firm"})

    industry_var = _resolve(df, INDUSTRY_CANDIDATES, "산업분류")
    if industry_var != "industry_sector":
        df = df.rename(columns={industry_var: "industry_sector"})

    if "cal" not in df.columns:
        if {COHORT_YEAR, REL_YEAR}.issubset(df.columns):
            df["cal"] = df[COHORT_YEAR] + df[REL_YEAR]
        elif "year" in df.columns:
            df["cal"] = df["year"]
        else:
            raise KeyError("연도 변수(cal/year)를 생성할 수 없습니다 (lyear, rel 필요).")

    if "year" not in df.columns:
        df["year"] = df["cal"]

    return df


def attrition_diagnosis(df, vc_col="vc", title="생존 편의(Survivorship Bias) 진단"):
    """dropna 이전, VC 투자 여부에 따른 표본 이탈률(attrition rate) 출력."""
    attr_col = _resolve(df, ATTRITION_CANDIDATES, "표본이탈(attrition)")

    print(f"\n[{title}] - dropna 이전 표본, 그룹 변수: '{vc_col}'")
    table = df.groupby(vc_col)[attr_col].agg(
        N_관측치="count", N_이탈="sum", 이탈률="mean"
    )
    print(table.to_string(float_format=lambda x: f"{x:.4f}"))

    print(
        "\n[해설 - 리뷰어 1: Survivorship Bias 방어]\n"
        " - 결측치 제거(dropna) 이전 단계에서 VC 투자 여부(vc)에 따른 표본\n"
        "   탈락(attrition) 패턴을 사전적으로 점검했습니다.\n"
        " - 두 그룹 간 이탈률 격차가 현저하지 않다면, 이후 분석 변수 결측치\n"
        "   제거 과정에서 VC-backed 또는 Non-VC 기업이 체계적으로 과소/과대\n"
        "   대표될 가능성(생존 편의)이 제한적임을 의미합니다."
    )
    return table


def add_mundlak_means(df, group_col="firm", tv6=TV6, suffix="_m"):
    """시변 통제변수(TV6)에 대한 기업별 평균(Mundlak 보조변수) 생성."""
    out = df.copy()
    for v in tv6:
        out[f"{v}{suffix}"] = out.groupby(group_col)[v].transform("mean")
    return out
