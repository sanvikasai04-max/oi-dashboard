#!/usr/bin/env python3
"""
OI Spike Dashboard Generator
Usage:
    python generate_dashboard.py <input.xlsx> [output.html]

Reads your OI console-output Excel file, parses all data rows,
and generates a self-contained HTML dashboard with 1min / 5min toggle,
spike/drop scanner, and opposite-side confirmation signals.
"""

import sys
import re
import json
import os
import argparse
import pandas as pd
import numpy as np


# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
SPIKE_THRESHOLDS = {
    'd_chg_pct': 5.0,   # Delta %
    'g_chg_pct': 3.0,   # Gamma %
    'p_pct':     3.0,   # Price %
    'v_pct':     50.0,  # Volume %
}

METRIC_LABELS = {
    'd_chg_pct': 'Delta%',
    'g_chg_pct': 'Gamma%',
    'p_pct':     'Price%',
    'v_pct':     'Volume%',
}


# ─────────────────────────────────────────────
# PARSER
# ─────────────────────────────────────────────
DATA_RE = re.compile(
    r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+'   # timestamp
    r'(\d+\.?\d*)\s+'                                   # strike
    r'(\d+\.?\d*)\s+'                                   # spot
    r'(CE|PE)\s+'                                       # side
    r'(-?\d+\.?\d*)\s+'                                 # score
    r'(MODERATE|WEAK|VERY WK|STRONG|VERY STR|n/a)\s+'  # strength
    r'(\d+\.?\d*)\s+'                                   # ltp
    r'(-?\d+\.?\d*)\s+'                                 # delta
    r'(?:([▲▼])\s+)?([0-9\.]+%|n/a)\s+'               # D CHG% (arrow + val)
    r'(\d+\.?\d+)\s+'                                   # gamma
    r'(?:([▲▼])\s+)?([0-9\.]+%|n/a)\s+'               # G CHG%
    r'([\d,]+)\s+'                                      # volume
    r'(?:([▲▼])\s+)?(-?[\d\.]+%|n/a|inf%)\s+'         # V%
    r'(\d+\.?\d*)\s+'                                   # price
    r'(?:([▲▼])\s+)?(-?[\d\.]+%|n/a)\s+'              # P%
    r'(\d+\.?\d+%)'                                     # IV
)


def signed(arrow, val_str):
    if val_str in ('n/a', 'inf%', None):
        return None
    v = float(val_str.replace('%', ''))
    return -v if arrow == '▼' else v


def parse_xlsx(path: str) -> pd.DataFrame:
    print(f"  Reading: {path}")
    df_raw = pd.read_excel(path)
    col = df_raw.columns[0]  # always first column

    rows = []
    for _, row in df_raw.iterrows():
        line = str(row[col])
        if line == 'nan':
            continue
        m = DATA_RE.search(line)
        if not m:
            continue
        rows.append({
            'timestamp':  pd.to_datetime(m.group(1)),
            'strike':     float(m.group(2)),
            'spot':       float(m.group(3)),
            'side':       m.group(4),
            'score':      float(m.group(5)),
            'strength':   m.group(6).strip(),
            'ltp':        float(m.group(7)),
            'delta':      float(m.group(8)),
            'd_chg_pct':  signed(m.group(9),  m.group(10)),
            'gamma':      float(m.group(11)),
            'g_chg_pct':  signed(m.group(12), m.group(13)),
            'volume':     int(m.group(14).replace(',', '')),
            'v_pct':      signed(m.group(15), m.group(16)),
            'price':      float(m.group(17)),
            'p_pct':      signed(m.group(18), m.group(19)),
            'iv':         m.group(20),
        })

    data = pd.DataFrame(rows)
    print(f"  Parsed {len(data):,} rows | "
          f"{data['timestamp'].nunique()} timestamps | "
          f"{data['strike'].nunique()} strikes")
    return data


# ─────────────────────────────────────────────
# AGGREGATION
# ─────────────────────────────────────────────
def resample_ts(data: pd.DataFrame, freq: str) -> list:
    """Resample to freq (e.g. '1min' or '5min').
    Returns list of dicts with max CE / min PE per window."""
    df2 = data.set_index('timestamp')
    results = []
    for ts, grp in df2.groupby(pd.Grouper(freq=freq)):
        if grp.empty:
            continue
        ce = grp[grp['side'] == 'CE']
        pe = grp[grp['side'] == 'PE']

        def mx(s):
            d = s.dropna()
            return round(float(d.max()), 3) if not d.empty else 0.0

        def mn(s):
            d = s.dropna()
            return round(float(d.min()), 3) if not d.empty else 0.0

        results.append({
            'ts':   ts.strftime('%H:%M'),
            'ce_d': mx(ce['d_chg_pct']), 'pe_d': mn(pe['d_chg_pct']),
            'ce_g': mx(ce['g_chg_pct']), 'pe_g': mn(pe['g_chg_pct']),
            'ce_p': mx(ce['p_pct']),     'pe_p': mn(pe['p_pct']),
            'ce_v': mx(ce['v_pct']),     'pe_v': mn(pe['v_pct']),
            'spot': round(float(grp['spot'].iloc[-1]), 2),
        })
    return results


