"""The companion: eggs hatch, Pokemon evolve, graduate, and fill a Pokedex.

Progress is driven by one monotonic number — lifetime tokens burned across all
Claude Code sessions. Each phase records the lifetime total it began at, so
progress is `lifetime - anchor` and nothing double-counts when the app restarts.

On first run the anchor is set to the current lifetime total, so an existing
3-billion-token history does not instantly graduate a shelf of Pokemon.
"""

from __future__ import annotations

import json
import os
import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .i18n import lang, nature as tr_nature, rarity as tr_rarity, t
from .pokedata import Pokedex

NATURES = [
    "Hardy", "Lonely", "Brave", "Adamant", "Naughty",
    "Bold", "Docile", "Relaxed", "Impish", "Lax",
    "Timid", "Hasty", "Serious", "Jolly", "Naive",
    "Modest", "Mild", "Quiet", "Bashful", "Rash",
    "Calm", "Gentle", "Sassy", "Careful", "Quirky",
]

# Tokens needed for an egg to hatch. Rarity is unknown until it does, so this
# cannot depend on the species.
EGG_HATCH_TOKENS = 25_000_000

# Tokens from hatch to graduation for a Common line. Calibrated so heavy use
# (~100M tokens/day) graduates a common in about three days.
BASE_GRADUATE_TOKENS = 300_000_000

RARITY_MULTIPLIER = {
    "Common": 1.0,
    "Uncommon": 1.6,
    "Rare": 2.7,
    "Very Rare": 4.5,
    "Legendary": 8.0,
}

# Fraction of the graduation total at which each evolution fires, by line length.
EVOLVE_FRACTIONS = {1: [], 2: [0.40], 3: [0.25, 0.60]}

BASE_SHINY_ODDS = 256          # 1 in N
SHINY_CHARM_FACTOR = 0.6       # charm multiplies the denominator

# A Rare Candy is worth this fraction of the current graduation total.
CANDY_VALUE_FRACTION = 0.05

SHOP_PRICES = {
    "rare_candy": 40_000_000,
    "mint": 25_000_000,
    "shiny_charm": 600_000_000,
    "egg_plain": 60_000_000,
    "egg_uncommon": 150_000_000,
    "egg_rare": 400_000_000,
}

# Minimum rarity guaranteed by each graded egg.
EGG_FLOORS = {
    "egg_plain": None,
    "egg_uncommon": ("Uncommon", "Rare", "Very Rare", "Legendary"),
    "egg_rare": ("Rare", "Very Rare", "Legendary"),
}

RARITY_ORDER = ["Common", "Uncommon", "Rare", "Very Rare", "Legendary"]


class SaveUnreadable(Exception):
    """The save exists but could not be parsed.

    Raised rather than handled quietly: starting a fresh egg here would erase a
    player's collection to work around what is usually a transient problem.
    """


