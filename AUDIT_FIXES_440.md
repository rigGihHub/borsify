# Decision integrity release 4.40.0

The scoring weights are unchanged. Missing evidence, financial arithmetic and
specialist explanations are corrected under a new MODEL_VERSION, independently
of the presentation release number. No previous recommendation is re-scored.

## Decisions and history

- Frozen final and base scores are decoded from the original snapshot on both
  SQLite and Supabase reads. Legacy snapshots without a final score stay excluded.
- Captures and outcomes use insert-once behavior. Cloud payloads use the existing
  JSON schema without requiring unverified production column migrations.
- Analysed finalists and actual displayed decisions are distinct. Displayed
  horizons receive separate immutable capture IDs.
- Prospective results use adjusted close-to-close total return, starting at the
  next trading session's close, in SEK. Benchmark observations must have the
  exact same start/end dates and currency. Price-only index symbols are excluded
  from total-return comparisons. Missing FX/index data stays missing.
- New cases support 1w, 1m, 3m, 6m and 1y follow-up. Older outcome methods are
  preserved and no longer automatically extended with today's price method.
- A scheduled worker evaluates missing due outcomes; it never sends messages.
  Existing GitHub Supabase server credentials are required. Anonymous SQLite
  history is local and is not visible to this cloud worker.

## Evidence and communication

- Missing score inputs do not earn positive percentile/risk evidence. Missing
  position inputs stop sizing; limited confidence caps first position size.
- Negative financial comparison bases and missing YoY quarters do not become
  positive growth percentages. Market cap and cash flow use explicit currency.
- Report text must match the issuer and period. Original publication metadata is
  kept separate from vendor timestamps. Numerical source snippets are frozen,
  but are not described as fully reconciled accounting facts.
- Report Delta requires compatible financial periods. Guidance needs both issuer
  identity and timing. Analyst revision windows must start after the event.
- Verified issuer discovery is initially configured for Investor/Industrivärden;
  exchange source checks work independently. Unknown IR domains remain untrusted.
- AI receives the actual final score, signal, specialist cap and user horizon.
- Specialist investment-company explanations replace generic margin/FCF claims.
- A single current-model calibration view uses benchmark-covered observations
  without letting a missing benchmark switch every other result to raw returns.
- Missing mature outcomes and correlated sectors/holdings are explicitly disclosed.

## Validation limits

Passing software tests does not establish investment performance. Mature forward
outcomes, accounting reconciliation, all-issuer primary-source coverage and a
complete historical delisting universe cannot be manufactured from present data.
The existing ablation/research views remain diagnostic; no engine is promoted,
removed or reweighted on a small sample. Extending the verified issuer registry
requires primary-source checks.

Dependencies are pinned for the tested Linux Python 3.12 and 3.14 environments.
CI runs the full suite, compilation and diff checks on both versions. Streamlit
Cloud auto-deploy is independent of GitHub branch protection; repository checks
alone do not create a mandatory deployment approval gate.

## Release verification

Full regression suite: 1,332 passing tests on Python 3.12 and Python 3.14
with the committed dependency locks. Existing deprecation warnings remain
(1 on 3.12, 21 on 3.14). Compilation, application import and diff checks pass.

Live follow-up: identical original-report checks are reused for at most 15 minutes,
keyed by issuer, country, event payload and calendar date. Changed inputs recheck.
First-time candidate acquisition still depends on upstream response times.

Displayed wait/build decisions also constrain sizing: waiting gives no new position,
and a staged-build decision cannot simultaneously advise a full first position.

Live IR checks also exposed navigation/AGM candidates; these are rejected before
download. A verified IR domain does not guarantee discovery of its latest report.