# ─────────────────────────────────────────────
# EVENTS (spike / drop rows)
# ─────────────────────────────────────────────
def build_events(data: pd.DataFrame) -> list:
    events = []
    for metric, thr in SPIKE_THRESHOLDS.items():
        label = METRIC_LABELS[metric]
        mask = data[metric].notna() & (data[metric].abs() >= thr)
        for _, r in data[mask].iterrows():
            val = r[metric]
            events.append({
                'ts':       r['timestamp'].strftime('%H:%M'),
                'strike':   int(r['strike']),
                'side':     r['side'],
                'metric':   label,
                'val':      round(val, 2),
                'type':     'spike' if val > 0 else 'drop',
                'spot':     round(r['spot'], 2),
                'strength': r['strength'],
                'score':    round(r['score'], 1),
            })
    # sort by absolute magnitude
    events.sort(key=lambda x: abs(x['val']), reverse=True)
    return events


# ─────────────────────────────────────────────
# OPPOSITE-SIDE CONFIRMATIONS
# ─────────────────────────────────────────────
def build_opposites(data: pd.DataFrame) -> list:
    confs = []
    for ts, grp in data.groupby('timestamp'):
        ce = grp[grp['side'] == 'CE'].set_index('strike')
        pe = grp[grp['side'] == 'PE'].set_index('strike')
        common = ce.index.intersection(pe.index)

        for metric, thr in SPIKE_THRESHOLDS.items():
            label = METRIC_LABELS[metric]
            for stk in common:
                ce_val = ce.loc[stk, metric] if pd.notna(ce.loc[stk, metric]) else None
                pe_val = pe.loc[stk, metric] if pd.notna(pe.loc[stk, metric]) else None
                if ce_val is None or pe_val is None:
                    continue

                # CE spike + PE drop
                if ce_val >= thr and pe_val <= -thr:
                    confs.append({
                        'ts':      ts.strftime('%H:%M'),
                        'strike':  int(stk),
                        'metric':  label,
                        'ce':      round(ce_val, 2),
                        'pe':      round(pe_val, 2),
                        'pattern': 'CE_spike_PE_drop',
                        'spot':    round(grp['spot'].iloc[0], 2),
                    })
                # PE spike + CE drop
                elif pe_val >= thr and ce_val <= -thr:
                    confs.append({
                        'ts':      ts.strftime('%H:%M'),
                        'strike':  int(stk),
                        'metric':  label,
                        'ce':      round(ce_val, 2),
                        'pe':      round(pe_val, 2),
                        'pattern': 'PE_spike_CE_drop',
                        'spot':    round(grp['spot'].iloc[0], 2),
                    })
    return confs


# ─────────────────────────────────────────────
# SUMMARY STATS
# ─────────────────────────────────────────────
def build_summary(data: pd.DataFrame, events: list, confs: list) -> dict:
    date_str = data['timestamp'].iloc[0].strftime('%Y-%m-%d')
    spot_open  = round(float(data['spot'].iloc[0]), 2)
    spot_close = round(float(data['spot'].iloc[-1]), 2)
    spot_high  = round(float(data['spot'].max()), 2)
    spot_low   = round(float(data['spot'].min()), 2)
    return {
        'date':        date_str,
        'spot_open':   spot_open,
        'spot_close':  spot_close,
        'spot_high':   spot_high,
        'spot_low':    spot_low,
        'total_rows':  len(data),
        'timestamps':  int(data['timestamp'].nunique()),
        'strikes':     sorted([int(s) for s in data['strike'].unique()]),
        'total_events': len(events),
        'total_spikes': len([e for e in events if e['type'] == 'spike']),
        'total_drops':  len([e for e in events if e['type'] == 'drop']),
        'total_confs':  len(confs),
    }


# ─────────────────────────────────────────────
# HTML TEMPLATE
# ─────────────────────────────────────────────
HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>OI Spike Dashboard — {DATE}</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
:root {
  --bg: #080a0f;
  --panel: #0f1117;
  --panel2: #13161e;
  --border: #1c2030;
  --border2: #252b3b;
  --text: #dde3f0;
  --muted: #4a5568;
  --muted2: #64748b;
  --ce: #38bdf8;
  --pe: #f472b6;
  --spike: #34d399;
  --drop: #f87171;
  --opp: #fbbf24;
  --accent: #7c3aed;
  --accent2: #6d28d9;
  --pill: #1e2535;
}
*{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%;overflow:hidden}
body{background:var(--bg);color:var(--text);font-family:'JetBrains Mono',Consolas,'Courier New',monospace;font-size:12px;display:flex;flex-direction:column}

/* ── HEADER ── */
.hdr{
  background:var(--panel);border-bottom:1px solid var(--border);
  padding:10px 20px;display:flex;align-items:center;gap:20px;flex-shrink:0;
}
.hdr-title{font-size:15px;font-weight:800;letter-spacing:3px;color:var(--ce)}
.hdr-date{color:var(--muted2);font-size:11px;letter-spacing:1px}
.hdr-spot{margin-left:auto;text-align:right}
.hdr-spot .val{font-size:18px;font-weight:700;color:var(--opp);letter-spacing:1px}
.hdr-spot .lbl{font-size:10px;color:var(--muted);letter-spacing:2px}
.hdr-range{font-size:11px;color:var(--muted2);margin-top:1px}

