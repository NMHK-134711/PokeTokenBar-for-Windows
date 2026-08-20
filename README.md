# PokeTokenBar for Windows

Raise a Pokémon with the Claude Code tokens you're already burning — in the
Windows system tray.

A from-scratch Windows implementation of the idea behind
[chattymin/PokeTokenBar](https://github.com/chattymin/PokeTokenBar) (macOS,
Swift 6, menu-bar only). No Swift code is ported; the data sources and the game
rules are reimplemented in Python against the same public inputs.

UI는 한국어가 기본입니다 (설정에서 English로 바꿀 수 있습니다).

## Install

**Option A — the executable (no Python needed).** Grab
`dist/PokeTokenBar.exe` and double-click it. Single file, 24 MB, nothing to
install.

**Option B — from source.**

```bash
pip install -r requirements.txt
python -m poketokenbar
```

Requires Python 3.10+ with tkinter (bundled with the python.org installer).

### Building the executable yourself

```bash
pip install pyinstaller
python build.py
```

Output lands in `dist/PokeTokenBar.exe`. The icon is drawn by the app itself at
build time, so no Pokémon artwork is compiled into the binary. If a copy is
running the build writes `PokeTokenBar-new.exe` beside it rather than failing.

**The tray icon starts hidden.** Windows puts new tray icons in the overflow —
click the `^` chevron next to the clock and drag it onto the taskbar to pin it.

**Start with Windows:** press `Win+R`, run `shell:startup`, and put a shortcut
to `PokeTokenBar.exe` (or `run.pyw`, if running from source) in the folder that
opens.

## What it does

Every token you spend in Claude Code incubates an egg. The egg hatches into a
Gen 1–5 Pokémon — one of **329 possible starting species**, weighted by the
official capture rate, so a legendary lands about **once in 136 hatches**. It
grows through its real evolution line, graduates into your Pokédex, and a fresh
egg arrives.

Underneath the companion it's an exact usage tracker: today's tokens and cost,
the current 5-hour block, 7- and 30-day rolling totals, and a burn-rate forecast.

| Surface | What's on it |
|---|---|
| **Tray icon** | Animated Gen-V sprite; hover for today's tokens, cost, and window % |
| **Floating pet** | Optional always-on-top companion with the token count under it — drag anywhere, hover for detail, click to open the window, right-click for a menu, and it pipes up when something happens |
| **Home** | Companion, growth bar, today's spend, 5-hour and weekly meters, burn rate |
| **Pokédex** | Every species you've owned, plus a catch log of everything you've raised |
| **Pin a favourite** | Click any owned species to pin it to the tray icon and desktop pet |
| **Bag / Shop** | Rare Candy, Mints, Shiny Charms, and graded eggs, bought with tokens |

Shiny hatches (~1 in 256, better with Shiny Charms) keep their colours through
every evolution.

**The floating pet is interactive.** Hovering shows today's tokens and cost, the
5-hour window with its countdown, the weekly figure, and what you're raising.
Right-click for open / refresh / unpin / hide / quit. Hatches, evolutions, and a
filled 5-hour window arrive as a speech bubble above it.

**Reset countdowns** sit in the meters — `100% (217.2M · 2h 9m left)`. For Codex
the reset instant is the one it reports itself; for Claude Code it is the end of
the current 5-hour block. The weekly figure for Claude Code is a rolling 7 days
with no reset instant, so it shows no countdown.

**Pinning.** Clicking a species in the Pokédex pins it to the tray icon and the
desktop pet, so those stop changing at every hatch and evolution. The companion
carries on being raised underneath — Home still shows it and its progress — and
clicking the pinned cell again, or the Unpin button, hands the icon back to it.
Only species you already own can be pinned.

## Agents it reads

| Agent | Logs | Cost | Limits |
|---|---|---|---|
| **Claude Code** | `~/.claude/projects/**/*.jsonl` | list price per model | your own budgets |
| **Codex** | `~/.codex/sessions/**/*.jsonl` | not estimated | **official**, from the log |

Whichever agents are present are detected automatically. With two or more, chips
on the Home tab switch between each agent and a combined view; the companion is
always raised by the combined total, so every token counts whichever tool spent
it.

Codex records its own rate-limit utilisation (`rate_limits.primary` /
`secondary`, with reset timestamps) in its session log, so for Codex the app
shows the **real** 5-hour and weekly percentages rather than a budget you set.
It does not record per-model prices, so Codex tokens are counted but not costed
— an honest blank instead of a guess.

## Where the numbers come from

Usage is read directly from the local session logs the agents already write. No
external CLI, no account access, nothing uploaded.

- **Tokens (Claude Code)** = `input + output + cache creation + cache read`,
  deduplicated by `(message id, request id)`.
