# Leo

**Website:** https://leo-claude.vercel.app · **Code:** https://github.com/leo-stack-hub/leo

A small desktop pet for Claude Code, on **macOS, Windows and Linux**. It floats on your screen
and shows, live, what Claude is doing: thinking, reading, typing, running commands, waiting for
you, asking permission, done. It plays a short system sound on the important moments and tells
you how long a turn took.

**Characters:** **Leo the lion cub** (default), plus an original **boy** and **girl**, drawn live in a flat, outlined sticker style, all facing you, with real limb animation for every state (wave, think, read, type, march, jump, sit, doze). Switch in right-click → Character or `character leo|boy|girl`.

**Hydration reminder:** Leo reminds you to drink water. Turn it on in right-click → Hydration reminder (pick every 15 min … 2 hours, or a custom interval), or from the terminal: `water on`, `water --every 30`, `water off`, `water --now` (preview). When it is time, Leo takes out a bottle, sips (the water level drops), and sighs "ahh", with water drops floating up and a sound (Mute silences it). Two buttons appear under the message: **✓ I drank** restarts the timer (Leo hops: "Nice! Next reminder in 45 min") and **In 10 min** snoozes it. Clicking Leo anywhere else also counts as "I drank"; if you ignore it, it fades after 25 seconds and the timer restarts. Reminders only run while Leo is running (he stays while Claude Code sessions are open; `run --stay` keeps him always on).

**Your own picture packs (optional):** a folder of transparent PNGs in `~/.leo/characters/<name>/` (`idle.png` required; optional `greeting thinking working reading typing done waiting permission sleeping`) becomes a character; states without a picture are animated by warping `idle.png`. Only use artwork you made or are licensed to use.

**Your own avatar:** upload any picture and Leo turns it into its face: sticker, cartoon or
pixel style, or **toon**: your head, cartoonized, on a drawn full body with a boy or girl outfit.
No AI service, no internet; it is all Pillow and OpenCV.

Inspired by [bao-claude](https://github.com/suhailparad/bao-claude), rebuilt on a much smaller
code base: ~800 lines of Python, one avatar image instead of sprite folders, no app bundle.

## Install

Needs Python 3.10+ and Claude Code. On Windows, Claude Code runs hooks through Git Bash
(installed with Git for Windows), which Leo's hook uses too.

**1. Download Leo:**

```sh
git clone https://github.com/leo-stack-hub/leo.git
cd leo
```

(No git? Download the ZIP from GitHub and unzip it.)

**2. One-time setup** (downloads PySide6 and OpenCV, ~150 MB, takes a few minutes and shows progress):

```sh
python3 setup.py        # macOS / Linux
py setup.py             # Windows
```

**3. Add the plugin** in Claude Code (`setup.py` prints this line with your real path):

```
/plugin marketplace add /full/path/to/leo
/plugin install leo@leo
```

Start a new Claude Code session and Leo appears. It quits ~15 minutes after the last session ends.
Try it without Claude: run the command that `setup.py` prints at the end (it ends in `run --stay`).

## Make your avatar

Right-click Leo → **Upload avatar…**, or from a terminal (`PY` is the venv python that
`setup.py` printed: `~/.leo/venv/bin/python`, or `%USERPROFILE%\.leo\venv\Scripts\python.exe`):

```sh
PY run_leo.py avatar ~/Pictures/me.jpg --style cartoon --remove-bg
```

| Style | Look |
|---|---|
| `sticker` | your picture with a white outline and soft shadow (default) |
| `cartoon` | flat colours and ink outlines |
| `pixel` | chunky 40x40 pixel art, 16 colours |
| `original` | rounded square, picture untouched |
| `toon` | only your head is taken from the photo, cartoonized, on a full body (`--body boy` or `--body girl`) |

`--remove-bg` makes a plain-coloured background transparent (flood fill from the corners), so it
works best on photos against a wall or flat colour. Your original is kept, so you can switch
style from the right-click menu without uploading again. `avatar --reset` removes the uploaded picture and returns to your chosen built-in character. Or just ask Claude: the plugin has a `leo` skill ("make Leo look like this
photo, pixel style").

### Toon: full-body cartoon

```sh
PY run_leo.py avatar ~/Pictures/me.jpg --style toon --body boy     # varsity jacket, denim shorts
PY run_leo.py avatar ~/Pictures/me.jpg --style toon --body girl    # lilac cardigan, pleated skirt
```

Leo finds the face (OpenCV), cuts out the head (face, hair, ears), cartoonizes it, and puts it on a
drawn body whose skin tone is sampled from your face. **You choose boy or girl**; Leo does not guess
it from the photo. Use a front-facing portrait with the whole head in frame; a plain background
and `--remove-bg` help. If no face is found, Leo uses the centre of the picture. The body is drawn
in code, so it is simple and flat, not a 3D render. Right-click → Body switches boy/girl.

## What it shows

| Claude Code is… | Leo | Sound |
|---|---|---|
| starting a session | waves a paw, laughs | hello |
| thinking about your prompt | paces slowly, looking up, three dots | – |
| reading / searching | walks with his nose down, sniffing | – |
| editing / writing | stands and taps his front paws | – |
| running a command | trots fast, mouth open | – |
| asking permission | ears up, wide eyes, shakes, red `!` | alert |
| finished | jumps with a happy face, stars, "finished in 4m 12s!" | done |
| waiting for you | sits, wags his tail, green dot | waiting |
| idle for 5 minutes | lies down asleep, floating z's | – |

(An uploaded avatar bobs, sways and shakes instead of walking, since it is a single picture.)

With several sessions there is still one pet: it shows the most urgent state and counts sessions.
Sounds are the system's own (macOS `/System/Library/Sounds`, Windows `C:\Windows\Media`, Linux
freedesktop theme via `canberra-gtk-play`). Right-click → Mute silences them.

## Right-click menu
Character · Upload avatar · Avatar style · Body · Remove plain background · Remove uploaded avatar · Size · Mute sounds · Quit.
Drag to move it; it remembers where you left it. Settings: `~/.leo/config.json`.

## Commands
`run_leo.py run [--stay]` · `avatar IMAGE [--style S] [--remove-bg]` · `avatar --reset` · `character leo|boy|girl` ·
`send STATE` (demo a state for 5 s) · `quit`

## How it works
Claude Code runs `hooks/leo-hook` (a tiny `sh` script) on each event; it calls `leo/hook.py`
(stdlib only, silent, always exits 0, starts the pet on SessionStart). The hook sends one JSON
line over localhost TCP to the Qt window; the port and a secret token live in `~/.leo/leo.port`.
`states.py` (pure Python) turns events into states, `app.py` animates the avatar and draws
badges, `avatar.py` builds the avatar.

## Uninstall
`/plugin uninstall leo@leo` and `/plugin marketplace remove leo`, quit Leo from its right-click menu, then delete the `~/.leo` folder and the downloaded `leo` folder.

## Not included (yet)
Click-to-focus terminal, wandering, Do Not Disturb, per-character sounds, a standalone app.

## Develop
`pip install pytest Pillow PySide6-Essentials && pytest`
