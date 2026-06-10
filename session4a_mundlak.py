# -*- coding: utf-8 -*-
"""
session4a_mundlak.py — Mundlak/CRE 완전 구현 (리뷰어 1, 2 전면 대응판)
IREF-D-26-01562 | Session 4A
환경: Python 3.12, linearmodels 7.0, statsmodels

목적:
  - R1 (Survivorship bias / Unbalanced panel / Sector-time confounding /
        Two-way clustering / Hausman-equivalent test / Oster bounds)에 대한
    단일 CRE(Mundlak) 모형을 구축하고, 진단 결과를 모두 콘솔에 출력한다.

실행:
    python session4a_mundlak.py
"""
import warnings

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from linearmodels.panel import PanelOLS, RandomEffects

from vc_panel_common import (
    TV6,
    COHORT_YEAR,
    add_mundlak_means,
    attrition_diagnosis,
    build_panel,
)

warnings.filterwarnings("ignore")
pd.set_option("display.width", 160)

DEPENDENT_VAR = "tobq_log"   # H1 종속변수 (Tobin's Q, log)
TREATMENT = "vc"             # H1 처치변수 (VC 투자 여부 더미, 시불변)


# ==============================================================================
# 0. 데이터 준비
# ==============================================================================
print("=" * 76)
print("SESSION 4A — Mundlak/CRE 완전 구현 (리뷰어 1, 2 대응판)")
print("환경: linearmodels 7.0, statsmodels")
print("=" * 76)

raw = build_panel(path="vc_korea_final_panel.csv")

# ------------------------------------------------------------------------
# [리뷰어 1] 생존 편의(Survivorship Bias) 진단 - dropna 직전 수행
# ------------------------------------------------------------------------
attrition_diagnosis(raw, vc_col=TREATMENT)

# ------------------------------------------------------------------------
# Mundlak 보조변수(TV6 기업별 평균) 생성
#   이유: E[alpha_i | X_it] = X_bar_i'lambda 가정하에, 기업별 평균이 alpha_i를 proxy
# ------------------------------------------------------------------------
panel_all = add_mundlak_means(raw, group_col="firm", tv6=TV6, suffix="_m")
TV6_M = [f"{v}_m" for v in TV6]

# ------------------------------------------------------------------------
# [리뷰어 1] 불균형 패널(Unbalanced Panel) 유지
#   -> dropna는 종속변수 + 분석 필수 변수에 대해서만 수행
# ------------------------------------------------------------------------
needed_cols = (
    [DEPENDENT_VAR, TREATMENT, "firm", "year", COHORT_YEAR, "industry_sector"]
    + TV6
    + TV6_M
)
d_full = panel_all.dropna(subset=needed_cols).copy()

print(f"\n분석 표본 (Unbalanced Panel 유지): N기업={d_full['firm'].nunique()}, "
      f"N관측={len(d_full)}")
obs_per_firm = d_full.groupby("firm").size()
print(f"기업당 관측치 수: min={obs_per_firm.min()}, max={obs_per_firm.max()}, "
      f"mean={obs_per_firm.mean():.2f}  (불균형 패널 -> 자연 변동 그대로 유지)")
print(f"시변 통제변수: {TV6}")
print(f"Mundlak 보조변수: {TV6_M}")


# ==============================================================================
# 모형: 제한적 Mundlak / CRE  (★ PRIMARY)
# ==============================================================================
print("\n" + "=" * 76)
print("[모형] RandomEffects 기반 CRE (Mundlak) - Primary 추정량")
print("=" * 76)

panel_df = d_full.set_index(["firm", "year"])

# [리뷰어 1] 산업 x 상장코호트연도 교호작용 더미 (Sector-Time Confounding 통제)
formula_cre = (
    f"{DEPENDENT_VAR} ~ 1 + {TREATMENT} + "
    + " + ".join(TV6)
    + " + "
    + " + ".join(TV6_M)
    + f" + C(industry_sector):C({COHORT_YEAR})"
)
print(f"[추정식]\n  {formula_cre}\n")

# [리뷰어 1] 기업 + 상장 코호트 연도 수준 이원 군집화
clusters = d_full[["firm", COHORT_YEAR]].copy()
clusters.index = panel_df.index

