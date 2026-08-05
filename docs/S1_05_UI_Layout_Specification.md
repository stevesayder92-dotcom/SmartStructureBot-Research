# UI layout specification

The application is a dark, high-contrast research console designed for a
1280px investor presentation and responsive review on smaller screens.

Top to bottom:

1. Sticky identity/health bar: symbol, UTC time, indices, event, speed,
   causality and permanent research/order badges.
2. Session controls: case, mode, preset, replay navigation, speed and jump.
3. Narrative banner: current published story plus Director action.
4. Synchronized M5 parent and M1 execution charts.
5. Collapsible presentation-only chart layers and export actions.
6. Canonical trade summary.
7. Bot brain and Director decision.
8. Engine recommendations and isolated shadow comparison.
9. Event timeline, trade story and bug flags.
10. Debug state diff/raw event and separate Steve review form.

Investor mode hides dense debug detail. Debug mode exposes hashes, raw event,
state differences and review controls. Mode, preset and layer changes never
mutate replay state. Timeline auto-centering is confined to its own scroll area.
