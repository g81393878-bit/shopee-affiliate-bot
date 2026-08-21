"""เทสต์ guard ของ tools/render_set_env.py — ต้องระบุคำสั่งชัดเจน

เจอจริง (21/08): รันด้วย --help ไปโดน batch mode (set env 5 ตัว + deploy) —
guard ใหม่: ไม่มีคำสั่ง / --help / คำสั่งไม่รู้จัก → โชว์ usage + exit 2 ไม่ทำอะไร
"""
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "render_set_env.py"


def _load():
    spec = importlib.util.spec_from_file_location("render_set_env_under_test", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_no_args_prints_usage_and_exits_2(monkeypatch, capsys):
    mod = _load()
    monkeypatch.setattr(sys, "argv", ["render_set_env.py"])
    with pytest.raises(SystemExit) as exc:
        mod.main()
    assert exc.value.code == 2
    assert "usage" in capsys.readouterr().out


def test_help_flag_prints_usage_and_exits_2(monkeypatch, capsys):
    """--help ต้องไม่โดน batch mode (เคย deploy เผลอ)"""
    mod = _load()
    monkeypatch.setattr(sys, "argv", ["render_set_env.py", "--help"])
    with pytest.raises(SystemExit) as exc:
        mod.main()
    assert exc.value.code == 2
    assert "usage" in capsys.readouterr().out


def test_unknown_command_prints_usage(monkeypatch, capsys):
    mod = _load()
    monkeypatch.setattr(sys, "argv", ["render_set_env.py", "frobnicate"])
    with pytest.raises(SystemExit) as exc:
        mod.main()
    assert exc.value.code == 2
    assert "usage" in capsys.readouterr().out


def test_no_args_never_calls_api(monkeypatch, capsys):
    """ไม่มีคำสั่ง → ไม่เรียก API เลย (กัน set+deploy เผลอ)"""
    mod = _load()
    monkeypatch.setattr(sys, "argv", ["render_set_env.py"])
    called = []
    monkeypatch.setattr(mod, "request",
                        lambda *a, **k: called.append(a) or (500, "should not call"))
    with pytest.raises(SystemExit):
        mod.main()
    assert called == []
