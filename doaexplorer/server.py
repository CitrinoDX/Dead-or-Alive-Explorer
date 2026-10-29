"""HTTP backend: serves the viewer page, a small JSON/PNG API over the configured games, and the Setup endpoints
that let users point the viewer at their own game files and optional data folders. Nothing is ever written to
those folders; the only file the server writes is config.json."""
import json, os, threading, traceback
from collections import OrderedDict
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, unquote
from . import export, config, __version__
from .games import GAMES, BY_KEY, ORDER, PLANNED
from .sources import Sources, find_greedxplorer, find_skeletons

STATIC = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "static"))
CACHE_SIZE = 8
LOCAL_HOSTS = ("127.0.0.1", "localhost")

try:
    import tkinter  # noqa: F401  (native file/folder dialogs for Setup)
    HAVE_DIALOGS = True
except ImportError:
    HAVE_DIALOGS = False
_dialog_lock = threading.Lock()


def browse(mode):
    """Open a native folder (mode='folder') or disc-image (mode='file') picker on this machine. -> path or None"""
    import tkinter as tk
    from tkinter import filedialog
    with _dialog_lock:
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        try:
            if mode == "file":
                p = filedialog.askopenfilename(parent=root, title="Choose a disc image",
                                               filetypes=[("Xbox disc image", "*.iso *.xiso"), ("All files", "*.*")])
            else:
                p = filedialog.askdirectory(parent=root, title="Choose a game or data folder", mustexist=True)
        finally:
            root.destroy()
    return os.path.normpath(p) if p else None


class App:
    def __init__(self, cfg, names=None):
        self.cfg = cfg
        self.names = names or {}
        self.lock = threading.RLock()
        self.cache = OrderedDict()
        self.loading = {}
        self.games = {}               # key -> Game
        self.errors = {}              # key -> (folder, message) for configured games that failed to open
        self.sources = Sources(cfg["data"].get("greedxplorer"), cfg["data"].get("skeletons"))
        for cls in GAMES:
            folder = cfg["games"].get(cls.key)
            if folder:
                self._open(cls, folder)

    # ---- games and data folders
    def _open(self, cls, folder):
        try:
            self.games[cls.key] = cls(folder, self.names, self.sources)
            self.errors.pop(cls.key, None)
        except Exception as e:
            self.games.pop(cls.key, None)
            self.errors[cls.key] = (folder, "%s: %s" % (type(e).__name__, e))

    def _reload_sources(self):
        self.sources = Sources(self.cfg["data"].get("greedxplorer"), self.cfg["data"].get("skeletons"))
        for g in self.games.values():
            g.set_sources(self.sources)

    def _changed(self):
        self.cache.clear()
        config.save(self.cfg)

    def add_path(self, path):
        """Detect every supported game and data folder in path (a folder or a disc image). -> list of findings"""
        path = os.path.abspath(os.path.expanduser(path.strip().strip('"')))
        if not os.path.exists(path):
            raise ValueError("not found: %s" % path)
        found = []
        with self.lock:
            for cls in GAMES:
                root = cls.find_root(path)
                if root:
                    self.cfg["games"][cls.key] = root
                    self._open(cls, root)
                    msg = "%s (%s)" % (cls.title, cls.platform)
                    found.append(msg + (" - could not open: " + self.errors[cls.key][1] if cls.key in self.errors else ""))
            gx, sk = find_greedxplorer(path), find_skeletons(path)
            if gx:
                self.cfg["data"]["greedxplorer"] = gx
                found.append("GreedXplorer layouts")
            if sk:
                self.cfg["data"]["skeletons"] = sk
                found.append("Team Ninja importer skeletons")
            if gx or sk:
                self._reload_sources()
            if found:
                self._changed()
        return found

    def remove(self, kind, key):
        with self.lock:
            if kind == "game":
                self.cfg["games"].pop(key, None)
                self.games.pop(key, None)
                self.errors.pop(key, None)
            elif kind == "data" and key in ("greedxplorer", "skeletons"):
                self.cfg["data"].pop(key, None)
                self._reload_sources()
            self._changed()

    # ---- models
    def scene(self, key, sid):
        k = (key, sid)
        with self.lock:
            if k in self.cache:
                self.cache.move_to_end(k)
                return self.cache[k]
            klock = self.loading.setdefault(k, threading.Lock())
            game = self.games[key]
        with klock:
            with self.lock:
                if k in self.cache:
                    return self.cache[k]
            sc = game.load(sid)
            with self.lock:
                self.cache[k] = sc
                while len(self.cache) > CACHE_SIZE:
                    self.cache.popitem(last=False)
                self.loading.pop(k, None)
            return sc

    # ---- JSON
    def games_json(self, everything=False):
        """Added games in the picker's order; everything=True also lists the games not added yet (added=False)."""
        with self.lock:
            have = {k: dict(key=k, title=g.title, platform=g.platform, folder=g.folder, summary=g.summary())
                    for k, g in self.games.items()}
            for k, (f, m) in self.errors.items():
                have[k] = dict(key=k, title=BY_KEY[k].title if k in BY_KEY else k,
                               platform=BY_KEY[k].platform if k in BY_KEY else "", folder=f, error=m)
        out = []
        for k in ORDER + [k for k in have if k not in ORDER]:
            if k in have:
                out.append(dict(have[k], added=True, supported=True))
            elif everything:
                title, platform = (BY_KEY[k].title, BY_KEY[k].platform) if k in BY_KEY else PLANNED[k]
                out.append(dict(key=k, title=title, platform=platform, added=False, supported=k in BY_KEY))
        return out

    def setup_json(self):
        return dict(version=__version__, games=self.games_json(), data=self.sources.summary(), dialogs=HAVE_DIALOGS,
                    supported=[dict(key=c.key, title=c.title, platform=c.platform, hint=c.hint) for c in GAMES])


