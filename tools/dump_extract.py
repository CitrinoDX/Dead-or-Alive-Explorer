#!/usr/bin/env python3
"""
dump_extract.py - pull useful pieces out of a Windows process dump (.DMP) of GreedXplorer.

How to make the dump (Windows 10/11):
  1. Open GX_003D.exe, open datahdd2.afs, click kas00.xpr so the model shows in the viewport.
  2. Task Manager -> Details tab -> right-click GX_003D.exe -> "Create memory dump file".
  3. Task Manager tells you where the .DMP was saved.

Usage:
    python dump_extract.py GX_003D.DMP [-o OUTDIR]

Outputs (small; zip OUTDIR and send it):
  modules.txt           module list with base addresses
  gx_image.bin          the in-memory image of GX_003D.exe (already unpacked) + gx_image.txt with its base
  xpr_<addr>_<size>.bin decrypted XPR/MDL buffers found in memory (the model data)
  mdl_<addr>.bin        fallback: 'MDL' blocks found without a full XPR header
Nothing is modified; the dump is only read.
"""
import os, struct, sys, bisect


class Dump:
    def __init__(self, path):
        self.f = open(path, "rb")
        h = self.f.read(32)
        if h[:4] != b"MDMP":
            raise SystemExit("not a minidump (.DMP) file")
        _, _, nstreams, dir_rva = struct.unpack_from("<IIII", h, 0)[0:4]
        nstreams = struct.unpack_from("<I", h, 8)[0]
        dir_rva = struct.unpack_from("<I", h, 12)[0]
        self.streams = {}
        self.f.seek(dir_rva)
        for _ in range(nstreams):
            t, size, rva = struct.unpack("<III", self.f.read(12))
            self.streams.setdefault(t, (size, rva))
        self.ranges = []  # (start, size, file_offset)
        self._read_memory()
        self.ranges.sort()
        self.starts = [r[0] for r in self.ranges]

    def _read_memory(self):
        if 9 in self.streams:  # Memory64ListStream
            size, rva = self.streams[9]
            self.f.seek(rva)
            n, base = struct.unpack("<QQ", self.f.read(16))
            descs = [struct.unpack("<QQ", self.f.read(16)) for _ in range(n)]
            off = base
            for start, sz in descs:
                self.ranges.append((start, sz, off))
                off += sz
        if 5 in self.streams:  # MemoryListStream
            size, rva = self.streams[5]
            self.f.seek(rva)
            n = struct.unpack("<I", self.f.read(4))[0]
            for _ in range(n):
                start, sz, off = struct.unpack("<QII", self.f.read(16))
                self.ranges.append((start, sz, off))

    def modules(self):
        res = []
        if 4 not in self.streams:
            return res
        size, rva = self.streams[4]
        self.f.seek(rva)
        n = struct.unpack("<I", self.f.read(4))[0]
        ents = [self.f.read(108) for _ in range(n)]
        for e in ents:
            base, msize, _, _, name_rva = struct.unpack_from("<QIIII", e, 0)
            self.f.seek(name_rva)
            ln = struct.unpack("<I", self.f.read(4))[0]
            name = self.f.read(ln).decode("utf-16le", "replace")
            res.append((base, msize, name))
        return res

    def read(self, addr, length):
        """Read virtual memory; unmapped bytes come back as zeros."""
        out = bytearray(length)
        i = bisect.bisect_right(self.starts, addr) - 1
        i = max(i, 0)
        while i < len(self.ranges):
            start, sz, off = self.ranges[i]
            if start >= addr + length:
                break
            lo = max(start, addr)
            hi = min(start + sz, addr + length)
            if hi > lo:
                self.f.seek(off + (lo - start))
                out[lo - addr:hi - addr] = self.f.read(hi - lo)
            i += 1
        return bytes(out)

    def scan(self, needle, chunk=1 << 24):
        for start, sz, off in self.ranges:
            pos = 0
            tail = b""
            while pos < sz:
                self.f.seek(off + pos)
                data = tail + self.f.read(min(chunk, sz - pos))
                base_addr = start + pos - len(tail)
                k = data.find(needle)
                while k != -1:
                    yield base_addr + k
                    k = data.find(needle, k + 1)
                tail = data[-(len(needle) - 1):] if len(needle) > 1 else b""
                pos += chunk


def main(argv):
    out = "dump_out"
    args = []
    it = iter(argv)
    for a in it:
        if a == "-o":
            out = next(it)
        else:
            args.append(a)
    if not args:
        print(__doc__)
        return 1
    os.makedirs(out, exist_ok=True)
    d = Dump(args[0])
    mods = d.modules()
    with open(os.path.join(out, "modules.txt"), "w") as m:
        for base, size, name in mods:
            m.write("0x%08x  %9d  %s\n" % (base, size, name))
    print("memory ranges:", len(d.ranges), " modules:", len(mods))

    for base, size, name in mods:
        if name.replace("\\", "/").rsplit("/", 1)[-1].lower().startswith("gx_"):
            img = d.read(base, size)
            with open(os.path.join(out, "gx_image.bin"), "wb") as o:
                o.write(img)
            with open(os.path.join(out, "gx_image.txt"), "w") as o:
                o.write("base=0x%x size=%d name=%s\n" % (base, size, name))
            print("wrote gx_image.bin (%d bytes) base 0x%x" % (size, base))
            break
    else:
        print("GX module not found in module list")

    found = set()
    n_xpr = 0
    for addr in d.scan(b"XPR0"):
        h = d.read(addr, 32)
        if h[12:16] == b"\x00\x00\x00\x80" and h[20:24] == b"MDL\x00":
            total = struct.unpack_from("<I", h, 4)[0]
            if 0x1000 < total < 0x4000000:
                data = d.read(addr, total)
                with open(os.path.join(out, "xpr_%08x_%d.bin" % (addr, total)), "wb") as o:
                    o.write(data)
                found.add(addr)
                n_xpr += 1
                print("XPR/MDL at 0x%x size %d" % (addr, total))
    n_mdl = 0
    for addr in d.scan(b"MDL\x00"):
        if addr - 20 in found or n_mdl >= 20:
            continue
        h = d.read(addr - 8, 32)
        objnum, texnum = struct.unpack_from("<II", h, 12)
        mdlsize = struct.unpack_from("<I", h, 4)[0]
        if 0 < objnum < 1000 and 0 <= texnum < 1000 and 0 < mdlsize < 0x4000000:
            with open(os.path.join(out, "mdl_%08x.bin" % addr), "wb") as o:
                o.write(d.read(addr - 20, min(0x400000, mdlsize + 0x2000)))
            n_mdl += 1
            print("MDL block at 0x%x (objs %d, texs %d)" % (addr, objnum, texnum))
    print("done: %d xpr buffers, %d mdl fallbacks -> %s" % (n_xpr, n_mdl, out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
