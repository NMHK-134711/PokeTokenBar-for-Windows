"""Application core: config, the refresh loop, and sprite frame loading."""

from __future__ import annotations

import json
import os
import sys
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

from .game import Game, SaveUnreadable
from .i18n import set_lang, t
from .pokedata import Pokedex
from .usage import CLAUDE_PROJECTS, UsageReader, compact, parse_anchor

ALL = "all"          # scope key for the combined view


# Item key -> PokeAPI item sprite name. PokeAPI has no mint sprite of any
# flavour, so the Mint borrows Ability Urge, which reads as a small lozenge.
ITEM_SPRITES = {
    "rare_candy": "rare-candy",
    "shiny_charm": "shiny-charm",
    "mint": "ability-urge",
}


def _fit(src: Image.Image, size: int) -> Image.Image:
    """Scale an icon into a size x size box, keeping aspect and pixel crispness."""
    scale = min(size / src.width, size / src.height)
    w, h = max(1, round(src.width * scale)), max(1, round(src.height * scale))
    resample = Image.NEAREST if scale >= 2 else Image.LANCZOS
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    resized = src.resize((w, h), resample)
    out.paste(resized, ((size - w) // 2, (size - h) // 2), resized)
    return out


def _brief(exc: BaseException, limit: int = 140) -> str:
    """Exception text short enough for a label; network errors are enormous."""
    text = " ".join(str(exc).split()) or type(exc).__name__
    return text if len(text) <= limit else text[: limit - 1] + "…"


def asset_dir() -> Path:
    """Where bundled images live, in a source checkout or inside the exe.

    PyInstaller's one-file build unpacks data files to a temp dir it points at
    with sys._MEIPASS, so the packaged path is not next to this module.
    """
    base = getattr(sys, "_MEIPASS", None)
    return Path(base) / "assets" if base else Path(__file__).resolve().parent / "assets"


_EGG_CACHE: dict[int, Image.Image] = {}


def egg_image(size: int, dex=None) -> Image.Image:
    """The egg shown before a companion hatches, scaled to `size`.

    Resolved in order: a PNG the user dropped into `assets/`, then the PokeAPI
    egg sprite fetched and cached at runtime, then a drawing of our own. Nothing
    Pokemon-derived is bundled, which keeps the binary free of game artwork.
    """
    if size in _EGG_CACHE:
        return _EGG_CACHE[size]

    src: Image.Image | None = None
    override = asset_dir() / "egg.png"
    if override.exists():
        try:
            src = Image.open(override).convert("RGBA")
        except OSError:
            src = None
    if src is None and dex is not None:
        path = dex.egg_sprite_path()
        if path is not None:
            try:
                src = Image.open(path).convert("RGBA")
            except OSError:
                src = None

    if src is None:
        img = _draw_egg(size)
    else:
        box = src.getbbox()            # the sprite sits in a lot of empty space
        img = _fit(src.crop(box) if box else src, size)
    _EGG_CACHE[size] = img
    return img


def _draw_egg(size: int) -> Image.Image:
    """Vector-ish fallback egg, used only if the asset cannot be loaded."""
    from PIL import ImageDraw

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pad = size // 6
    d.ellipse(
        [pad, pad // 2, size - pad, size - pad // 2],
        fill=(246, 238, 217, 255), outline=(180, 160, 120, 255),
        width=max(2, size // 32),
    )
    for i in range(3):
        y = size // 2 + i * size // 8
        d.arc([pad + size // 12, y - size // 10, size - pad - size // 12, y + size // 10],
              200, 340, fill=(210, 188, 140, 255), width=max(2, size // 40))
    return img


def data_dir() -> Path:
    root = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(root) / "PokeTokenBarWin"


@dataclass
class Config:
    refresh_minutes: int = 3
    # There is no supported API for the real 5-hour / weekly caps, so these are
    # user-set token budgets. Filling one earns a Rare Candy.
    block_limit_tokens: int = 120_000_000
    weekly_limit_tokens: int = 2_000_000_000
    # One boundary of your real 5-hour window as "HH:MM" (read it off
    # `/usage`). Empty means derive the windows from activity instead.
    block_anchor: str = ""
    language: str = "ko"            # "ko" or "en"
    show_cost: bool = True
    show_percent: bool = True
    floating_pet: bool = False
    pet_size: int = 96
    # Where the user dragged the pet. -1 means "pick a default corner"; storing
    # it keeps the pet put across restarts and sidesteps display-scaling maths.
    pet_x: int = -1
    pet_y: int = -1
    animate_tray: bool = True

    @classmethod
    def load(cls, path: Path) -> "Config":
        """Read the config, tolerating a BOM, unknown keys, and missing keys.

        A file written by an older version simply lacks the newer fields; the
        dataclass defaults fill them in, and App.__init__ writes the file back
        complete, so upgrading never strands a half-populated config.
        """
        if path.exists():
            try:
                raw = json.loads(path.read_text(encoding="utf-8-sig"))
                known = {k: v for k, v in raw.items() if k in cls.__annotations__}
                return cls(**known)
            except (OSError, ValueError, TypeError):
                pass
        return cls()

    def matches_file(self, path: Path) -> bool:
        """True if `path` already holds exactly these settings."""
        try:
            return json.loads(path.read_text(encoding="utf-8-sig")) == asdict(self)
        except (OSError, ValueError):
            return False

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=1), encoding="utf-8")


@dataclass
class ScopeStats:
    """Usage figures for one agent, or for all of them combined."""

    today_tokens: int = 0
    today_cost: float = 0.0
    week_tokens: int = 0
    week_cost: float = 0.0
    month_tokens: int = 0
    month_cost: float = 0.0
    lifetime_tokens: int = 0
    lifetime_cost: float = 0.0
    block_tokens: int = 0
    block_cost: float = 0.0
    block_ends: datetime | None = None
    block_percent: float = 0.0
    week_percent: float = 0.0
    burn_per_hour: float = 0.0
    eta_key: str = "eta.none"          # i18n key, resolved at render time
    eta_time: str = ""
    # True when the percentages come from the agent's own reported limits
    # rather than a budget the user typed in.
    official: bool = False
    priced: bool = True                # False when cost is not estimated

    def eta(self) -> str:
        return t(self.eta_key, time=self.eta_time) if self.eta_time else t(self.eta_key)


@dataclass
class Snapshot:
    """Everything the UI needs for one render pass."""

    scopes: dict[str, ScopeStats] = field(default_factory=dict)
    providers: list[tuple[str, str]] = field(default_factory=list)  # (name, label)
    no_logs: bool = False

    def scope(self, name: str) -> ScopeStats:
        return self.scopes.get(name) or self.scopes.get(ALL) or ScopeStats()

    @property
    def combined(self) -> ScopeStats:
        return self.scope(ALL)

    # The companion is raised by everything you burn, whichever agent it was.
    @property
    def lifetime_tokens(self) -> int:
        return self.combined.lifetime_tokens

    def menu_text(self, cfg: Config) -> str:
        c = self.combined
        bits = [compact(c.today_tokens)]
        if cfg.show_cost and c.today_cost:
            bits.append(f"${c.today_cost:,.2f}")
        if cfg.show_percent:
            bits.append(f"{c.block_percent * 100:.0f}%")
        return "  ".join(bits)


class App:
    """Owns the data, the game, and the background refresh."""

    def __init__(self) -> None:
        self.dir = data_dir()
        self.dir.mkdir(parents=True, exist_ok=True)
        self.config_path = self.dir / "config.json"
        self.config = Config.load(self.config_path)
        if not self.config.matches_file(self.config_path):
            # First run, or a file from an older version missing newer keys.
            self.config.save(self.config_path)
        set_lang(self.config.language)

        self.reader = UsageReader()
        self.dex = Pokedex(self.dir / "cache")
        self.game = Game(self.dex, self.dir / "save.json")

        self.snapshot = Snapshot()
        self.events: list[str] = []
        self.ready = False
        self.error: str | None = None
        self.listeners: list = []
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._frame_cache: dict[tuple[int, bool], list[Image.Image]] = {}
        self._still_cache: dict[tuple[int, bool, int], Image.Image] = {}
        self._item_cache: dict[tuple[str, int], Image.Image] = {}

    # ---- lifecycle -------------------------------------------------

    def start(self) -> None:
        threading.Thread(target=self._loop, name="poke-refresh", daemon=True).start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()

    def request_refresh(self) -> None:
        self._wake.set()

    def _loop(self) -> None:
        try:
            self.dex.load()
        except Exception as exc:                      # network or disk failure
            self.error = t("err.dexload", err=_brief(exc))
            self._notify()
            return

        while not self._stop.is_set():
            try:
                self.refresh()
            except Exception as exc:
                self.error = t("err.refresh", err=_brief(exc))
                self._notify()
            interval = max(1, self.config.refresh_minutes) * 60
            self._wake.wait(interval)
            self._wake.clear()

    def refresh(self) -> None:
        self.reader.refresh()
        anchor = parse_anchor(self.config.block_anchor)
        now = datetime.now(timezone.utc)

        detected = self.reader.detected()
        snap = Snapshot(providers=[(s.name, s.label) for s in detected])
        snap.no_logs = not self.reader.entries and not CLAUDE_PROJECTS.exists()

        names = [ALL] + [s.name for s in detected]
        for name in names:
            provider = None if name == ALL else name
            snap.scopes[name] = self._scope_stats(provider, anchor, now)

        if not self.game.initialized:
            try:
                self.game.load(snap.lifetime_tokens)
            except SaveUnreadable as exc:
                # Stop here: refusing to run beats overwriting a damaged save.
                self.error = t("err.save", err=_brief(exc))
                self.ready = False
                self._notify()
                return

        # Rare Candy is earned on the combined 5-hour window, so any agent's
        # work can fill it.
        limit = max(1, self.config.block_limit_tokens)
        filled = [
            b for b in self.reader.blocks(anchor)
            if not b.is_active(now) and b.tokens >= limit
        ]
        new_events = self.game.update(snap.lifetime_tokens, filled)

        wanted = set(self.game.pokedex)
        for rec in self.game.catch_log:
            wanted.update(rec.get("line", []))
        self.prefetch(sorted(wanted))

        with self._lock:
            self.snapshot = snap
            self.events.extend(new_events)
            self.events = self.events[-50:]
            self.ready = True
            self.error = None
        self._notify(new_events)

    def _scope_stats(self, provider: str | None, anchor, now) -> ScopeStats:
        r = self.reader
        st = ScopeStats()
        st.today_tokens, st.today_cost = r.today(provider)
        st.week_tokens, st.week_cost = r.rolling(7, provider)
        st.month_tokens, st.month_cost = r.rolling(30, provider)
        st.lifetime_tokens, st.lifetime_cost = r.lifetime(provider)
        st.priced = st.lifetime_cost > 0 or provider != "codex"

        active = r.active_block(anchor, provider)
        if active:
            st.block_tokens, st.block_cost = active.tokens, active.cost
            st.block_ends = active.end
            elapsed_h = max((now - active.entries[0].ts).total_seconds() / 3600, 1 / 60)
            st.burn_per_hour = active.tokens / elapsed_h

        primary, secondary = r.limits(provider) if provider else (None, None)
        if primary or secondary:
            # The agent tells us its real utilisation; prefer that to a guess.
            st.official = True
            if primary:
                st.block_percent = min(primary.used_percent / 100, 1.0)
                st.block_ends = primary.resets_at or st.block_ends
            if secondary:
                st.week_percent = min(secondary.used_percent / 100, 1.0)
            st.eta_key = "eta.official"
            return st

        limit = max(1, self.config.block_limit_tokens)
        st.block_percent = min(st.block_tokens / limit, 1.0)
        st.week_percent = min(
            st.week_tokens / max(1, self.config.weekly_limit_tokens), 1.0
        )
        if st.block_tokens >= limit:
            st.eta_key = "eta.reached"
        elif active and st.burn_per_hour > 0:
            hours_left = (limit - st.block_tokens) / st.burn_per_hour
            eta_dt = datetime.fromtimestamp(
                now.timestamp() + hours_left * 3600
            ).astimezone()
            if eta_dt < active.end.astimezone():
                st.eta_key, st.eta_time = "eta.at", f"{eta_dt:%H:%M}"
            else:
                st.eta_key = "eta.never"
        return st

    # ---- observers -------------------------------------------------

    def subscribe(self, fn) -> None:
        self.listeners.append(fn)

    def _notify(self, events: list[str] | None = None) -> None:
        for fn in list(self.listeners):
            try:
                fn(events or [])
            except Exception:
                pass

    # ---- sprites ---------------------------------------------------

    def frames(self, species_id: int, shiny: bool, size: int) -> list[Image.Image]:
        """Animated sprite frames, scaled with nearest-neighbour to stay crisp."""
        key = (species_id, shiny)
        if key not in self._frame_cache:
            path = self.dex.sprite_path(species_id, shiny)
            if path is None:
                return []
            try:
                img = Image.open(path)
            except OSError:
                return []
            frames = []
            try:
                while True:
                    frames.append(img.convert("RGBA"))
                    img.seek(img.tell() + 1)
            except EOFError:
                pass
            self._frame_cache[key] = frames
        raw = self._frame_cache[key]
        if not raw:
            return []
        scale = max(1, size // max(raw[0].width, raw[0].height))
        out = []
        for f in raw:
            w, h = f.width * scale, f.height * scale
            canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            resized = f.resize((w, h), Image.NEAREST)
            canvas.paste(resized, ((size - w) // 2, (size - h) // 2), resized)
            out.append(canvas)
        return out

    def egg_frames(self, size: int) -> list[Image.Image]:
        """A simple drawn egg, used before the companion hatches."""
        return [egg_image(size, self.dex)]

    def still(self, species_id: int, shiny: bool, size: int) -> Image.Image | None:
        """One static frame, for grids where 24 animations would be wasteful."""
        key = (species_id, shiny, size)
        if key in self._still_cache:
            return self._still_cache[key]
        frames = self.frames(species_id, shiny, size)
        img = frames[0] if frames else None
        if img is not None:
            self._still_cache[key] = img
        return img

    def item_image(self, item_key: str, size: int) -> Image.Image | None:
        """Icon for a bag/shop item.

        A PNG dropped into `assets/<item_key>.png` wins, so icons can be
        replaced without touching code. Otherwise fall back to the PokeAPI item
        sprite; the three egg grades all reuse the app's own egg.
        """
        cache_key = (item_key, size)
        if cache_key in self._item_cache:
            return self._item_cache[cache_key]

        img: Image.Image | None = None
        override = asset_dir() / f"{item_key}.png"
        src: Image.Image | None = None
        if override.exists():
            try:
                src = Image.open(override).convert("RGBA")
            except OSError:
                src = None
        if src is None and item_key.startswith("egg_"):
            src = egg_image(size, self.dex)
        if src is None:
            name = ITEM_SPRITES.get(item_key)
            path = self.dex.item_sprite_path(name) if name else None
            if path is not None:
                try:
                    src = Image.open(path).convert("RGBA")
                except OSError:
                    src = None
        if src is not None:
            img = _fit(src, size)
            self._item_cache[cache_key] = img
        return img

    def prefetch(self, species_ids) -> None:
        """Pull sprites onto disk from the refresh thread.

        Downloading during a render would freeze the UI, so the background loop
        warms the cache for everything the Pokedex is about to draw.
        """
        for sid in species_ids:
            if self._stop.is_set():
                return
            self.dex.sprite_path(sid, False)
        self.dex.egg_sprite_path()
        for key, name in ITEM_SPRITES.items():
            if self._stop.is_set():
                return
            self.dex.item_sprite_path(name)
