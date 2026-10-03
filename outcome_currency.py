"""Comparable currency basis for prospective close-to-close total returns."""
import pandas as pd
from fx import major_currency


def prices_in_sek(history: pd.DataFrame, currency: str, fx_history: pd.DataFrame | None = None) -> pd.DataFrame:
    out = history.copy()
    code = major_currency(currency) if currency else ""
    if not code:
        return pd.DataFrame()
    if code != "SEK":
        if fx_history is None or fx_history.empty or "Close" not in fx_history:
            return pd.DataFrame()
        def dates(index):
            return pd.to_datetime(index, utc=True).tz_localize(None).normalize()
        rate = pd.Series(pd.to_numeric(fx_history['Close'], errors='coerce').values, index=dates(fx_history.index)).sort_index()
        rate = rate[~rate.index.duplicated(keep='last')]
        # Backward-only match, bounded to four calendar days; no future FX filling.
        target = dates(out.index)
        matched = rate.reindex(target, method='ffill', tolerance=pd.Timedelta(days=4))
        out['Close'] = pd.to_numeric(out['Close'], errors='coerce').values * matched.values
        out = out.dropna(subset=['Close'])
    out.attrs['currency'] = 'SEK'
    return out
