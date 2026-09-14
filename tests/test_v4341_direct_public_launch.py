from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "app.py").read_text(encoding="utf-8")


def test_public_app_has_no_internal_shared_password_gate():
    assert 'APP_VERSION = "4.35.0"' in APP
    assert "require_site_access()" not in APP
    assert "APP_ACCESS_PASSWORD" not in APP
    assert "Åtkomstlösenord" not in APP


def test_optional_user_accounts_remain_available():
    assert "auth_sign_in" in APP
    assert "Supabase" in APP