/* ── TOOLBAR ── */
.toolbar{
  background:var(--panel);border-bottom:1px solid var(--border);
  padding:8px 20px;display:flex;align-items:center;gap:8px;flex-wrap:wrap;flex-shrink:0;
}
.tab-btn{
  padding:5px 14px;border-radius:4px;border:1px solid var(--border2);
  background:transparent;color:var(--muted2);font-size:11px;font-weight:700;
  font-family:inherit;cursor:pointer;letter-spacing:1px;transition:all .15s;
}
.tab-btn:hover{color:var(--text);border-color:var(--muted2)}
.tab-btn.active{background:var(--accent);color:#fff;border-color:var(--accent)}

.sep{width:1px;height:20px;background:var(--border2);margin:0 4px}

.metric-btn{
  padding:4px 12px;border-radius:4px;border:1px solid var(--border2);
  background:transparent;color:var(--muted2);font-size:11px;font-weight:700;
  font-family:inherit;cursor:pointer;letter-spacing:1px;transition:all .15s;
}
.metric-btn:hover{color:var(--text)}
.metric-btn.active.D{background:rgba(56,189,248,.2);color:var(--ce);border-color:var(--ce)}
.metric-btn.active.G{background:rgba(52,211,153,.2);color:var(--spike);border-color:var(--spike)}
.metric-btn.active.P{background:rgba(251,191,36,.2);color:var(--opp);border-color:var(--opp)}
.metric-btn.active.V{background:rgba(244,114,182,.2);color:var(--pe);border-color:var(--pe)}

.res-btn{
  padding:4px 10px;border-radius:4px;border:1px solid var(--border2);
  background:transparent;color:var(--muted2);font-size:11px;font-weight:700;
  font-family:inherit;cursor:pointer;letter-spacing:1px;transition:all .15s;margin-left:auto;
}
.res-btn:hover{color:var(--text)}
.res-btn.active{background:var(--panel2);color:var(--text);border-color:var(--border2)}

.kbd-hint{font-size:10px;color:var(--muted);letter-spacing:.5px;margin-left:4px}

/* ── MAIN LAYOUT ── */
.main{display:flex;flex:1;overflow:hidden;gap:0}

/* ── LEFT SIDEBAR ── */
.sidebar{
  width:260px;flex-shrink:0;background:var(--panel);
  border-right:1px solid var(--border);display:flex;flex-direction:column;overflow:hidden;
}
.sb-section{border-bottom:1px solid var(--border);flex-shrink:0}
.sb-head{
  padding:8px 12px;font-size:10px;font-weight:700;
  color:var(--muted2);letter-spacing:2px;text-transform:uppercase;
  background:var(--panel2);display:flex;justify-content:space-between;align-items:center;
}
.sb-stat{padding:8px 12px;display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--border)}
.sb-stat .lbl{font-size:10px;color:var(--muted2)}
.sb-stat .v{font-size:13px;font-weight:700}
.sb-filter{padding:6px 8px;display:flex;flex-direction:column;gap:4px}
.flt-row{display:flex;gap:4px;flex-wrap:wrap}
.flt-btn{
  padding:3px 9px;border-radius:3px;border:1px solid var(--border2);
  background:transparent;color:var(--muted2);font-size:10px;font-weight:700;
  font-family:inherit;cursor:pointer;letter-spacing:.5px;transition:all .12s;
}
.flt-btn:hover{color:var(--text);border-color:var(--muted)}
.flt-btn.active{background:var(--accent);color:#fff;border-color:var(--accent)}
.flt-btn.ce.active{background:rgba(56,189,248,.2);color:var(--ce);border-color:var(--ce)}
.flt-btn.pe.active{background:rgba(244,114,182,.2);color:var(--pe);border-color:var(--pe)}
.flt-btn.spk.active{background:rgba(52,211,153,.2);color:var(--spike);border-color:var(--spike)}
.flt-btn.drp.active{background:rgba(248,113,113,.2);color:var(--drop);border-color:var(--drop)}
.flt-btn.bull.active{background:rgba(52,211,153,.15);color:var(--spike);border-color:var(--spike)}
.flt-btn.bear.active{background:rgba(248,113,113,.15);color:var(--drop);border-color:var(--drop)}

.sb-search{
  width:100%;background:var(--bg);border:1px solid var(--border2);
  border-radius:3px;color:var(--text);font-family:inherit;
  font-size:11px;padding:5px 8px;margin-top:4px;outline:none;
}
.sb-search:focus{border-color:var(--accent)}
.sb-table-wrap{flex:1;overflow-y:auto}
.sb-table-wrap::-webkit-scrollbar{width:4px}
.sb-table-wrap::-webkit-scrollbar-track{background:var(--panel)}
.sb-table-wrap::-webkit-scrollbar-thumb{background:var(--border2);border-radius:2px}

.event-row{
  display:grid;grid-template-columns:38px 54px 28px 1fr 52px;
  gap:0;padding:5px 10px;border-bottom:1px solid var(--border);
  cursor:pointer;transition:background .1s;align-items:center;
}
.event-row:hover{background:rgba(124,58,237,.1)}
.event-row.selected{background:rgba(124,58,237,.18)}
.event-row .e-ts{font-size:10px;color:var(--muted2)}
.event-row .e-stk{font-size:11px;font-weight:700;color:var(--text)}
.event-row .e-side{font-size:9px;font-weight:700;padding:1px 4px;border-radius:2px}
.e-side.CE{background:rgba(56,189,248,.15);color:var(--ce)}
.e-side.PE{background:rgba(244,114,182,.15);color:var(--pe)}
.event-row .e-metric{font-size:10px;color:var(--muted2)}
.event-row .e-val{font-size:11px;font-weight:700;text-align:right}
.e-val.pos{color:var(--spike)}
.e-val.neg{color:var(--drop)}

.opp-row-sb{
  display:grid;grid-template-columns:38px 54px 1fr 50px 50px;
  gap:0;padding:5px 10px;border-bottom:1px solid var(--border);
  cursor:pointer;transition:background .1s;align-items:center;
}
.opp-row-sb:hover{background:rgba(251,191,36,.07)}
.opp-row-sb .e-ts{font-size:10px;color:var(--muted2)}
.opp-row-sb .e-stk{font-size:11px;font-weight:700}
.opp-row-sb .e-metric{font-size:10px;color:var(--muted2)}
.opp-row-sb .e-ce{font-size:11px;font-weight:700;text-align:right}
.opp-row-sb .e-pe{font-size:11px;font-weight:700;text-align:right}

.count-lbl{font-size:10px;color:var(--muted2);padding:4px 10px}

/* ── CHARTS AREA ── */
.charts-area{flex:1;display:flex;flex-direction:column;overflow:hidden;padding:12px;gap:10px}
.charts-area.hidden{display:none}
.chart-row{display:grid;grid-template-columns:1fr 1fr;gap:10px;flex:1;min-height:0}
.chart-box{
  background:var(--panel);border:1px solid var(--border);
  border-radius:5px;padding:10px 14px;display:flex;flex-direction:column;min-height:0;
}
.chart-box.full{grid-column:1/-1}
.ch-title{font-size:10px;font-weight:700;letter-spacing:1.5px;color:var(--muted2);
  text-transform:uppercase;margin-bottom:6px;flex-shrink:0;display:flex;justify-content:space-between}
.ch-title .ch-thr{font-size:9px;color:var(--muted);letter-spacing:0}
canvas{flex:1;min-height:0}

/* ── SHORTCUTS PAGE ── */
.shortcuts-area{flex:1;overflow-y:auto;padding:20px 24px}
.shortcuts-area.hidden{display:none}
.sc-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px}
.sc-card{background:var(--panel);border:1px solid var(--border);border-radius:5px;padding:14px}
.sc-card h3{font-size:11px;color:var(--opp);letter-spacing:1.5px;margin-bottom:10px;font-weight:800}
.sc-card p{font-size:11px;color:var(--muted2);line-height:1.9}
.sc-card .cmd{
  display:block;background:var(--bg);border:1px solid var(--border);
  border-left:3px solid var(--accent);padding:5px 9px;
  margin:5px 0;border-radius:3px;color:var(--ce);font-size:11px;
}
.k{display:inline-block;background:var(--border2);border:1px solid var(--border2);
  border-radius:3px;padding:1px 5px;font-size:10px;color:var(--opp)}

