"""Evidence-aware inputs shared by the screener and regression tests."""
import pandas as pd
import numpy as np

def _percentile_score(series: pd.Series, higher_is_better: bool = True) -> pd.Series:
    s = pd.to_numeric(series, errors="coerce")
    valid = pd.Series(np.isfinite(s), index=s.index)
    out = pd.Series(0.0, index=s.index, dtype=float)
    if valid.sum() >= 2:
        pct = s[valid].rank(pct=True, method="average") * 100
        if not higher_is_better:
            pct = 100 - pct + (100 / valid.sum())
        out.loc[valid] = pct.clip(0, 100)
    return out


def _risk_score(out: pd.DataFrame) -> pd.Series:
    risk = pd.Series(75.0, index=out.index)
    debt = pd.to_numeric(out["Skuld/eget kapital"], errors="coerce")
    roe = pd.to_numeric(out["ROE"], errors="coerce")
    margin = pd.to_numeric(out["Vinstmarginal"], errors="coerce")
    draw = pd.to_numeric(out["52v från topp"], errors="coerce")
    dist = pd.to_numeric(out["Avstånd SMA200"], errors="coerce")
    m3 = pd.to_numeric(out["3 mån"], errors="coerce")
    risk -= np.where(debt > 300, 25, np.where(debt > 200, 15, 0))
    risk -= np.where(roe < 0, 18, 0)
    risk -= np.where(margin < 0, 18, 0)
    risk -= np.where(draw < -.50, 16, np.where(draw < -.35, 8, 0))
    risk -= np.where((dist < -.10) & (m3 < -.15), 18, 0)
    known = out[["Skuld/eget kapital", "ROE", "Vinstmarginal", "52v från topp", "Avstånd SMA200", "3 mån"]].apply(pd.to_numeric, errors="coerce").apply(np.isfinite).mean(axis=1)
    return risk.clip(0, 100).where(known.eq(1), np.minimum(risk, known * 75))