def make_handler(app):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def send(self, code, body, ctype, extra=None):
            if isinstance(body, str):
                body = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def json(self, obj, code=200):
            return self.send(code, json.dumps(obj), "application/json")

        def local_only(self):
            """Only answer pages served from this machine (blocks DNS-rebinding style access from websites)."""
            host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]").lower()
            if host not in LOCAL_HOSTS:
                self.send(403, "forbidden", "text/plain")
                return False
            return True

        def do_POST(self):
            if not self.local_only():
                return
            # the custom header forces a CORS preflight, which this server never approves, so other sites can't post
            if self.headers.get("X-DOA-Explorer") != "1":
                return self.send(403, "forbidden", "text/plain")
            try:
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(min(n, 65536)) or b"{}")
                p = urlparse(self.path).path
                if p == "/api/setup/browse":
                    if not HAVE_DIALOGS:
                        return self.json(dict(path=None, error="no native dialog available - paste the path instead"))
                    return self.json(dict(path=browse(body.get("mode", "folder"))))
                if p == "/api/setup/add":
                    found = app.add_path(str(body.get("path", "")))
                    return self.json(dict(found=found, setup=app.setup_json()))
                if p == "/api/setup/remove":
                    app.remove(body.get("kind"), body.get("key"))
                    return self.json(dict(setup=app.setup_json()))
                return self.send(404, "not found", "text/plain")
            except ValueError as e:
                return self.json(dict(error=str(e)), 400)
            except Exception as e:
                traceback.print_exc()
                return self.json(dict(error="%s: %s" % (type(e).__name__, e)), 500)

        def do_GET(self):
            if not self.local_only():
                return
            u = urlparse(self.path)
            parts = [unquote(p) for p in u.path.split("/") if p]
            q = parse_qs(u.query)
            try:
                if not parts or parts == ["index.html"]:
                    with open(os.path.join(STATIC, "index.html"), "rb") as f:
                        return self.send(200, f.read(), "text/html; charset=utf-8")
                if parts[0] != "api" or len(parts) < 2:
                    return self.send(404, "not found", "text/plain")
                cmd = parts[1]
                if cmd == "games":
                    return self.json(app.games_json(everything=True))
                if cmd == "setup":
                    return self.json(app.setup_json())
                key = parts[2] if len(parts) > 2 else None
                if key not in app.games:
                    return self.send(404, "unknown game %s" % key, "text/plain")
                game = app.games[key]
                if cmd == "library":
                    return self.json(dict(key=key, title=game.title, folder=game.folder, groups=game.tree(),
                                          dress=hasattr(game, "dress")))
                if cmd == "dress" and hasattr(game, "dress"):
                    return self.json(game.dress())
                if cmd == "model" and len(parts) == 4:
                    return self.json(app.scene(key, parts[3]).payload())
                if cmd == "tex" and len(parts) == 5:
                    sc = app.scene(key, parts[3])
                    opaque = q.get("opaque", ["0"])[0] == "1"
                    return self.send(200, sc.texture_png(int(parts[4].split(".")[0]), opaque), "image/png")
                if cmd == "textures" and len(parts) == 4 and parts[3].endswith(".zip"):
                    sid = parts[3][:-4]
                    data = export.export_textures_zip(app.scene(key, sid), sid)
                    return self.send(200, data, "application/zip", disposition("%s_%s_textures.zip" % (key, sid)))
                if cmd == "export" and len(parts) == 4:
                    fn = parts[3]
                    ext = next((x for x in (".obj.zip", ".glb", ".fbx") if fn.endswith(x)), None)
                    if not ext:
                        return self.send(404, "unknown export type", "text/plain")
                    sid = fn[:-len(ext)]
                    sc = app.scene(key, sid)
                    if "parts" in q:
                        ids = [int(v) for v in q["parts"][0].split(",") if v != ""]
                    else:
                        ids = [i for i, p in enumerate(sc.parts) if p["visible"]]
                    base = "%s_%s" % (key, export.safe(sc.export_name or sid))
                    if ext == ".glb":
                        return self.send(200, export.export_glb(sc, ids, base), "model/gltf-binary", disposition(base + ".glb"))
                    if ext == ".fbx":
                        return self.send(200, export.export_fbx(sc, ids, base), "application/octet-stream", disposition(base + ".fbx"))
                    return self.send(200, export.export_obj_zip(sc, ids, base), "application/zip", disposition(base + "_obj.zip"))
                return self.send(404, "not found", "text/plain")
            except KeyError as e:
                return self.send(404, "unknown entry %s" % e, "text/plain")
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception as e:
                traceback.print_exc()
                return self.send(500, "%s: %s" % (type(e).__name__, e), "text/plain")
    return H


def disposition(filename):
    return {"Content-Disposition": 'attachment; filename="%s"' % export.safe(filename)}


def serve(app, port, on_ready=None):
    srv = ThreadingHTTPServer(("127.0.0.1", port), make_handler(app))
    srv.daemon_threads = True
    if on_ready:
        on_ready("http://127.0.0.1:%d/" % srv.server_address[1])
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
