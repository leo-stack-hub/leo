import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from leo import avatar, states  # noqa: E402


@pytest.fixture(autouse=True)
def jhome(tmp_path, monkeypatch):
    monkeypatch.setenv("LEO_HOME", str(tmp_path / "jh"))
    return tmp_path / "jh"


def ev(event, t, **kw):
    return {"event": event, "session": kw.pop("session", "a"), "ts": t, **kw}


def test_turn_lifecycle_and_duration():
    tr = states.Tracker()
    assert tr.apply(ev("SessionStart", 0)) == "hello"
    tr.apply(ev("UserPromptSubmit", 10))
    tr.apply(ev("PreToolUse", 11, tool="Bash"))
    assert tr.display().text == "Leo is running a command…"
    assert tr.apply(ev("Stop", 262)) == "done"
    assert tr.display().text == "Leo finished in 4m 12s!"
    tr.tick(262 + 5)
    assert tr.display().state == "waiting"
    assert "4m 12s" in tr.display().text


def test_permission_beats_everything_across_sessions():
    tr = states.Tracker()
    tr.apply(ev("UserPromptSubmit", 1, session="a"))
    assert tr.apply(ev("Notification", 2, session="b", ntype="permission_prompt")) == "alert"
    d = tr.display()
    assert d.state == "permission" and d.sessions == 2 and "2 sessions" in d.text


def test_end_stale_and_sleep():
    tr = states.Tracker()
    tr.apply(ev("UserPromptSubmit", 0))
    tr.tick(states.STALE_BUSY_AFTER + 1)
    assert tr.display().state == "idle"
    tr.tick(states.STALE_BUSY_AFTER + 1 + states.SLEEP_AFTER + 1)
    assert tr.display().state == "sleeping"
    tr.apply(ev("SessionEnd", 1))
    assert tr.sessions == {}


def test_quick_tools_stay_visible_then_think():
    tr = states.Tracker()
    tr.apply(ev("UserPromptSubmit", 0))
    tr.apply(ev("PreToolUse", 1, tool="Read"))
    tr.apply(ev("PostToolUse", 1.05, tool="Read"))  # Read finishes in a blink
    tr.tick(1.05 + states.TOOL_LINGER - 0.1)
    d = tr.display()
    assert d.state == "working" and d.detail == "reading"  # still on screen with his book
    tr.tick(1.05 + states.TOOL_LINGER)
    assert tr.display().state == "thinking"
    tr.apply(ev("PreToolUse", 5, tool="Edit"))
    tr.apply(ev("PostToolUse", 5.1, tool="Edit"))
    assert tr.display().detail == "typing"
    tr.apply(ev("Notification", 5.2, ntype="permission_prompt"))  # urgent states win at once
    assert tr.display().state == "permission"


@pytest.mark.parametrize("command,detail", [
    ("cat README.md", "reading"), ("cd /src && grep -rn foo .", "reading"),
    ("git log --oneline", "reading"), ("sed -n 1,40p a.py", "reading"),
    ("sed -i '' s/a/b/ a.py", "typing"), ("FOO=1 ls -la", "reading"),
    ("npm test", "running a command"), ("git push", "running a command"),
    ("python3 -m pytest | tail -5", "running a command"),
])
def test_bash_commands_classified(command, detail):
    assert states.tool_detail("Bash", command) == detail


def test_hook_passes_the_shell_command():
    from leo import hook

    msg = hook.build_message({"hook_event_name": "PreToolUse", "tool_name": "Bash",
                              "tool_input": {"command": "cat a.txt"}})
    assert msg["tool"] == "Bash" and msg["command"] == "cat a.txt"
    assert hook.build_message({"hook_event_name": "PreToolUse", "tool_name": "Read",
                               "tool_input": {"file_path": "a"}})["command"] is None


def test_auth_notification_ignored():
    assert states.Tracker().apply(ev("Notification", 1, ntype="auth_success")) is None


@pytest.mark.parametrize("style", [x for x in avatar.STYLES if x != "toon"])
@pytest.mark.parametrize("remove_bg", [False, True])
def test_every_style_makes_256_rgba(tmp_path, style, remove_bg):
    from PIL import Image, ImageDraw

    src = tmp_path / "in.jpg"
    im = Image.new("RGB", (500, 300), (200, 230, 250))
    ImageDraw.Draw(im).ellipse([150, 50, 350, 250], fill=(220, 60, 60))
    im.save(src)
    out = avatar.make_avatar(src, style, remove_bg)
    assert out.size == (256, 256) and out.mode == "RGBA"
    assert out.getchannel("A").getextrema()[0] == 0  # transparent corners


