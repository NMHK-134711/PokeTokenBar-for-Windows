"""Tkinter surfaces: the main window, and the floating desktop pet.

Windows has no menu-bar text the way macOS does, so the glanceable readout the
original puts in the menu bar lives in two places here: the tray tooltip, and
an optional always-on-top floating pet that shows the sprite plus today's count.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from PIL import ImageTk

from .app import ALL
from .game import EGG_FLOORS, RARITY_ORDER, SHOP_PRICES
from .i18n import nature as tr_nature, rarity as tr_rarity, set_lang, t
from .usage import compact, parse_anchor

BG = "#16171d"
PANEL = "#1e2028"
FG = "#e8e8ef"
MUTED = "#9aa0b0"
ACCENT = "#f2b544"
GOOD = "#5ad18b"

RARITY_COLOR = {
    "Common": "#8d93a3",
    "Uncommon": "#5ad18b",
    "Rare": "#6aa8f0",
    "Very Rare": "#b98cf0",
    "Legendary": "#f2b544",
}

DEX_COLS, DEX_ROWS = 4, 6
DEX_PER_PAGE = DEX_COLS * DEX_ROWS      # 24, matching the original
DEX_SPRITE = 52
LOG_SPRITE = 44
ITEM_ICON = 34


def _matte(img, threshold: int = 128):
    """Force alpha to 0 or 255.

    A `-transparentcolor` window keys out exactly one colour. Anti-aliased edge
    pixels get blended with that key colour and land *near* it but not on it, so
    they survive as a dark halo around the sprite. Making the alpha binary means
    every pixel is either exactly the key colour or fully opaque, and the halo
    disappears. Only needed on the floating pet; normal windows composite fine.
    """
    alpha = img.getchannel("A").point(lambda v: 255 if v >= threshold else 0)
    out = img.copy()
    out.putalpha(alpha)
    return out


class SpriteView(tk.Label):
    """A label that plays an animated sprite."""

    def __init__(self, master, app, size: int = 96, matte: bool = False, **kw) -> None:
        super().__init__(master, bd=0, highlightthickness=0, bg=kw.pop("bg", PANEL), **kw)
        self.app = app
        self.size = size
        self.matte = matte
        self._frames: list[ImageTk.PhotoImage] = []
        self._index = 0
        self._job = None
        self._key = None

    def show(self, species_id: int | None, shiny: bool) -> None:
        key = (species_id, shiny, self.size)
        if key == self._key:
            return
        self._key = key
        images = (
            self.app.frames(species_id, shiny, self.size)
            if species_id is not None
            else self.app.egg_frames(self.size)
        )
        if self.matte:
            images = [_matte(f) for f in images]
        self._frames = [ImageTk.PhotoImage(f) for f in images] or []
        self._index = 0
        if self._job:
            self.after_cancel(self._job)
            self._job = None
        if self._frames:
            self.configure(image=self._frames[0])
            if len(self._frames) > 1:
                self._tick()

    def _tick(self) -> None:
        self._index = (self._index + 1) % len(self._frames)
        self.configure(image=self._frames[self._index])
        self._job = self.after(110, self._tick)

    def stop(self) -> None:
        if self._job:
            self.after_cancel(self._job)
            self._job = None


def _action(parent, text: str, command, enabled: bool) -> tk.Button:
    """A small accent button that visibly greys out when it can't be used."""
    return tk.Button(
        parent, text=text, command=command, relief="flat", cursor="hand2",
        font=("Segoe UI", 9, "bold"), width=5,
        bg=ACCENT if enabled else "#33363f",
        fg="#1a1a1a" if enabled else MUTED,
        disabledforeground=MUTED,
        state="normal" if enabled else "disabled",
    )


def _meter(parent, label: str) -> tuple[tk.Frame, ttk.Progressbar, tk.Label]:
    row = tk.Frame(parent, bg=PANEL)
    head = tk.Frame(row, bg=PANEL)
    head.pack(fill="x")
    tk.Label(head, text=label, bg=PANEL, fg=MUTED, font=("Segoe UI", 9)).pack(side="left")
    value = tk.Label(head, text="-", bg=PANEL, fg=FG, font=("Segoe UI", 9, "bold"))
    value.pack(side="right")
    bar = ttk.Progressbar(row, maximum=100, style="Poke.Horizontal.TProgressbar")
    bar.pack(fill="x", pady=(3, 0))
    return row, bar, value


