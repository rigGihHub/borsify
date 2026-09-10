from pathlib import Path
from market_universe import load_avanza_universe, universe_symbols, audit_catalog, catalog_integrity_summary

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / 'app.py').read_text(encoding='utf-8')


def test_version_and_default_market_remain_scandinavian():
    assert 'APP_VERSION = "3.73.0"' in APP
    assert 'index=list(MARKET_CONFIGS).index("Sverige + Norge + Danmark")' in APP


def test_nordic_catalog_is_materially_broader():
    catalog = load_avanza_universe(ROOT / 'avanza_universe.csv')
    counts = catalog.groupby('Land').size().to_dict()
    assert counts['Sverige'] >= 120
    assert counts['Norge'] >= 50
    assert counts['Danmark'] >= 45
    nordic = universe_symbols(catalog, ['Sverige','Norge','Danmark'], broad=True)
    assert len(nordic) >= 225


def test_expansion_is_broad_tier_and_catalog_passes_local_qc():
    catalog = load_avanza_universe(ROOT / 'avanza_universe.csv')
    assert len(catalog) == 876
    assert catalog['Ticker'].is_unique
    expanded = catalog[catalog['Ticker'].isin(['MIPS.ST','FRO.OL','ZEAL.CO'])]
    assert len(expanded) == 3
    assert expanded['Nivå'].eq('Bred').all()
    summary = catalog_integrity_summary(audit_catalog(ROOT / 'avanza_universe.csv'))
    assert summary == {'approved': 876, 'excluded': 0, 'total': 876, 'countries': 15}


def test_core_universe_size_is_not_inflated_by_expansion():
    catalog = load_avanza_universe(ROOT / 'avanza_universe.csv')
    broad = universe_symbols(catalog, ['Sverige','Norge','Danmark'], broad=True)
    core = universe_symbols(catalog, ['Sverige','Norge','Danmark'], broad=False)
    assert len(broad) > len(core)
    assert all(t in broad for t in core)