/* ── SCROLLBAR ── */
::-webkit-scrollbar{width:4px;height:4px}
::-webkit-scrollbar-track{background:var(--panel)}
::-webkit-scrollbar-thumb{background:var(--border2);border-radius:2px}
</style>
</head>
<body>

<!-- HEADER -->
<div class="hdr">
  <div>
    <div class="hdr-title">⚡ OI SPIKE DASHBOARD</div>
    <div class="hdr-date">NIFTY OPTIONS · {DATE} · 1-MIN CANDLES</div>
  </div>
  <div style="display:flex;gap:20px;align-items:center">
    <div style="font-size:11px;color:var(--muted2);line-height:1.8">
      <div>Strikes: <span style="color:var(--text)">{STRIKES}</span></div>
      <div>Rows: <span style="color:var(--text)">{TOTAL_ROWS}</span></div>
    </div>
    <div class="hdr-spot">
      <div class="val" id="spotDisp">—</div>
      <div class="lbl">SPOT</div>
      <div class="hdr-range" id="rangeDisp">—</div>
    </div>
  </div>
</div>

<!-- TOOLBAR -->
<div class="toolbar">
  <button class="tab-btn active" onclick="showPage('charts')" id="tb-charts">📈 CHARTS</button>
  <button class="tab-btn" onclick="showPage('shortcuts')" id="tb-shortcuts">⌨ SHORTCUTS</button>

  <div class="sep"></div>

  <button class="metric-btn D active" onclick="setMetric('D')" id="mb-D">D Delta</button>
  <button class="metric-btn G" onclick="setMetric('G')" id="mb-G">G Gamma</button>
  <button class="metric-btn P" onclick="setMetric('P')" id="mb-P">P Price</button>
  <button class="metric-btn V" onclick="setMetric('V')" id="mb-V">V Volume</button>

  <div class="sep"></div>

  <button class="res-btn active" onclick="setRes('1min')" id="rb-1min">1 MIN</button>
  <button class="res-btn" onclick="setRes('5min')" id="rb-5min">5 MIN</button>

  <span class="kbd-hint">| keyboard: D G P V · 1 5 · E O S X C A B R</span>
</div>

