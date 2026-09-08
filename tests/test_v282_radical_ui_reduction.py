from pathlib import Path
APP=(Path(__file__).resolve().parents[1]/"app.py").read_text(encoding="utf-8")

def test_main_decision_copy_is_shorter():
    assert 'st.markdown("## Aktier att titta på")' in APP
    assert '"Kortare sikt", "Ungefär 1–6 månader"' in APP
    assert '"Längre sikt", "Flera år"' in APP
    assert 'st.subheader("Bäst för dina val")' in APP

def test_old_dense_headlines_removed():
    assert 'Dagens fynd · snabbaste beslutsunderlaget' not in APP
    assert 'Bästa långsiktiga case · flerårig djupkontroll' not in APP
    assert 'Bästa kortsiktiga case · 1–6 månader' not in APP
    assert 'st.subheader("Dagens bästa möjligheter")' not in APP
