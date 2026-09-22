from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "app.py").read_text(encoding="utf-8")


def test_optional_cold_start_helper_cannot_crash_core_import():
    assert 'APP_VERSION = "4.39.1"' in APP
    assert "from first_choice_audit import build_first_choice_record, save_first_choice_records" in APP
    assert "try:" in APP[APP.index("from first_choice_audit import build_first_choice_record"):APP.index("from up_and_coming import")]
    assert "except ImportError:" in APP
    assert "def latest_first_choice(*_args, **_kwargs):" in APP
    assert "return None" in APP