def test_remove_bg_cuts_background(tmp_path):
    from PIL import Image, ImageDraw

    im = Image.new("RGB", (400, 400), (10, 200, 10))
    ImageDraw.Draw(im).ellipse([100, 100, 300, 300], fill=(250, 250, 0))
    im.save(tmp_path / "x.png")
    cut = avatar.remove_background(avatar.load_square(tmp_path / "x.png"))
    assert cut.getpixel((3, 3))[3] < 20 and cut.getpixel((128, 128))[3] > 240


def test_save_restyle_reset(tmp_path, jhome):
    from PIL import Image

    Image.new("RGB", (80, 80), (1, 2, 3)).save(tmp_path / "p.png")
    avatar.save_avatar(tmp_path / "p.png", "pixel", False)
    assert avatar.avatar_path().exists() and avatar.source_path().exists()
    assert avatar.custom_avatar() is not None
    avatar.restyle("cartoon", True)
    assert json.loads((jhome / "config.json").read_text())["style"] == "cartoon"
    avatar.save_avatar(None)  # back to the built-in character
    assert not avatar.source_path().exists() and avatar.custom_avatar() is None
    assert json.loads((jhome / "config.json").read_text())["custom"] is False


def test_restyle_needs_an_upload_first():
    with pytest.raises(ValueError):
        avatar.restyle("pixel", False)


def test_bad_image_keeps_old_avatar(tmp_path):
    from PIL import Image

    Image.new("RGB", (80, 80), (9, 9, 9)).save(tmp_path / "ok.png")
    avatar.save_avatar(tmp_path / "ok.png")
    before = avatar.avatar_path().read_bytes()
    (tmp_path / "bad.png").write_text("not an image")
    with pytest.raises(Exception):
        avatar.save_avatar(tmp_path / "bad.png")
    assert avatar.avatar_path().read_bytes() == before


def test_hook_is_silent_and_exits_zero_without_pet(jhome):
    env = dict(os.environ, LEO_HOME=str(jhome), LEO_NO_LAUNCH="1")
    for stdin in (json.dumps({"hook_event_name": "Stop"}), "garbage", ""):
        r = subprocess.run([sys.executable, str(ROOT / "leo/hook.py")], input=stdin.encode(),
                           env=env, capture_output=True)
        assert r.returncode == 0 and r.stdout == b"" and r.stderr == b""


def test_hooks_json_covers_events():
    h = json.loads((ROOT / ".claude-plugin/../hooks/hooks.json").read_text())["hooks"]
    assert {"SessionStart", "UserPromptSubmit", "PreToolUse", "Notification", "Stop",
            "SessionEnd"} <= set(h)


def test_venv_python_paths_per_platform(jhome):
    from leo import common

    assert common.venv_python(platform="darwin") == jhome / "venv" / "bin" / "python"
    assert common.venv_python(platform="win32").name == "python.exe"
    assert common.venv_python(windowed=True, platform="win32").name == "pythonw.exe"


def test_send_without_pet_raises_oserror():
    from leo import common

    with pytest.raises(OSError):
        common.send({"event": "Stop"})


def test_hooks_use_the_sh_launcher():
    h = json.loads((ROOT / "hooks/hooks.json").read_text())["hooks"]
    cmds = {x["command"] for v in h.values() for e in v for x in e["hooks"]}
    assert cmds == {'sh "${CLAUDE_PLUGIN_ROOT}/hooks/leo-hook"'}


@pytest.mark.parametrize("who", ["boy", "girl"])
@pytest.mark.parametrize("state,detail", [
    ("sleeping", None), ("idle", None), ("greeting", None), ("thinking", None),
    ("working", "reading"), ("working", "typing"), ("working", "running a command"),
    ("done", None), ("waiting", None), ("permission", None), ("hydrate", None),
])
def test_people_draw_every_state(who, state, detail):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtWidgets import QApplication

    from leo import people

    QApplication.instance() or QApplication([])
    img = QImage(people.W + 40, people.H + 20, QImage.Format_ARGB32)
    img.fill(0)
    p = QPainter(img)
    p.translate(img.width() / 2, img.height() - 8)
    people.draw_person(p, who, state, detail, 0.41)
    p.end()
    assert any(img.pixelColor(x, y).alpha() for x in range(0, img.width(), 7) for y in range(0, img.height(), 7))


