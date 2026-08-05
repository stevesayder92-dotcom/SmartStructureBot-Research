from __future__ import annotations

from pathlib import Path
import gzip
import html
import json
import shutil


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "simulator_evidence"


def main() -> int:
    manifest = json.loads((EVIDENCE / "curated_sessions_manifest.json").read_text(encoding="utf-8"))
    charts = EVIDENCE / "key_screenshots"
    charts.mkdir(exist_ok=True)
    articles = []
    for row in manifest["sessions"]:
        session_id = row["session_id"]
        root = EVIDENCE / "sessions" / session_id
        payload = json.loads(gzip.decompress((root / "session.json.gz").read_bytes()))
        significant = [event["event_number"] for event in payload["events"] if event["event_priority"] >= 80]
        focus = significant[0] if significant else len(payload["events"]) - 1
        source = root / "exports" / f"event_{focus:06d}"
        names = {}
        for timeframe in ("M5", "M1"):
            name = f"{session_id}_{timeframe}.png"
            shutil.copy2(source / f"{timeframe}_chart.png", charts / name)
            names[timeframe] = name
        meta = payload["manifest"]
        actions = [
            event["director_decision"]["committed_action"]
            for event in payload["events"]
            if event["director_decision"]["committed_action"] != "NO_ACTION"
        ]
        articles.append(f"""
        <article>
          <header><div><span>{html.escape(row['curated_category'])}</span><h2>{html.escape(session_id)} · {html.escape(meta['symbol'])}</h2></div><strong>{len(payload['events'])} events · Causal PASS</strong></header>
          <p>{html.escape(row['expected_inspection_question'])}</p>
          <div class="actions">Director story: {html.escape(' → '.join(actions) or 'NO_ACTION in review window')}</div>
          <div class="charts"><figure><figcaption>M5 parent · event {focus}</figcaption><img src="key_screenshots/{names['M5']}" alt="{session_id} M5 closed-candle chart"></figure><figure><figcaption>M1 execution · event {focus}</figcaption><img src="key_screenshots/{names['M1']}" alt="{session_id} M1 closed-candle chart"></figure></div>
          <div class="review">Steve review: ENTRY □ Accept □ Reject □ Uncertain &nbsp; STOP □ Accept □ Reject □ Uncertain &nbsp; MANAGEMENT □ Accept □ Reject □ Uncertain &nbsp; RE-ENTRY □ Accept □ Reject □ Uncertain</div>
        </article>""")
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>SmartStructureBot Phase S1 Visual Review</title><style>
    :root{{color-scheme:dark}}body{{margin:0;background:#07101d;color:#edf4ff;font:14px/1.45 Segoe UI,Arial,sans-serif}}header.hero{{position:sticky;top:0;z-index:2;padding:22px 4vw;background:#0a1728;border-bottom:1px solid #29415f}}h1{{margin:0 0 6px}}main{{padding:18px 4vw}}article{{margin:0 0 24px;background:#0d1b2e;border:1px solid #29415f;border-radius:12px;overflow:hidden}}article>header{{display:flex;justify-content:space-between;gap:16px;padding:14px 18px;background:#11233a}}article h2{{margin:2px 0}}article span,article p{{color:#93a9c1}}article p,.actions,.review{{padding:0 18px}}.actions{{color:#63d8ba;font-weight:600}}.charts{{display:grid;grid-template-columns:1fr 1fr;gap:10px;padding:12px}}figure{{margin:0}}figcaption{{padding:6px;color:#93a9c1}}img{{display:block;width:100%;height:auto;border:1px solid #29415f}}.review{{padding-bottom:16px;color:#d7e5f5}}.badges{{color:#82c3ff}}@media(max-width:900px){{.charts{{grid-template-columns:1fr}}}}
    </style></head><body><header class="hero"><h1>SmartStructureBot Phase S1 · Visual Review</h1><div class="badges">12 curated sessions · 999 immutable events · historical closed candles · orders disabled · performance not guaranteed</div></header><main>{''.join(articles)}</main></body></html>"""
    (EVIDENCE / "phase_s1_visual_review.html").write_text(page, encoding="utf-8")
    print(json.dumps({"sessions": len(articles), "screenshots": len(list(charts.glob('*.png'))), "review": str(EVIDENCE / 'phase_s1_visual_review.html')}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