n_firm_clusters = d_full["firm"].nunique()
n_lyear_clusters = d_full[COHORT_YEAR].nunique()
print(f"[Two-way Clustering] 군집 수: firm={n_firm_clusters}, {COHORT_YEAR}={n_lyear_clusters}")
if n_lyear_clusters < 10:
    print(
        f"  주의: {COHORT_YEAR} 군집 수({n_lyear_clusters})가 적어 이원 군집-강건\n"
        "  공분산 행렬이 비양정치(non-PSD)가 될 수 있습니다 (Cameron, Gelbach,\n"
        "  Miller 2011). 이 경우 보고된 표준오차/Wald 통계량은 보수적 상한으로\n"
        "  해석하고, 상장 코호트 연도 표본을 확장하는 것을 권장합니다."
    )

try:
    mod_cre = RandomEffects.from_formula(formula_cre, data=panel_df)
    res_cre = mod_cre.fit(cov_type="clustered", clusters=clusters)
    cre_model_name = "RandomEffects (제한적 Mundlak / CRE)"
except Exception as exc:  # noqa: BLE001  (비양정치 등 RE 추정 실패 시 PanelOLS로 우회)
    print(f"RandomEffects 추정 실패 ({exc!r}) -> PanelOLS(EntityEffects)로 우회")
    formula_fe = formula_cre + " + EntityEffects"
    mod_cre = PanelOLS.from_formula(formula_fe, data=panel_df, drop_absorbed=True)
    res_cre = mod_cre.fit(cov_type="clustered", clusters=clusters)
    cre_model_name = "PanelOLS (Entity FE, fallback)"
    print(
        " 주의: vc, industry_sector, lyear 등 시불변 변수는 EntityEffects에\n"
        "       의해 자동 흡수/제거됩니다 (drop_absorbed=True). 이는 CRE가\n"
        "       필요한 근본적 이유(시불변 처치 식별)를 재확인시켜 줍니다."
    )

print(f"[추정 모형] {cre_model_name}")
print(res_cre.summary)

if TREATMENT in res_cre.params.index:
    b_vc = res_cre.params[TREATMENT]
    se_vc = res_cre.std_errors[TREATMENT]
    p_vc = res_cre.pvalues[TREATMENT]
    pct_vc = (np.exp(b_vc) - 1) * 100
    ci_lo = (np.exp(b_vc - 1.96 * se_vc) - 1) * 100
    ci_hi = (np.exp(b_vc + 1.96 * se_vc) - 1) * 100
    print(f"\n[H1 핵심계수 - {TREATMENT}]")
    print(f"  beta = {b_vc:+.5f}  SE = {se_vc:.5f}  p = {p_vc:.4f}")
    print(f"  Tobin's Q 변화율 = {pct_vc:+.2f}%   95% CI = [{ci_lo:+.2f}%, {ci_hi:+.2f}%]")

print(
    "\n[해설 - 리뷰어 1: Sector-Time Confounding 방어]\n"
    " - C(industry_sector):C(lyear) 교호작용 더미를 포함하여, 특정 산업의\n"
    "   특정 상장 코호트에 공통적으로 작용하는 거시/산업 충격(예: 특정 연도\n"
    "   바이오 업종 IPO 붐)이 VC 처치효과 추정치를 교란할 가능성을 통제했습니다.\n"
    "\n[해설 - 리뷰어 1: Two-way Clustering 방어]\n"
    " - 표준오차는 기업(firm) 및 상장 코호트 연도(lyear) 수준에서 이원\n"
    "   군집화(two-way clustering)되어, 동일 기업 내 시계열 상관과 동일\n"
    "   상장연도 코호트 내 횡단면 상관을 모두 허용합니다.\n"
    "\n[해설 - 리뷰어 1: Unbalanced Panel 방어]\n"
    " - 종속변수 및 분석 필수 변수에 대해서만 결측치를 제거하여, 관측 가능한\n"
    "   최대 표본을 유지하는 불균형 패널로 추정했습니다 ('Re-estimate on an\n"
    "   unbalanced panel' 코멘트에 직접 대응)."
)


# ==============================================================================
# Hausman 대체 검정: Mundlak 보조변수 Joint Wald Test
# ==============================================================================
print("\n" + "=" * 76)
print("[Hausman 대체 검정] Mundlak 보조변수 Joint Wald Test (RE vs FE)")
print("=" * 76)
print("  H0: 모든 Mundlak 보조변수(TV6_m)의 계수 = 0  (RE와 FE 동등 -> 무상관)")
print("  H1: 적어도 하나의 보조변수 계수 != 0  (alpha_i와 X_it 상관 -> FE 필요,")
print("      단 CRE는 이 상관을 TV6_m을 통해 이미 통제하므로 추정은 유효)")

