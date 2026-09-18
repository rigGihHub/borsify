from __future__ import annotations

from typing import Iterable
import pandas as pd


def apply_country_price_filters(
    df: pd.DataFrame,
    countries: Iterable[str] | None = None,
    min_price_sek: float = 0.0,
    max_price_sek: float = 0.0,
    dividend_only: bool = False,
) -> pd.DataFrame:
    """Apply shared user filters to the stock universe."""
    if df is None or df.empty:
        return df.copy() if isinstance(df, pd.DataFrame) else pd.DataFrame()

    out = df.copy()
    if countries is not None:
        selected = [str(x) for x in countries if str(x)]
        if not selected:
            return out.iloc[0:0].copy()
        if "Land" in out.columns:
            out = out[out["Land"].astype(str).isin(selected)].copy()

    price = pd.to_numeric(out.get("Pris SEK", pd.Series(index=out.index, dtype=float)), errors="coerce")
    if float(min_price_sek or 0) > 0:
        out = out.loc[price.loc[out.index].notna() & (price.loc[out.index] >= float(min_price_sek))].copy()
        price = pd.to_numeric(out.get("Pris SEK"), errors="coerce")
    if float(max_price_sek or 0) > 0:
        out = out.loc[price.notna() & (price <= float(max_price_sek))].copy()

    if dividend_only:
        yield_values = pd.to_numeric(
            out.get("Direktavkastning", pd.Series(index=out.index, dtype=float)), errors="coerce"
        )
        dividend_values = pd.to_numeric(
            out.get("Utdelning", pd.Series(index=out.index, dtype=float)), errors="coerce"
        )
        out = out.loc[yield_values.gt(0) | dividend_values.gt(0)].copy()

    return out