<!-- MAIN -->
<div class="main">

  <!-- SIDEBAR -->
  <div class="sidebar">
    <!-- Stats -->
    <div class="sb-section">
      <div class="sb-head">Session Stats</div>
      <div class="sb-stat"><span class="lbl">Spikes</span><span class="v" style="color:var(--spike)" id="stat-spikes">—</span></div>
      <div class="sb-stat"><span class="lbl">Drops</span><span class="v" style="color:var(--drop)" id="stat-drops">—</span></div>
      <div class="sb-stat"><span class="lbl">Opp Confirms</span><span class="v" style="color:var(--opp)" id="stat-confs">—</span></div>
    </div>

    <!-- Filters -->
    <div class="sb-section sb-filter">
      <div class="sb-head" style="padding:0 0 4px 0;background:transparent;font-size:10px">VIEW</div>
      <div class="flt-row">
        <button class="flt-btn active" onclick="setSbView('events',this)" id="v-events">Events</button>
        <button class="flt-btn" onclick="setSbView('opp',this)" id="v-opp">Opp</button>
      </div>
      <div class="flt-row" id="evt-filters">
        <button class="flt-btn spk active" onclick="toggleEvtFilter('spike',this)">⬆ Spike</button>
        <button class="flt-btn drp active" onclick="toggleEvtFilter('drop',this)">⬇ Drop</button>
        <button class="flt-btn ce active" onclick="toggleEvtFilter('CE',this)">CE</button>
        <button class="flt-btn pe active" onclick="toggleEvtFilter('PE',this)">PE</button>
        <button class="flt-btn active" onclick="toggleEvtFilter('Delta%',this)">Δ</button>
        <button class="flt-btn active" onclick="toggleEvtFilter('Gamma%',this)">Γ</button>
        <button class="flt-btn active" onclick="toggleEvtFilter('Price%',this)">P</button>
        <button class="flt-btn active" onclick="toggleEvtFilter('Volume%',this)">V</button>
      </div>
      <div class="flt-row" id="opp-filters" style="display:none">
        <button class="flt-btn bull active" onclick="setOppFilter('all',this)">All</button>
        <button class="flt-btn bull" onclick="setOppFilter('bull',this)">🟢 Bull</button>
        <button class="flt-btn bear" onclick="setOppFilter('bear',this)">🔴 Bear</button>
        <button class="flt-btn active" onclick="setOppFilterMetric('Delta%',this)">Δ</button>
        <button class="flt-btn active" onclick="setOppFilterMetric('Gamma%',this)">Γ</button>
        <button class="flt-btn active" onclick="setOppFilterMetric('Price%',this)">P</button>
        <button class="flt-btn active" onclick="setOppFilterMetric('Volume%',this)">V</button>
      </div>
      <input class="sb-search" id="sbSearch" placeholder="Search time / strike …" oninput="renderSidebar()">
    </div>

    <!-- List -->
    <div class="sb-table-wrap">
      <div id="sbList"></div>
      <div class="count-lbl" id="sbCount"></div>
    </div>
  </div>

  <!-- CHARTS -->
  <div class="charts-area" id="chartsArea">
    <div class="chart-row">
      <div class="chart-box">
        <div class="ch-title">
          <span>CE <span id="ce-lbl">Delta%</span></span>
          <span class="ch-thr" id="ce-thr">thr ±5%</span>
        </div>
        <canvas id="ceChart"></canvas>
      </div>
      <div class="chart-box">
        <div class="ch-title">
          <span>PE <span id="pe-lbl">Delta%</span></span>
          <span class="ch-thr" id="pe-thr">thr ±5%</span>
        </div>
        <canvas id="peChart"></canvas>
      </div>
    </div>
    <div class="chart-row" style="flex:0.6">
      <div class="chart-box full">
        <div class="ch-title">
          CE vs PE overlay — <span id="both-lbl">Delta%</span>
          <span style="color:var(--muted2);font-weight:400"><span style="color:var(--ce)">■</span> CE &nbsp;<span style="color:var(--pe)">■</span> PE</span>
        </div>
        <canvas id="bothChart"></canvas>
      </div>
    </div>
  </div>

  <!-- SHORTCUTS -->
  <div class="shortcuts-area hidden" id="shortcutsArea">
    <div class="sc-grid">
      <div class="sc-card">
        <h3>⌨ METRIC KEYS</h3>
        <code class="cmd"><span class="k">D</span>  Delta %  — option delta change/candle</code>
        <code class="cmd"><span class="k">G</span>  Gamma %  — gamma change/candle</code>
        <code class="cmd"><span class="k">P</span>  Price %  — LTP % change/candle</code>
        <code class="cmd"><span class="k">V</span>  Volume % — volume % change/candle</code>
      </div>
      <div class="sc-card">
        <h3>🕐 RESOLUTION KEYS</h3>
        <code class="cmd"><span class="k">1</span>  1-minute bars — raw candle data</code>
        <code class="cmd"><span class="k">5</span>  5-minute bars — max/min aggregated</code>
        <p style="margin-top:6px">5-min takes the max CE spike and min PE drop within each 5-min window — good for cutting noise.</p>
      </div>
      <div class="sc-card">
        <h3>📋 VIEW KEYS</h3>
        <code class="cmd"><span class="k">E</span>  Show Events sidebar</code>
        <code class="cmd"><span class="k">S</span>  Spikes only</code>
        <code class="cmd"><span class="k">X</span>  Drops only</code>
        <code class="cmd"><span class="k">C</span>  CE side only</code>
        <code class="cmd"><span class="k">A</span>  PE side only</code>
        <code class="cmd"><span class="k">O</span>  Opposite confirmations</code>
        <code class="cmd"><span class="k">B</span>  Bullish confirms (CE↑ PE↓)</code>
        <code class="cmd"><span class="k">R</span>  Bearish confirms (PE↑ CE↓)</code>
      </div>
      <div class="sc-card">
        <h3>📖 READING SIGNALS</h3>
        <p>
          <span style="color:var(--spike)">▲ CE spike</span> — calls gaining, bullish pressure<br>
          <span style="color:var(--drop)">▼ CE drop</span> — calls unwinding, bearish pressure<br>
          <span style="color:var(--spike)">▲ PE spike</span> — puts gaining, bearish pressure<br>
          <span style="color:var(--drop)">▼ PE drop</span> — puts unwinding, bullish pressure<br><br>
          <span style="color:var(--opp)">CE↑ + PE↓ same strike = BULLISH confirm</span><br>
          <span style="color:var(--opp)">PE↑ + CE↓ same strike = BEARISH confirm</span>
        </p>
      </div>
      <div class="sc-card">
        <h3>⚙ SPIKE THRESHOLDS</h3>
        <code class="cmd">Delta %   ≥ ±5.0 %</code>
        <code class="cmd">Gamma %   ≥ ±3.0 %</code>
        <code class="cmd">Price %   ≥ ±3.0 %</code>
        <code class="cmd">Volume %  ≥ ±50 %</code>
        <p style="margin-top:6px">Bars highlighted bright when they cross these thresholds.</p>
      </div>
      <div class="sc-card">
        <h3>🚀 FAST WORKFLOW</h3>
        <p>
          1. Press <span class="k">O</span> → check opposite confirms<br>
          2. Filter <span class="k">B</span> bullish / <span class="k">R</span> bearish<br>
          3. Press <span class="k">D</span> → see Delta chart at that time<br>
          4. Press <span class="k">V</span> → confirm with volume<br>
          5. Toggle <span class="k">5</span> → 5-min to see macro trend<br>
          6. Toggle <span class="k">1</span> → back to 1-min for entry timing
        </p>
      </div>
    </div>
  </div>

