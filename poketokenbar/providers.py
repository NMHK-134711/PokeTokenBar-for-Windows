"""Where usage comes from: one class per coding agent.

Each source knows which files to scan and how to turn a line into an `Entry`.
`UsageReader` owns the per-file caching, so adding an agent means adding a class
here and nothing else.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .entry import Entry, price

CLAUDE_PROJECTS = Path.home() / ".claude" / "projects"
CODEX_SESSIONS = Path.home() / ".codex" / "sessions"


def _iso(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        ts = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


@dataclass
class Limit:
    """A rate-limit window an agent reports about itself."""

    used_percent: float
    window_minutes: int
    resets_at: datetime | None

    @property
    def is_weekly(self) -> bool:
        return self.window_minutes > 24 * 60


class Source:
    """Base class. Subclasses declare where the logs are and how to read them."""

    name = ""
    label = ""

    @property
    def root(self) -> Path:
        raise NotImplementedError

    def available(self) -> bool:
        return self.root.exists()

    def files(self) -> list[Path]:
        raise NotImplementedError

    def parse(self, path: Path) -> list[tuple[tuple, Entry]]:
        raise NotImplementedError

    def limits(self) -> tuple[Limit | None, Limit | None]:
        """Official (5-hour, weekly) windows, when the agent records them."""
        return None, None


class ClaudeSource(Source):
    """Claude Code writes one JSONL per session under ~/.claude/projects."""

    name = "claude"
    label = "Claude Code"

    @property
    def root(self) -> Path:
        return CLAUDE_PROJECTS

    def files(self) -> list[Path]:
        return sorted(self.root.glob("*/*.jsonl"))

    def parse(self, path: Path) -> list[tuple[tuple, Entry]]:
        out: list[tuple[tuple, Entry]] = []
        try:
            fh = path.open(encoding="utf-8", errors="replace")
        except OSError:
            return out
        with fh:
            for line in fh:
                if '"usage"' not in line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if rec.get("type") != "assistant":
                    continue
                msg = rec.get("message") or {}
                usage = msg.get("usage")
                if not usage:
                    continue
                model = msg.get("model") or ""
                if model == "<synthetic>":
                    continue
                ts = _iso(rec.get("timestamp"))
                if ts is None:
                    continue

                inp = int(usage.get("input_tokens") or 0)
                out_tok = int(usage.get("output_tokens") or 0)
                cache_r = int(usage.get("cache_read_input_tokens") or 0)
                created = usage.get("cache_creation") or {}
                w5 = int(created.get("ephemeral_5m_input_tokens") or 0)
                w1h = int(created.get("ephemeral_1h_input_tokens") or 0)
                if not (w5 or w1h):
                    w5 = int(usage.get("cache_creation_input_tokens") or 0)

                cost = price(model, ts, inp, out_tok, w5, w1h, cache_r)
                key = ("claude", msg.get("id") or "", rec.get("requestId") or "")
                out.append((key, Entry(ts, model, inp, out_tok, w5, w1h, cache_r,
                                       cost, "claude")))
        return out


class CodexSource(Source):
    """Codex writes rollout JSONLs under ~/.codex/sessions/YYYY/MM/DD.

    Usage arrives as `event_msg` records whose payload type is `token_count`,
    carrying both a per-turn `last_token_usage` and a running
    `total_token_usage`. We difference the running total rather than summing the
    per-turn figure: Codex re-emits `token_count` without new work fairly often
    (74 repeats in a 474-event session here), and summing double-counts those —
    18% high on this machine's log. Differencing the cumulative field reproduces
    the session's own final total exactly.

    `cached_input_tokens` is already part of `input_tokens`, and
    `reasoning_output_tokens` is part of `output_tokens`, so the token total is
    input + output.

    Codex also records its own rate-limit percentages, which is why this source
    can report official 5-hour and weekly windows where Claude cannot.
    """

    name = "codex"
    label = "Codex"

    def __init__(self) -> None:
        self._primary: Limit | None = None
        self._secondary: Limit | None = None
        self._limit_seen: datetime | None = None

    @property
    def root(self) -> Path:
        return CODEX_SESSIONS

    def files(self) -> list[Path]:
        return sorted(self.root.glob("**/*.jsonl"))

    def parse(self, path: Path) -> list[tuple[tuple, Entry]]:
        out: list[tuple[tuple, Entry]] = []
        try:
            fh = path.open(encoding="utf-8", errors="replace")
        except OSError:
            return out
        running = {"input_tokens": 0, "output_tokens": 0, "cached_input_tokens": 0}
        with fh:
            for index, line in enumerate(fh):
                if '"token_count"' not in line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if rec.get("type") != "event_msg":
                    continue
                payload = rec.get("payload") or {}
                if payload.get("type") != "token_count":
                    continue
                ts = _iso(rec.get("timestamp"))
                if ts is None:
                    continue

                self._absorb_limits(payload.get("rate_limits"), ts)

                totals = (payload.get("info") or {}).get("total_token_usage")
                if not totals:
                    continue

                delta = {}
                for name in running:
                    cur = int(totals.get(name) or 0)
                    prev = running[name]
                    # A drop means the session restarted its accounting (a
                    # rollback); the new value is then the delta on its own.
                    delta[name] = cur - prev if cur >= prev else cur
                    running[name] = cur

                inp, out_tok = delta["input_tokens"], delta["output_tokens"]
                cached = delta["cached_input_tokens"]
                if inp <= 0 and out_tok <= 0:
                    continue                      # a re-emitted event, no new work
                # Report the cached slice separately so the UI can show it, but
                # subtract it from input so the total is not counted twice.
                uncached = max(0, inp - cached)
                # Codex records no per-model price, so cost is left at zero
                # rather than invented.
                out.append((
                    ("codex", str(path), index),
                    Entry(ts, "codex", uncached, max(0, out_tok), 0, 0,
                          max(0, cached), 0.0, "codex"),
                ))
        return out

    def _absorb_limits(self, raw, ts: datetime) -> None:
        if not raw or (self._limit_seen and ts <= self._limit_seen):
            return
        self._limit_seen = ts
        self._primary = _limit(raw.get("primary"))
        self._secondary = _limit(raw.get("secondary"))

    def limits(self) -> tuple[Limit | None, Limit | None]:
        return self._primary, self._secondary


def _limit(raw) -> Limit | None:
    if not raw:
        return None
    resets = raw.get("resets_at")
    when = None
    if isinstance(resets, (int, float)):
        when = datetime.fromtimestamp(resets, tz=timezone.utc)
    try:
        used = float(raw.get("used_percent") or 0.0)
        window = int(raw.get("window_minutes") or 0)
    except (TypeError, ValueError):
        return None
    return Limit(used, window, when)


def all_sources() -> list[Source]:
    return [ClaudeSource(), CodexSource()]
