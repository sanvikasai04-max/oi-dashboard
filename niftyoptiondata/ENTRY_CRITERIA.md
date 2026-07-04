# NIFTY Option Strength Analyser - Entry Criteria

> Source: `3_strength_analyser.py`  
> Model: multi-factor, cross-strike, cross-candle confirmation for CE/PE option entries.

---

## Quick Decision Flow

```text
Candidate row
   |
   v
Same-side strength across nearby strikes?
   |
   v
Opposite-side weakness confirms the move?
   |
   v
At least 3 confirmed candles inside last 5 snapshots?
   |
   v
Latest strength is not weaker than first strength?
   |
   v
ENTRY ALLOWED
```

For a normal entry, the script waits for strength to appear across strikes and across candles. A single exciting candle is not enough unless it qualifies through the spike-override path.

---

## Direction Meaning

| Entry Side | Market View | Same-Side Requirement | Opposite-Side Confirmation |
|---|---:|---|---|
| `CE` | Bullish | CE delta, price, and volume should rise | PE delta and price should fall |
| `PE` | Bearish | PE delta, price, and volume should rise | CE delta and price should fall |

The analyser buys the selected option side. PnL is calculated from option entry price to option exit price.

---

## Nearby Strike Window

The confirmation engine checks strikes around the candidate strike:

| Setting | Default | Meaning |
|---|---:|---|
| `STRIKES_NEARBY` | `2` | Check 2 strikes below and 2 strikes above |
| `STRIKE_STEP` | `50` | NIFTY option strike spacing |

So a candidate at `25000` checks:

```text
24900, 24950, 25000, 25050, 25100
```

---

## Snapshot Confirmation Pillars

Every snapshot is scored using three pillars.

### 1. Volume Pillar

| Rule | Default | Purpose |
|---|---:|---|
| Minimum own-side volume | `>= 80%` | Confirms real participation |
| Bonus tier 1 | `>= 100%` | Stronger volume expansion |
| Bonus tier 2 | `>= 150%` | High-conviction volume |
| Bonus tier 3 | `>= 200%` | Extreme volume expansion |

Opposite-side volume can confirm in three ways:

| Pattern | Condition | Meaning |
|---|---|---|
| Active selling | Opposite volume `>= 80%` | Opposite side is being sold aggressively |
| Clean exits | Opposite volume `< 0` | Opposite-side positions are exiting |
| Slow unwind | Opposite volume `0%` to `80%` and opposite price `<= -5%` | Weak unwind with price damage |

### 2. Delta Pillar

| Rule | Default | Purpose |
|---|---:|---|
| Minimum own-side delta | `>= 2%` | Base directional confirmation |
| Bonus tiers | `>= 3%`, `>= 4%`, `>= 5%` | Measures deeper directional strength |
| Opposite-side delta drop | `<= -2%` | Confirms the other side is weakening |
| Opposite bonus drops | `<= -4%`, `<= -6%` | Stronger weakness confirmation |

### 3. Price Pillar

| Rule | Default | Purpose |
|---|---:|---|
| Minimum own-side price | `>= 3%` | Confirms option premium is moving |
| Bonus tiers | `>= 4%`, `>= 5%`, `>= 6%`, `>= 7%` | Measures price momentum depth |
| Opposite-side price fall | `<= -3%` | Confirms cross-side weakness |
| Opposite bonus fall | `<= -5%` | Stronger cross-side confirmation |

---

## Cross-Strike Confirmation

A snapshot passes only when both same-side strength and opposite-side weakness are present.

| Requirement | Default | Code Setting |
|---|---:|---|
| Same-side confirming nearby strikes | `>= 3` | `STRICT_MIN_SAME_STRIKES` |
| Opposite-side confirming nearby strikes | `>= 2` | `STRICT_MIN_OPP_STRIKES` |

### Volume-Neutral Rule

Volume does not always have to be explosive.

