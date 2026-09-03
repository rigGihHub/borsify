from pathlib import Path
APP=(Path(__file__).resolve().parents[1]/"app.py").read_text(encoding="utf-8")

def test_version_is_250_or_newer():
    assert 'APP_VERSION = "2.49.0"' not in APP

def test_toplists_are_named_best_buy():
    assert "⚡ Bästa köp · 1–2 dagar" in APP
    assert "📈 Bästa köp · 1 vecka–3 månader" in APP
    assert "🏗️ Bästa köp · 1–5 år" in APP
    assert "♾️ Bästa köp · mycket lång sikt" in APP

def test_provider_outage_explanation_is_plain_swedish():
    assert "Saknade aktier får därför ingen felmarkering eller karantän" in APP
