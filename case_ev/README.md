# 📦 Case Expected Value vs Case Price Dynamics

### Project Overview

This study investigates **how CS2 case prices and the expected value (EV) of their contents evolve over time**, using **historical daily data from the Pricempire API**.  
The goal is to test whether case prices *lead* or *lag* the expected value of their contents — an analogue to **spot–forward basis** or **NAV deviations** in traditional markets.

---

## Research Question

> Does the expected value of a CS2 case’s contents predict future case price changes, or do case prices anticipate shifts in item values?

---

## Economic Framework

Each CS2 case contains a fixed set of weapon skins across rarity tiers, with probabilistic unboxing odds.  
At any time \( t \), define the **expected value of opening the case** as:

\[
E_{contents}(t) = \sum_{i} P_i \cdot Price_i(t)
\]

where:
- \( P_i \) = probability of receiving skin \( i \) (based on rarity odds)
- \( Price_i(t) \) = market price of skin \( i \) at time \( t \)

The **net expected return of opening** is:

\[
Basis(t) = CasePrice(t) + KeyCost - E_{contents}(t)
\]

- **Positive Basis** → case trades rich vs contents (opening negative EV)  
- **Negative Basis** → contents rich vs case (opening positive EV)

---

## 📊 Data Source and Methodology

### Source
All data comes from **Pricempire.com’s historical API**, which aggregates marketplace listings across 59+ exchanges.  
We use **daily-level historical prices** only — no intraday sampling — due to API budget limits.

### Key data fields
- `item_name` – name of skin or case  
- `timestamp` – daily UTC date  
- `price_usd` – lowest market price for that day  
- `float_bucket` – wear category (Factory New, Minimal Wear, Field-Tested, etc.)  

### Treatment of float/wear data
Each wear tier’s lowest price is treated as its representative price.  
However, we weight these tiers by their **true generation probabilities**, not equally — since Factory New (FN) is far rarer than Battle-Scarred (BS).

#### Valve float-generation model
- Floats are uniformly generated within each skin’s allowed range \([f_{min}, f_{max}]\).  
- The probability of each wear tier is proportional to the **overlap** between that tier’s interval and the skin’s float range:

\[
p_w = \frac{length([f_{min}, f_{max}] \cap bucket_w)}{f_{max} - f_{min}}
\]

#### Default wear buckets
| Tier | Range | Approx. Probability (default \([0.06, 0.80]\)) |
|------|--------|---------------------------------------------|
| Factory New | [0.00, 0.07) | 1.35% |
| Minimal Wear | [0.07, 0.15) | 10.8% |
| Field-Tested | [0.15, 0.38) | 31.1% |
| Well-Worn | [0.38, 0.45) | 9.5% |
| Battle-Scarred | [0.45, 1.00] | 47.3% |

These probabilities form realistic priors for average price calculations when skin-specific float ranges are unavailable.

---

## Computation Steps

### 1. Build Expected Value per Case
For each case:
1. Collect all contained skins and their rarity tiers.  
2. Apply official Valve unboxing probabilities:
   - Mil-Spec: 79.92%
   - Restricted: 15.98%
   - Classified: 3.2%
   - Covert: 0.64%
   - Rare Special (knives/gloves): 0.26%
3. Compute daily EV:
   \[
   E_{contents}(t) = \sum_r p(r) \cdot AvgPrice_r(t)
   \]
   where \( AvgPrice_r(t) \) is the mean price of all skins in tier \( r \) for that day.

### 2. Compute the Case Basis
\[
Basis(t) = CasePrice(t) - E_{contents}(t)
\]

### 3. Analyze Dynamics
- Correlation and cross-correlation between case returns and EV returns.  
- Granger causality tests for lead–lag relationships.  
- Mean reversion of Basis (z-score).  
- Cointegration between \( CasePrice \) and \( E_{contents} \).

---

## Hypotheses

1. **Prime / Active Cases** — Case prices lead EV due to strong speculative demand.  
2. **Discontinued / Rare Cases** — EV leads case prices as rare skins drive slow repricing.  
3. **High Basis Periods** revert as either case or contents adjust.  
4. **Basis persistence** increases with illiquidity (e.g., knife-heavy cases).

---

## Deliverables

- `notebooks/ev_case_relationship.ipynb` – main analysis notebook  
- `data/processed/ev_case_panel.csv` – EV and case prices per day  
- `plots/` – time series, basis distributions, and lead–lag heatmaps  
- `report_ev_vs_case.md` – written summary (this file)

---

## Interpretation Example

- Case A (Prime Drop): Basis positive, stable — speculative premium dominates.  
- Case B (Discontinued): EV surges first, Basis turns negative, then case catches up → content-led regime.  
- These shifts mirror **ETF NAV premia** or **futures–spot bases** in real markets.

---

## Relation to Main Project Suite

This module plugs into the larger **CS2 Quant Research Series**, complementing:

| Core Study | Relation |
|-------------|-----------|
| Market Efficiency | Tests return correlation and lag between assets |
| Liquidity / Price Impact | Connects basis persistence with liquidity metrics |
| Skindex Construction | EV of cases contributes to index basket valuation |
| Portfolio Diversification | Adds a structured CS2-specific pricing anomaly |
| Volatility Regimes | Case–content lead–lag cycles may define micro regimes |

---

## Limitations

- Only daily data (no intraday microstructure).  
- No adjustment for Steam fee asymmetry.  
- EV computed from lowest listing, not volume-weighted average.  
- Approximated wear probabilities use Valve defaults, not empirical distributions.

---

## Future Extensions

- Include **key cost** for net-open EV.  
- Use **1-min live data** for top 5 cases to measure short-run adjustment speed.  
- Extend to **cross-case co-movement** (pairs trading opportunities).  

---

## 🧠 Implementation Architecture

The dashboard is built entirely in JavaScript:

- `data_loader.js` — Expands case JSONs, enumerates all wear/StatTrak variants, and generates deterministic time-series placeholders for prices.  
- `analysis.js` — Coordinates module execution and aggregates results.  
- `analysis/*.js` — Each file represents one analytical layer:
  - `core_stats.js` — correlation, z-scores  
  - `efficiency.js` — lead–lag (Granger-like) analysis  
  - `volatility.js` — rolling vol & mean-reversion half-life  
  - `signals.js` — z-score trading bands  
  - `liquidity.js` — return-volatility proxy for illiquidity  
  - `cross_section.js` — EV/Price relative value  
- `index.html` — Lightweight Bloomberg-style dashboard layout.

These components visualize all key relationships outlined in the study.

---

**Author:** Christian Garry  
**Project:** CS2 Quant Research Series – Pricempire Data Edition  
**Focus:** Digital Asset Market Microstructure and Portfolio Behavior  