class MainWindow(tk.Toplevel):
    def __init__(self, master, app) -> None:
        super().__init__(master)
        self.app = app
        self._images: list = []          # keeps PhotoImages alive
        self._dex_view = "dex"
        self._dex_page = 0
        self._scope = ALL
        self.title(t("app.title"))
        self.configure(bg=BG)
        self.geometry("520x700")
        self.minsize(470, 600)
        self.protocol("WM_DELETE_WINDOW", self.hide)

        self._style()
        self.nb = ttk.Notebook(self, style="Poke.TNotebook")
        self.nb.pack(fill="both", expand=True, padx=10, pady=10)

        self.home = tk.Frame(self.nb, bg=PANEL)
        self.dex_tab = tk.Frame(self.nb, bg=PANEL)
        self.bag_tab = tk.Frame(self.nb, bg=PANEL)
        self.shop_tab = tk.Frame(self.nb, bg=PANEL)
        self.settings_tab = tk.Frame(self.nb, bg=PANEL)
        self._tabs = (
            (self.home, "tab.home"), (self.dex_tab, "tab.pokedex"),
            (self.bag_tab, "tab.bag"), (self.shop_tab, "tab.shop"),
            (self.settings_tab, "tab.settings"),
        )
        for frame, key in self._tabs:
            self.nb.add(frame, text=t(key))

        self._build_home()
        self._build_settings()
        self.withdraw()

    def _style(self) -> None:
        st = ttk.Style(self)
        try:
            st.theme_use("clam")
        except tk.TclError:
            pass
        st.configure("Poke.TNotebook", background=BG, borderwidth=0)
        st.configure("Poke.TNotebook.Tab", background=BG, foreground=MUTED,
                     padding=(12, 6), borderwidth=0)
        st.map("Poke.TNotebook.Tab", background=[("selected", PANEL)],
               foreground=[("selected", FG)])
        st.configure("Poke.Horizontal.TProgressbar", troughcolor="#2a2d38",
                     background=ACCENT, borderwidth=0, thickness=8)

    # ---- home ------------------------------------------------------

    def _build_home(self) -> None:
        pad = {"padx": 16}
        top = tk.Frame(self.home, bg=PANEL)
        top.pack(fill="x", pady=(16, 8), **pad)

        self.sprite = SpriteView(top, self.app, size=96)
        self.sprite.pack(side="left")

        info = tk.Frame(top, bg=PANEL)
        info.pack(side="left", fill="x", expand=True, padx=(14, 0))
        self.name_lbl = tk.Label(info, text=t("common.loading"), bg=PANEL, fg=FG,
                                 font=("Segoe UI", 15, "bold"), anchor="w")
        self.name_lbl.pack(fill="x")
        self.sub_lbl = tk.Label(info, text="", bg=PANEL, fg=MUTED,
                                font=("Segoe UI", 9), anchor="w", justify="left")
        self.sub_lbl.pack(fill="x", pady=(2, 6))
        self.grow_bar = ttk.Progressbar(info, maximum=100,
                                        style="Poke.Horizontal.TProgressbar")
        self.grow_bar.pack(fill="x")
        self.grow_lbl = tk.Label(info, text="", bg=PANEL, fg=MUTED,
                                 font=("Segoe UI", 8), anchor="w")
        self.grow_lbl.pack(fill="x", pady=(3, 0))

        self.line_lbl = tk.Label(self.home, text="", bg=PANEL, fg=MUTED,
                                 font=("Segoe UI", 9), anchor="w")
        self.line_lbl.pack(fill="x", pady=(0, 10), **pad)

        tk.Frame(self.home, bg="#2a2d38", height=1).pack(fill="x", **pad)

        self.scope_row = tk.Frame(self.home, bg=PANEL)
        self.scope_row.pack(fill="x", pady=(10, 0), **pad)

        stats = tk.Frame(self.home, bg=PANEL)
        stats.pack(fill="x", pady=(8, 12), **pad)
        self.today_lbl = tk.Label(stats, text="-", bg=PANEL, fg=FG,
                                  font=("Segoe UI", 26, "bold"), anchor="w")
        self.today_lbl.pack(fill="x")
        self.today_sub = tk.Label(stats, text="", bg=PANEL, fg=MUTED,
                                  font=("Segoe UI", 9), anchor="w")
        self.today_sub.pack(fill="x")

        meters = tk.Frame(self.home, bg=PANEL)
        meters.pack(fill="x", **pad)
        row1, self.block_bar, self.block_val = _meter(meters, t("meter.block"))
        row1.pack(fill="x", pady=(0, 10))
        row2, self.week_bar, self.week_val = _meter(meters, t("meter.week"))
        row2.pack(fill="x", pady=(0, 10))

        self.meter_note = tk.Label(self.home, text="", bg=PANEL, fg="#6f7686",
                                   font=("Segoe UI", 8), anchor="w")
        self.meter_note.pack(fill="x", **pad)

        self.burn_lbl = tk.Label(self.home, text="", bg=PANEL, fg=MUTED,
                                 font=("Segoe UI", 9), anchor="w")
        self.burn_lbl.pack(fill="x", pady=(6, 0), **pad)

        self.totals_lbl = tk.Label(self.home, text="", bg=PANEL, fg=MUTED,
                                   font=("Segoe UI", 9), anchor="w", justify="left")
        self.totals_lbl.pack(fill="x", pady=(10, 0), **pad)

        self.event_lbl = tk.Label(self.home, text="", bg=PANEL, fg=GOOD,
                                  font=("Segoe UI", 9), anchor="w", wraplength=400,
                                  justify="left")
        self.event_lbl.pack(fill="x", pady=(10, 16), **pad)

    # ---- settings --------------------------------------------------

    def _build_settings(self) -> None:
        cfg = self.app.config
        wrap = tk.Frame(self.settings_tab, bg=PANEL)
        wrap.pack(fill="both", expand=True, padx=16, pady=16)

        self.vars = {
            "refresh_minutes": tk.StringVar(value=str(cfg.refresh_minutes)),
            "block_limit_tokens": tk.StringVar(value=str(cfg.block_limit_tokens)),
            "weekly_limit_tokens": tk.StringVar(value=str(cfg.weekly_limit_tokens)),
            "block_anchor": tk.StringVar(value=cfg.block_anchor),
            "language": tk.StringVar(value=cfg.language),
            "show_cost": tk.BooleanVar(value=cfg.show_cost),
            "show_percent": tk.BooleanVar(value=cfg.show_percent),
            "floating_pet": tk.BooleanVar(value=cfg.floating_pet),
            "pet_size": tk.StringVar(value=str(cfg.pet_size)),
        }

        def field(label: str, key: str, hint: str = "") -> None:
            tk.Label(wrap, text=label, bg=PANEL, fg=FG, anchor="w",
                     font=("Segoe UI", 9, "bold")).pack(fill="x", pady=(10, 2))
            tk.Entry(wrap, textvariable=self.vars[key], bg="#2a2d38", fg=FG,
                     insertbackground=FG, relief="flat").pack(fill="x", ipady=4)
            if hint:
                tk.Label(wrap, text=hint, bg=PANEL, fg=MUTED, anchor="w",
                         font=("Segoe UI", 8), wraplength=400,
                         justify="left").pack(fill="x", pady=(2, 0))

        field(t("set.refresh"), "refresh_minutes")
        field(t("set.block"), "block_limit_tokens", t("set.block.hint"))
        field(t("set.anchor"), "block_anchor", t("set.anchor.hint"))
        field(t("set.week"), "weekly_limit_tokens")
        field(t("set.petsize"), "pet_size")

        for key, text in (
            ("show_cost", t("set.show_cost")),
            ("show_percent", t("set.show_percent")),
            ("floating_pet", t("set.pet")),
        ):
            tk.Checkbutton(
                wrap, text=text, variable=self.vars[key], bg=PANEL, fg=FG,
                selectcolor=PANEL, activebackground=PANEL, activeforeground=FG,
                anchor="w", font=("Segoe UI", 9), highlightthickness=0, bd=0,
            ).pack(fill="x", pady=(8, 0))

        tk.Label(wrap, text=t("set.language"), bg=PANEL, fg=FG, anchor="w",
                 font=("Segoe UI", 9, "bold")).pack(fill="x", pady=(12, 2))
        langs = tk.Frame(wrap, bg=PANEL)
        langs.pack(fill="x")
        for value, text in (("ko", "한국어"), ("en", "English")):
            tk.Radiobutton(
                langs, text=text, value=value, variable=self.vars["language"],
                bg=PANEL, fg=FG, selectcolor=PANEL, activebackground=PANEL,
                activeforeground=FG, font=("Segoe UI", 9), highlightthickness=0, bd=0,
            ).pack(side="left", padx=(0, 12))

        # Showing the path makes it obvious which save is in play — sandboxed
        # launchers can silently redirect %LOCALAPPDATA% elsewhere.
        tk.Label(wrap, text=t("set.datadir"), bg=PANEL, fg=FG, anchor="w",
                 font=("Segoe UI", 9, "bold")).pack(fill="x", pady=(14, 2))
        path_box = tk.Entry(wrap, bg="#23262f", fg=MUTED, insertbackground=FG,
                            relief="flat", font=("Consolas", 8))
        path_box.insert(0, str(self.app.dir))
        path_box.configure(state="readonly", readonlybackground="#23262f")
        path_box.pack(fill="x", ipady=3)

        tk.Button(wrap, text=t("set.save"), command=self._save_settings, bg=ACCENT,
                  fg="#1a1a1a", relief="flat", font=("Segoe UI", 10, "bold"),
                  cursor="hand2").pack(fill="x", pady=(18, 0), ipady=6)
        self.settings_msg = tk.Label(wrap, text="", bg=PANEL, fg=GOOD,
                                     font=("Segoe UI", 9))
        self.settings_msg.pack(fill="x", pady=(8, 0))

    def _save_settings(self) -> None:
        cfg = self.app.config
        try:
            cfg.refresh_minutes = max(1, min(60, int(self.vars["refresh_minutes"].get())))
            cfg.block_limit_tokens = max(1, int(self.vars["block_limit_tokens"].get()))
            cfg.weekly_limit_tokens = max(1, int(self.vars["weekly_limit_tokens"].get()))
            cfg.pet_size = max(48, min(192, int(self.vars["pet_size"].get())))
        except ValueError:
            self.settings_msg.configure(text=t("set.numbers"), fg="#e0665f")
            return
        anchor = self.vars["block_anchor"].get().strip()
        if anchor and parse_anchor(anchor) is None:
            self.settings_msg.configure(text=t("set.anchor.bad"), fg="#e0665f")
            return
        cfg.block_anchor = anchor

        cfg.show_cost = self.vars["show_cost"].get()
        cfg.show_percent = self.vars["show_percent"].get()
        cfg.floating_pet = self.vars["floating_pet"].get()
        cfg.language = self.vars["language"].get()
        set_lang(cfg.language)
        cfg.save(self.app.config_path)
        self._retitle()
        self.settings_msg.configure(text=t("set.saved"), fg=GOOD)
        self.app.request_refresh()
        self.event_generate("<<SettingsChanged>>")

    def _retitle(self) -> None:
        """Re-label window chrome after a language change."""
        self.title(t("app.title"))
        for i, (_frame, key) in enumerate(self._tabs):
            self.nb.tab(i, text=t(key))

    # ---- rendering -------------------------------------------------

    def show(self) -> None:
        self.deiconify()
        self.lift()
        self.focus_force()

    def hide(self) -> None:
        self.withdraw()

    def render(self, events: list[str]) -> None:
        app, snap, game = self.app, self.app.snapshot, self.app.game
        lang = app.config.language

        if app.error:
            self.name_lbl.configure(text=t("common.problem"))
            self.sub_lbl.configure(text=app.error)
            return
        if not app.ready:
            return

        c = game.companion
        if c.hatched and c.species_id is not None:
            species = app.dex.species[c.species_id]
            self.sprite.show(c.species_id, c.shiny)
            star = " ✨" if c.shiny else ""
            self.name_lbl.configure(text=f"{species.name(lang)}{star}")
            self.sub_lbl.configure(text=t("home.subtitle", rarity=tr_rarity(c.rarity),
                                          nature=tr_nature(c.nature)))
            names = " → ".join(app.dex.species[s].name(lang) for s in c.path)
            self.line_lbl.configure(text=t("home.line", names=names))
        else:
            self.sprite.show(None, False)
            self.name_lbl.configure(text=t("egg.name"))
            self.sub_lbl.configure(text=t("egg.hint"))
            self.line_lbl.configure(text="")

        progress, goal = game.progress(snap.lifetime_tokens), game.goal()
        pct = min(progress / max(1, goal), 1.0)
        self.grow_bar["value"] = pct * 100
        step = t("step.hatch") if not c.hatched else (
            t("step.evolve") if c.stage < len(c.path) - 1 else t("step.graduate")
        )
        self.grow_lbl.configure(text=t(
            "home.progress", done=compact(progress), goal=compact(goal), step=step))

        self._render_scope_chips(snap)
        st = snap.scope(self._scope)

        self.today_lbl.configure(text=compact(st.today_tokens))
        self.today_sub.configure(
            text=t("home.today", cost=f"{st.today_cost:,.2f}") if st.priced
            else t("home.today.nocost"))

        self.block_bar["value"] = st.block_percent * 100
        ends = st.block_ends.astimezone().strftime("%H:%M") if st.block_ends else "-"
        self.block_val.configure(text=t(
            "meter.block.val", pct=f"{st.block_percent * 100:.0f}",
            tokens=compact(st.block_tokens), ends=ends))
        self.week_bar["value"] = st.week_percent * 100
        self.week_val.configure(text=t(
            "meter.week.val", pct=f"{st.week_percent * 100:.0f}",
            tokens=compact(st.week_tokens)))
        # Say plainly whether the percentages are the agent's own numbers.
        self.meter_note.configure(
            text=t("meter.official") if st.official else t("meter.budget"))

        self.burn_lbl.configure(text=t(
            "home.burn", rate=compact(int(st.burn_per_hour)), eta=st.eta()))
        self.totals_lbl.configure(text=t(
            "home.totals",
            w=compact(st.week_tokens), wc=f"{st.week_cost:,.2f}",
            m=compact(st.month_tokens), mc=f"{st.month_cost:,.2f}",
            a=compact(st.lifetime_tokens), ac=f"{st.lifetime_cost:,.2f}"))
        if snap.no_logs:
            # Nothing to track yet — say why, or the egg looks broken.
            self.event_lbl.configure(text=t("hint.nologs"), fg=MUTED)
        elif events:
            self.event_lbl.configure(text="\n".join(events[-3:]), fg=GOOD)

        self._images.clear()
        self._render_pokedex()
        self._render_bag()
        self._render_shop()

    def _render_scope_chips(self, snap) -> None:
        """One chip per detected agent, plus a combined view.

        Hidden entirely when only one agent is present — there is nothing to
        switch between.
        """
        for child in self.scope_row.winfo_children():
            child.destroy()
        if len(snap.providers) < 2:
            return
        options = [(ALL, t("scope.all"))] + list(snap.providers)
        for name, label in options:
            selected = self._scope == name
            tk.Button(
                self.scope_row, text=label,
                command=lambda n=name: self._set_scope(n),
                bg=ACCENT if selected else "#2a2d38",
                fg="#1a1a1a" if selected else MUTED,
                relief="flat", cursor="hand2", font=("Segoe UI", 8, "bold"),
                padx=10, pady=2,
            ).pack(side="left", padx=(0, 5))

    def _set_scope(self, name: str) -> None:
        self._scope = name
        self.render([])

    # ---- pokedex / bag / shop --------------------------------------

    def _clear(self, frame: tk.Frame) -> None:
        for child in frame.winfo_children():
            child.destroy()

    def _sprite_label(self, parent, species_id, shiny, size, bg):
        """A static sprite, or a dim placeholder while it is still downloading."""
        img = self.app.still(species_id, shiny, size)
        if img is None:
            return tk.Frame(parent, width=size, height=size, bg=bg)
        photo = ImageTk.PhotoImage(img)
        self._images.append(photo)          # Tk does not own PhotoImage refs
        return tk.Label(parent, image=photo, bg=bg, bd=0, highlightthickness=0)

    def _icon_label(self, parent, item_key, size, bg):
        img = self.app.item_image(item_key, size)
        if img is None:
            return tk.Frame(parent, width=size, height=size, bg=bg)
        photo = ImageTk.PhotoImage(img)
        self._images.append(photo)
        return tk.Label(parent, image=photo, bg=bg, bd=0, highlightthickness=0)

    def _scrollable(self, parent):
        """A vertically scrollable panel; returns the frame to fill."""
        canvas = tk.Canvas(parent, bg=PANEL, highlightthickness=0, bd=0)
        bar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        inner = tk.Frame(canvas, bg=PANEL)
        window = canvas.create_window((0, 0), window=inner, anchor="nw")

        def on_config(_e=None):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfigure(window, width=canvas.winfo_width())
            # Only show the scrollbar when there is something to scroll to.
            if inner.winfo_reqheight() > canvas.winfo_height():
                if not bar.winfo_ismapped():
                    bar.pack(side="right", fill="y")
            elif bar.winfo_ismapped():
                bar.pack_forget()

        inner.bind("<Configure>", on_config)
        canvas.bind("<Configure>", on_config)
        canvas.configure(yscrollcommand=bar.set)
        canvas.pack(side="left", fill="both", expand=True)

        def wheel(event):
            canvas.yview_scroll(-1 * (event.delta // 120), "units")

        # Bind the wheel only while the pointer is over this panel. A global
        # bind_all would also fire for other panels — including destroyed ones
        # left over from a previous render.
        def grab_wheel(_e=None):
            canvas.bind_all("<MouseWheel>", wheel)

        def release_wheel(_e=None):
            canvas.unbind_all("<MouseWheel>")

        for w in (canvas, inner):
            w.bind("<Enter>", grab_wheel)
            w.bind("<Leave>", release_wheel)
        canvas.bind("<Destroy>", release_wheel)
        return inner

    def _rarity_chips(self, parent, counts) -> None:
        row = tk.Frame(parent, bg=PANEL)
        row.pack(fill="x", pady=(6, 10))
        for key in reversed(RARITY_ORDER):
            tk.Label(row, text="\u25cf", bg=PANEL, fg=RARITY_COLOR[key],
                     font=("Segoe UI", 8)).pack(side="left")
            tk.Label(row, text=f"{tr_rarity(key)} {counts.get(key, 0)}", bg=PANEL,
                     fg=MUTED, font=("Segoe UI", 8)).pack(side="left", padx=(2, 12))

    # ---- pokedex ---------------------------------------------------

    def _render_pokedex(self) -> None:
        self._clear(self.dex_tab)
        wrap = tk.Frame(self.dex_tab, bg=PANEL)
        wrap.pack(fill="both", expand=True, padx=12, pady=12)

        switch = tk.Frame(wrap, bg=PANEL)
        switch.pack(fill="x")
        for view, key in (("dex", "dex.tab.dex"), ("log", "dex.tab.log")):
            selected = self._dex_view == view
            tk.Button(
                switch, text=t(key), command=lambda v=view: self._set_dex_view(v),
                bg=ACCENT if selected else "#2a2d38",
                fg="#1a1a1a" if selected else MUTED,
                relief="flat", cursor="hand2", font=("Segoe UI", 9, "bold"),
                padx=12, pady=3,
            ).pack(side="left", padx=(0, 6))

        body = tk.Frame(wrap, bg=PANEL)
        body.pack(fill="both", expand=True, pady=(10, 0))
        if self._dex_view == "dex":
            self._render_dex_grid(body)
        else:
            self._render_catch_log(body)

    def _set_dex_view(self, view: str) -> None:
        self._dex_view = view
        self._render_pokedex()

    def _render_dex_grid(self, parent) -> None:
        app, game = self.app, self.app.game
        owned = sorted(game.pokedex)

        counts = {}
        for sid in owned:
            sp = app.dex.species.get(sid)
            if sp:
                counts[sp.rarity] = counts.get(sp.rarity, 0) + 1

        tk.Label(parent, text=t("dex.title", n=len(owned)), bg=PANEL, fg=FG,
                 font=("Segoe UI", 11, "bold"), anchor="w").pack(fill="x")
        self._rarity_chips(parent, counts)

        if owned:
            bar = tk.Frame(parent, bg=PANEL)
            bar.pack(fill="x", pady=(0, 8))
            pinned = app.config.pinned_species
            sp = app.dex.species.get(pinned) if pinned else None
            if sp is not None:
                tk.Label(bar, text=t("dex.pin.current",
                                     name=sp.name(app.config.language)),
                         bg=PANEL, fg=ACCENT, font=("Segoe UI", 8, "bold"),
                         anchor="w").pack(side="left")
                tk.Button(bar, text=t("dex.pin.clear"),
                          command=lambda: self._toggle_pin(pinned),
                          bg="#2a2d38", fg=MUTED, relief="flat", cursor="hand2",
                          font=("Segoe UI", 8), padx=8).pack(side="right")
            else:
                tk.Label(bar, text=t("dex.pin.hint"), bg=PANEL, fg=MUTED,
                         font=("Segoe UI", 8), anchor="w").pack(side="left")

        if not owned:
            tk.Label(parent, text=t("dex.empty"), bg=PANEL, fg=MUTED,
                     font=("Segoe UI", 9), anchor="w").pack(fill="x")
            return

        pages = max(1, (len(owned) + DEX_PER_PAGE - 1) // DEX_PER_PAGE)
        self._dex_page = max(0, min(self._dex_page, pages - 1))
        page = owned[self._dex_page * DEX_PER_PAGE:(self._dex_page + 1) * DEX_PER_PAGE]

        # Pager first and anchored to the bottom, so a short window can never
        # push it out of reach; the grid then scrolls in whatever space is left.
        if pages > 1:
            nav = tk.Frame(parent, bg=PANEL)
            nav.pack(fill="x", side="bottom", pady=(8, 0))
            pager = tk.Frame(nav, bg=PANEL)
            pager.pack(anchor="center")
            _action(pager, "‹", lambda: self._turn_page(-1),
                    enabled=self._dex_page > 0).pack(side="left")
            tk.Label(pager, text=f"{self._dex_page + 1} / {pages}", bg=PANEL,
                     fg=MUTED, font=("Segoe UI", 9), width=8).pack(side="left")
            _action(pager, "›", lambda: self._turn_page(1),
                    enabled=self._dex_page < pages - 1).pack(side="left")

        holder = tk.Frame(parent, bg=PANEL)
        holder.pack(fill="both", expand=True)
        grid = self._scrollable(holder)
        for c in range(DEX_COLS):
            grid.columnconfigure(c, weight=1, uniform="dex")

        pinned = app.config.pinned_species
        for n, sid in enumerate(page):
            sp = app.dex.species.get(sid)
            if not sp:
                continue
            rec = game.pokedex[sid]
            shiny = bool(rec.get("shiny"))
            is_pinned = sid == pinned
            bg = "#2c2a22" if is_pinned else "#23262f"
            cell = tk.Frame(grid, bg=bg, highlightthickness=2 if is_pinned else 1,
                            highlightbackground=ACCENT if is_pinned
                            else RARITY_COLOR.get(sp.rarity, MUTED))
            cell.grid(row=n // DEX_COLS, column=n % DEX_COLS, padx=3, pady=3, sticky="nsew")
            self._sprite_label(cell, sid, shiny, DEX_SPRITE, bg).pack(pady=(6, 0))
            tk.Label(cell, text=("\u2605 " if is_pinned else "") + f"#{sid}", bg=bg,
                     fg=ACCENT if is_pinned else MUTED,
                     font=("Segoe UI", 7)).pack()
            tk.Label(cell, text=sp.name(app.config.language) + (" \u2728" if shiny else ""),
                     bg=bg, fg=FG, font=("Segoe UI", 8), wraplength=88).pack(pady=(0, 6))
            # The whole cell is the hit target, children included.
            for w in (cell, *cell.winfo_children()):
                w.bind("<Button-1>", lambda _e, i=sid: self._toggle_pin(i))
                w.configure(cursor="hand2")

    def _toggle_pin(self, species_id: int) -> None:
        """Pin this species to the tray/pet, or unpin it if already pinned."""
        cfg = self.app.config
        cfg.pinned_species = 0 if cfg.pinned_species == species_id else species_id
        cfg.save(self.app.config_path)
        self.render([])
        self.event_generate("<<PinChanged>>")

    def _turn_page(self, delta: int) -> None:
        self._dex_page += delta
        self._render_pokedex()

    # ---- catch log -------------------------------------------------

    def _render_catch_log(self, parent) -> None:
        app, game = self.app, self.app.game
        log = game.catch_log

        counts = {}
        for rec in log:
            r = rec.get("rarity", "Common")
            counts[r] = counts.get(r, 0) + 1
        tk.Label(parent, text=t("dex.log.title", n=len(log)), bg=PANEL, fg=FG,
                 font=("Segoe UI", 11, "bold"), anchor="w").pack(fill="x")
        self._rarity_chips(parent, counts)

        holder = tk.Frame(parent, bg=PANEL)
        holder.pack(fill="both", expand=True)
        inner = self._scrollable(holder)

        c = game.companion
        if c.hatched and c.path:
            self._log_row(inner, c.path, c.stage, c.shiny, c.rarity, c.nature,
                          raising=True)
        for rec in log[:60]:
            self._log_row(inner, rec.get("line", []), len(rec.get("line", [])) - 1,
                          bool(rec.get("shiny")), rec.get("rarity", "Common"),
                          rec.get("nature", ""), caught_at=rec.get("caught_at", ""))
        if not log and not (c.hatched and c.path):
            tk.Label(inner, text=t("dex.log.empty"), bg=PANEL, fg=MUTED,
                     font=("Segoe UI", 9), anchor="w").pack(fill="x", pady=6)

    def _log_row(self, parent, line, upto, shiny, rarity, nature,
                 raising: bool = False, caught_at: str = "") -> None:
        app = self.app
        card = tk.Frame(parent, bg="#23262f")
        card.pack(fill="x", pady=3, padx=(0, 6))

        head = tk.Frame(card, bg="#23262f")
        head.pack(fill="x", padx=8, pady=(6, 0))
        tk.Label(head, text=tr_rarity(rarity), bg=RARITY_COLOR.get(rarity, MUTED),
                 fg="#1a1a1a", font=("Segoe UI", 7, "bold"), padx=5).pack(side="left")
        if raising:
            tk.Label(head, text=t("dex.raising"), bg=ACCENT, fg="#1a1a1a",
                     font=("Segoe UI", 7, "bold"), padx=5).pack(side="left", padx=(4, 0))
        tk.Label(head, text=tr_nature(nature), bg="#23262f", fg=MUTED,
                 font=("Segoe UI", 8)).pack(side="right")

        strip = tk.Frame(card, bg="#23262f")
        strip.pack(fill="x", padx=8, pady=(4, 6))
        for idx, sid in enumerate(line):
            sp = app.dex.species.get(sid)
            if not sp:
                continue
            if idx:
                tk.Label(strip, text="\u2192", bg="#23262f", fg=MUTED,
                         font=("Segoe UI", 9)).pack(side="left", padx=2)
            col = tk.Frame(strip, bg="#23262f")
            col.pack(side="left")
            # Stages not yet reached are shown, but dimmed by the name colour.
            reached = idx <= upto
            self._sprite_label(col, sid, shiny and reached, LOG_SPRITE, "#23262f").pack()
            tk.Label(col, text=sp.name(app.config.language), bg="#23262f",
                     fg=FG if reached else "#555a68", font=("Segoe UI", 7)).pack()
        if caught_at:
            tk.Label(strip, text=caught_at[:10], bg="#23262f", fg="#555a68",
                     font=("Segoe UI", 7)).pack(side="right")

    # ---- bag -------------------------------------------------------

    def _render_bag(self) -> None:
        game = self.app.game
        self._clear(self.bag_tab)
        wrap = tk.Frame(self.bag_tab, bg=PANEL)
        wrap.pack(fill="both", expand=True, padx=16, pady=16)

        tk.Label(wrap, text=t("bag.title"), bg=PANEL, fg=FG,
                 font=("Segoe UI", 11, "bold"), anchor="w").pack(fill="x", pady=(0, 10))
        self.bag_msg = tk.Label(wrap, text="", bg=PANEL, fg=GOOD,
                                font=("Segoe UI", 9), anchor="w", wraplength=380,
                                justify="left")

        def use(fn):
            def handler():
                msg = fn() or t("bag.none")
                # render() rebuilds this tab, so set the message on the new
                # label afterwards rather than on the one about to be destroyed.
                self.render([])
                self.bag_msg.configure(text=msg)
            return handler

        for key, count, desc, fn in (
            ("rare_candy", game.candies, t("item.rare_candy.desc"), game.use_candy),
            ("mint", game.mints, t("item.mint.desc"), game.use_mint),
        ):
            row = tk.Frame(wrap, bg="#2a2d38")
            row.pack(fill="x", pady=4)
            self._icon_label(row, key, ITEM_ICON, "#2a2d38").pack(
                side="left", padx=(10, 8), pady=8)
            text = tk.Frame(row, bg="#2a2d38")
            text.pack(side="left", fill="x", expand=True)
            tk.Label(text, text=f"{t('item.' + key)}  \u00d7{count}", bg="#2a2d38",
                     fg=FG, font=("Segoe UI", 10, "bold"), anchor="w").pack(fill="x")
            tk.Label(text, text=desc, bg="#2a2d38", fg=MUTED,
                     font=("Segoe UI", 8), anchor="w").pack(fill="x")
            _action(row, t("bag.use"), use(fn), enabled=bool(count)).pack(
                side="right", padx=10, pady=6)

        charm = tk.Frame(wrap, bg=PANEL)
        charm.pack(fill="x", pady=(12, 0))
        self._icon_label(charm, "shiny_charm", 24, PANEL).pack(side="left", padx=(0, 6))
        tk.Label(charm, text=t("bag.charms", n=game.shiny_charms,
                               odds=f"{game.shiny_odds():.0f}"),
                 bg=PANEL, fg=MUTED, font=("Segoe UI", 9), anchor="w").pack(side="left")
        self.bag_msg.pack(fill="x", pady=(10, 0))

    # ---- shop ------------------------------------------------------

    def _render_shop(self) -> None:
        game, snap = self.app.game, self.app.snapshot
        self._clear(self.shop_tab)
        wrap = tk.Frame(self.shop_tab, bg=PANEL)
        wrap.pack(fill="both", expand=True, padx=12, pady=12)

        balance = game.currency(snap.lifetime_tokens)
        tk.Label(wrap, text=t("shop.title", balance=compact(balance)),
                 bg=PANEL, fg=FG, font=("Segoe UI", 11, "bold"), anchor="w").pack(
            fill="x", pady=(0, 8))
        self.shop_msg = tk.Label(wrap, text="", bg=PANEL, fg=GOOD,
                                 font=("Segoe UI", 9), anchor="w", wraplength=380,
                                 justify="left")
        self.shop_msg.pack(fill="x", side="bottom", pady=(8, 0))

        inner = self._scrollable(wrap)

        def buy(item):
            def handler():
                msg = game.buy(item, self.app.snapshot.lifetime_tokens)
                self.render([])
                self.shop_msg.configure(text=msg)
            return handler

        for item in ("rare_candy", "mint", "shiny_charm",
                     "egg_plain", "egg_uncommon", "egg_rare"):
            price = SHOP_PRICES[item]
            row = tk.Frame(inner, bg="#2a2d38")
            row.pack(fill="x", pady=3, padx=(0, 6))
            self._icon_label(row, item, ITEM_ICON, "#2a2d38").pack(
                side="left", padx=(10, 8), pady=8)
            text = tk.Frame(row, bg="#2a2d38")
            text.pack(side="left", fill="x", expand=True)
            title = tk.Frame(text, bg="#2a2d38")
            title.pack(fill="x")
            tk.Label(title, text=t(f"item.{item}"), bg="#2a2d38", fg=FG,
                     font=("Segoe UI", 10, "bold")).pack(side="left")
            floor = EGG_FLOORS.get(item)
            if floor:
                tk.Label(title, text=tr_rarity(floor[0]),
                         bg=RARITY_COLOR.get(floor[0], MUTED), fg="#1a1a1a",
                         font=("Segoe UI", 7, "bold"), padx=4).pack(side="left", padx=6)
            tk.Label(text, text=t("shop.price", desc=t(f"item.{item}.desc"),
                                  price=compact(price)),
                     bg="#2a2d38", fg=MUTED, font=("Segoe UI", 8), anchor="w",
                     wraplength=250, justify="left").pack(fill="x")
            _action(row, t("shop.buy"), buy(item), enabled=balance >= price).pack(
                side="right", padx=10, pady=8)


class FloatingPet(tk.Toplevel):
    """Frameless always-on-top companion with today's count underneath."""

    def __init__(self, master, app, on_click) -> None:
        super().__init__(master)
        self.app = app
        self.on_click = on_click
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(bg="#010101")
        self.attributes("-transparentcolor", "#010101")

        self.sprite = SpriteView(self, app, size=app.config.pet_size,
                                 matte=True, bg="#010101")
        self.sprite.pack()
        # The pet floats over arbitrary wallpaper and windows, so the caption
        # gets its own opaque chip rather than relying on the desktop behind it.
        self.caption = tk.Label(self, text="", bg=BG, fg=FG,
                                font=("Segoe UI", 9, "bold"), padx=8, pady=2)
        self.caption.pack()

        self._drag = (0, 0)
        for widget in (self, self.sprite, self.caption):
            widget.bind("<Button-1>", self._press)
            widget.bind("<B1-Motion>", self._move)
            widget.bind("<ButtonRelease-1>", self._release)

        self._moved = False
        self.update_idletasks()
        self._restore_position()

    def _restore_position(self) -> None:
        """Put the pet back where it was dragged, or in a default corner."""
        cfg = self.app.config
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        w = max(self.winfo_reqwidth(), cfg.pet_size)
        h = max(self.winfo_reqheight(), cfg.pet_size)
        if cfg.pet_x >= 0 and cfg.pet_y >= 0:
            x, y = cfg.pet_x, cfg.pet_y
        else:
            x, y = sw - cfg.pet_size - 60, 80
        # Keep it reachable if the display layout changed since it was saved.
        x = max(0, min(x, sw - w))
        y = max(0, min(y, sh - h))
        self.geometry(f"+{x}+{y}")

    def _press(self, event) -> None:
        self._drag = (event.x_root - self.winfo_x(), event.y_root - self.winfo_y())
        self._moved = False

    def _move(self, event) -> None:
        self._moved = True
        x = event.x_root - self._drag[0]
        y = event.y_root - self._drag[1]
        self.geometry(f"+{x}+{y}")

    def _release(self, event) -> None:
        if not self._moved:
            self.on_click()
            return
        cfg = self.app.config
        cfg.pet_x, cfg.pet_y = self.winfo_x(), self.winfo_y()
        cfg.save(self.app.config_path)

    def render(self) -> None:
        size = self.app.config.pet_size
        if self.sprite.size != size:
            self.sprite.size = size
            self.sprite._key = None
        self.sprite.show(*self.app.display_sprite())
        # Always the combined figure: the pet is a glance, not a per-agent view.
        self.caption.configure(text=compact(self.app.snapshot.combined.today_tokens))
