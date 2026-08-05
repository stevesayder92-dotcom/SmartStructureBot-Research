from __future__ import annotations

from pathlib import Path
from typing import Any
import csv
import hashlib
import io
import json
import zipfile
import html

from simulator.analytics.account_metrics import AccountMetrics
from simulator.kernel.replay_session import ReplaySession
from simulator.models.schema import json_safe


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(json_safe(payload), indent=2, sort_keys=True), encoding="utf-8"
    )


def _chart(session: ReplaySession, event_number: int, timeframe: str, path: Path) -> None:
    from PIL import Image, ImageDraw, ImageFont

    event = session.events[event_number]
    as_of = event.visible_m1_rows - 1 if timeframe == "M1" else event.visible_m5_rows - 1
    frame = session.dataset.m1 if timeframe == "M1" else session.dataset.m5
    start = max(0, as_of - (90 if timeframe == "M1" else 60))
    data = frame.iloc[start : as_of + 1]
    snap = event.snapshot
    entry = snap.get("entry") or {}
    management = snap.get("management") or {}
    latest = management.get("latest_attempt") or {}
    width, height = 2200, 980
    image = Image.new("RGB", (width, height), "#08111f")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=18)
    small = ImageFont.load_default(size=14)
    left, right, top, bottom = 95, 170, 90, 80
    low_price = float(data["low"].min())
    high_price = float(data["high"].max())
    overlays: list[tuple[str, float | None, str, str]] = [
        ("ENTRY", latest.get("entry_price") or entry.get("price"), "#4da3ff", "solid"),
        ("LOGICAL STOP", latest.get("logical_stop") or entry.get("logical_stop"), "#ffb84d", "dash"),
        ("EMERGENCY", latest.get("emergency_broker_stop") or entry.get("emergency_broker_stop"), "#ff5575", "dot"),
        ("TP1", latest.get("position_1_target"), "#35d07f", "dash"),
        ("PROTECTION", latest.get("current_protection"), "#bd8cff", "solid"),
    ]
    for _, price, _, _ in overlays:
        if price is not None:
            low_price = min(low_price, float(price))
            high_price = max(high_price, float(price))
    margin = (high_price - low_price) * 0.08 or 1.0
    low_price -= margin
    high_price += margin

    def x_at(position: int) -> float:
        return left + position * (width - left - right) / max(1, len(data) - 1)

    def y_at(price: float) -> float:
        return top + (high_price - price) / (high_price - low_price) * (height - top - bottom)

    for step in range(6):
        y = top + step * (height - top - bottom) / 5
        draw.line((left, y, width - right, y), fill="#20334b", width=1)
        price = high_price - step * (high_price - low_price) / 5
        draw.text((width - right + 14, y - 9), f"{price:.5f}", fill="#91a5bd", font=small)
    for step in range(8):
        x = left + step * (width - left - right) / 7
        draw.line((x, top, x, height - bottom), fill="#172b42", width=1)
    body_width = max(4, min(17, int((width - left - right) / max(1, len(data)) * 0.62)))
    for local, (_, row) in enumerate(data.iterrows()):
        up = float(row.close) >= float(row.open)
        color = "#22c7a9" if up else "#f05d7a"
        x = x_at(local)
        draw.line((x, y_at(float(row.high)), x, y_at(float(row.low))), fill=color, width=2)
        y_open, y_close = y_at(float(row.open)), y_at(float(row.close))
        draw.rectangle((x - body_width / 2, min(y_open, y_close), x + body_width / 2, max(y_open + 2, y_close + 2)), fill=color)

    def patterned_line(y: float, color: str, style: str) -> None:
        if style == "solid":
            draw.line((left, y, width - right, y), fill=color, width=3)
            return
        segment, gap = (20, 12) if style == "dash" else (4, 10)
        x = left
        while x < width - right:
            draw.line((x, y, min(x + segment, width - right), y), fill=color, width=2)
            x += segment + gap

    for label, price, color, style in overlays:
        if price is not None:
            y = y_at(float(price))
            patterned_line(y, color, style)
            draw.text((left + 12, y - 25), f"{label}  {float(price):.5f}", fill=color, font=small)
    draw.text((left, 26), f"{session.dataset.symbol}  {timeframe}  ·  event {event_number}  ·  closed-candle prefix only", fill="#edf4ff", font=font)
    draw.text((left, height - 40), "HISTORICAL RESEARCH REPLAY  ·  ORDERS DISABLED  ·  FUTURE CANDLES NOT VISIBLE", fill="#8297b0", font=small)
    image.save(path, format="PNG", optimize=True)


