"""
Script 2: ATM Options Spike Analyser  — COLOR EDITION
══════════════════════════════════════════════════════
Reads the CSV produced by script 1 and shows a color-coded terminal report:

  🟢 GREEN  = increase / bullish
  🔴 RED    = decrease / bearish
  🟡 YELLOW = spike (volume / delta / gamma anomaly)
  🟠 ORANGE = extreme spike (>3σ)
  💜 PURPLE = IV highlight

Color intensity scales with % magnitude.

Usage  : python 2_atm_spike_analysis.py
Output : atm_spike_report.csv  +  color console table
"""

import re
import pandas as pd
import numpy as np
from pathlib import Path

# ── CONFIG ────────────────────────────────────────────────────────────────────
CSV_PATH        = "oi_2026_06_15.csv"
OUT_PATH        = "atm_spike_report.csv"
Z_THRESHOLD     = 2.0    # σ — flag delta/gamma/volume spikes
EXTREME_Z       = 3.0    # σ — extreme spike threshold (shown in orange)
PRICE_CHG_PCT   = 5.0    # % — flag price up/down moves
# ─────────────────────────────────────────────────────────────────────────────

# ── ANSI COLOR HELPERS ───────────────────────────────────────────────────────
RESET  = "\033[0m"
BOLD   = "\033[1m"

def _c(text, code): return f"\033[{code}m{text}{RESET}"

def green(t):       return _c(t, "32")
def bright_green(t):return _c(t, "92")
def red(t):         return _c(t, "31")
def bright_red(t):  return _c(t, "91")
def yellow(t):      return _c(t, "33")
def orange(t):      return _c(t, "38;5;208")
def cyan(t):        return _c(t, "36")
def magenta(t):     return _c(t, "35")
def white(t):       return _c(t, "97")
def dim(t):         return _c(t, "2")
def bold(t):        return _c(t, "1")

# ── ALIGNMENT HELPERS ────────────────────────────────────────────────────────
def strip_ansi(s):
    return re.sub(r'\033\[[0-9;]*m', '', str(s))

def rjust(s, width):
    """Right-justify a string that may contain ANSI codes."""
    pad = width - len(strip_ansi(s))
    return ' ' * max(0, pad) + s

def ljust(s, width):
    """Left-justify a string that may contain ANSI codes."""
    pad = width - len(strip_ansi(s))
    return s + ' ' * max(0, pad)

# ── COLOR FORMATTERS ─────────────────────────────────────────────────────────
def color_pct(val, extreme=20.0):
    """Color a % change value: green=up, red=down, brighter=larger."""
    if pd.isna(val):
        return "   n/a  "
    sign = "▲" if val > 0 else "▼" if val < 0 else " "
    txt  = f"{sign}{abs(val):6.2f}%"
    if val > extreme:    return bright_green(txt)
    elif val > 0:        return green(txt)
    elif val < -extreme: return bright_red(txt)
    elif val < 0:        return red(txt)
    else:                return dim(txt)

def color_spike(val, z, extreme_z=3.0):
    if abs(z) >= extreme_z: return orange(f"{val:>12,.4f} !!!")
    elif abs(z) >= 2.0:     return yellow(f"{val:>12,.4f}  ! ")
    else:                   return dim(f"{val:>12,.4f}    ")

def color_volume(val, z, extreme_z=3.0):
    txt = f"{val:>12,.0f}"
    if abs(z) >= extreme_z: return orange(txt + " !!!")
    elif abs(z) >= 2.0:     return yellow(txt + "  ! ")
    else:                   return dim(txt + "    ")

def color_delta(val, z):
    txt = f"{val:>8.4f}"
    if abs(z) >= EXTREME_Z:   return orange(txt + " !!!")
    if abs(z) >= Z_THRESHOLD: return yellow(txt + "  ! ")
    if val > 0.5:  return bright_green(txt + "    ")
    if val > 0:    return green(txt + "    ")
    if val < -0.5: return bright_red(txt + "    ")
    return red(txt + "    ")

