# Phase 9 old-versus-new stop comparison

| Question | Rejected Phase 8 behavior | Phase 9 Steve behavior |
|---|---|---|
| Initial stop source | Absolute broad retracement wick | Relevant defended pre-BOS LOW/LL for BUY or HIGH/HH for SELL |
| ATR | Universal one full ATR | Configurable M5 tolerance; M1 uses structure candle close |
| Future influence | Later structures blurred the visual risk story | Initial contract records `post_entry_candles_used=false` |
| Logical vs hard stop | One stop performed both roles | Logical invalidation and emergency broker stop are separate |
| Trail candidate | Every confirmed fractal | Correct-side HL/LH only, initially unproven |
| Trail proof | Fractal confirmation alone | Later same-direction body-close BOS |
| Opposing exit | Latest raw swing break | Body-close break of meaningful proven protection |
| Re-entry arming | First stop-out | Fresh counter-structure plus new continuation BOS |
| Re-entry limit | Reserved immediately | Maximum one; second failure closes parent |
| Position split | Fixed twin positions | Configurable profile; 50/50 remains an option |

The accepted entry trigger, entry candle, entry price and source datasets are
unchanged. Outcomes are not used to select or tune stops.
