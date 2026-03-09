---
name: observatorio-competitor-scraping
description: "Use when working on Samsung price scraping in Sistema_Observatorio: run Santander + selected competitors, validate cash/financing/renting coverage by model+capacity, and keep docs/project_checkpoint.md updated without regressing previously closed competitors."
---

# Observatorio Competitor Scraping

## Overview

This skill standardizes how to advance competitor-by-competitor scraping in `Sistema_Observatorio`.
It enforces a safe loop: run, validate coverage and modalities, prevent regressions on already closed competitors, then update the project checkpoint document.

## When To Use

- User asks to add/improve scraping for one competitor in this project.
- User asks to verify coverage or modality capture from `output/latest_prices.json`.
- User asks to continue the "close one competitor, then move to next" workflow.

Do not use this skill for unrelated scraping projects or generic web scraping outside this repo.

## Workflow

1. Confirm current state
- Read `docs/project_checkpoint.md`.
- Check the latest checkpoint and which competitors are already considered closed.

2. Run target competitor with the smallest useful scope
- Default iterative run should target only the competitor being worked on.
- Expand to regression runs with already closed competitors only before finalizing a closure or when a change can affect shared matching/parsing logic.
- Use script:
```bash
python skills/observatorio-competitor-scraping/scripts/run_competitor.py --competitor "Media Markt"
```

3. Summarize output and verify coverage
- Use:
```bash
python skills/observatorio-competitor-scraping/scripts/summarize_prices.py --json output/latest_prices.json
```
- Validate by `model + capacity` against Santander base.
- Validate modalities expected for that competitor:
  - Santander Boutique: renting + financing + cash (as available on site/API)
  - Amazon: mostly cash
  - Media Markt: cash + financing periodicities when available

4. Decide closure status
- Mark competitor as closed only when coverage and modality extraction are acceptable for the project criteria.
- If anti-bot or site constraints limit one modality, document it explicitly.

5. Update checkpoint context
- Update `docs/project_checkpoint.md` with:
  - command used
  - coverage results
  - notable limitations
  - next competitor in queue

## Commands

Core execution:
```bash
python run_observatorio.py --max-products 8 --competitors "Santander Boutique,Amazon,Media Markt"
```

Single competitor helper:
```bash
python skills/observatorio-competitor-scraping/scripts/run_competitor.py --competitor "Media Markt"
```

Summary helper:
```bash
python skills/observatorio-competitor-scraping/scripts/summarize_prices.py --json output/latest_prices.json
```

## Guardrails

- Do not claim a competitor is closed if coverage is incomplete without documenting why.
- Always run regression checks on already closed competitors before finalizing changes.
- Keep `docs/project_checkpoint.md` as source of truth for handoff between chats.
- Prefer deterministic scripts in `scripts/` over ad-hoc manual analysis when possible.

## References

- `references/workflow.md` contains closure criteria and expected outputs.
