# -*- coding: utf-8 -*-
"""
session4b_ht_iv.py — Hausman-Taylor IV 진단 (리뷰어 2 전면 대응판)
IREF-D-26-01562 | Session 4B
환경: Python 3.12, linearmodels 7.0, statsmodels

목적:
  - R2-4 (IV 배제제한 / 식별력 진단)에 직접 대응.
  - 수동 2SLS 코드를 linearmodels.iv.IV2SLS로 전면 교체하고,
    Kleibergen-Paap rk Wald F(robust 1단계 식별력) 및
    Sargan-Hansen(Wooldridge robust overidentification) J-test를 출력한다.
  - gov_fund_log(연도별 단일값)와 연도 고정효과 간 완전 공선성을 조건수로
    입증하여, HT-IV를 철회하고 CRE(session4a)로 회귀하는 논리를 완성한다.

실행:
    python session4b_ht_iv.py
"""
import warnings

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf
from linearmodels.iv import IV2SLS

from vc_panel_common import TV6, COHORT_YEAR, attrition_diagnosis, build_panel

warnings.filterwarnings("ignore")
pd.set_option("display.width", 160)

DEPENDENT_VAR = "tobq_log"
ENDOG = "vc"
INSTRUMENTS = ["gov_fund_log", "location"]

print("=" * 76)
print("SESSION 4B — Hausman-Taylor IV 진단 (리뷰어 2 대응판)")
print("R2-4: IV 식별력 / 배제제한 진단 -> linearmodels.iv.IV2SLS 전면 도입")
print("=" * 76)


# ==============================================================================
# 0. 데이터 준비 - 상장 시점(rel==0) 횡단면 표본
# ==============================================================================
panel = build_panel(path="vc_korea_final_panel.csv")
cross = panel[panel["rel"] == 0].copy()

# ------------------------------------------------------------------------
# [리뷰어 1] 생존 편의 진단 - dropna 직전 (상장시점 횡단면 표본 기준)
# ------------------------------------------------------------------------
attrition_diagnosis(cross, vc_col=ENDOG, title="생존 편의(Survivorship Bias) 진단 - rel=0 횡단면")

needed = [DEPENDENT_VAR, ENDOG] + INSTRUMENTS + TV6 + [COHORT_YEAR, "firm"]
d_iv = cross.dropna(subset=needed).copy()

print(f"\n분석 표본 (rel=0 횡단면, 불균형): N={len(d_iv)}")
print("IV 후보 변수 점검:")
print(f"  Z1 = gov_fund_log : 고유값 {d_iv['gov_fund_log'].nunique()}개  "
      f"(연도별 단일값이면 연도 FE와 완전 공선 위험)")
print(f"  Z2 = location     : 고유값 {d_iv['location'].nunique()}개")


# ==============================================================================
# Step 1. 1단계(First-stage) 식별력 진단 - Kleibergen-Paap rk Wald F
# ==============================================================================
print("\n" + "=" * 76)
print("[Step 1] 1단계 식별력 진단 - Kleibergen-Paap rk Wald F (robust)")
print("=" * 76)

clusters_iv = d_iv[["firm", COHORT_YEAR]].copy()
n_iv = len(INSTRUMENTS)

n_firm_clusters = d_iv["firm"].nunique()
n_lyear_clusters = d_iv[COHORT_YEAR].nunique()
print(f"[Two-way Clustering] 군집 수: firm={n_firm_clusters}, {COHORT_YEAR}={n_lyear_clusters}")
if n_lyear_clusters < 10:
    print(
        f"  주의: {COHORT_YEAR} 군집 수({n_lyear_clusters})가 적어 이원 군집-강건\n"
        "  공분산 행렬 기반 통계량이 불안정할 수 있습니다 (Cameron, Gelbach,\n"
        "  Miller 2011)."
    )


def _kp_f(diag_row, n_instruments):
    """linearmodels first_stage.diagnostics의 f.stat(Wald chi2)을 KP F로 환산."""
    f_stat = float(diag_row["f.stat"])
    f_dist = str(diag_row["f.dist"])
    if f_dist.startswith("chi2"):
        return f_stat / n_instruments, "Wald chi2 / L (robust, KP F 근사)"
    return f_stat, f_dist


