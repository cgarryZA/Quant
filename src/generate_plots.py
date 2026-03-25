"""Generate README plots for all three repos."""
import json
import glob
import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

plt.rcParams.update({
    'figure.facecolor': '#0d1117',
    'axes.facecolor': '#0d1117',
    'text.color': '#cbd5e1',
    'axes.labelcolor': '#cbd5e1',
    'xtick.color': '#8b949e',
    'ytick.color': '#8b949e',
    'axes.edgecolor': '#1f2937',
    'grid.color': '#1f2937',
    'grid.alpha': 0.5,
    'font.family': 'sans-serif',
    'font.size': 11,
})

CASEV = "C:/Users/z00503ku/Documents/case-ev"
PF = "C:/Users/z00503ku/Documents/portfolio-frontier"
QUANT = "C:/Users/z00503ku/Documents/Quant"

# === PLOT 1: EV vs Case Price (Chroma 2) ===
with open(f"{CASEV}/data/precomputed/Chroma_2.json") as f:
    d = json.load(f)

ts = d['timescales']['ALL']
cp = [p[1] for p in ts['case_price']]
ev = [p[1] for p in ts['ev']]
basis = [p[1] for p in ts['basis']]
n = min(len(cp), len(ev))
x = np.linspace(0, 1, n)

fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 7), height_ratios=[2, 1], sharex=True)
fig.subplots_adjust(hspace=0.05)
ax1.plot(x, [c + 2.49 for c in cp[:n]], color='#ef4444', linewidth=1.5, label='Case Price + Key')
ax1.plot(x, ev[:n], color='#38bdf8', linewidth=1.5, label='Expected Value')
ax1.set_ylabel('USD')
ax1.legend(loc='upper left', framealpha=0.3)
ax1.set_title('Chroma 2 Case Price + Key vs Expected Value of Contents', fontsize=14, fontweight='bold', pad=12)
ax1.grid(True)
ax2.fill_between(x, basis[:n], 0, where=[b >= 0 for b in basis[:n]], color='#22c55e', alpha=0.3, label='EV > Price')
ax2.fill_between(x, basis[:n], 0, where=[b < 0 for b in basis[:n]], color='#ef4444', alpha=0.3, label='Price > EV')
ax2.plot(x, basis[:n], color='#a78bfa', linewidth=1)
ax2.axhline(0, color='#8b949e', linewidth=0.5)
ax2.set_ylabel('Basis (EV - Price)')
ax2.set_xlabel('Time (2021-2026)')
ax2.legend(loc='lower left', framealpha=0.3)
ax2.grid(True)
plt.savefig(f"{CASEV}/docs/ev_vs_price.png", dpi=150, bbox_inches='tight')
plt.close()
print("1/4: ev_vs_price.png")

# === PLOT 2: EV/Price ratio bar chart ===
results = []
for f in sorted(glob.glob(f"{CASEV}/data/precomputed/*.json")):
    with open(f) as fh:
        dd = json.load(fh)
    name = os.path.basename(f).replace('.json', '').replace('_', ' ')
    a = dd.get('timescales', {}).get('ALL', {}).get('analysis', {})
    xs = a.get('cross_section', {}).get('metrics', {})
    evp = xs.get('EV / Price (last)')
    if evp is not None:
        results.append((name, evp))

results.sort(key=lambda r: r[1])
fig, ax = plt.subplots(figsize=(12, 8))
names_list = [r[0] for r in results]
evps = [r[1] for r in results]
colors = ['#22c55e' if e > 1 else '#ef4444' if e < 0.5 else '#f59e0b' for e in evps]
ax.barh(range(len(names_list)), evps, color=colors, height=0.7)
ax.axvline(1.0, color='white', linestyle='--', linewidth=1, alpha=0.5, label='EV = Price')
ax.set_yticks(range(len(names_list)))
ax.set_yticklabels(names_list, fontsize=8)
ax.set_xlabel('EV / Price Ratio')
ax.set_title('Which Cases Are Worth Opening? (EV / Price Ratio)', fontsize=14, fontweight='bold', pad=12)
ax.legend(framealpha=0.3)
ax.grid(True, axis='x')
plt.savefig(f"{CASEV}/docs/ev_price_ratio.png", dpi=150, bbox_inches='tight')
plt.close()
print("2/4: ev_price_ratio.png")

# === PLOT 3: Efficient Frontier (two panels) ===
with open(f"{PF}/data/precomputed/frontier.json") as f:
    fd = json.load(f)

frontier = fd['frontier']['long_only']
items = fd['items']
special = fd['special_portfolios']

TYPE_COLORS = {
    'rifle': '#ef4444', 'pistol': '#f59e0b', 'smg': '#22c55e',
    'shotgun': '#a78bfa', 'mg': '#ec4899', 'knife': '#38bdf8',
    'glove': '#f97316', 'other': '#6b7280',
}