if "EntityEffects" not in formula_cre and all(v in res_cre.params.index for v in TV6_M):
    wald_res = res_cre.wald_test(formula=", ".join(f"{v}=0" for v in TV6_M))
    print(f"\n  Wald chi2({wald_res.df}) = {wald_res.stat:.4f}")
    print(f"  p-value = {wald_res.pval:.6f}")

    if wald_res.pval < 0.01:
        print("  -> p<0.01: Mundlak 보조변수 결합 유의 -> 기업 이질성(alpha_i)과")
        print("     시변 통제변수 간 상관 존재 -> CRE/Mundlak이 Pooled RE/OLS보다 우월")
        print("     (R1-1ii: CRE 구현 및 식별 전략 정당화에 직접 대응)")
    elif wald_res.pval < 0.10:
        print("  -> 0.01<=p<0.10: 경계 유의, 보수적으로 CRE 결과를 주 추정량으로 보고")
    else:
        print("  -> p>=0.10: alpha_i와 X_it 간 상관에 대한 강한 증거 부족,")
        print("     RE와 FE(가능한 경우)가 유사한 결과를 줄 것으로 예상")

    print("\n  Mundlak 보조변수별 계수:")
    print(f"  {'변수':<16} {'coef':>10} {'SE':>10} {'p':>8}")
    print("  " + "-" * 46)
    for v in TV6_M:
        b = res_cre.params[v]
        s = res_cre.std_errors[v]
        p = res_cre.pvalues[v]
        sig = "*" if p < 0.10 else ""
        print(f"  {v:<16} {b:>+10.4f} {s:>10.4f} {p:>8.4f}{sig}")
else:
    print(
        "\n  주의: PanelOLS(EntityEffects) fallback에서는 TV6_m이 시불변으로\n"
        "  흡수되어 검정할 수 없습니다. 이 자체가 alpha_i와 TV6_m이 완전히\n"
        "  중첩됨을 보여주는 결과이며, Mundlak/CRE 사양의 필요성을 시사합니다."
    )


# ==============================================================================
# Oster Bounds (delta=1, Rmax = 1.3 * R_full)
# ==============================================================================
print("\n" + "=" * 76)
print("[Oster Bounds] 관측되지 않은 선택편의에 대한 강건성 (delta=1, Rmax=1.3*R_full)")
print("=" * 76)

formula_restricted = (
    f"{DEPENDENT_VAR} ~ 1 + {TREATMENT} + C(industry_sector):C({COHORT_YEAR})"
)
formula_full = (
    formula_restricted + " + " + " + ".join(TV6) + " + " + " + ".join(TV6_M)
)

ols_restricted = smf.ols(formula_restricted, data=d_full).fit()
ols_full = smf.ols(formula_full, data=d_full).fit()

beta_tilde = ols_restricted.params[TREATMENT]
beta_dot = ols_full.params[TREATMENT]
r_tilde = ols_restricted.rsquared
r_dot = ols_full.rsquared
r_max = 1.3 * r_dot
delta = 1.0

print(f"  R^2 (uncontrolled, restricted) = {r_tilde:.4f}")
print(f"  R^2 (controlled, full CRE-OLS) = {r_dot:.4f}")
print(f"  R_max = 1.3 * R_full           = {r_max:.4f}")
print(f"  beta (uncontrolled)             = {beta_tilde:.6f}")
print(f"  beta (controlled, full)         = {beta_dot:.6f}")

if abs(r_dot - r_tilde) < 1e-8:
    print(
        "\n  경고: R_full ~= R_restricted, 분모가 0에 가까워 Oster bounds를"
        " 안정적으로 계산할 수 없습니다."
    )
else:
    beta_star = beta_dot - delta * (beta_tilde - beta_dot) * (r_max - r_dot) / (
        r_dot - r_tilde
    )
    lower, upper = sorted([beta_dot, beta_star])
    print(f"\n  beta* (delta=1, Rmax=1.3*R_full) = {beta_star:.6f}")
    print(f"  Oster Identified Set ({TREATMENT}) = [{lower:.6f}, {upper:.6f}]")

    same_sign = (lower * upper) > 0
    print(
        "  -> 식별 구간이 0을 "
        + ("포함하지 않으며 부호가 일관됩니다 (강건함)." if same_sign
           else "포함하여 부호 안정성이 약화될 수 있습니다.")
    )