- **Tokens (Codex)** come from differencing the cumulative `total_token_usage`
  rather than summing the per-turn `last_token_usage`: Codex re-emits
  `token_count` without new work fairly often, and summing double-counts those
  (18% high on the log tested here). Differencing reproduces the session's own
  final total exactly. `cached_input_tokens` is already inside `input_tokens`,
  so it is not added twice.
- **Cost** is computed at public list prices per model, with cache writes billed
  at 1.25× input for the 5-minute TTL and 2× for the 1-hour TTL, and cache reads
  at 0.1×. The logs record the two TTLs separately, so this is exact rather than
  estimated. On a subscription plan, treat it as "what this would have cost on
  the API".
- **5-hour blocks** are derived from the log timestamps by default: a block
  opens on the hour of its first message and runs five hours; a gap of five
  hours also opens a new one. That mirrors the real limit, which starts its
  window when you send the first message after the previous one lapsed. If your
  windows sit on a schedule you already know, put one boundary (the reset time
  Claude Code's `/usage` shows you) into **5-hour window reset time** in
  Settings and the blocks line up with that clock instead.

Only two hosts are contacted, both for Pokémon data, never for your usage:
`raw.githubusercontent.com` (species tables and sprites) and nothing else.
Everything is cached under `%LOCALAPPDATA%\PokeTokenBarWin\`.

### One deliberate difference from the macOS original

The original shows Anthropic's **official** 5-hour and weekly limit percentages
by reading an OAuth token out of the macOS Keychain and calling an unofficial
`api.anthropic.com` endpoint. This version does not. Windows stores credentials
differently, and an undocumented endpoint is a fragile thing to depend on — so
the 5-hour and weekly meters run against **budgets you set yourself** in
Settings (defaults: 120M per window, 2B per week). Filling one still earns a
Rare Candy. Nothing here ever reads your credentials.

## Tuning

Settings lets you change the refresh interval, both budgets, the 5-hour window
reset time, the floating pet and its size, tooltip contents, and the UI language
(한국어 / English). Species names, natures, and rarities all follow the chosen
language — saves store the English keys, so switching language never invalidates
your Pokédex.

Settings also shows the data folder currently in use. That matters more than it
sounds: a sandboxed launcher can redirect `%LOCALAPPDATA%` elsewhere, so two
copies started different ways can quietly keep separate saves. If a companion
seems to have vanished, check this path first.

`%LOCALAPPDATA%\PokeTokenBarWin\config.json` holds the same settings if you
prefer editing them by hand; it is read as UTF-8 with or without a BOM, so
Notepad is safe.

Game constants live at the top of `poketokenbar/game.py` — `EGG_HATCH_TOKENS`,
`BASE_GRADUATE_TOKENS`, `RARITY_MULTIPLIER`, and `SHOP_PRICES`. The defaults are
calibrated so that at heavy use (~100M tokens/day) a Common graduates in about
three days and a Legendary in about twenty-four, matching the original's stated
pacing. Lower `BASE_GRADUATE_TOKENS` if you use Claude Code less than that.

## Layout

```
poketokenbar/
  providers.py one class per agent: where its logs are and how to read them
  entry.py     a single call's usage, and list-price costing
  usage.py     merges every agent, dedupes, builds 5-hour blocks and rollups
  pokedata.py  species table + evolution trees from PokeAPI, sprite cache
  game.py      egg → hatch → evolve → graduate, Pokédex, bag, shop
  app.py       config, background refresh, sprite frame loading
  ui.py        main window and floating pet (tkinter)
  tray.py      system tray icon (pystray)
  i18n.py      every UI string, in Korean and English
build.py       draws the icon and runs PyInstaller
```

### Adding another agent

Subclass `Source` in `providers.py` with `files()` and `parse()`, add it to
`all_sources()`, and it appears in the UI automatically. If the agent reports
its own rate limits, override `limits()` and its meters become official too.

### Replacing an icon

Create `poketokenbar/assets/` and drop a transparent PNG in, named after the
item key — `rare_candy.png`, `mint.png`, `shiny_charm.png`, or `egg.png`. It
takes priority over the fetched sprite. Any size works; icons are scaled with
nearest-neighbour when enlarging so pixel art stays crisp. The folder is absent
by default, and anything you put there is yours, not part of this project.

## Licence & disclaimer

MIT for the code here. This is an unofficial, non-commercial fan project, **not
affiliated with, endorsed, or sponsored by Nintendo, Game Freak, Creatures Inc.,
or The Pokémon Company**. Pokémon and all related names and imagery are
trademarks of their respective owners. Provided as is, for personal use only.

**No Pokémon artwork is bundled or redistributed.** Species data, Pokémon
sprites, the egg, and every item icon are fetched at runtime from the public
[PokéAPI](https://pokeapi.co) and cached under the user's own
`%LOCALAPPDATA%`; none of it is committed to this repository or compiled into
the executable. The app icon is a plain egg the program draws itself. PokéAPI
has no mint sprite in any flavour, so the Mint item borrows the Ability Urge
icon — also fetched, not shipped.