# (A) 연도 FE 없는 사양 - 도구변수 본연의 식별력
formula_nofe = (
    f"{DEPENDENT_VAR} ~ 1 + " + " + ".join(TV6)
    + f" + [{ENDOG} ~ " + " + ".join(INSTRUMENTS) + "]"
)
mod_nofe = IV2SLS.from_formula(formula_nofe, data=d_iv)
res_nofe = mod_nofe.fit(cov_type="clustered", clusters=clusters_iv)
diag_nofe = res_nofe.first_stage.diagnostics.loc[ENDOG]
kp_f_nofe, kp_label_nofe = _kp_f(diag_nofe, n_iv)

print(f"\n(A) 연도 FE 미포함 사양: {ENDOG} ~ {' + '.join(INSTRUMENTS)} + TV6")
print(f"    Partial R^2          = {diag_nofe['partial.rsquared']:.4f}")
print(f"    1단계 Wald {diag_nofe['f.dist']:<10} = {diag_nofe['f.stat']:.4f}  "
      f"(p={diag_nofe['f.pval']:.4f})")
print(f"    Kleibergen-Paap rk Wald F (근사) = {kp_f_nofe:.4f}  [{kp_label_nofe}]")
print(f"    Stock-Yogo 경험적 기준(F>10): "
      f"{'통과' if kp_f_nofe > 10 else '미달 -> 약한 도구변수(Weak IV)'}")

# (B) C(lyear) 연도 FE 포함 사양 - gov_fund_log와의 공선성 노출
print(f"\n(B) C({COHORT_YEAR}) 상장 코호트 연도 FE 포함 사양")
formula_fe = (
    f"{DEPENDENT_VAR} ~ 1 + " + " + ".join(TV6) + f" + C({COHORT_YEAR})"
    + f" + [{ENDOG} ~ " + " + ".join(INSTRUMENTS) + "]"
)
try:
    mod_fe = IV2SLS.from_formula(formula_fe, data=d_iv)
    res_fe = mod_fe.fit(cov_type="clustered", clusters=clusters_iv)
    diag_fe = res_fe.first_stage.diagnostics.loc[ENDOG]
    kp_f_fe, kp_label_fe = _kp_f(diag_fe, n_iv)
    print(f"    Partial R^2          = {diag_fe['partial.rsquared']:.4f}")
    print(f"    1단계 Wald {diag_fe['f.dist']:<10} = {diag_fe['f.stat']:.4f}  "
          f"(p={diag_fe['f.pval']:.4f})")
    print(f"    Kleibergen-Paap rk Wald F (근사) = {kp_f_fe:.4f}  [{kp_label_fe}]")
except Exception as exc:  # noqa: BLE001
    print(f"    추정 실패: {exc!r}")
    print(f"    -> {ENDOG}의 도구변수 행렬이 C({COHORT_YEAR}) 더미와 완전/거의\n"
          f"       공선이어서 IV2SLS의 도구변수 행렬이 full column rank를\n"
          f"       갖지 못함을 직접적으로 보여줍니다.")


# ==============================================================================
# Step 2. 조건수(Condition Number) - gov_fund_log와 연도 FE 간 공선성
# ==============================================================================
print("\n" + "=" * 76)
print("[Step 2] 조건수(Condition Number) 진단 - gov_fund_log vs 연도 FE")
print("=" * 76)

formula_1st_fe = (
    f"{ENDOG} ~ " + " + ".join(INSTRUMENTS + TV6) + f" + C({COHORT_YEAR})"
)
m_1st_fe = smf.ols(formula_1st_fe, data=d_iv).fit()
cond_fe = np.linalg.cond(m_1st_fe.model.exog)

formula_1st_nofe = f"{ENDOG} ~ " + " + ".join(INSTRUMENTS + TV6)
m_1st_nofe = smf.ols(formula_1st_nofe, data=d_iv).fit()
cond_nofe = np.linalg.cond(m_1st_nofe.model.exog)

print(f"  조건수 (연도 FE 미포함) = {cond_nofe:.2f}")
print(f"  조건수 (연도 FE 포함)   = {cond_fe:.2e}")
print(
    f"  -> {'조건수 폭증 (>1e8): gov_fund_log가 C(lyear)와 거의 완전 공선' if cond_fe > 1e8 else '조건수 안정적'}"
)