</div><!-- .main -->

<script>
// ── DATA ──
const DATA = __DATA__;

// ── STATE ──
let metric   = 'D';
let res      = '1min';
let page     = 'charts';
let sbView   = 'events';
let evtActiveFilters = new Set(['spike','drop','CE','PE','Delta%','Gamma%','Price%','Volume%']);
let oppFilter   = 'all';
let oppMetrics  = new Set(['Delta%','Gamma%','Price%','Volume%']);
let sbSearch    = '';

const METRIC_MAP = {
  D: { ce:'ce_d', pe:'pe_d', label:'Delta%',  thr:5,  color:'var(--ce)'  },
  G: { ce:'ce_g', pe:'pe_g', label:'Gamma%',  thr:3,  color:'var(--spike)'},
  P: { ce:'ce_p', pe:'pe_p', label:'Price%',  thr:3,  color:'var(--opp)' },
  V: { ce:'ce_v', pe:'pe_v', label:'Volume%', thr:50, color:'var(--pe)'  },
};

// ── CHARTS ──
let ceChart, peChart, bothChart;

function tsData() { return res === '1min' ? DATA.ts1 : DATA.ts5; }

function buildChartData(key, posColor, negColor, thr) {
  const ts = tsData();
  return {
    labels: ts.map(r => r.ts),
    data:   ts.map(r => r[key]),
    bgs:    ts.map(r => {
      const v = r[key];
      if (Math.abs(v) >= thr) return v > 0 ? posColor : negColor;
      return v > 0 ? posColor.replace(')', ',0.35)').replace('rgb','rgba') : negColor.replace(')', ',0.35)').replace('rgb','rgba');
    })
  };
}

const commonOpts = (yLabel) => ({
  responsive: true,
  maintainAspectRatio: false,
  animation: { duration: 250 },
  plugins: {
    legend: { display: false },
    tooltip: {
      backgroundColor: '#0f1117',
      borderColor: '#1c2030', borderWidth: 1,
      titleColor: '#dde3f0', bodyColor: '#94a3b8',
      callbacks: {
        label: ctx => {
          const v = ctx.raw;
          return ` ${v >= 0 ? '▲' : '▼'} ${Math.abs(v).toFixed(2)}%`;
        }
      }
    }
  },
  scales: {
    x: {
      grid: { color: '#1c2030' },
      ticks: { color: '#3d4a5e', maxTicksLimit: res === '5min' ? 20 : 14, font: { size: 9 } }
    },
    y: {
      grid: { color: '#1c2030' },
      ticks: { color: '#3d4a5e', font: { size: 9 }, callback: v => v + '%' }
    }
  }
});

function renderCharts() {
  const m = METRIC_MAP[metric];
  const ts = tsData();
  const labels = ts.map(r => r.ts);
  const ceVals = ts.map(r => r[m.ce]);
  const peVals = ts.map(r => r[m.pe]);
  const thr = m.thr;

  const ceColors = ceVals.map(v =>
    Math.abs(v) >= thr ? (v >= 0 ? '#38bdf8' : '#f87171')
                       : (v >= 0 ? 'rgba(56,189,248,0.3)' : 'rgba(248,113,113,0.3)')
  );
  const peColors = peVals.map(v =>
    Math.abs(v) >= thr ? (v >= 0 ? '#f472b6' : '#f87171')
                       : (v >= 0 ? 'rgba(244,114,182,0.3)' : 'rgba(248,113,113,0.3)')
  );

  if (ceChart) ceChart.destroy();
  ceChart = new Chart(document.getElementById('ceChart'), {
    type: 'bar',
    data: { labels, datasets: [{ data: ceVals, backgroundColor: ceColors, borderRadius: 2, borderWidth: 0 }] },
    options: commonOpts('CE')
  });

  if (peChart) peChart.destroy();
  peChart = new Chart(document.getElementById('peChart'), {
    type: 'bar',
    data: { labels, datasets: [{ data: peVals, backgroundColor: peColors, borderRadius: 2, borderWidth: 0 }] },
    options: commonOpts('PE')
  });

  if (bothChart) bothChart.destroy();
  bothChart = new Chart(document.getElementById('bothChart'), {
    type: 'line',
    data: {
      labels,
      datasets: [
        { label: 'CE', data: ceVals, borderColor: '#38bdf8', backgroundColor: 'rgba(56,189,248,0.05)',
          borderWidth: 1.5, pointRadius: 0, tension: 0.25, fill: false },
        { label: 'PE', data: peVals, borderColor: '#f472b6', backgroundColor: 'rgba(244,114,182,0.05)',
          borderWidth: 1.5, pointRadius: 0, tension: 0.25, fill: false }
      ]
    },
    options: {
      ...commonOpts('both'),
      plugins: {
        ...commonOpts('both').plugins,
        legend: { display: false }
      }
    }
  });

  // update labels
  document.getElementById('ce-lbl').textContent = m.label;
  document.getElementById('pe-lbl').textContent = m.label;
  document.getElementById('both-lbl').textContent = m.label;
  document.getElementById('ce-thr').textContent = `thr ±${m.thr}%`;
  document.getElementById('pe-thr').textContent = `thr ±${m.thr}%`;
}

