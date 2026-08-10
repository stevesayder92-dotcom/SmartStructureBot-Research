# S2B.1 manual review report

All four hand-marked parents were reconstructed without hard-coding their
prices or identities. The review package is
`research_runs/s2b1/s2b1_manual_anchor_review.html`.

| Anchor | Causal result |
|---|---|
| AUDUSD# bearish PB_2121 | Exact ACTIVE-only match: touch wicks 0.69761/0.69762, migrated trigger 0.69749, BOS close 0.69748, touch-2 stop 0.69762. |
| USDJPY# bearish PB_1538 | The marked later sequence is recognized in the earned-early path; ACTIVE-only retains its accepted fallback. |
| GER40Cash# bearish PB_2066 | Reconstructed, but the frozen recognizer does not accept a causal second touch before the selected entry. |
| GER40Cash# bullish PB_2365 | Reconstructed, but the frozen recognizer does not accept a causal second touch before the selected entry. |

Therefore the honest answer to “do all four now match Steve's marked intent?”
is **no**: two align with a second-touch path, and two GER40 cases remain manual
discrepancies. The ATR thresholds were frozen before replay and were not tuned
after seeing these outcomes.

Steve should mark each of the 34 charts (30 population reviews plus four anchor
reviews) `ACCEPT`, `REJECT`, or `UNCERTAIN` with a reason. Until that review,
second-touch execution remains research-only and disabled by default.