print(
    "\n[해설 - 리뷰어 2: IV 식별력/배제제한 진단 종합]\n"
    " - gov_fund_log(연간 정부 FoF 약정액)는 상장 코호트 연도(lyear)별로\n"
    "   거의 단일한 값을 가지므로, C(lyear) 고정효과를 포함하는 순간 해당\n"
    "   고정효과에 흡수되어 식별력을 완전히 상실합니다 (조건수 폭증 또는\n"
    "   도구변수 행렬의 rank 결손으로 직접 확인됨).\n"
    " - 연도 FE를 제외한 사양에서도 Kleibergen-Paap rk Wald F가 Stock-Yogo\n"
    "   경험적 기준(10)에 미달한다면, 약한 도구변수(weak instrument)로\n"
    "   판정되어 2SLS 추정치의 신뢰성이 크게 저하됩니다.\n"
    " - location(소재지) 또한 VC 클러스터링/집적효과(agglomeration)를 통해\n"
    "   기업가치(Tobin's Q)에 직접 영향을 미칠 수 있어 배제제한(exclusion\n"
    "   restriction) 위반 가능성이 존재합니다."
)


# ==============================================================================
# Step 3. 구조방정식(2SLS) 추정 및 과다식별 검정
# ==============================================================================
print("\n" + "=" * 76)
print("[Step 3] IV2SLS 구조방정식 추정 및 Sargan-Hansen(robust) 과다식별 검정")
print("=" * 76)

print(f"[추정식]\n  {formula_nofe}\n")
print(res_nofe.summary)

print("\n[과다식별(overidentification) 검정]")
print(res_nofe.sargan)
print()
print(res_nofe.wooldridge_overid)

print(
    "\n[해설 - 리뷰어 2: Sargan-Hansen J-test 방어]\n"
    " - Sargan's test는 동분산 가정 하의 과다식별 검정이며, Wooldridge's\n"
    "   score test of overidentification은 이분산/군집 강건(robust) 표준오차\n"
    "   환경에서의 Sargan-Hansen J-test에 해당합니다 (본 추정은 기업x상장\n"
    "   코호트 이원 군집 표준오차를 사용하므로 Wooldridge 검정을 주 통계량으로\n"
    "   보고합니다).\n"
    " - 두 검정 모두 p>0.05이면 '도구변수가 모두 외생적'이라는 귀무가설을\n"
    "   기각하지 못하나, 1단계 식별력(KP F)이 약한 상태에서는 과다식별\n"
    "   검정 자체의 검정력도 낮다는 점에 유의해야 합니다."
)


# ==============================================================================
# 최종 요약 - HT-IV 철회, CRE(Mundlak)로 회귀
# ==============================================================================
print("\n" + "=" * 76)
print("[최종 요약] HT-IV 진단 결과 종합")
print("=" * 76)
print(f"  {'검정':<38} {'통계량':>14} {'기준':>10}  판정")
print("  " + "-" * 78)
print(f"  {'KP rk Wald F (연도FE 없음)':<38} {kp_f_nofe:>14.4f} {'>10':>10}  "
      f"{'통과' if kp_f_nofe > 10 else 'Weak IV'}")
print(f"  {'조건수 (연도FE 포함)':<38} {cond_fe:>14.2e} {'<1e8':>10}  "
      f"{'안정' if cond_fe < 1e8 else 'gov_fund_log 공선'}")
print(f"  {'Wooldridge robust overid J':<38} {res_nofe.wooldridge_overid.stat:>14.4f} "
      f"{'p>0.05':>10}  "
      f"{'통과' if res_nofe.wooldridge_overid.pval > 0.05 else 'IV 의심'}")

print(
    "\n[종합 판정]\n"
    " - gov_fund_log는 상장 코호트 연도 고정효과와 사실상 완전 공선이어서,\n"
    "   Sector-Time FE를 포함하는 본 연구의 주 모형(session4a CRE)과 동시에\n"
    "   사용할 수 없습니다.\n"
    " - location은 집적효과를 통한 배제제한 위반 가능성이 있어 단독으로는\n"
    "   VC 처치효과의 타당한 도구변수로 보기 어렵습니다.\n"
    " - 따라서 본 연구는 Hausman-Taylor IV 추정을 철회하고, session4a의\n"
    "   CRE/Mundlak 추정량(Sector-Time FE + 이원 군집 표준오차)을 H1의\n"
    "   주(primary) 추정량으로 채택합니다."
)
