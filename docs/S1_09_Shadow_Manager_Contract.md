# Shadow-manager contract

Shadows answer “what would this isolated policy recommend from the same visible
prefix?” They are not trades and never reach the Director.

Profiles: pure structure runner, TP1 partial plus runner, earned opportunity
manager, M5 confirmation re-entry and M1 reset re-entry.

For every event each shadow receives the same current price, canonical snapshot
and visible indices. It publishes open/closed state, action, position fraction,
unrealized R, deviation from canonical and causal validity. It cannot access
future candles, final outcomes or another shadow's state.

Required invariants:

- no canonical object mutation;
- identical output after rewind/replay;
- identical output when an unrevealed suffix changes;
- explicit deviation label;
- no broker/order integration.

Phase S1 proves the isolation framework. Policy optimization is reserved for
Phase S2 and must not be inferred from shadow outcomes here.
