# Borsify – Relationship Data Builder

`verified_company_relationships.csv` is evidence, not a heuristic lookup table.

## Rule

A row may enter the production registry only when the relationship is explicitly supported by a primary source and has a source date plus verification date. Industry similarity, model inference, search snippets, Wikipedia and unsourced media summaries are not enough.

Preferred source classes are company portfolio/IR pages, annual or interim reports, exchange filings and regulatory filings. Each row keeps the exact source URL and a short evidence label so the relationship can be re-checked later.

## v3.61 seed coverage

The first production seed deliberately focuses on unusually easy-to-verify ownership relationships from Investor AB and Industrivärden. These are useful for exercising the verified read-through pipeline while keeping evidence quality high. The builder is designed to expand later into explicitly disclosed customers, suppliers, commodity dependencies and market exposures.

## Update workflow

1. Research a candidate relationship from a primary source.
2. Add it to a candidate DataFrame/CSV with all required metadata, including `source_kind`.
3. Run `build_relationship_registry(...)`.
4. Review every rejected row and its `rejection_reason`.
5. Run `relationship_registry_health(...)` and re-check stale rows.
6. Only then replace the production registry.

The builder never auto-discovers or auto-promotes relationships. Missing evidence remains missing.
