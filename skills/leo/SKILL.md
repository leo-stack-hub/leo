---
name: leo
description: Set up and control the Leo desktop pet that shows what Claude Code is doing. Use when the user mentions Leo or "the pet", wants to upload or change the pet's avatar, restyle it (sticker, cartoon, pixel, toon full-body cartoon of their head), resize or mute it, or asks why it isn't reacting.
---

# Leo desktop pet (macOS, Linux, Windows)

The plugin's hooks send every Claude Code event to a small pet window. The pet runs from a
private Python environment at `~/.leo/venv`, created once by `${CLAUDE_PLUGIN_ROOT}/setup.py`.

Define `LEO` as: `<venv python> ${CLAUDE_PLUGIN_ROOT}/run_leo.py`
- macOS/Linux venv python: `~/.leo/venv/bin/python`
- Windows venv python: `%USERPROFILE%\.leo\venv\Scripts\python.exe`

## Set up
If `~/.leo/venv` does not exist, run `python3 ${CLAUDE_PLUGIN_ROOT}/setup.py` (Windows: `py`
instead of `python3`; needs Python 3.10+). It downloads ~100 MB, so tell the user it takes a
minute or two. Then `LEO run --stay` starts the pet now; otherwise it starts with the next
Claude Code session.

## Make an avatar from the user's picture
The user gives a path to a png/jpg/webp.

    LEO avatar /path/to/picture.jpg --style sticker --remove-bg

Styles: `sticker` (white outline, default), `cartoon` (flat colours and ink lines),
`pixel` (chunky pixel art), `original` (rounded square, picture untouched), `toon` (only the head is
taken from the photo, cartoonized, on a drawn full body).
For `toon`, add `--body boy` or `--body girl`. ALWAYS ask the user which body/outfit they want; never
decide from the photo. It needs a front-facing portrait with the whole head in frame.
`--remove-bg` makes a plain-coloured background transparent; use it for photos on a plain
wall or flat colour, skip it for busy backgrounds. Run again with another style to compare.
`LEO character leo|boy|girl` picks a character (leo = the lion cub, the default) (or a pack folder name from ~/.leo/characters).

`LEO water on|off`, `LEO water --every MINUTES` and `LEO water --now` control the hydration reminder (Leo drinks from a bottle and reminds the user to drink water; default off, every 45 minutes). `LEO avatar --reset` removes an uploaded picture and returns to the built-in character; who walks, sits, sleeps and jumps depending on state. A running pet reloads automatically.
The pet's right-click menu has the same options (Upload avatar, Avatar style, Size, Mute).

## Check or demo
- `LEO send thinking` shows a state for 5 seconds (idle greeting thinking working done waiting permission sleeping)
- `LEO quit` stops the pet
- Not reacting? Check `~/.leo/venv` exists, run `LEO run --stay`, then `LEO send done`.

Settings: `~/.leo/config.json` (style, remove_bg, size, muted, x, y).
