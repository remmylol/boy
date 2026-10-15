import os, subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def test_live_mode_rejected():
    env = dict(os.environ, PAPER_MODE="false", LIVE_TRADING_ENABLED="false")
    p = subprocess.run([sys.executable, str(ROOT/'bot.py')], env=env, capture_output=True, text=True, timeout=8)
    assert p.returncode == 2

def test_live_flag_rejected():
    env = dict(os.environ, PAPER_MODE="true", LIVE_TRADING_ENABLED="true")
    p = subprocess.run([sys.executable, str(ROOT/'bot.py')], env=env, capture_output=True, text=True, timeout=8)
    assert p.returncode == 2
