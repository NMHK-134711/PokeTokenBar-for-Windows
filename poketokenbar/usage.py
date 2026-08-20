"""Aggregate local agent usage: totals, 5-hour blocks, and rolling windows.

No external CLI and no network — everything comes from the JSONL session logs
the agents already write. See `providers.py` for the per-agent readers.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .entry import Entry
from .providers import CLAUDE_PROJECTS, Limit, Source, all_sources

__all__ = [
    "CLAUDE_PROJECTS", "Block", "Entry", "Limit", "UsageReader",
    "compact", "parse_anchor",
]

BLOCK_HOURS = 5


@dataclass(slots=True)
class Block:
    """A 5-hour usage window, the unit Claude's rate limits use."""

    start: datetime
    end: datetime
    entries: list[Entry] = field(default_factory=list)

    @property
    def tokens(self) -> int:
        return sum(e.total for e in self.entries)

    @property
    def cost(self) -> float:
        return sum(e.cost for e in self.entries)

    def is_active(self, now: datetime) -> bool:
        return self.start <= now < self.end


class UsageReader:
    """Scans every available agent's logs, re-reading only files that changed."""

    def __init__(self, sources: list[Source] | None = None) -> None:
        self.sources = sources if sources is not None else all_sources()
        self._cache: dict[str, tuple[float, int, list[tuple[tuple, Entry]]]] = {}
        self.entries: list[Entry] = []

    # ---- scanning ---------------------------------------------------

    def detected(self) -> list[Source]:
        """Sources that actually have a log directory on this machine."""
        return [s for s in self.sources if s.available()]

    def refresh(self) -> None:
        collected: list[tuple[tuple, Entry]] = []
        live: set[str] = set()

        for source in self.sources:
            if not source.available():
                continue
            for path in source.files():
                cache_key = f"{source.name}:{path}"
                live.add(cache_key)
                try:
                    st = path.stat()
                except OSError:
                    continue
                cached = self._cache.get(cache_key)
                if cached and cached[0] == st.st_mtime and cached[1] == st.st_size:
                    collected.extend(cached[2])
                else:
                    pairs = source.parse(path)
                    self._cache[cache_key] = (st.st_mtime, st.st_size, pairs)
                    collected.extend(pairs)

        for stale in set(self._cache) - live:
            del self._cache[stale]

        # Dedupe globally: the same message can appear in more than one file
        # when a session is resumed or forked.
        seen: set[tuple] = set()
        entries: list[Entry] = []
        for key, entry in collected:
            if key in seen:
                continue
            seen.add(key)
            entries.append(entry)

        entries.sort(key=lambda e: e.ts)
        self.entries = entries

    def limits(self, provider: str) -> tuple[Limit | None, Limit | None]:
        for s in self.sources:
            if s.name == provider:
                return s.limits()
        return None, None

    # ---- aggregates -------------------------------------------------

    def _scope(self, provider: str | None) -> list[Entry]:
        if provider is None:
            return self.entries
        return [e for e in self.entries if e.provider == provider]

    def _since(self, since: datetime, provider: str | None) -> list[Entry]:
        return [e for e in self._scope(provider) if e.ts >= since]

    def today(self, provider: str | None = None) -> tuple[int, float]:
        """Tokens and cost since local midnight."""
        midnight = datetime.now().astimezone().replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        window = self._since(midnight.astimezone(timezone.utc), provider)
        return sum(e.total for e in window), sum(e.cost for e in window)

    def rolling(self, days: int, provider: str | None = None) -> tuple[int, float]:
        since = datetime.now(timezone.utc) - timedelta(days=days)
        window = self._since(since, provider)
        return sum(e.total for e in window), sum(e.cost for e in window)

    def lifetime(self, provider: str | None = None) -> tuple[int, float]:
        scope = self._scope(provider)
        return sum(e.total for e in scope), sum(e.cost for e in scope)

    def blocks(self, anchor: datetime | None = None,
               provider: str | None = None) -> list[Block]:
        """Group entries into 5-hour windows.

        Without an anchor, a block opens at the top of the hour containing its
        first entry and runs 5 hours; a gap of 5 hours also starts a new one.
        That mirrors how the real limit works — the window starts when you send
        the first message after the previous one lapsed.

        With an anchor (one boundary the user read off `/usage`), windows fall on
        a fixed 5-hour grid through that instant instead, so the app agrees with
        the clock time they actually see.
        """
        span = timedelta(hours=BLOCK_HOURS)
        entries = self._scope(provider)
        blocks: list[Block] = []

        if anchor is not None:
            by_start: dict[datetime, Block] = {}
            for e in entries:
                steps = math.floor((e.ts - anchor) / span)
                start = anchor + steps * span
                block = by_start.get(start)
                if block is None:
                    block = Block(start, start + span)
                    by_start[start] = block
                    blocks.append(block)
                block.entries.append(e)
            blocks.sort(key=lambda b: b.start)
            return blocks

        current: Block | None = None
        prev_ts: datetime | None = None
        for e in entries:
            start_new = (
                current is None
                or e.ts >= current.end
                or (prev_ts is not None and e.ts - prev_ts >= span)
            )
            if start_new:
                start = e.ts.replace(minute=0, second=0, microsecond=0)
                current = Block(start, start + span)
                blocks.append(current)
            current.entries.append(e)
            prev_ts = e.ts
        return blocks

    def active_block(self, anchor: datetime | None = None,
                     provider: str | None = None) -> Block | None:
        now = datetime.now(timezone.utc)
        for b in reversed(self.blocks(anchor, provider)):
            if b.is_active(now):
                return b
        return None


def parse_anchor(text: str) -> datetime | None:
    """Turn a user-entered "HH:MM" into a concrete window boundary.

    Any one boundary defines the whole grid, so today's local date is fine as
    the carrier; the 5-hour steps extend from it in both directions.
    """
    text = (text or "").strip()
    if not text:
        return None
    for sep in (":", "."):
        if sep in text:
            hh, _, mm = text.partition(sep)
            break
    else:
        hh, mm = text, "0"
    try:
        hour, minute = int(hh), int(mm or 0)
    except ValueError:
        return None
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    local = datetime.now().astimezone().replace(
        hour=hour, minute=minute, second=0, microsecond=0
    )
    return local.astimezone(timezone.utc)


def compact(n: int) -> str:
    """200_712_345 -> '200.7M', the menu-bar format."""
    for limit, suffix in ((1_000_000_000, "B"), (1_000_000, "M"), (1_000, "K")):
        if abs(n) >= limit:
            return f"{n / limit:.1f}{suffix}"
    return str(n)