# All values now annualized in the JSON
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 7), width_ratios=[1, 1])
fig.subplots_adjust(wspace=0.3)

# LEFT: Frontier zoomed in
frisks = [p['risk'] for p in frontier]
frets = [p['ret'] for p in frontier]

ax1.plot(frisks, frets, color='#38bdf8', linewidth=3, zorder=10, label='Efficient Frontier')

marker_cfg = {
    'equal_weight': ('s', '#6b7280', 'Equal Weight'),
    'min_variance': ('D', '#22c55e', 'Min Variance'),
    'max_sharpe': ('*', '#f59e0b', 'Max Sharpe'),
    'risk_parity': ('P', '#a78bfa', 'Risk Parity'),
}
for key, (marker, color, label) in marker_cfg.items():
    if key in special:
        p = special[key]
        ax1.scatter([p['risk']], [p['ret']], marker=marker, c=color, s=200, zorder=15,
                    edgecolors='white', linewidths=1.5, label=label)
        ax1.annotate(label, (p['risk'], p['ret']), textcoords="offset points",
                     xytext=(10, 8), fontsize=9, fontweight='bold', color=color)

ax1.set_xlabel('Annualized Volatility')
ax1.set_ylabel('Annualized Return')
ax1.set_title('Efficient Frontier (Top 500 by Sharpe)', fontsize=13, fontweight='bold', pad=10)
ax1.legend(loc='lower right', framealpha=0.3, fontsize=9)
ax1.grid(True)

# RIGHT: Full item scatter with frontier overlay
for itype, color in TYPE_COLORS.items():
    xs = [d['vol'] for n, d in items.items() if d['type'] == itype and d['vol'] < 3 and abs(d['mean_ret']) < 2]
    ys = [d['mean_ret'] for n, d in items.items() if d['type'] == itype and d['vol'] < 3 and abs(d['mean_ret']) < 2]
    if xs:
        ax2.scatter(xs, ys, c=color, s=3, alpha=0.25, label=f"{itype} ({len(xs)})")

# Overlay frontier on the scatter
ax2.plot(frisks, frets, color='#38bdf8', linewidth=3, zorder=10, label='Frontier')

ax2.set_xlabel('Annualized Volatility')
ax2.set_ylabel('Annualized Return')
ax2.set_title(f'All {len(items):,} Items — Risk vs Return', fontsize=13, fontweight='bold', pad=10)
ax2.legend(loc='upper right', framealpha=0.3, fontsize=8, ncol=2)
ax2.grid(True)
ax2.set_xlim(0, 3)
ax2.set_ylim(-1.5, 1.5)

plt.savefig(f"{PF}/docs/efficient_frontier.png", dpi=150, bbox_inches='tight')
plt.close()
print("3/4: efficient_frontier.png")

# === PLOT 4: Summary for Quant landing ===
cases_data = []
for f in sorted(glob.glob(f"{CASEV}/data/precomputed/*.json")):
    with open(f) as fh:
        dd = json.load(fh)
    name = os.path.basename(f).replace('.json', '').replace('_', ' ')
    a = dd.get('timescales', {}).get('ALL', {}).get('analysis', {})
    eff = a.get('efficiency', {}).get('metrics', {})
    lead = eff.get('Inference', '?')
    cases_data.append((name, lead))

ev_leads = sum(1 for c in cases_data if 'EV leads' in str(c[1]))
price_leads = sum(1 for c in cases_data if 'Price leads' in str(c[1]))
contemp = len(cases_data) - ev_leads - price_leads

fig, ax = plt.subplots(figsize=(8, 5))
wedges, texts, autotexts = ax.pie(
    [price_leads, ev_leads, contemp],
    labels=['Price Leads EV', 'EV Leads Price', 'Contemporaneous'],
    colors=['#ef4444', '#38bdf8', '#a78bfa'],
    autopct='%1.0f%%', startangle=90,
    textprops={'color': '#cbd5e1', 'fontsize': 13}
)
for t in autotexts:
    t.set_fontweight('bold')
ax.set_title('Who Moves First? Lead-Lag Across 42 Cases', fontsize=14, fontweight='bold', pad=16)
plt.savefig(f"{QUANT}/docs/lead_lag_summary.png", dpi=150, bbox_inches='tight')
plt.close()
print("4/4: lead_lag_summary.png")

# Copy frontier plot to Quant docs too
import shutil
shutil.copy(f"{PF}/docs/efficient_frontier.png", f"{QUANT}/docs/efficient_frontier.png")
shutil.copy(f"{CASEV}/docs/ev_vs_price.png", f"{QUANT}/docs/ev_vs_price.png")

print("\nAll plots done!")