class ExportService:
    def __init__(self, session: ReplaySession, output_root: Path):
        self.session = session
        self.output_root = output_root
        self.output_root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _hashes(folder: Path) -> dict[str, str]:
        result: dict[str, str] = {}
        for path in sorted(folder.rglob("*")):
            if path.is_file() and path.name != "export_hashes.json":
                result[str(path.relative_to(folder)).replace("\\", "/")] = hashlib.sha256(path.read_bytes()).hexdigest()
        return result

    def export_event(self, event_number: int) -> Path:
        event = self.session.events[int(event_number)]
        folder = self.output_root / f"event_{event_number:06d}"
        folder.mkdir(parents=True, exist_ok=True)
        _write_json(folder / "event_snapshot.json", event.snapshot)
        if event_number > 0:
            _write_json(folder / "previous_event.json", self.session.events[event_number - 1].payload())
        if event_number + 1 < len(self.session.events):
            _write_json(folder / "next_event.json", self.session.events[event_number + 1].payload())
        _write_json(folder / "recommendation_table.json", list(event.recommendations))
        _write_json(folder / "Director_decision.json", event.director_decision)
        _write_json(folder / "bug_flags.json", list(event.bug_flags))
        _write_json(folder / "state_diff.json", self.session.compare(max(0, event_number - 1), event_number))
        _write_json(folder / "brain_state.json", event.snapshot)
        (folder / "trade_story.txt").write_text(
            "\n".join(f"{row['timestamp']}: {row['description']}" for row in event.trade_story_events), encoding="utf-8"
        )
        _chart(self.session, event_number, "M5", folder / "M5_chart.png")
        _chart(self.session, event_number, "M1", folder / "M1_chart.png")
        _write_json(folder / "export_hashes.json", self._hashes(folder))
        return self._zip(folder)

    def export_sequence(self) -> Path:
        folder = self.output_root / "sequence"
        folder.mkdir(parents=True, exist_ok=True)
        _write_json(folder / "replay_manifest.json", self.session.manifest())
        with (folder / "full_event_ledger.jsonl").open("w", encoding="utf-8") as handle:
            for event in self.session.events:
                handle.write(json.dumps(event.payload(), sort_keys=True) + "\n")
        final = len(self.session.events) - 1
        _chart(self.session, final, "M5", folder / "M5_chart.png")
        _chart(self.session, final, "M1", folder / "M1_chart.png")
        _write_json(folder / "sequence_accounting.json", self.session.events[-1].snapshot.get("sequence_accounting"))
        _write_json(folder / "shadow_comparison.json", list(self.session.events[-1].shadow_managers))
        _write_json(folder / "bug_report.json", [flag for event in self.session.events for flag in event.bug_flags])
        self._write_financial_files(folder)
        (folder / "review_notes.txt").write_text(
            "ENTRY: UNCERTAIN\nSTOP: UNCERTAIN\nMANAGEMENT: UNCERTAIN\nREENTRY: UNCERTAIN\nBUG_FLAG_STATUS: UNREVIEWED\nNOTES:\n",
            encoding="utf-8",
        )
        _write_json(folder / "export_hashes.json", self._hashes(folder))
        return self._zip(folder)

    def export_review_package(self, event_number: int) -> Path:
        event = self.session.events[int(event_number)]
        folder = self.output_root / f"chatgpt_review_{event_number:06d}"
        folder.mkdir(parents=True, exist_ok=True)
        _write_json(folder / "replay_manifest.json", self.session.manifest())
        _write_json(folder / "selected_event_snapshot.json", event.snapshot)
        with (folder / "event_window.jsonl").open("w", encoding="utf-8") as handle:
            for item in self.session.events[max(0, event_number - 10): event_number + 11]:
                handle.write(json.dumps(item.payload(), sort_keys=True) + "\n")
        _chart(self.session, event_number, "M5", folder / "M5_chart.png")
        _chart(self.session, event_number, "M1", folder / "M1_chart.png")
        _write_json(folder / "brain_state.json", event.snapshot)
        _write_json(folder / "recommendation_conflict.json", list(event.recommendations))
        _write_json(folder / "Director_decision.json", event.director_decision)
        with (folder / "shadow_comparison.csv").open("w", encoding="utf-8", newline="") as handle:
            rows = list(event.shadow_managers)
            writer = csv.DictWriter(handle, fieldnames=sorted({key for row in rows for key in row}))
            writer.writeheader()
            writer.writerows(rows)
        (folder / "trade_story.txt").write_text(
            "\n".join(row["description"] for row in event.trade_story_events), encoding="utf-8"
        )
        (folder / "review_notes.txt").write_text("Steve review notes:\n", encoding="utf-8")
        _write_json(folder / "export_hashes.json", self._hashes(folder))
        return self._zip(folder)

    def export_full_replay(self) -> Path:
        """Export the complete immutable session, checkpoints and manifest."""
        folder = self.output_root / "full_replay_session"
        folder.mkdir(parents=True, exist_ok=True)
        _write_json(folder / "replay_manifest.json", self.session.manifest())
        _write_json(folder / "checkpoints.json", self.session.checkpoints)
        with (folder / "full_event_ledger.jsonl").open("w", encoding="utf-8") as handle:
            for event in self.session.events:
                handle.write(json.dumps(event.payload(), sort_keys=True) + "\n")
        _write_json(folder / "trade_story.json", self.session.story)
        self._write_financial_files(folder)
        (folder / "manual_review_template.txt").write_text(
            "ENTRY: UNCERTAIN\nSTOP: UNCERTAIN\nMANAGEMENT: UNCERTAIN\n"
            "REENTRY: UNCERTAIN\nBUG_FLAG_STATUS: UNREVIEWED\nNOTES:\n",
            encoding="utf-8",
        )
        _write_json(folder / "export_hashes.json", self._hashes(folder))
        return self._zip(folder)

    def export_financial(self) -> Path:
        folder = self.output_root / "financial_account_package"
        folder.mkdir(parents=True, exist_ok=True)
        _write_json(folder / "replay_manifest.json", self.session.manifest())
        self._write_financial_files(folder)
        _write_json(folder / "export_hashes.json", self._hashes(folder))
        return self._zip(folder)

    @staticmethod
    def _csv(path: Path, rows: list[dict[str, Any]]) -> None:
        flattened = []
        for row in rows:
            flattened.append({
                key: json.dumps(value, sort_keys=True) if isinstance(value, (dict, list)) else value
                for key, value in row.items()
            })
        fields = sorted({key for row in flattened for key in row})
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(flattened)

    def _write_financial_files(self, folder: Path) -> None:
        final = self.session.paper_final or self.session.paper_service.final_payload()
        canonical = final["canonical"]
        ledger = list(canonical.get("execution_ledger") or [])
        equity = list(canonical.get("equity_history") or [])
        attempts = list(canonical.get("attempt_reports") or [])
        metrics = AccountMetrics.calculate(canonical)
        with (folder / "execution_ledger.jsonl").open("w", encoding="utf-8") as handle:
            for row in ledger:
                handle.write(json.dumps(row, sort_keys=True) + "\n")
        self._csv(folder / "execution_ledger.csv", ledger)
        self._csv(folder / "account_statement.csv", ledger)
        self._csv(folder / "equity_curve.csv", equity)
        _write_json(folder / "trade_attempt_report.json", attempts)
        _write_json(folder / "sequence_report.json", metrics.get("sequences"))
        _write_json(folder / "cost_report.json", metrics.get("costs"))
        _write_json(folder / "margin_report.json", [row for row in ledger if row.get("action") in {"MARGIN_WARNING", "MARGIN_CALL", "STOP_OUT"}])
        _write_json(folder / "performance_summary.json", metrics)
        _write_json(folder / "symbol_summary.json", metrics.get("by_symbol"))
        _write_json(folder / "session_summary.json", metrics.get("by_session"))
        _write_json(folder / "shadow_account_comparison.json", final.get("shadows"))
        _write_json(folder / "money_story.json", canonical.get("money_story"))
        _write_json(folder / "financial_bug_report.json", [flag for event in self.session.events for flag in event.bug_flags if flag.get("category") == "FINANCIAL"])
        account = canonical.get("account") or {}
        rows_html = "".join(
            "<tr>" + "".join(f"<td>{html.escape(str(row.get(key, '')))}</td>" for key in ("timestamp", "action", "symbol", "volume", "fill_price", "gross_pl", "net_pl", "balance_after", "equity_after")) + "</tr>"
            for row in ledger
        ) or "<tr><td colspan='9'>No monetary execution events in this replay.</td></tr>"
        statement = f"""<!doctype html><html><head><meta charset='utf-8'><title>SmartStructureBot Paper Account Statement</title><style>
body{{font-family:Segoe UI,Arial;background:#07101d;color:#eaf1fb;margin:0;padding:28px}}main{{max-width:1500px;margin:auto}}h1{{margin-bottom:4px}}.warn{{color:#ffcc78}}.metrics{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:20px 0}}.metric{{background:#111f33;border:1px solid #314966;padding:14px;border-radius:8px}}.metric span{{color:#8da2bb;display:block;font-size:12px}}table{{width:100%;border-collapse:collapse;background:#0c1727}}th,td{{padding:8px;border-bottom:1px solid #243854;text-align:left;font-size:12px}}th{{color:#8da2bb}}footer{{margin-top:20px;color:#8da2bb}}
</style></head><body><main><h1>SmartStructureBot Paper Account Statement</h1><p class='warn'><strong>HISTORICAL PAPER SIMULATION · NOT A BROKER STATEMENT · NO ORDERS EXECUTED</strong></p><div class='metrics'>
<div class='metric'><span>Starting balance</span><strong>R{float(account.get('initial_balance',0)):,.2f}</strong></div><div class='metric'><span>Ending balance</span><strong>R{float(account.get('current_balance',0)):,.2f}</strong></div><div class='metric'><span>Ending equity</span><strong>R{float(account.get('current_equity',0)):,.2f}</strong></div><div class='metric'><span>Maximum drawdown</span><strong>{float(metrics.get('maximum_drawdown_percent',0)):,.2f}%</strong></div></div>
<table><thead><tr><th>Timestamp</th><th>Action</th><th>Symbol</th><th>Volume</th><th>Fill</th><th>Gross P/L</th><th>Net P/L</th><th>Balance</th><th>Equity</th></tr></thead><tbody>{rows_html}</tbody></table>
<footer>Estimated costs where native broker data is unavailable. Historical research only. Past results do not guarantee future performance.</footer></main></body></html>"""
        (folder / "account_statement.html").write_text(statement, encoding="utf-8")

    @staticmethod
    def _zip(folder: Path) -> Path:
        archive = folder.with_suffix(".zip")
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as handle:
            for path in sorted(folder.rglob("*")):
                if path.is_file():
                    handle.write(path, path.relative_to(folder))
        return archive
