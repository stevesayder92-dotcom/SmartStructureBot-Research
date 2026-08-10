# S2B Earned Early M1 Permission Contract

Status: opt-in research validation only. Default strategy behavior remains
`COUNTER_CONFIRMED_ACTIVE`. Live and demo execution are disabled.

## Exact lifecycle

`PARENT_ARMED` is published only after the M5 pullback anchor's required
right-side candles close. It grants M1 observation, not execution. The parent
retains exact HTF, setup, retracement, impulse-cycle, protection, direction and
Fib-anchor ownership. `PARENT_ACTIVE` is unchanged: it occurs only after the
M5 counter swing's right-side confirmation closes.

Under `EARNED_EARLY_OR_COUNTER_CONFIRMED_ACTIVE`, the interval after ARMED and
before ACTIVE is evaluated candle by candle. A candidate earns
`EARLY_M1_PERMISSION_EARNED` only when the unchanged M1 detector proves its
meaningful counter, complete initial/counter/trigger sequence, displacement,
minimum bars, available fresh trigger, correctly directed body-close BOS,
price boundary, dominant protection, exact ownership, logical-stop side and
unchanged causal quality threshold. Wick-only, wrong-body, noise, incomplete,
stale, outside-parent, broken-protection and observe-only candidates remain
rejected.

The entry price is the BOS candle close. The initial logical stop is the
accepted M1 relevant-swing body edge available by that close. The emergency
stop remains separate and wider. No transition to M5 management may widen
protection.

## Causal boundary

The decision snapshot at `T` contains no eventual M5 entry, price, stop,
target, failure trigger not yet available, later parent state, future swing,
MFE/MAE or outcome. Those fields are analytics-only. A–E prefix/suffix tests
prove invariance for ownership, permission, trigger, BOS, quality, grade,
policy, readiness, entry, stops, owner and Director action.

## Consumption and re-entry

An earned-early M1 entry is attempt 1 and atomically consumes later M1 and M5
first-entry competitors for the same parent. Parent and sequence identities do
not change. The existing maximum of one re-entry remains one; every existing
re-entry proof and protection blocker remains unchanged.

## Ownership

- Parent facts: `SystemStateDirector`
- Child evidence: `M1ChildStructureEngine`
- Permission state: `M1PermissionPolicyEngine`
- First valid commitment: Director/first-valid entry arbiter
- Trade management: existing `SteveTradeManagementEngine`
- Analytics and visuals: research-only S2B evidence runner

No UI, diagnostic or shadow field has action authority. No order API is
enabled or called.
