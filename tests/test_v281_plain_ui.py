from pathlib import Path
APP=Path(__file__).resolve().parents[1]/"app.py"
def test_plain_ui():
 t=APP.read_text(encoding="utf-8")
 assert 'APP_VERSION = "2.83.1"' in t
 assert "Olika sätt att hitta köplägen" in t
 assert "Vad betyder börsorden?" in t
 assert "Har Borsify fungerat tidigare?" in t
