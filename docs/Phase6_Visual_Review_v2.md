# Phase 6 Visual Review v2

The review page was rebuilt after Steve reported that the first audit layout
was difficult to read.

## Changes

- One review case is shown at a time.
- Fourteen clearly labeled selector buttons switch between cases.
- Every case begins with a plain-English, numbered explanation of what the bot
  believes about trend, pullback, qualification, failure trigger, decision,
  and protection.
- Missing HTF evidence and stale-entry warnings are shown before the chart.
- Each case has two separate large images:
  - full setup lifecycle;
  - decision zoom with larger candles.
- The colors and numbers now have one stable meaning:
  - blue: trend-origin BOS;
  - purple: pullback start and qualification;
  - orange: failed-retracement trigger;
  - green: bot decision;
  - grey: post-decision outcome candles.
- The engine's exact recorded reasons are displayed under each chart.
- Steve's manual screenshots are moved into a collapsible reference section so
  they do not compete with the active bot case.

The visual-only repair did not change strategy thresholds, canonical entries,
or order safety.
