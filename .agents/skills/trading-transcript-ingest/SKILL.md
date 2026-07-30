---
name: trading-transcript-ingest
description: Standardized skill for ingesting market session transcripts (AHH Access Time, TAW Pro, Weekly Review, TAR Session) into the trading wiki, enforcing strict instrument naming conventions, key level extraction, directional bias, and technical rule capture.
license: MIT
metadata:
  author: AI Trading Team
  version: "1.0.0"
  tags:
    - trading
    - transcript
    - wiki
    - ingest
---

# Transcript Ingest Skill

This skill defines the precise protocol for ingesting market session transcripts (such as *AHH Access Time*, *TAW Pro*, *Weekly Review*, and *TAR Session*) into the personal LLM Trading Wiki (`wiki/`).

---

## 🎯 Trader Persona & Objectives

As a trader, you are actively analyzing transcripts to extract **actionable trading opportunities**.

For every ingested transcript, you must identify and extract:
1. **Instruments Traded**: Forex, Commodities, Indices, Crypto, or Stocks.
2. **Key Levels**: Specific numerical prices, TAT levels, Support/Resistance boundaries, and Wash & Rinse lines (Magenta/Green/Orange).
3. **Direction of Trade**: Long (Bullish), Short (Bearish), or Neutral / Watchlist pending breakout. List them in numbered bullet form.
4. **Multi-Timeframe Context**: Cross-reference lower-timeframe entry setups (e.g. H1 short/long) with higher-timeframe structural boundaries (e.g. H4 or Daily support/resistance for TP targets).
5. **Technical Trading Rules Emphasized**: Any technical trading rules emphasized must be added to the bottom.

---

## 🏷️ Mandatory Instrument & Terminology Conventions

All extracted text and wiki pages MUST strictly follow these normalization rules:

### 1. Instrument Formatting
* **Remove slashes**: Always write forex, crypto, and commodities pairs without slashes (e.g. `EURUSD`, not `EUR/USD`).
* **Crypto Formatting**: All crypto instruments MUST end with `USD` (e.g., `BTCUSD`, `ETHUSD`, `SOLUSD`).
* **Wiki Linking**: Wrap ALL instrument references in double square brackets: e.g., `[[EURUSD]]`, `[[BTCUSD]]`, `[[XAUUSD]]`, `[[USOIL]]`, `[[DXY]]`, `[[HSI]]`, `[[CN50]]`.
* **Spoken Nickname Translation**:
  * "Aussie" -> `AUD` (e.g., "Aussie dollar" -> `[[AUDUSD]]`, "Aussie Cad" -> `[[AUDCAD]]`, "Aussie Yen" -> `[[AUDJPY]]`)
  * "Kiwi" -> `NZD` (e.g., "Kiwi dollar" -> `[[NZDUSD]]`, "Kiwi Cad" -> `[[NZDCAD]]`)
  * "Pound" or "Sterling" -> `GBP` (e.g., "Pound dollar" -> `[[GBPUSD]]`, "Pound Cad" -> `[[GBPCAD]]`, "Pound Aussie" -> `[[GBPAUD]]`)
  * "Yen" -> `JPY` (e.g., "Aussie Yen" -> `[[AUDJPY]]`, "Pound Yen" -> `[[GBPJPY]]`)
  * "Loonie" or "Cad" -> `CAD`
  * "Swissy" -> `CHF`

### 2. Technical Terms, Wash Lines & TAT Prefixes
* **TAT Uniformity**: If spoken text mentions `tad`, `tat`, or `ted`, standardize and refer to it as **TAT**.
* **Wash Lines**:
  * `Day Buy` = Daily Buy Wash Line (Magenta Line).
  * `Day Sell` = Daily Sell Wash Line (Green Line).
  * `Wk Buy` = Weekly Buy Wash Line.
  * `Wk Sell` = Weekly Sell Wash Line.