If delta and price are strong, and own-side volume is non-negative, the snapshot can still count as a partial/neutral-volume confirmation when:

```text
STRICT_ALLOW_VOLUME_NEUTRAL = True
```

This supports the rule:

```text
Delta spike + price spike + neutral volume = still valid confirmation
```

Use `--strict-require-volume` to disable this flexibility.

---

## Composite Score

The script gives more importance to delta and price than volume.

| Pillar | Weight |
|---|---:|
| Delta | `40%` |
| Price | `40%` |
| Volume | `20%` |
| Opposite-side weakness | Added as extra confirmation points |

The score is used to compare strength across candles and to trigger spike overrides.

---

## Normal Entry Criteria

Normal entries use cross-candle confirmation.

| Rule | Default | Code Setting |
|---|---:|---|
| Lookback window | Last `5` snapshots | `STRICT_CONFIRM_WINDOW` |
| Required confirmations | `3` snapshots | `STRICT_MIN_CONFIRM_BARS` |
| Confirmations must be consecutive? | No | Non-consecutive confirmations count |
| Growth check | Latest units must be `>=` first units | Avoids fading entries |

Example:

```text
Last 5 snapshots:  Confirm, Weak, Confirm, Confirm, Weak
Confirmed count:   3 of 5
Entry:             Allowed if latest confirmation is not weaker than first
```

The final reason usually includes:

```text
CONF=3/5 FIRST_UNITS=... LAST_UNITS=... FIRST_SCORE=... LAST_SCORE=...
```

---

## Spike Override Entry

Spike override allows a faster entry when the current snapshot is explosive, even before normal `3 of 5` confirmation is complete.

| Guard | Default | Meaning |
|---|---:|---|
| Composite score | `>= 60` | Current snapshot must be strong enough |
| `V80` count | `>= 4` | Volume `>= 80%` on at least 4 nearby strikes |
| `V150` count | `>= 4` | Volume `>= 150%` on at least 4 nearby strikes |
| `P5` count | `>= 3` | Own-side price `>= 5%` on at least 3 nearby strikes |
| `OppP5` count | `>= 3` | Opposite price `<= -5%` on at least 3 nearby strikes |
| Depth guard | `D4 >= 3` OR `P6 >= 2` | Move should still have depth |
| Minimum time | `09:45` | Blocks blind session-open spike overrides |

Spike override is allowed only if all active guards pass.

```text
SPIKE_OVERRIDE score>=60
AND V80>=4
AND V150>=4
AND P5>=3
AND OppP5>=3
AND (D4>=3 OR P6>=2)
AND time>=09:45
```

### Spike Pending / Rescue

If a spike has strong delta and price but volume is not ready, the script may wait briefly:

| Path | Behavior |
|---|---|
| `SPIKE_PENDING` | Waits 1-2 candles when volume is the main missing guard |
| `SPIKE_OVERRIDE_NEXT_VOL` | Allows next candle if volume confirms strongly |
| `spike_override_volume_rescue` | Checks current plus next 2 minutes for valid rescue |

This avoids taking weak first spikes while still catching a move when volume arrives immediately after.

---

## Entry Filters

| Filter | Default | Meaning |
|---|---:|---|
| Entry start | `09:20` | Session starts from this time |
| Entry cutoff | `15:00` | No fresh entries after this |
| Side switch | Enabled | Opposite signal can close and flip active trade |
| Overlapping trades | Disabled | Only one active trade by default |

---

## Exit Criteria

The entry criteria should always be read together with exits.

| Exit Type | Default | Behavior |
|---|---:|---|
| Stop loss | `30` option points | Exit if option PnL reaches `-30` |
| Opposite confirmation | `2` confirmations | Exit when opposite side confirms with growing strength |
| Opposite surge | `1.5x` score ratio | Early exit if second opposite confirmation surges |
| Fake spike chop exit | Enabled | Spike entries must move away quickly |
| Force exit | `15:25` | Exit near market close |

### Fake Spike Chop Exit

