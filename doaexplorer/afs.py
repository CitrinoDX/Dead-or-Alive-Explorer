"""CRI AFS archive reader (used by DOA2U and DOAX2)."""
import os, struct, threading


class Afs:
    """AFS\\0, count, (offset, size) x count, then a pointer to 48-byte name records (32-byte name + 16 meta)."""

    def __init__(self, path, stream=None):
        """path: file on disk, or a display name when stream (any seekable binary file object) is given"""
        self.path = path
        self.name = os.path.basename(path)
        self._f = stream or open(path, "rb")
        self._lock = threading.Lock()
        h = self._f.read(8)
        if h[:3] != b"AFS":
            raise ValueError("%s is not an AFS archive" % path)
        n = struct.unpack_from("<I", h, 4)[0]
        toc = self._f.read(8 * n + 8)
        self.toc = [struct.unpack_from("<II", toc, 8 * i) for i in range(n)]
        noff, nlen = struct.unpack_from("<II", toc, 8 * n)
        if not noff and n and self.toc[0][0] >= 16:
            # some builds keep the name-table pointer just before the first file instead of after the TOC
            self._f.seek(self.toc[0][0] - 8)
            noff, nlen = struct.unpack("<II", self._f.read(8))
        self.names = [None] * n
        if noff and nlen >= n * 48:
            self._f.seek(noff)
            blob = self._f.read(n * 48)
            if len(blob) == n * 48:
                self.names = [blob[i * 48:i * 48 + 32].split(b"\0")[0].decode("latin-1") or None for i in range(n)]
        self._index = {}
        for i, nm in enumerate(self.names):
            if nm:
                self._index.setdefault(nm.lower(), i)

    def __len__(self):
        return len(self.toc)

    def size(self, i):
        return self.toc[i][1]

    def find(self, name):
        return self._index.get(name.lower())

    def read(self, i, length=None):
        off, ln = self.toc[i]
        if length is not None:
            ln = min(ln, length)
        with self._lock:
            self._f.seek(off)
            return self._f.read(ln)
