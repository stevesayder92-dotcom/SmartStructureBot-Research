# S2B.1 causality report

All four manual parents were rerun at a frozen decision boundary under:

1. prefix only;
2. actual suffix;
3. modified suffix; and
4. forced reversal suffix.

The resulting 16 decisions were identical for entry time, entry price,
logical stop and active trigger. Swing confirmation remains delayed by the
configured right-side sensitivity; wicks can define touches but cannot define
BOS. No later touch rewrote an earlier entry, and the measured retroactive
change count is zero.

Canonical `research_data/` SHA-256 values matched before and after the replay.
The complete portable-library input hashes are also published in
`research_runs/s2b1/research_input_hashes_before.json` and
`research_input_hashes_after.json`.

The permanent suite covers ownership, delay, wick-only rejection, correctly
directed body-close BOS, supersession, touch-2 stop ownership, M1/M5 symmetry,
post-entry immutability, fresh Attempt 2, the one-re-entry limit, default-off
reproduction, source-data hashes and absence of order APIs.