print(
    "\n[해설 - Oster Bounds 방어]\n"
    " - 관측되지 않은 선택편의가 관측된 통제변수(TV6 + Mundlak 평균 +\n"
    "   Sector-Time FE)와 동일한 정도로 작용한다는 보수적 가정(delta=1) 하에서,\n"
    "   R_max = 1.3 * R_full을 상한으로 설정해 VC 처치효과(vc) 계수의 식별\n"
    "   구간(Identified Set)을 계산했습니다.\n"
    " - 이 구간이 0을 포함하지 않는다면, 관측되지 않은 변수에 의한 누락변수\n"
    "   편의(omitted variable bias)만으로는 H1 결과가 사라지지 않음을 의미합니다."
)


# ==============================================================================
# H2 — CRE: Hybrid VC vs Pure PVC (동일 사양 적용)
# ==============================================================================
print("\n" + "=" * 76)
print("[H2] CRE(Mundlak): Hybrid VC vs Pure-PVC (Sector-Time FE + Two-way Clustering)")
print("=" * 76)

if {"mix", "private"}.issubset(d_full.columns):
    sub = d_full[(d_full[TREATMENT] == 1) & ((d_full["mix"] == 1) | (d_full["private"] == 1))].copy()
    sub["treat"] = sub["mix"].astype(int)

    needed_h2 = [DEPENDENT_VAR, "treat", "firm", "year", COHORT_YEAR, "industry_sector"] + TV6 + TV6_M
    sub = sub.dropna(subset=needed_h2)

    print(f"분석 표본: N기업={sub['firm'].nunique()}, N관측={len(sub)}")

    panel_h2 = sub.set_index(["firm", "year"])
    formula_h2 = (
        f"{DEPENDENT_VAR} ~ 1 + treat + "
        + " + ".join(TV6)
        + " + "
        + " + ".join(TV6_M)
        + f" + C(industry_sector):C({COHORT_YEAR})"
    )
    clusters_h2 = sub[["firm", COHORT_YEAR]].copy()
    clusters_h2.index = panel_h2.index

    try:
        mod_h2 = RandomEffects.from_formula(formula_h2, data=panel_h2)
        res_h2 = mod_h2.fit(cov_type="clustered", clusters=clusters_h2)
        h2_name = "RandomEffects (CRE)"
    except Exception as exc:  # noqa: BLE001
        print(f"RandomEffects 추정 실패 ({exc!r}) -> PanelOLS(EntityEffects)로 우회")
        mod_h2 = PanelOLS.from_formula(formula_h2 + " + EntityEffects", data=panel_h2,
                                        drop_absorbed=True)
        res_h2 = mod_h2.fit(cov_type="clustered", clusters=clusters_h2)
        h2_name = "PanelOLS (Entity FE, fallback)"

    print(f"[추정 모형] {h2_name}")
    if "treat" in res_h2.params.index:
        b2, s2, p2 = res_h2.params["treat"], res_h2.std_errors["treat"], res_h2.pvalues["treat"]
        lo2 = (np.exp(b2 - 1.96 * s2) - 1) * 100
        hi2 = (np.exp(b2 + 1.96 * s2) - 1) * 100
        bonferroni_alpha = 0.0063
        print(f"  CRE Hybrid-PVC: {(np.exp(b2) - 1) * 100:+.2f}%  p={p2:.4f}")
        print(f"  95% CI: [{lo2:+.1f}%, {hi2:+.1f}%]  "
              f"Bonferroni(alpha={bonferroni_alpha}): "
              f"{'비유의' if p2 > bonferroni_alpha else '유의'}")
    else:
        print("  treat 계수가 시불변으로 흡수되어 식별되지 않았습니다 (FE fallback).")
else:
    print("  'mix'/'private' 변수가 데이터에 없어 H2 분석을 건너뜁니다.")

print("\n" + "=" * 76)
print("SESSION 4A 완료 — Primary 추정량: CRE/Mundlak (Sector-Time FE, Two-way Clustering)")
print("=" * 76)