// ── HEADER ──
function renderHeader() {
  const ts = tsData();
  const last = ts[ts.length - 1];
  if (!last) return;
  document.getElementById('spotDisp').textContent =
    last.spot.toLocaleString('en-IN', { minimumFractionDigits: 2 });
  const spots = ts.map(r => r.spot).filter(Boolean);
  const hi = Math.max(...spots), lo = Math.min(...spots);
  document.getElementById('rangeDisp').textContent =
    `H ${hi.toLocaleString('en-IN')} · L ${lo.toLocaleString('en-IN')}`;
}

// ── SIDEBAR ──
function getFilteredEvents() {
  const search = document.getElementById('sbSearch').value.toLowerCase();
  return DATA.events.filter(e => {
    if (!evtActiveFilters.has(e.type))   return false;
    if (!evtActiveFilters.has(e.side))   return false;
    if (!evtActiveFilters.has(e.metric)) return false;
    if (search && !e.ts.includes(search) && !String(e.strike).includes(search)) return false;
    return true;
  });
}

function getFilteredOpp() {
  const search = document.getElementById('sbSearch').value.toLowerCase();
  return DATA.opp.filter(o => {
    if (oppFilter === 'bull' && o.pattern !== 'CE_spike_PE_drop') return false;
    if (oppFilter === 'bear' && o.pattern !== 'PE_spike_CE_drop') return false;
    if (!oppMetrics.has(o.metric)) return false;
    if (search && !o.ts.includes(search) && !String(o.strike).includes(search)) return false;
    return true;
  });
}

function renderSidebar() {
  // stats
  document.getElementById('stat-spikes').textContent = DATA.summary.total_spikes;
  document.getElementById('stat-drops').textContent  = DATA.summary.total_drops;
  document.getElementById('stat-confs').textContent  = DATA.summary.total_confs;

  if (sbView === 'events') {
    const evts = getFilteredEvents();
    const html = evts.slice(0, 400).map(e => {
      const cls = e.val > 0 ? 'pos' : 'neg';
      const sign = e.val > 0 ? '+' : '';
      return `<div class="event-row">
        <span class="e-ts">${e.ts}</span>
        <span class="e-stk">${e.strike}</span>
        <span class="e-side ${e.side}">${e.side}</span>
        <span class="e-metric">${e.metric}</span>
        <span class="e-val ${cls}">${sign}${e.val.toFixed(1)}%</span>
      </div>`;
    }).join('');
    document.getElementById('sbList').innerHTML = html;
    document.getElementById('sbCount').textContent = `${evts.length} events`;
  } else {
    const opps = getFilteredOpp();
    const html = opps.slice(0, 400).map(o => {
      const isBull = o.pattern === 'CE_spike_PE_drop';
      const stkColor = isBull ? 'var(--spike)' : 'var(--drop)';
      const ceC = o.ce > 0 ? 'pos' : 'neg';
      const peC = o.pe > 0 ? 'pos' : 'neg';
      return `<div class="opp-row-sb">
        <span class="e-ts">${o.ts}</span>
        <span class="e-stk" style="color:${stkColor}">${o.strike}</span>
        <span class="e-metric">${o.metric}</span>
        <span class="e-ce e-val ${ceC}">${o.ce > 0 ? '+' : ''}${o.ce.toFixed(1)}</span>
        <span class="e-pe e-val ${peC}">${o.pe > 0 ? '+' : ''}${o.pe.toFixed(1)}</span>
      </div>`;
    }).join('');
    document.getElementById('sbList').innerHTML = html;
    document.getElementById('sbCount').textContent = `${opps.length} confirmations`;
  }
}

// ── CONTROLS ──
function showPage(p) {
  page = p;
  document.getElementById('chartsArea').classList.toggle('hidden', p !== 'charts');
  document.getElementById('shortcutsArea').classList.toggle('hidden', p !== 'shortcuts');
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.getElementById(`tb-${p}`).classList.add('active');
}

function setMetric(m) {
  metric = m;
  document.querySelectorAll('.metric-btn').forEach(b => b.classList.remove('active'));
  document.getElementById(`mb-${m}`).classList.add('active');
  renderCharts();
}

function setRes(r) {
  res = r;
  document.querySelectorAll('.res-btn').forEach(b => b.classList.remove('active'));
  document.getElementById(`rb-${r}`).classList.add('active');
  renderCharts();
  renderHeader();
}

