# Phase 9 remaining strategy questions for Steve

These questions do not block research review. They should be answered before
paper/demo execution is automated.

1. M5 momentum invalidation currently accepts either a sufficiently strong
   body or sufficient close distance after the ATR-tolerant boundary is
   crossed. Should production require both conditions?

2. M1 invalidation uses the exact close of the relevant swing candle. Should
   a bullish invalidation instead use the lower body edge (`min(open, close)`)
   and a bearish invalidation the upper body edge (`max(open, close)`)?

3. For a proven trail, Phase 9 requires the later body close to break the
   associated post-entry impulse extreme. Do you also require a minimum
   displacement/ATR body size for that proof candle?

4. When M30 and M15 both publish valid dominant protection, the current
   contract selects the tighter still-valid level and records both sources.
   Should M30 always own protection, M15 always own it, or should the cleaner
   structure win?

5. For profiles with TP1, the research detector currently treats a wick touch
   of the objective as reached. Should TP1 require a candle close?

6. If a proven trailing level is still behind entry when TP1 triggers, the
   prior MAX/MIN instruction moves runner protection no worse than entry.
   Confirm that break-even remains mandatory in every partial profile.

7. How many closed M5 candles without a clean M5 BOS count as “no timely M5
   entry” before M1 fallback becomes preferred rather than merely available?

8. Session windows are currently research labels. Should production block
   entries outside London/New York/overlap, or reduce risk instead?