For spike-override entries:

| Setting | Default |
|---|---:|
| Minimum bars | `4` |
| Maximum bars | `7` |
| Near-entry buffer | `+3` option points |
| Required favorable move | `10` option points |

If a spike entry comes back near entry inside this candle window and has not produced at least `10` points of favorable movement, it exits early as chop.

---

## Important CLI Tuning Knobs

```powershell
python .\3_strength_analyser.py --csv oi_2026_06_02.csv --date 2026-06-02 --console-xlsx
```

| Option | Default | What It Controls |
|---|---:|---|
| `--strict-volume-pct` | `80` | Own-side volume threshold |
| `--strict-delta-pct` | `2` | Own-side delta and opposite delta drop |
| `--strict-price-pct` | `3` | Own-side price and opposite price fall |
| `--strict-same-strikes` | `3` | Same-side strike count |
| `--strict-opp-strikes` | `2` | Opposite-side strike count |
| `--strict-window` | `5` | Confirmation lookback window |
| `--strict-confirm-bars` | `3` | Required confirmations inside window |
| `--strict-exit-bars` | `2` | Opposite confirmations for exit |
| `--exit-surge-ratio` | `1.5` | Strong opposite surge exit sensitivity |
| `--spike-override-score` | `60` | Minimum score for spike override |
| `--spike-min-v80` | `4` | Spike volume breadth guard |
| `--spike-min-v150` | `4` | Strong spike volume guard |
| `--spike-min-p5` | `3` | Own-side price momentum guard |
| `--spike-min-opp-p5` | `3` | Opposite-side weakness guard |
| `--spike-min-d4` | `3` | Delta depth guard |
| `--spike-min-p6` | `2` | Price depth guard |
| `--spike-override-min-time` | `09:45` | Earliest spike override time |
| `--strict-require-volume` | Off | Requires volume; disables neutral-volume confirmation |
| `--no-side-switch` | Off | Prevents close-and-flip behavior |
| `--no-fake-spike-exit` | Off | Disables fake-spike chop exit |

---

## Reading Entry Reasons

The analyser prints compact reason strings. These are the main tokens:

| Token | Meaning |
|---|---|
| `OWN=` | Number of same-side confirming strikes |
| `OPP=` | Number of opposite-side confirming strikes |
| `V80`, `V100`, `V150`, `V200` | Volume tier counts |
| `D2`, `D3`, `D4`, `D5` | Delta tier counts |
| `P3`, `P4`, `P5`, `P6`, `P7` | Price tier counts |
| `OppD2`, `OppD4` | Opposite delta drop counts |
| `OppP3`, `OppP5` | Opposite price fall counts |
| `CONF=3/5` | Confirmed snapshots in the lookback window |
| `FIRST_UNITS`, `LAST_UNITS` | Strength breadth comparison |
| `SPIKE_OVERRIDE` | Fast entry path passed |
| `SPIKE_PENDING` | Spike is waiting for quick volume confirmation |
| `SPIKE_OVERRIDE_BLOCKED` | Spike failed one or more quality guards |

---

## Practical Entry Checklist

Before trusting an entry, check:

```text
[ ] Same side has at least 3 nearby strikes confirming
[ ] Opposite side has at least 2 nearby strikes weakening
[ ] Delta and price both agree with the direction
[ ] Volume is strong, or neutral-volume rule is intentionally allowed
[ ] At least 3 of the last 5 snapshots confirm
[ ] Latest confirmation is not weaker than the first
[ ] Spike override entries pass V80, V150, P5, OppP5, and depth guards
[ ] Entry time is before 15:00
[ ] Exit logic is acceptable for the test: stop, opposite confirm, fake-spike chop, force exit
```

---

## One-Line Summary

The analyser enters only when option-side strength is broad across nearby strikes, confirmed by opposite-side weakness, repeated across recent candles, and not fading. Spike entries are allowed, but only after strict volume, price, cross-side, depth, and time guards pass.