function setSbView(v, btn) {
  sbView = v;
  document.querySelectorAll('.flt-btn').forEach(b => {
    if (b.id === 'v-events' || b.id === 'v-opp') b.classList.remove('active');
  });
  btn.classList.add('active');
  document.getElementById('evt-filters').style.display = v === 'events' ? 'flex' : 'none';
  document.getElementById('opp-filters').style.display = v === 'opp'    ? 'flex' : 'none';
  renderSidebar();
}

function toggleEvtFilter(key, btn) {
  if (evtActiveFilters.has(key)) evtActiveFilters.delete(key);
  else evtActiveFilters.add(key);
  btn.classList.toggle('active', evtActiveFilters.has(key));
  renderSidebar();
}

function setOppFilter(f, btn) {
  oppFilter = f;
  document.querySelectorAll('#opp-filters .flt-btn').forEach(b => {
    if (['all','bull','bear'].some(x => b.onclick?.toString().includes(`'${x}'`))) b.classList.remove('active');
  });
  btn.classList.add('active');
  renderSidebar();
}

function setOppFilterMetric(m, btn) {
  if (oppMetrics.has(m)) oppMetrics.delete(m);
  else oppMetrics.add(m);
  btn.classList.toggle('active', oppMetrics.has(m));
  renderSidebar();
}

// ── KEYBOARD ──
document.addEventListener('keydown', e => {
  if (e.target.tagName === 'INPUT') return;
  const k = e.key.toUpperCase();
  const map = {
    'D': () => { setMetric('D'); showPage('charts'); },
    'G': () => { setMetric('G'); showPage('charts'); },
    'P': () => { setMetric('P'); showPage('charts'); },
    'V': () => { setMetric('V'); showPage('charts'); },
    '1': () => setRes('1min'),
    '5': () => setRes('5min'),
    'E': () => { setSbView('events', document.getElementById('v-events')); },
    'O': () => { setSbView('opp',    document.getElementById('v-opp'));    },
    'S': () => {
      evtActiveFilters = new Set(['spike','CE','PE','Delta%','Gamma%','Price%','Volume%']);
      renderSidebar();
    },
    'X': () => {
      evtActiveFilters = new Set(['drop','CE','PE','Delta%','Gamma%','Price%','Volume%']);
      renderSidebar();
    },
    'C': () => {
      evtActiveFilters = new Set(['spike','drop','CE','Delta%','Gamma%','Price%','Volume%']);
      renderSidebar();
    },
    'A': () => {
      evtActiveFilters = new Set(['spike','drop','PE','Delta%','Gamma%','Price%','Volume%']);
      renderSidebar();
    },
    'B': () => {
      oppFilter = 'bull'; setSbView('opp', document.getElementById('v-opp'));
    },
    'R': () => {
      oppFilter = 'bear'; setSbView('opp', document.getElementById('v-opp'));
    },
  };
  if (map[k]) { e.preventDefault(); map[k](); }
});

// ── INIT ──
renderHeader();
renderCharts();
renderSidebar();
</script>
</body>
</html>
"""


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description='OI Spike Dashboard Generator')
    parser.add_argument('input', help='Input Excel file (.xlsx)')
    parser.add_argument('output', nargs='?', help='Output HTML file (default: <input>_dashboard.html)')
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"ERROR: File not found: {args.input}")
        sys.exit(1)

    output_path = args.output or os.path.splitext(args.input)[0] + '_dashboard.html'

    print("=" * 60)
    print("  OI Spike Dashboard Generator")
    print("=" * 60)

    # 1. Parse
    print("\n[1/5] Parsing Excel …")
    data = parse_xlsx(args.input)

    # 2. Resample
    print("[2/5] Resampling timeseries …")
    ts1 = resample_ts(data, '1min')
    ts5 = resample_ts(data, '5min')
    print(f"  1-min: {len(ts1)} bars | 5-min: {len(ts5)} bars")

    # 3. Events
    print("[3/5] Detecting spike/drop events …")
    events = build_events(data)
    spikes = [e for e in events if e['type'] == 'spike']
    drops  = [e for e in events if e['type'] == 'drop']
    print(f"  {len(spikes)} spikes | {len(drops)} drops")

    # 4. Opposites
    print("[4/5] Finding opposite-side confirmations …")
    confs = build_opposites(data)
    bull = [c for c in confs if c['pattern'] == 'CE_spike_PE_drop']
    bear = [c for c in confs if c['pattern'] == 'PE_spike_CE_drop']
    print(f"  {len(confs)} total | {len(bull)} bullish | {len(bear)} bearish")

    # 5. Build HTML
    print("[5/5] Generating dashboard …")
    summary = build_summary(data, events, confs)

    payload = {
        'ts1':     ts1,
        'ts5':     ts5,
        'events':  events[:1000],   # cap at 1000 for performance
        'opp':     confs,
        'summary': summary,
    }

    date_str   = summary['date']
    strikes_str = ', '.join(str(s) for s in summary['strikes'])
    total_rows  = f"{summary['total_rows']:,}"

    html = HTML_TEMPLATE.replace('{DATE}', date_str)
    html = html.replace('{STRIKES}', strikes_str)
    html = html.replace('{TOTAL_ROWS}', total_rows)
    html = html.replace('__DATA__', json.dumps(payload))

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)

    size_kb = os.path.getsize(output_path) / 1024
    print(f"\n✓ Dashboard saved: {output_path}  ({size_kb:.0f} KB)")
    print(f"  Open in any browser — no server needed.")
    print("=" * 60)


if __name__ == '__main__':
    main()
