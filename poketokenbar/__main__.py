"""Entry point.

Tkinter owns the main thread; the tray icon and the usage refresh each run on
their own daemon thread. Everything that touches a widget is marshalled back
onto the Tk thread with `root.after`.
"""

from __future__ import annotations

import sys
import tkinter as tk
import traceback

from .app import App
from .i18n import t
from .tray import Tray
from .ui import FloatingPet, MainWindow


def _claim_single_instance():
    """Return a lock handle if we are the only instance, else None.

    Two copies both own the save file and will overwrite each other's progress,
    so a second launch bows out. The lock is a file in the data directory rather
    than a named mutex: the data directory is the thing actually being guarded,
    and a file lock still works when the two processes sit on opposite sides of
    a sandbox boundary (where a Global\\ mutex may be unreachable). Windows
    drops the lock automatically when the process exits, so a crash cannot leave
    the app permanently unlaunchable.
    """
    import msvcrt

    from .app import data_dir

    path = data_dir() / "instance.lock"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(path, "a+b")
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        try:
            handle.close()
        except (OSError, NameError):
            pass
        return None
    return handle


def main() -> int:
    # Held for the process lifetime; Windows releases it when we exit.
    lock = _claim_single_instance()
    if lock is None:
        return 0

    app = App()

    root = tk.Tk()
    root.withdraw()

    window = MainWindow(root, app)
    state = {"pet": None, "quitting": False}

    def _window_just_filled() -> bool:
        """True on the refresh where the 5-hour budget first reaches 100%."""
        full = app.snapshot.combined.block_percent >= 1.0
        was, state["block_full"] = state.get("block_full", full), full
        return full and not was

    def sync_pet() -> None:
        if app.config.floating_pet and state["pet"] is None:
            state["pet"] = FloatingPet(
                root, app, on_click=window.show,
                on_open_settings=lambda: apply([]), on_quit=quit_app,
            )
        elif not app.config.floating_pet and state["pet"] is not None:
            state["pet"].destroy()
            state["pet"] = None

    def apply(events: list[str]) -> None:
        if state["quitting"]:
            return

        # Each surface is refreshed independently. One of them raising must not
        # take the others down with it — a broken floating pet used to stop the
        # tray tooltip updating too, which made the cause hard to spot.
        def surface(name, fn):
            try:
                fn()
            except Exception:
                traceback.print_exc()
                print(f"[poketokenbar] {name} failed to render", file=sys.stderr)

        surface("window", lambda: window.render(events))
        surface("pet", sync_pet)
        pet = state["pet"]
        if pet is not None:
            surface("pet", pet.render)
            # Hatches, evolutions and a filled window are worth interrupting for.
            note = events[-1] if events else None
            if note is None and _window_just_filled():
                note = t("alert.block_full")
            if note:
                surface("pet", lambda n=note: pet.say(n))
        surface("tray", tray.refresh)

    def on_update(events: list[str]) -> None:
        # Called from the refresh thread — hop back onto the Tk thread.
        try:
            root.after(0, lambda: apply(events))
        except RuntimeError:
            pass

    def toggle_pet() -> None:
        app.config.floating_pet = not app.config.floating_pet
        app.config.save(app.config_path)
        root.after(0, sync_pet)

    def quit_app() -> None:
        state["quitting"] = True
        app.stop()
        tray.stop()
        root.after(0, root.destroy)

    tray = Tray(app, on_open=lambda: root.after(0, window.show),
                on_toggle_pet=toggle_pet, on_quit=quit_app)

    app.subscribe(on_update)
    window.bind("<<SettingsChanged>>", lambda _e: apply([]))
    window.bind("<<PinChanged>>", lambda _e: apply([]))

    tray.start()
    app.start()

    try:
        root.mainloop()
    except KeyboardInterrupt:
        quit_app()
    return 0


if __name__ == "__main__":
    sys.exit(main())
