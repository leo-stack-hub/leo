"""leo command line:  python run_leo.py <command>

    run                  start the pet          avatar IMAGE   make an avatar from a picture
    send STATE           demo a state           character NAME leo | boy | girl
    water on|off|--every N   hydration reminder
    autostart on|off     start Leo at login (also adds Leo to Applications / Start menu)
    app [--remove]       add Leo to Applications / Start menu (or remove everything)
    quit                 stop the pet
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys

from . import __version__
from .common import send


def notify_running() -> None:
    try:
        send({"cmd": "reload"})
    except OSError:
        pass  # not running: the avatar loads on next start


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="leo", description="Leo: a desktop pet for Claude Code")
    ap.add_argument("--version", action="version", version=__version__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="start the pet")
    r.add_argument("--first", help="(internal) hook event that launched the pet")
    r.add_argument("--stay", action="store_true", help="don't quit when no session is open")

    a = sub.add_parser("avatar", help="create the avatar from a picture")
    a.add_argument("image", nargs="?", help="path to a png/jpg/webp (omit to restyle the current one)")
    a.add_argument("--style", default="sticker", choices=["sticker", "cartoon", "pixel", "original", "toon"],
                   help="toon = your head on a cartoon full body")
    a.add_argument("--body", default="boy", choices=["boy", "girl"], help="body and outfit for --style toon")
    a.add_argument("--remove-bg", action="store_true", help="make a plain background transparent")
    a.add_argument("--reset", action="store_true", help="remove the uploaded picture (back to the built-in character)")

    c = sub.add_parser("character", help="pick a built-in character")
    c.add_argument("name", help="leo (lion cub) | boy | girl | any pack in ~/.leo/characters")

    w = sub.add_parser("water", help="hydration reminder: on | off | --every MINUTES | --now")
    w.add_argument("mode", nargs="?", choices=["on", "off"], help="turn the reminder on or off")
    w.add_argument("--every", type=int, metavar="MINUTES", help="how often to remind (1-480; turns it on)")
    w.add_argument("--now", action="store_true", help="show the reminder now (preview)")

    au = sub.add_parser("autostart", help="start Leo at login: on | off | status")
    au.add_argument("mode", choices=["on", "off", "status"])

    ap_ = sub.add_parser("app", help="add Leo to Applications / the Start menu")
    ap_.add_argument("--remove", action="store_true", help="remove the app and the login item")

    s = sub.add_parser("send", help="show a state for 5 seconds")
    s.add_argument("state", choices=["idle", "greeting", "thinking", "working", "done",
                                     "waiting", "permission", "sleeping", "hydrate"])
    sub.add_parser("quit", help="stop the pet")
    sub.add_parser("desktop", help="macOS: allow Leo to follow chats in the Claude desktop app")

    args = ap.parse_args(argv)

    if args.cmd == "run":
        from .app import run  # imports Qt only when needed

        return run(json.loads(args.first) if args.first else None, args.stay)

    if args.cmd == "water":
        from . import config, hydrate

        cfg = config.load()
        if args.mode:
            cfg["hydrate"] = args.mode == "on"
        if args.every is not None:
            cfg["hydrate_minutes"] = hydrate.clamp(args.every)
            cfg["hydrate"] = args.mode != "off"
        config.save(cfg)
        print(f"hydration reminder: {'every %d minutes' % cfg['hydrate_minutes'] if cfg['hydrate'] else 'off'}")
        notify_running()
        if args.now:
            try:
                send({"cmd": "show", "state": "hydrate"})
            except OSError:
                print("leo isn't running: start it first (run_leo.py run --stay)", file=sys.stderr)
                return 1
        return 0

    if args.cmd == "autostart":
        from . import autostart

        if args.mode == "status":
            print("start at login: " + ("on" if autostart.enabled() else "off"))
            return 0
        try:
            path = autostart.set_login(args.mode == "on")
        except (OSError, subprocess.CalledProcessError) as exc:
            print(f"leo: could not change start at login: {exc}", file=sys.stderr)
            return 1
        if args.mode == "on":
            print(f"Leo will start at login ({path}).\nApp: {autostart.app_path()}")
        else:
            print("Leo won't start at login any more.")
        return 0

    if args.cmd == "app":
        from . import autostart

        try:
            if args.remove:
                autostart.remove_all()
                print("Leo removed from your apps and from login.")
            else:
                print(f"Leo added: {autostart.install_app()}")
        except (OSError, subprocess.CalledProcessError) as exc:
            print(f"leo: {exc}", file=sys.stderr)
            return 1
        return 0

    if args.cmd == "desktop":
        from . import desktop

        return desktop.probe()

    if args.cmd == "character":
        from . import avatar

        try:
            avatar.use_character(args.name)
        except ValueError as exc:
            print(f"leo: {exc}", file=sys.stderr)
            return 1
        print(f"character: {args.name}")
        notify_running()
        return 0

    if args.cmd == "avatar":
        from . import avatar  # Pillow only

        try:
            if args.reset:
                avatar.save_avatar(None)
                print("uploaded avatar removed")
                notify_running()
                return 0
            elif args.image:
                path = avatar.save_avatar(args.image, args.style, args.remove_bg, args.body)
            else:  # no picture given: restyle the current one
                path = avatar.restyle(args.style, args.remove_bg, args.body)
        except (OSError, ValueError) as exc:
            print(f"leo: {exc}", file=sys.stderr)
            return 1
        print(f"avatar saved: {path}")
        notify_running()
        return 0

    try:
        send({"cmd": "show", "state": args.state} if args.cmd == "send" else {"cmd": "quit"})
    except OSError:
        print("leo is not running (start it with: python run_leo.py run --stay)", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