* **TAT Level Prefixes & Timeframe Suffixes**:
  * `MajD` = Major Daily TAT Level.
  * `MinD` = Minor Daily TAT Level.
  * **First Retracement**: `MajD/MinD <Price> FiRet m15/h1/h4/D/W/M` (15m, 1h, 4h, Daily, Weekly, Monthly).
  * **Support / Resistance**: `MajD/MinD <Price> Sup/Res m15/h1/h4/D/W` (15m, 1h, 4h, Daily, Weekly).
  * **Take Profit**: `TP : <Price>` (e.g. `TP : 1.64055`).
  * **TAT Alerts**: `OptBull` (Optimal Bull), `LBull` (Large Bull), `SBull` (Small Bull), `OptBear` (Optimal Bear), `LBear` (Large Bear), `SBear` (Small Bear).
* **Proprietary Color Coding**:
  * *Magenta lines* = Buy setup wash lines (`Day Buy` / `Wk Buy`).
  * *Green lines* = Sell setup wash lines (`Day Sell` / `Wk Sell`).
  * *Orange lines* = Retracement / turning points.

---

## 📋 Standardized Ingest Document Template

Every transcript ingested produces a source summary page under `wiki/sources/<YYYY-MM-DD-session-title>.md` following this structure:

```markdown
---
date: YYYY-MM-DD
title: "Session Title"
type: transcript
audio_file: raw/recordings/YYYY-MM-DD-session-title.mp3
---

# Session Summary: <Session Title> (<Date>)

## Executive Summary
One-line summary of market sentiment and core focus for the session.

## 📈 Trading Opportunities
1. **[[INSTRUMENT]]**
   - **Direction**: Long / Short / Watch
   - **Key Levels**: Support (e.g. 1.0850), Resistance (e.g. 1.0920), TAT Level (e.g. 1.0880)
   - **Timeframe & Setup**: Detail on H1 entry setup, H4/Daily structural boundaries, Wash & Rinse lines.
2. **[[INSTRUMENT]]**
   ...

## 🔍 Multi-Timeframe Context
- Summary of how lower timeframe setups align with higher timeframe S/R boundaries for Take Profit & Stop Loss management.

## 📐 Technical Trading Rules Emphasized
- Bulleted list of rules, entry criteria (e.g. "1+1 confirmation"), risk management guidelines, and trade management advice discussed in the session.
```

---

## 🔄 Bookkeeping Discipline (Executed on Every Ingest)

1. **Source Summary**: File in `wiki/sources/<YYYY-MM-DD-slug>.md`.
2. **Entity Integration**: Create or update entity pages in `wiki/entities/<instrument-slug>.md` for every instrument mentioned (e.g., `wiki/entities/btcusd.md`, `wiki/entities/eurusd.md`).
3. **Concept Integration**: Update trading methodology concept pages in `wiki/concepts/` (e.g. `tat.md`, `wash-and-rinse.md`, `support-and-resistance.md`) with any new rules or nuances discussed.
4. **Log Operation**: Append entry to `wiki/log.md` via `python scripts/append_log.py --path . --action ingest --title "<Session Title>"`.
5. **Update Index**: Update `wiki/index.md` via `python scripts/update_index.py --path . --category sources --title "<Session Title>" --page-path "wiki/sources/<slug>.md" --summary "<Summary>"`.
6. **Rewrite Hot Cache**: Fully rewrite `wiki/hot.md` with the updated vault state, active knowledge, and open work items.

---

## 🗑️ Post-Ingest Deletion Protocol

- **Deletion Timing**: Deletion from Fireflies.ai cloud MUST only take place AFTER the entire ingestion process (source summary creation, entity/concept page updates, log appending, index updating, and hot cache rewriting) is fully completed and verified.
- **Explicit Permission Required**: NEVER auto-delete transcripts during fetch or ingest. Once ingestion is complete, explicitly ask the user for permission before running the deletion command (e.g. `python3 scripts/fetch_fireflies.py --delete-id <ID>`).