def test_character_registry_and_switch(tmp_path, monkeypatch):
    from leo import avatar, characters, config

    monkeypatch.setenv("LEO_HOME", str(tmp_path))
    assert set(characters.CHARACTERS) == {"leo", "boy", "girl"}
    assert characters.get("nope").key == "leo"
    w, h = characters.screen_size(characters.get("girl"), 128)
    assert h > w
    avatar.use_character("girl")
    cfg = config.load()
    assert cfg["character"] == "girl" and cfg["custom"] is False and avatar.custom_avatar() is None
    with pytest.raises(ValueError):
        avatar.use_character("dragon")


def test_packs_find_and_fallback(tmp_path, monkeypatch):
    from leo import packs

    monkeypatch.setenv("LEO_HOME", str(tmp_path))
    mine = tmp_path / "characters" / "fox"
    mine.mkdir(parents=True)
    assert "fox" not in packs.find()  # no idle picture yet
    (mine / "idle.png").write_bytes(b"x")
    (mine / "typing.png").write_bytes(b"x")
    found = packs.find()
    assert found["fox"] == mine
    assert packs.picture(mine, "working", "typing a file").name == "typing.png"
    assert packs.picture(mine, "working", "reading a file").name == "idle.png"  # falls back
    assert packs.picture(mine, "sleeping").name == "idle.png"


@pytest.mark.parametrize("state,detail", [
    ("idle", None), ("greeting", None), ("thinking", None), ("working", "reading"),
    ("working", "typing"), ("working", "running a command"), ("done", None),
    ("waiting", None), ("permission", None), ("sleeping", None),
])
def test_leo_animates_every_state(state, detail):
    np = pytest.importorskip("numpy")
    cv2 = pytest.importorskip("cv2")
    from leo import animate

    im = np.zeros((200, 160, 4), np.uint8)  # a plain orange block stands in for a picture
    im[40:190, 30:130] = (230, 150, 60, 255)
    a = animate.Animator(im)
    frames = a.frames(state, detail)
    assert len(frames) == animate.N and frames[0].shape == im.shape
    assert frames[0].dtype == np.uint8
    assert any(not np.array_equal(frames[0], f) for f in frames[1:])  # it actually moves


def test_hydrate_reminder_schedule():
    from leo import hydrate

    r = hydrate.Reminder(True, 30, now=0)
    assert not r.tick(29 * 60)                      # not yet
    assert r.tick(30 * 60) and r.active              # due: starts
    assert not r.tick(30 * 60 + 5)                   # no double start
    assert r.tick(30 * 60 + hydrate.SHOW_SECS) is False and not r.active  # fades by itself
    assert r.next == 30 * 60 + hydrate.SHOW_SECS + 30 * 60
    r.configure(True, 30, now=100)                   # same settings: countdown untouched
    assert r.next != 100 + 30 * 60
    r.configure(True, 15, now=1000)                  # new interval restarts it
    assert r.next == 1000 + 15 * 60 and r.minutes_left(1000) == 15


def test_hydrate_snooze():
    from leo import hydrate

    r = hydrate.Reminder(True, 45, now=0)
    assert r.tick(45 * 60)  # reminder starts
    r.snooze(45 * 60 + 5)
    assert not r.active and r.next == 45 * 60 + 5 + hydrate.SNOOZE_MINUTES * 60
    assert not r.tick(r.next - 1) and r.tick(r.next)  # comes back after the snooze


def test_hydrate_off_busy_and_clamp():
    from leo import hydrate

    assert not hydrate.Reminder(False, 1, now=0).tick(10_000)  # off never fires
    r = hydrate.Reminder(True, 1, now=0)
    assert not r.tick(61, can_show=False) and not r.active and r.next == 121  # busy: postponed
    assert r.tick(121)
    assert hydrate.clamp(0) == 1 and hydrate.clamp(9999) == 480 and hydrate.clamp("x") == 45
    r.dismiss(200)
    assert not r.active


