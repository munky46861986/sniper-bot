# AMBATA GUIDA V1 — solo SHADOW

Goal: test whether choosing a single persistent *anchor number* before a real
10eLotto 5-minute draw improves a single ambo and virtual cash flow.

The fixed algorithm uses exactly the last 60 verified real BASE draws. It
selects the number with the largest minimum frequency over the last two
non-overlapping blocks of 30 draws (ties: overall frequency, numeric order).
Only anchors observed at least eight times in **each** block qualify.
The partner is chosen by frozen score:
3×historical co-occurrences with anchor + historical 60-draw frequency
+4 if in prepublished DECINE20, +3 if in prepublished HYBRID20,
+2 if in prepublished RITARDATARI20. Numeric order breaks ties.
A baseline ambo uses the top two 60-draw numbers by frequency.
No postdraw data may enter the decision.

A forecast may be emitted once per 12 draws (one per hour), only when a
preview exists, the specialist forecasts are queued for the same target,
and there is enough lead time to get a Telegram acknowledgement.

After acknowledgement, record guide's H1 and any H1-H5 appearance, pair
and baseline H1 / at-least-one H1-H5 hits, and independently simulate:
- FULL5: €1 on the pair on each of five successive verified BASE draws.
- STOP1: €1 on the pair, stop after its first win. Baseline stops itself.
Gross 14× stake per winning ambo; costs deducted; daily / ISO-weekly
ledgers are built by actual draw date. Results are VIRTUAL, no bets.

All forecasts, counterfactuals and analysis are SHADOW only. There is no
assurance of above-chance predictive power or positive weekly returns.
Previous exploratory data have overlapping test windows; do not treat
their signal counts as independent validation.
