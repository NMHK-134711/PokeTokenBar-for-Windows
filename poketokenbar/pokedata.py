"""Species, evolution lines, and sprites, sourced from PokeAPI at runtime.

Two CSVs from the PokeAPI repo carry everything the game needs — evolution
parentage, capture rates, legendary flags, and localized names — so we fetch
those once instead of making 649 REST calls. Sprites are the Gen-V animated
GIFs, fetched lazily and cached on disk.

Nothing Pokemon-related is bundled with this program; it is all fetched at
runtime and cached under the user's local app data, same as the original.
"""

from __future__ import annotations

import csv
import io
import threading
from dataclasses import dataclass, field
from pathlib import Path

import requests

CSV_BASE = "https://raw.githubusercontent.com/PokeAPI/pokeapi/master/data/v2/csv"
SPRITE_BASE = (
    "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon"
    "/versions/generation-v/black-white/animated"
)
ITEM_BASE = "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/items"
EGG_URL = "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/egg.png"

MAX_GENERATION = 5          # Gen 1-5 have animated sprites
LANG_EN, LANG_KO = "9", "3"

# capture_rate -> rarity. Lower capture rate means harder to catch, so rarer.
RARITY_TIERS = [
    (150, "Common"),
    (90, "Uncommon"),
    (45, "Rare"),
    (0, "Very Rare"),
]


@dataclass(slots=True)
class Species:
    id: int
    identifier: str
    generation: int
    evolves_from: int | None
    chain_id: int
    capture_rate: int
    is_legendary: bool
    is_mythical: bool
    names: dict[str, str] = field(default_factory=dict)
    children: list[int] = field(default_factory=list)

    def name(self, lang: str = "en") -> str:
        key = LANG_KO if lang == "ko" else LANG_EN
        return self.names.get(key) or self.identifier.replace("-", " ").title()

    @property
    def rarity(self) -> str:
        if self.is_legendary or self.is_mythical:
            return "Legendary"
        for threshold, label in RARITY_TIERS:
            if self.capture_rate >= threshold:
                return label
        return "Very Rare"


class Pokedex:
    """The full Gen 1-5 species table plus lazily-fetched sprites."""

    def __init__(self, cache_dir: Path) -> None:
        self.cache_dir = cache_dir
        self.sprite_dir = cache_dir / "sprites"
        self.item_dir = cache_dir / "items"
        self.sprite_dir.mkdir(parents=True, exist_ok=True)
        self.item_dir.mkdir(parents=True, exist_ok=True)
        self.species: dict[int, Species] = {}
        self.bases: list[int] = []
        self._lock = threading.Lock()

    # ---- data ------------------------------------------------------

    def _fetch_csv(self, name: str) -> str:
        path = self.cache_dir / f"{name}.csv"
        if path.exists() and path.stat().st_size > 0:
            return path.read_text(encoding="utf-8")
        resp = requests.get(f"{CSV_BASE}/{name}.csv", timeout=30)
        resp.raise_for_status()
        text = resp.content.decode("utf-8")
        path.write_text(text, encoding="utf-8")
        return text

    def load(self) -> None:
        """Populate the species table. Safe to call more than once."""
        if self.species:
            return

        rows = csv.DictReader(io.StringIO(self._fetch_csv("pokemon_species")))
        for row in rows:
            gen = int(row["generation_id"])
            if gen > MAX_GENERATION:
                continue
            sid = int(row["id"])
            parent = row["evolves_from_species_id"]
            self.species[sid] = Species(
                id=sid,
                identifier=row["identifier"],
                generation=gen,
                evolves_from=int(parent) if parent else None,
                chain_id=int(row["evolution_chain_id"]),
                capture_rate=int(row["capture_rate"]),
                is_legendary=row["is_legendary"] == "1",
                is_mythical=row["is_mythical"] == "1",
            )

        names = csv.DictReader(io.StringIO(self._fetch_csv("pokemon_species_names")))
        for row in names:
            sid = int(row["pokemon_species_id"])
            sp = self.species.get(sid)
            if sp and row["local_language_id"] in (LANG_EN, LANG_KO):
                sp.names[row["local_language_id"]] = row["name"]

        for sp in self.species.values():
            if sp.evolves_from is not None:
                parent = self.species.get(sp.evolves_from)
                if parent:
                    parent.children.append(sp.id)

        self.bases = sorted(
            sid for sid, sp in self.species.items() if sp.evolves_from is None
        )

    # ---- evolution -------------------------------------------------

    def evolution_path(self, base_id: int, rng) -> list[int]:
        """Walk one concrete branch of a species' evolution tree.

        Branching lines (Eevee, Tyrogue, Wurmple) pick a single branch at hatch
        time so the companion has a definite future to grow into.
        """
        path = [base_id]
        current = self.species[base_id]
        while current.children:
            nxt = rng.choice(sorted(current.children))
            path.append(nxt)
            current = self.species[nxt]
        return path

    # ---- sprites ---------------------------------------------------

    def sprite_path(self, species_id: int, shiny: bool) -> Path | None:
        """Local path to an animated sprite, downloading it on first use."""
        name = f"{species_id}{'-shiny' if shiny else ''}.gif"
        url = f"{SPRITE_BASE}/{'shiny/' if shiny else ''}{species_id}.gif"
        return self._cached(self.sprite_dir / name, url)

    def item_sprite_path(self, item_name: str) -> Path | None:
        """Local path to a PokeAPI item sprite (e.g. 'rare-candy')."""
        return self._cached(self.item_dir / f"{item_name}.png",
                            f"{ITEM_BASE}/{item_name}.png")

    def egg_sprite_path(self) -> Path | None:
        """The egg shown before a companion hatches, fetched like any sprite."""
        return self._cached(self.item_dir / "egg.png", EGG_URL)

    def _cached(self, path: Path, url: str) -> Path | None:
        """Return `path`, fetching `url` into it the first time it is needed."""
        if path.exists() and path.stat().st_size > 0:
            return path
        with self._lock:
            if path.exists() and path.stat().st_size > 0:
                return path
            try:
                resp = requests.get(url, timeout=30)
                resp.raise_for_status()
            except requests.RequestException:
                return None
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(resp.content)
        return path
