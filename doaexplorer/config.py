"""config.json next to run_explorer.py: per-machine game folders and data folders (never committed)."""
import json, os

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
CONFIG = os.path.join(ROOT, "config.json")
NAMES = os.path.join(ROOT, "names.json")


def load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def load():
    cfg = load_json(CONFIG)
    cfg.setdefault("games", {})
    cfg.setdefault("data", {})
    return cfg


def save(cfg):
    with open(CONFIG, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
