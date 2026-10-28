"""Read game files from a plain folder or straight out of an Xbox disc image (XDVDFS / .xiso / redump .iso)."""
import io, os, struct

SECTOR = 2048
XISO_MAGIC = b"MICROSOFT*XBOX*MEDIA"
XISO_BASES = (0, 0x18300000, 0xFD90000, 0x2080000)   # xiso, redump game partition, early/late discs


class SubFile(io.RawIOBase):
    """Read-only window [offset, offset+size) of a file, with its own handle (safe to use from one thread)."""

    def __init__(self, path, offset, size):
        self._f = open(path, "rb")
        self._off, self._size, self._pos = offset, size, 0

    def readable(self):
        return True

    def seekable(self):
        return True

    def seek(self, pos, whence=0):
        self._pos = pos if whence == 0 else self._pos + pos if whence == 1 else self._size + pos
        return self._pos

    def tell(self):
        return self._pos

    def read(self, n=-1):
        n = self._size - self._pos if n is None or n < 0 else min(n, self._size - self._pos)
        if n <= 0:
            return b""
        self._f.seek(self._off + self._pos)
        b = self._f.read(n)
        self._pos += len(b)
        return b

    def close(self):
        self._f.close()
        super().close()


class DirFS:
    def __init__(self, root):
        self.root = root
        self.label = root

    def _p(self, rel):
        return os.path.join(self.root, *rel.split("/"))

    def exists(self, rel):
        return os.path.exists(self._p(rel))

    def size(self, rel):
        return os.path.getsize(self._p(rel))

    def open(self, rel):
        return open(self._p(rel), "rb")

    def read(self, rel):
        with self.open(rel) as f:
            return f.read()

    def listdir(self, rel=""):
        p = self._p(rel) if rel else self.root
        return sorted(os.listdir(p)) if os.path.isdir(p) else []


class XIso:
    """XDVDFS: volume descriptor at sector 32 of the game partition; directories are binary trees of
    (left u16, right u16 [in dwords], sector u32, size u32, attributes u8, name length u8, name)."""

    def __init__(self, path):
        self.path = path
        self.label = path
        self.files = {}      # lower-case 'dir/name' -> (absolute offset, size)
        self.dirs = {"": []}
        with open(path, "rb") as f:
            self.base = None
            for b in XISO_BASES:
                f.seek(b + 32 * SECTOR)
                if f.read(20) == XISO_MAGIC:
                    self.base = b
                    break
            if self.base is None:
                raise ValueError("%s is not an Xbox disc image" % path)
            root_sector, root_size = struct.unpack("<II", f.read(8))
            self._walk(f, root_sector, root_size, "")

    def _walk(self, f, sector, size, prefix, depth=0):
        if depth > 32 or not size:
            return
        f.seek(self.base + sector * SECTOR)
        data = f.read(size)
        stack, seen = [0], set()
        while stack:
            off = stack.pop()
            if off in seen or off + 14 > len(data):
                continue
            seen.add(off)
            left, right, sec, sz, attr, nl = struct.unpack_from("<HHIIBB", data, off)
            if left == 0xFFFF and right == 0xFFFF:
                continue
            name = data[off + 14:off + 14 + nl].decode("latin-1")
            if left:
                stack.append(left * 4)
            if right:
                stack.append(right * 4)
            rel = prefix + name
            self.dirs.setdefault(prefix.rstrip("/"), []).append(name)
            if attr & 0x10:
                self.dirs.setdefault(rel, [])
                self._walk(f, sec, sz, rel + "/", depth + 1)
            else:
                self.files[rel.lower()] = (self.base + sec * SECTOR, sz)

    def _key(self, rel):
        return rel.replace("\\", "/").strip("/").lower()

    def exists(self, rel):
        k = self._key(rel)
        return k in self.files or any(d.lower() == k for d in self.dirs)

    def size(self, rel):
        return self.files[self._key(rel)][1]

    def open(self, rel):
        off, sz = self.files[self._key(rel)]
        return SubFile(self.path, off, sz)

    def read(self, rel):
        off, sz = self.files[self._key(rel)]
        with open(self.path, "rb") as f:
            f.seek(off)
            return f.read(sz)

    def listdir(self, rel=""):
        k = self._key(rel)
        for d, names in self.dirs.items():
            if d.lower() == k:
                return sorted(names, key=str.lower)
        return []


def open_source(path):
    """A folder or a disc image -> DirFS / XIso"""
    if os.path.isfile(path):
        return XIso(path)
    return DirFS(path)


def is_disc_image(path):
    if not os.path.isfile(path) or os.path.getsize(path) < 33 * SECTOR:
        return False
    with open(path, "rb") as f:
        for b in XISO_BASES:
            f.seek(b + 32 * SECTOR)
            if f.read(20) == XISO_MAGIC:
                return True
    return False