def test_water_cli_saves_settings(tmp_path, monkeypatch, capsys):
    from leo import __main__ as cli
    from leo import config

    monkeypatch.setenv("LEO_HOME", str(tmp_path))
    assert cli.main(["water", "--every", "20"]) == 0
    cfg = config.load()
    assert cfg["hydrate"] is True and cfg["hydrate_minutes"] == 20
    assert cli.main(["water", "off"]) == 0
    assert config.load()["hydrate"] is False


@pytest.mark.parametrize("state,detail", [
    ("sleeping", None), ("idle", None), ("greeting", None), ("thinking", None),
    ("working", "reading"), ("working", "typing"), ("working", "running a command"),
    ("done", None), ("waiting", None), ("permission", None), ("hydrate", None),
])
def test_lion_draws_every_state(state, detail):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtWidgets import QApplication

    from leo import lion

    QApplication.instance() or QApplication([])
    img = QImage(lion.W + 40, lion.H + 20, QImage.Format_ARGB32)
    img.fill(0)
    p = QPainter(img)
    p.translate(img.width() / 2, img.height() - 8)
    lion.draw_lion(p, state, detail, 0.41)
    p.end()
    assert any(img.pixelColor(x, y).alpha() for x in range(0, img.width(), 7) for y in range(0, img.height(), 7))


# --- Leo as an app / start at login ----------------------------------------------------------


@pytest.fixture
def fake_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("APPDATA", str(tmp_path / "AppData" / "Roaming"))
    return tmp_path


def test_mac_app_and_login_item(fake_home, jhome):
    import plistlib

    from leo import autostart

    login = autostart.set_login(True, "darwin", icons=False)
    app = fake_home / "Applications" / "Leo.app"
    exe = app / "Contents" / "MacOS" / "Leo"
    assert exe.exists() and os.access(exe, os.X_OK) and "launch.py" in exe.read_text()
    info = plistlib.loads((app / "Contents" / "Info.plist").read_bytes())
    assert info["CFBundleExecutable"] == "Leo" and info["LSUIElement"] is True
    agent = plistlib.loads(login.read_bytes())
    assert agent["RunAtLoad"] is True and agent["ProgramArguments"] == [str(exe)]
    assert autostart.enabled("darwin")
    autostart.set_login(False, "darwin")
    assert not autostart.enabled("darwin") and app.exists()  # app stays, login item gone
    autostart.remove_all("darwin")
    assert not app.exists() and not (jhome / "launch.py").exists()


def test_linux_desktop_entries(fake_home, jhome):
    from leo import autostart

    autostart.set_login(True, "linux", icons=False)
    for f in (fake_home / ".local/share/applications/leo.desktop",
              fake_home / ".config/autostart/leo.desktop"):
        text = f.read_text()
        assert "Name=Leo" in text and str(jhome / "launch.py") in text


def test_windows_shortcut_script_uses_pythonw():
    from leo import autostart

    ps = autostart.win_shortcut_script(Path("C:/Users/O'Neil/Start Menu/Leo.lnk"), None)
    assert "pythonw.exe" in ps and "launch.py" in ps and "O''Neil" in ps and ps.endswith("$s.Save()")


def test_launcher_finds_the_installed_plugin(fake_home, jhome):
    from leo import autostart

    code = autostart.write_launcher().read_text()
    compile(code, "launch.py", "exec")
    ns: dict = {}
    exec(code.split("\nroot = plugin_root()")[0], ns)  # everything but the actual start
    assert ns["plugin_root"]() == autostart.ROOT  # nothing installed: falls back to this copy
    plugins = fake_home / ".claude" / "plugins"
    plugins.mkdir(parents=True)
    (plugins / "installed_plugins.json").write_text(json.dumps(
        {"plugins": {"leo@leo": [{"installPath": str(ROOT)}]}}))
    assert ns["plugin_root"]() == ROOT


def test_mac_app_runs_python_natively():
    from leo import autostart

    assert "/usr/bin/arch -arm64 " in autostart.mac_exe_script("arm64")
    assert "/usr/bin/arch -x86_64 " in autostart.mac_exe_script("x86_64")
    assert "arch" not in autostart.mac_exe_script("ppc")