@dataclass
class Companion:
    """The Pokemon (or egg) currently being raised."""

    hatched: bool = False
    path: list[int] = field(default_factory=list)   # chosen evolution branch
    stage: int = 0                                  # index into path
    shiny: bool = False
    nature: str = "Hardy"
    rarity: str = "Common"
    anchor: int = 0            # lifetime tokens when this phase started
    bonus: int = 0             # tokens granted by Rare Candy
    born_at: str = ""
    egg_floor: list[str] | None = None

    @property
    def species_id(self) -> int | None:
        return self.path[self.stage] if self.hatched and self.path else None

    def to_dict(self) -> dict:
        return {
            "hatched": self.hatched, "path": self.path, "stage": self.stage,
            "shiny": self.shiny, "nature": self.nature, "rarity": self.rarity,
            "anchor": self.anchor, "bonus": self.bonus, "born_at": self.born_at,
            "egg_floor": self.egg_floor,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Companion":
        return cls(**{k: d.get(k, getattr(cls(), k)) for k in cls().to_dict()})


class Game:
    def __init__(self, dex: Pokedex, path: Path) -> None:
        self.dex = dex
        self.path = path
        self.companion = Companion()
        self.pokedex: dict[int, dict] = {}     # species id -> {"shiny": bool, "count": int}
        self.catch_log: list[dict] = []
        self.candies = 0
        self.mints = 0
        self.shiny_charms = 0
        self.spent = 0                          # tokens spent in the shop
        # Shop currency accrues from install onward, like the companion's
        # progress. Counting a pre-existing multi-billion-token history would
        # make every item affordable on day one.
        self.currency_anchor = 0
        # Rare Candy is only paid for windows that complete after install, for
        # the same reason progress is anchored: a long pre-existing history must
        # not pay out retroactively, and lowering the budget must not either.
        self.started_at = ""
        self.credited_blocks: list[str] = []    # block starts already paid out
        self.initialized = False
        self.rng = random.Random()

    # ---- persistence -----------------------------------------------

    def load(self, lifetime_tokens: int) -> None:
        data = {}
        if self.path.exists() and self.path.stat().st_size > 0:
            try:
                data = json.loads(self.path.read_text(encoding="utf-8-sig"))
            except (OSError, ValueError) as exc:
                # Keep the file exactly as it is so it can be recovered by hand.
                raise SaveUnreadable(str(exc)) from exc
            if not isinstance(data, dict):
                raise SaveUnreadable("save is not a JSON object")

        if data:
            self.companion = Companion.from_dict(data.get("companion", {}))
            self.pokedex = {int(k): v for k, v in data.get("pokedex", {}).items()}
            self.catch_log = data.get("catch_log", [])
            self.candies = data.get("candies", 0)
            self.mints = data.get("mints", 0)
            self.shiny_charms = data.get("shiny_charms", 0)
            self.spent = data.get("spent", 0)
            self.currency_anchor = data.get("currency_anchor", 0)
            self.credited_blocks = data.get("credited_blocks", [])
            self.started_at = data.get("started_at", "")
            if not self.started_at:                  # save from an older version
                self.started_at = datetime.now(timezone.utc).isoformat()
            self.initialized = True
        else:
            # First run: start a fresh egg and an empty wallet from this moment.
            self.companion = Companion(anchor=lifetime_tokens)
            self.currency_anchor = lifetime_tokens
            self.started_at = datetime.now(timezone.utc).isoformat()
            self.initialized = True
            self.save()

    def save(self) -> None:
        payload = {
            "companion": self.companion.to_dict(),
            "pokedex": self.pokedex,
            "catch_log": self.catch_log,
            "candies": self.candies,
            "mints": self.mints,
            "shiny_charms": self.shiny_charms,
            "spent": self.spent,
            "currency_anchor": self.currency_anchor,
            "started_at": self.started_at,
            "credited_blocks": self.credited_blocks,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Per-process temp name: two instances sharing one scratch file could
        # interleave writes and publish a half-written save.
        tmp = self.path.with_name(f"save.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.path)

    # ---- derived numbers -------------------------------------------

    def graduate_total(self) -> int:
        mult = RARITY_MULTIPLIER.get(self.companion.rarity, 1.0)
        return int(BASE_GRADUATE_TOKENS * mult)

    def progress(self, lifetime_tokens: int) -> int:
        return max(0, lifetime_tokens - self.companion.anchor) + self.companion.bonus

    def goal(self) -> int:
        """Tokens needed to reach the next milestone (hatch, evolve, graduate)."""
        c = self.companion
        if not c.hatched:
            return EGG_HATCH_TOKENS
        total = self.graduate_total()
        fractions = EVOLVE_FRACTIONS.get(len(c.path), [])
        if c.stage < len(fractions):
            return int(total * fractions[c.stage])
        return total

    def currency(self, lifetime_tokens: int) -> int:
        return max(0, lifetime_tokens - self.currency_anchor - self.spent)

    # ---- the loop --------------------------------------------------

    def update(self, lifetime_tokens: int, completed_blocks: list) -> list[str]:
        """Advance the companion. Returns human-readable event lines."""
        events: list[str] = []
        events.extend(self._award_candies(completed_blocks))

        # A single update can cross several milestones at once (the app may
        # have been closed for days), so loop until nothing more fires.
        for _ in range(64):
            c = self.companion
            progress = self.progress(lifetime_tokens)
            if progress < self.goal():
                break
            if not c.hatched:
                events.append(self._hatch(lifetime_tokens))
            elif c.stage < len(c.path) - 1:
                events.append(self._evolve())
            else:
                events.append(self._graduate(lifetime_tokens))

        if events:
            self.save()
        return events

    def _award_candies(self, completed_blocks: list) -> list[str]:
        events = []
        try:
            since = datetime.fromisoformat(self.started_at)
        except ValueError:
            since = datetime.now(timezone.utc)
        for block in completed_blocks:
            if block.end <= since:
                continue          # finished before this install; not our reward
            key = block.start.isoformat()
            if key in self.credited_blocks:
                continue
            self.credited_blocks.append(key)
            self.candies += 1
            events.append(t("ev.candy_earned"))
        # Keep the ledger bounded.
        self.credited_blocks = self.credited_blocks[-500:]
        return events

    def _roll_species(self, floor: list[str] | None) -> int:
        pool = self.dex.bases
        if floor:
            allowed = set(floor)
            filtered = [sid for sid in pool if self.dex.species[sid].rarity in allowed]
            pool = filtered or pool
        weights = [self.dex.species[sid].capture_rate for sid in pool]
        return self.rng.choices(pool, weights=weights, k=1)[0]

    def _hatch(self, lifetime_tokens: int) -> str:
        c = self.companion
        base = self._roll_species(c.egg_floor)
        species = self.dex.species[base]

        odds = BASE_SHINY_ODDS * (SHINY_CHARM_FACTOR ** self.shiny_charms)
        c.shiny = self.rng.random() < 1 / max(1.0, odds)
        c.nature = self.rng.choice(NATURES)
        c.path = self.dex.evolution_path(base, self.rng)
        c.stage = 0
        c.hatched = True
        c.rarity = species.rarity
        c.anchor = lifetime_tokens
        c.bonus = 0
        c.egg_floor = None
        c.born_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

        self._record(base)
        return t("ev.hatched", name=species.name(lang()), rarity=tr_rarity(c.rarity),
                 nature=tr_nature(c.nature),
                 shiny=t("ev.shiny_suffix") if c.shiny else "")

    def _evolve(self) -> str:
        c = self.companion
        before = self.dex.species[c.path[c.stage]].name(lang())
        c.stage += 1
        after_species = self.dex.species[c.path[c.stage]]
        self._record(after_species.id)
        return t("ev.evolved", before=before, after=after_species.name(lang()))

    def _graduate(self, lifetime_tokens: int) -> str:
        c = self.companion
        final = self.dex.species[c.path[-1]]
        self.catch_log.insert(0, {
            "line": c.path,
            "final": final.id,
            "shiny": c.shiny,
            "nature": c.nature,
            "rarity": c.rarity,
            "caught_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        })
        self.catch_log = self.catch_log[:300]
        name = final.name(lang())
        self.companion = Companion(anchor=lifetime_tokens)
        return t("ev.graduated", name=name)

    def _record(self, species_id: int) -> None:
        entry = self.pokedex.setdefault(species_id, {"shiny": False, "count": 0})
        entry["count"] += 1
        if self.companion.shiny:
            entry["shiny"] = True

    # ---- bag & shop ------------------------------------------------

    def use_candy(self) -> str | None:
        if self.candies <= 0:
            return None
        if not self.companion.hatched:
            return t("ev.candy_need")
        self.candies -= 1
        self.companion.bonus += int(self.graduate_total() * CANDY_VALUE_FRACTION)
        self.save()
        return t("ev.candy_used")

    def use_mint(self) -> str | None:
        if self.mints <= 0:
            return None
        if not self.companion.hatched:
            return t("ev.mint_need")
        self.mints -= 1
        old = self.companion.nature
        choices = [n for n in NATURES if n != old]
        self.companion.nature = self.rng.choice(choices)
        self.save()
        return t("ev.mint_used", old=tr_nature(old), new=tr_nature(self.companion.nature))

    def buy(self, item: str, lifetime_tokens: int) -> str:
        price = SHOP_PRICES.get(item)
        if price is None:
            return t("ev.unknown_item")
        if self.currency(lifetime_tokens) < price:
            return t("ev.too_poor")
        self.spent += price

        if item == "rare_candy":
            self.candies += 1
            msg = t("ev.bought", item=t("item.rare_candy"))
        elif item == "mint":
            self.mints += 1
            msg = t("ev.bought", item=t("item.mint"))
        elif item == "shiny_charm":
            self.shiny_charms += 1
            msg = t("ev.charm_bought", odds=f"{self.shiny_odds():.0f}")
        else:
            floor = EGG_FLOORS.get(item)
            self.companion = Companion(
                anchor=lifetime_tokens,
                egg_floor=list(floor) if floor else None,
            )
            msg = t("ev.egg_bought", item=t(f"item.{item}"))
        self.save()
        return msg

    def shiny_odds(self) -> float:
        return BASE_SHINY_ODDS * (SHINY_CHARM_FACTOR ** self.shiny_charms)
