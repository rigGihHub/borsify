import json
import sqlite3
import pandas as pd
import pytest
from analysis_memory import export_memory, restore_memory
from research_rotation import save_research_batch, cached_research
from investment_controls import holding_review


def test_memory_survives_database_replacement(tmp_path):
    original, replacement = tmp_path/'first.db', tmp_path/'new.db'
    save_research_batch(pd.DataFrame([{'Ticker':'A','Historik år':4}]), original)
    holding_review(7,{'Vinstmarginal':.2,'Fundamental hämtad':'2026-10-01'},original)
    backup = json.loads(json.dumps(export_memory(original,[7])))
    restore_memory(replacement, backup,[7])
    assert cached_research(replacement).iloc[0]['Ticker'] == 'A'
    with sqlite3.connect(replacement) as conn:
        assert conn.execute('select count(*) from holding_review_baselines').fetchone()[0] == 1


def test_restore_never_replaces_existing_baseline_or_other_holding(tmp_path):
    original, replacement = tmp_path/'first.db', tmp_path/'new.db'
    holding_review(7,{'Vinstmarginal':.2,'Fundamental hämtad':'2026-10-01'},original)
    holding_review(8,{'Vinstmarginal':.4,'Fundamental hämtad':'2026-10-01'},original)
    holding_review(7,{'Vinstmarginal':.3,'Fundamental hämtad':'2026-10-02'},replacement)
    restore_memory(replacement,export_memory(original,[7,8]),[7])
    with sqlite3.connect(replacement) as conn:
        rows=conn.execute('select holding_id,payload from holding_review_baselines').fetchall()
    assert len(rows)==1 and json.loads(rows[0][1])[0]['Utgångsvärde']==.3


def test_corrupt_backup_is_rejected_before_writes(tmp_path):
    target=tmp_path/'new.db'
    with pytest.raises(ValueError):
        restore_memory(target,{'version':1,'tables':{'research_rotation':[{'symbol':'A','attempted':'now','payload':'broken'}]}})
    assert not target.exists()


def test_anonymous_baselines_are_not_uploaded_for_signed_in_account(tmp_path):
    public, private=tmp_path/'public.db',tmp_path/'private.db'
    holding_review(7,{'Vinstmarginal':.2,'Fundamental hämtad':'2026-10-01'},public)
    assert export_memory(public,[7],private)['tables']['holding_review_baselines']==[]


def test_half_year_links_are_reports_but_not_presentations():
    from report_sources import candidate_report
    assert candidate_report('H1 report (pdf)', '', 'https://issuer.example/report')['is_financial_report']
    assert not candidate_report('H1 presentation', '', 'https://issuer.example/presentation')['is_financial_report']
