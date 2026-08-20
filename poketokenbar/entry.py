"""One API call's worth of usage, and what it would cost at list price."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

# USD per 1,000,000 tokens: (input, output).
# Cache writes bill at 1.25x input for the 5-minute TTL and 2x for the 1-hour
# TTL; cache reads bill at 0.1x input.
PRICING: dict[str, tuple[float, float]] = {
    "claude-fable-5": (10.00, 50.00),
    "claude-mythos-5": (10.00, 50.00),
    "claude-opus-5": (5.00, 25.00),
    "claude-opus-4-8": (5.00, 25.00),
    "claude-opus-4-7": (5.00, 25.00),
    "claude-opus-4-6": (5.00, 25.00),
    "claude-opus-4-5": (5.00, 25.00),
    "claude-sonnet-5": (3.00, 15.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-sonnet-4-5": (3.00, 15.00),
    "claude-haiku-4-5": (1.00, 5.00),
}

# Claude Sonnet 5 introductory pricing runs through 2026-08-31.
SONNET_5_INTRO_UNTIL = datetime(2026, 9, 1, tzinfo=timezone.utc)
SONNET_5_INTRO = (2.00, 10.00)

CACHE_WRITE_5M = 1.25
CACHE_WRITE_1H = 2.00
CACHE_READ = 0.10


def rates(model: str, when: datetime) -> tuple[float, float] | None:
    if model == "claude-sonnet-5" and when < SONNET_5_INTRO_UNTIL:
        return SONNET_5_INTRO
    base = PRICING.get(model)
    if base:
        return base
    # Unknown model id: fall back to the closest family we recognise so a newly
    # released Claude model does not silently count as free. Non-Claude agents
    # fall through to None, which means "tokens tracked, cost not estimated".
    for prefix, rate in (("claude-fable", (10.0, 50.0)),
                         ("claude-opus", (5.0, 25.0)),
                         ("claude-sonnet", (3.0, 15.0)),
                         ("claude-haiku", (1.0, 5.0))):
        if model.startswith(prefix):
            return rate
    return None


def price(model: str, when: datetime, inp: int, out: int,
          cache_w5: int, cache_w1h: int, cache_r: int) -> float:
    r = rates(model, when)
    if r is None:
        return 0.0
    rin, rout = r
    return (
        inp * rin
        + out * rout
        + cache_w5 * rin * CACHE_WRITE_5M
        + cache_w1h * rin * CACHE_WRITE_1H
        + cache_r * rin * CACHE_READ
    ) / 1_000_000


@dataclass(slots=True)
class Entry:
    """One assistant API call."""

    ts: datetime          # UTC
    model: str
    inp: int
    out: int
    cache_w5: int
    cache_w1h: int
    cache_r: int
    cost: float
    provider: str = "claude"

    @property
    def total(self) -> int:
        """Total tokens, matching the original app: input + output + cache."""
        return self.inp + self.out + self.cache_w5 + self.cache_w1h + self.cache_r