def color_gamma(val, z):
    txt = f"{val:>8.5f}"
    if abs(z) >= EXTREME_Z:   return orange(txt + " !!!")
    if abs(z) >= Z_THRESHOLD: return yellow(txt + "  ! ")
    return cyan(txt + "    ")

def color_iv(val):
    txt = f"{val:>6.2f}%"
    if val > 20:  return bright_red(txt)
    if val > 17:  return red(txt)
    if val > 14:  return yellow(txt)
    return green(txt)

def zscore_series(series):
    mu, sigma = series.mean(), series.std()
    if sigma == 0:
        return pd.Series(np.zeros(len(series)), index=series.index)
    return (series - mu) / sigma

def flag_spikes(series, z_thresh):
    return zscore_series(series).abs() > z_thresh

# ── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    csv = Path(CSV_PATH)
    if not csv.exists():
        raise FileNotFoundError(
            f"CSV not found: {CSV_PATH}\n"
            "Run script 1 first:  python 1_db_to_csv.py"
        )

    print(bold(cyan(f"\n  Loading {CSV_PATH} …")))
    df = pd.read_csv(CSV_PATH, parse_dates=["timestamp"])
    df.sort_values(["timestamp","strike"], inplace=True)
    df.reset_index(drop=True, inplace=True)

    print(f"  {dim('Rows      :')} {len(df):,}")
    print(f"  {dim('Timestamps:')} {df['timestamp'].nunique()}")
    print(f"  {dim('Spot range:')} {df['spot'].min()} – {df['spot'].max()}")

    # ── ATM extraction ────────────────────────────────────────────────────────
    def pick_atm(grp):
        spot = grp["spot"].iloc[0]
        return grp.loc[(grp["strike"] - spot).abs().idxmin()]

    result = df.groupby("timestamp", group_keys=False).apply(pick_atm)
    if "timestamp" not in result.columns:
        result = result.reset_index()
    else:
        result = result.reset_index(drop=True)
    atm = result.sort_values("timestamp").reset_index(drop=True)

    # ── Compute pct changes ───────────────────────────────────────────────────
    atm["ce_delta_chg_pct"]  = (atm["call_delta"].pct_change()  * 100).round(2)
    atm["ce_gamma_chg_pct"]  = (atm["call_gamma"].pct_change()  * 100).round(2)
    atm["ce_volume_chg_pct"] = (atm["call_volume"].pct_change() * 100).round(2)
    atm["ce_price_chg_pct"]  = (atm["call_price"].pct_change()  * 100).round(2)

    atm["pe_delta_chg_pct"]  = (atm["put_delta"].pct_change()   * 100).round(2)
    atm["pe_gamma_chg_pct"]  = (atm["put_gamma"].pct_change()   * 100).round(2)
    atm["pe_volume_chg_pct"] = (atm["put_volume"].pct_change()  * 100).round(2)
    atm["pe_price_chg_pct"]  = (atm["put_price"].pct_change()   * 100).round(2)

    # ── Z-scores ──────────────────────────────────────────────────────────────
    atm["ce_delta_z"]  = zscore_series(atm["call_delta"]).round(3)
    atm["ce_gamma_z"]  = zscore_series(atm["call_gamma"]).round(3)
    atm["ce_volume_z"] = zscore_series(atm["call_volume"]).round(3)
    atm["pe_delta_z"]  = zscore_series(atm["put_delta"]).round(3)
    atm["pe_gamma_z"]  = zscore_series(atm["put_gamma"]).round(3)
    atm["pe_volume_z"] = zscore_series(atm["put_volume"]).round(3)

    # ── Spike flags ───────────────────────────────────────────────────────────
    atm["ce_delta_spike"]  = atm["ce_delta_z"].abs()  > Z_THRESHOLD
    atm["ce_gamma_spike"]  = atm["ce_gamma_z"].abs()  > Z_THRESHOLD
    atm["ce_volume_spike"] = atm["ce_volume_z"].abs() > Z_THRESHOLD
    atm["ce_price_up"]     = atm["ce_price_chg_pct"]  >  PRICE_CHG_PCT
    atm["ce_price_down"]   = atm["ce_price_chg_pct"]  < -PRICE_CHG_PCT

    atm["pe_delta_spike"]  = atm["pe_delta_z"].abs()  > Z_THRESHOLD
    atm["pe_gamma_spike"]  = atm["pe_gamma_z"].abs()  > Z_THRESHOLD
    atm["pe_volume_spike"] = atm["pe_volume_z"].abs() > Z_THRESHOLD
    atm["pe_price_up"]     = atm["pe_price_chg_pct"]  >  PRICE_CHG_PCT
    atm["pe_price_down"]   = atm["pe_price_chg_pct"]  < -PRICE_CHG_PCT

    flag_cols = [
        "ce_delta_spike","ce_gamma_spike","ce_volume_spike","ce_price_up","ce_price_down",
        "pe_delta_spike","pe_gamma_spike","pe_volume_spike","pe_price_up","pe_price_down",
    ]
    atm["any_spike"] = atm[flag_cols].any(axis=1)

    # ── Save CSV ──────────────────────────────────────────────────────────────
    save_cols = [
        "timestamp","expiry","spot","strike",
        "call_price","ce_price_chg_pct","call_delta","ce_delta_chg_pct",
        "call_gamma","ce_gamma_chg_pct","call_volume","ce_volume_chg_pct","call_iv",
        "put_price","pe_price_chg_pct","put_delta","pe_delta_chg_pct",
        "put_gamma","pe_gamma_chg_pct","put_volume","pe_volume_chg_pct","put_iv",
        "ce_delta_spike","ce_gamma_spike","ce_volume_spike","ce_price_up","ce_price_down",
        "pe_delta_spike","pe_gamma_spike","pe_volume_spike","pe_price_up","pe_price_down",
        "any_spike",
    ]
    atm[save_cols].to_csv(OUT_PATH, index=False)
    print(f"  {green('✅')} Saved → {OUT_PATH}\n")

    # ══════════════════════════════════════════════════════════════════════════
    # COLOR TABLE — one row per alert timestamp
    # ══════════════════════════════════════════════════════════════════════════

    # Fixed visible column widths
    W_TS    = 19
    W_SPOT  = 10
    W_STK   = 10
    W_PRICE = 10
    W_PCT   =  9
    W_DELTA = 16
    W_GAMMA = 16
    W_VOL   = 19
    W_IV    =  8

    W = 220
    alerts = atm[atm["any_spike"]].copy()

    print(bold("═" * W))
    print(bold(f"  {'ATM SPIKE REPORT':^{W-4}}"))
    print(bold(f"  Z≥{Z_THRESHOLD}σ spike  |  Price move ≥±{PRICE_CHG_PCT}%  |  {len(alerts)} alerts / {len(atm)} timestamps"))
    print(bold("═" * W))

    # ── Legend ────────────────────────────────────────────────────────────────
    print(f"\n  {bold('LEGEND:')}  "
          f"{bright_green('▲ UP / BULLISH')}  "
          f"{bright_red('▼ DOWN / BEARISH')}  "
          f"{yellow('! SPIKE (≥2σ)')}  "
          f"{orange('!!! EXTREME (≥3σ)')}  "
          f"{cyan('── normal ──')}\n")

    # ── Header (plain text, always aligned) ──────────────────────────────────
    hdr = (
        f"  {'TIMESTAMP':<{W_TS}}  "
        f"{'SPOT':>{W_SPOT}}  {'STRIKE':>{W_STK}}  "
        f"║  {'CE PRICE':>{W_PRICE}} {'Δ%':>{W_PCT}}  "
        f"{'CE DELTA':>{W_DELTA}} {'Δ%':>{W_PCT}}  "
        f"{'CE GAMMA':>{W_GAMMA}} {'Δ%':>{W_PCT}}  "
        f"{'CE VOL':>{W_VOL}} {'Δ%':>{W_PCT}}  "
        f"{'CE IV':>{W_IV}}  "
        f"║  {'PE PRICE':>{W_PRICE}} {'Δ%':>{W_PCT}}  "
        f"{'PE DELTA':>{W_DELTA}} {'Δ%':>{W_PCT}}  "
        f"{'PE GAMMA':>{W_GAMMA}} {'Δ%':>{W_PCT}}  "
        f"{'PE VOL':>{W_VOL}} {'Δ%':>{W_PCT}}  "
        f"{'PE IV':>{W_IV}}"
    )
    print(bold(hdr))
    print(dim("─" * W))

    for _, r in alerts.iterrows():
        ts   = dim(f"{str(r['timestamp'])[:19]:<{W_TS}}")
        spot = rjust(cyan(f"{r['spot']:.2f}"),  W_SPOT)
        stk  = rjust(cyan(f"{r['strike']:.1f}"), W_STK)

        # price value colored, then right-justified to W_PRICE
        def fmt_price(price, up, down):
            fn = bright_green if up else (bright_red if down else dim)
            return rjust(fn(f"{price:.2f}"), W_PRICE)

        def fmt_pct(v, ex=20.0):
            return rjust(color_pct(v, ex), W_PCT)

        row = (
            f"  {ts}  {spot}  {stk}  "
            f"║  {fmt_price(r['call_price'], r['ce_price_up'], r['ce_price_down'])} {fmt_pct(r['ce_price_chg_pct'])}  "
            f"{rjust(color_delta(r['call_delta'],  r['ce_delta_z']),  W_DELTA)} {fmt_pct(r['ce_delta_chg_pct'])}  "
            f"{rjust(color_gamma(r['call_gamma'],  r['ce_gamma_z']),  W_GAMMA)} {fmt_pct(r['ce_gamma_chg_pct'])}  "
            f"{rjust(color_volume(r['call_volume'], r['ce_volume_z'], EXTREME_Z), W_VOL)} {fmt_pct(r['ce_volume_chg_pct'], 50.0)}  "
            f"{rjust(color_iv(r['call_iv']), W_IV)}  "
            f"║  {fmt_price(r['put_price'], r['pe_price_up'], r['pe_price_down'])} {fmt_pct(r['pe_price_chg_pct'])}  "
            f"{rjust(color_delta(r['put_delta'],   r['pe_delta_z']),  W_DELTA)} {fmt_pct(r['pe_delta_chg_pct'])}  "
            f"{rjust(color_gamma(r['put_gamma'],   r['pe_gamma_z']),  W_GAMMA)} {fmt_pct(r['pe_gamma_chg_pct'])}  "
            f"{rjust(color_volume(r['put_volume'],  r['pe_volume_z'], EXTREME_Z), W_VOL)} {fmt_pct(r['pe_volume_chg_pct'], 50.0)}  "
            f"{rjust(color_iv(r['put_iv']), W_IV)}"
        )
        print(row)

    print(dim("─" * W))

    # ══════════════════════════════════════════════════════════════════════════
    # SECTION SUMMARIES
    # ══════════════════════════════════════════════════════════════════════════
    sections = [
        ("CE DELTA SPIKE  📈",  "ce_delta_spike",  "call_delta",  "ce_delta_chg_pct",  "ce_delta_z"),
        ("CE GAMMA SPIKE  ⚡",  "ce_gamma_spike",  "call_gamma",  "ce_gamma_chg_pct",  "ce_gamma_z"),
        ("CE VOLUME SPIKE 🔊",  "ce_volume_spike", "call_volume", "ce_volume_chg_pct", "ce_volume_z"),
        ("CE PRICE UP     ↑",   "ce_price_up",     "call_price",  "ce_price_chg_pct",  None),
        ("CE PRICE DOWN   ↓",   "ce_price_down",   "call_price",  "ce_price_chg_pct",  None),
        ("PE DELTA SPIKE  📉",  "pe_delta_spike",  "put_delta",   "pe_delta_chg_pct",  "pe_delta_z"),
        ("PE GAMMA SPIKE  ⚡",  "pe_gamma_spike",  "put_gamma",   "pe_gamma_chg_pct",  "pe_gamma_z"),
        ("PE VOLUME SPIKE 🔊",  "pe_volume_spike", "put_volume",  "pe_volume_chg_pct", "pe_volume_z"),
        ("PE PRICE UP     ↑",   "pe_price_up",     "put_price",   "pe_price_chg_pct",  None),
        ("PE PRICE DOWN   ↓",   "pe_price_down",   "put_price",   "pe_price_chg_pct",  None),
    ]

    print(f"\n{bold('═' * 70)}")
    print(bold("  SECTION BREAKDOWN"))
    print(bold("═" * 70))

    for title, flag, val_col, pct_col, z_col in sections:
        sub = atm[atm[flag]]
        n   = len(sub)
        if n == 0:
            print(f"\n  {dim('── ' + title + f'  (0 events) ── none')}")
            continue

        is_up   = "UP"   in title or "↑" in title
        is_down = "DOWN" in title or "↓" in title
        label   = (bright_green(f"── {title}") if is_up else
                   bright_red(f"── {title}")   if is_down else
                   yellow(f"── {title}"))

        print(f"\n  {label}  {bold(f'({n} events)')}")
        z_hdr = f"  {'Z-score':>9}" if z_col else ""
        print(f"  {'TIME             SPOT    STRIKE':<38}  {'         VALUE'}  {'      Δ%'}  {z_hdr}")

        for _, r in sub.iterrows():
            ts  = str(r["timestamp"])[11:19]
            val = r[val_col]
            pct = r[pct_col]
            z   = r[z_col] if z_col else None

            if "volume" in val_col.lower():
                vc = (orange if z and abs(z) >= EXTREME_Z else
                      yellow if z and abs(z) >= Z_THRESHOLD else
                      dim)(f"{val:>14,.0f}")
            elif "delta" in val_col.lower():
                vc = color_delta(val, z if z else 0)
            elif "gamma" in val_col.lower():
                vc = color_gamma(val, z if z else 0)
            else:
                vc = (bright_green if is_up else bright_red)(f"{val:>14.2f}")

            zstr = ""
            if z_col:
                zc   = orange if abs(z) >= EXTREME_Z else yellow
                zstr = f"  {zc(f'{z:>+8.2f}σ')}"

            print(f"  {dim(str(r['timestamp'])[:19])}  "
                  f"{cyan(f'{r.spot:>8.2f}')}  {cyan(f'{r.strike:>8.1f}')}  "
                  f"{vc}  {color_pct(pct)}{zstr}")

    # ══════════════════════════════════════════════════════════════════════════
    # QUICK STATS
    # ══════════════════════════════════════════════════════════════════════════
    print(f"\n{bold('═' * 70)}")
    print(bold("  QUICK STATS — full ATM session"))
    print(bold("═" * 70))
    print(f"  {'Metric':<14}  {'Min':>10}  {'Max':>10}  "
          f"{'Mean':>10}  {'Std':>10}  {'Avg Δ%':>10}")
    print(dim("  " + "─" * 66))

    stat_rows = [
        ("CE Price",  "call_price",  "ce_price_chg_pct"),
        ("CE Delta",  "call_delta",  "ce_delta_chg_pct"),
        ("CE Gamma",  "call_gamma",  "ce_gamma_chg_pct"),
        ("CE Volume", "call_volume", "ce_volume_chg_pct"),
        ("CE IV",     "call_iv",     None),
        ("PE Price",  "put_price",   "pe_price_chg_pct"),
        ("PE Delta",  "put_delta",   "pe_delta_chg_pct"),
        ("PE Gamma",  "put_gamma",   "pe_gamma_chg_pct"),
        ("PE Volume", "put_volume",  "pe_volume_chg_pct"),
        ("PE IV",     "put_iv",      None),
    ]
    for label, col, pct_col in stat_rows:
        s    = atm[col]
        mn   = f"{s.min():>10.4f}"
        mx   = f"{s.max():>10.4f}"
        mean = f"{s.mean():>10.4f}"
        std  = f"{s.std():>10.4f}"
        avg_pct = ""
        if pct_col:
            ap = atm[pct_col].dropna()
            avg_pct = color_pct(ap.mean(), extreme=10.0)
        print(f"  {bold(label):<14}  {dim(mn)}  {dim(mx)}  {dim(mean)}  {dim(std)}  {avg_pct}")

    print()


if __name__ == "__main__":
    main()