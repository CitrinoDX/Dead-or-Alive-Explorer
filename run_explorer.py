#!/usr/bin/env python3
"""Dead or Alive Explorer - one local viewer for the Dead or Alive games' models and textures.

    python run_explorer.py                      then use Setup in the browser to add your games
    python run_explorer.py "D:\\Games\\DOA2U"     add (and remember) any game folder or disc image it recognises
    python run_explorer.py --doax2 DIR --greedxplorer DIR --skeletons DIR
    options: --port 8765  --no-browser  --forget KEY

No game data is included: the viewer reads your own copies, read-only. Folders are remembered in config.json.
Needs Python 3.8+ and numpy. Works offline.
"""
import argparse, os, sys, threading, webbrowser

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from doaexplorer import server, config, __version__
from doaexplorer.games import GAMES


def main():
    ap = argparse.ArgumentParser(description="Dead or Alive Explorer")
    ap.add_argument("paths", nargs="*", help="game folders, disc images or data folders to detect and remember")
    for g in GAMES:
        ap.add_argument("--" + g.key, metavar="DIR", help="%s (%s): %s" % (g.title, g.platform, g.hint))
    ap.add_argument("--greedxplorer", metavar="DIR", help="your GreedXplorer folder (optional limb layouts)")
    ap.add_argument("--skeletons", metavar="DIR", help="the Team Ninja importer's skeletons folder (optional)")
    ap.add_argument("--maxscripts", metavar="DIR", help="the DOA2U 3ds Max layout scripts folder (optional)")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--forget", metavar="KEY", action="append", default=[], help="drop a remembered game or data folder")
    ap.add_argument("--version", action="version", version="Dead or Alive Explorer " + __version__)
    a = ap.parse_args()
    print("Dead or Alive Explorer", __version__)

    cfg = config.load()
    for k in a.forget:
        cfg["games"].pop(k, None)
        cfg["data"].pop(k, None)
    for g in GAMES:
        v = getattr(a, g.key)
        if v:
            r = g.find_root(os.path.abspath(v))
            if r:
                cfg["games"][g.key] = r
            else:
                print("! %s: no %s data found in %s" % (g.key, g.title, v))
    for k in server.DATA_KEYS:
        if getattr(a, k):
            cfg["data"][k] = os.path.abspath(getattr(a, k))
    config.save(cfg)

    app = server.App(cfg, config.load_json(config.NAMES))
    for p in a.paths:
        try:
            found = app.add_path(p)
            print(("  %s: %s" % (p, ", ".join(found))) if found else "! nothing recognised in %s" % p)
        except ValueError as e:
            print("! %s" % e)

    for key, g in app.games.items():
        print("  %-6s %-38s %s  (%s)" % (key, g.title, g.folder, g.summary()))
    for key, (folder, msg) in app.errors.items():
        print("! %-6s %s: %s" % (key, folder, msg))
    if not app.games:
        print("No games added yet - open the viewer and use Setup to point it at your own game files.")

    def ready(url):
        print("Viewer running at", url, "- press Ctrl+C to stop")
        if not a.no_browser:
            threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    server.serve(app, a.port, ready)


if __name__ == "__main__":
    main()
