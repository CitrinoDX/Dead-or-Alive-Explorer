#!/usr/bin/env python3
"""
afs_extract.py - pull named files out of CRI AFS archives (read-only on the archive).

Usage:
    python afs_extract.py ARCHIVE.afs name1 [name2 ...] [-o OUTDIR]
    python afs_extract.py ARCHIVE.afs --all [-o OUTDIR]
    python afs_extract.py ARCHIVE.afs --list

Names are matched exactly against the archive's filename table (case-insensitive).
Example:
    python afs_extract.py "D:\\...\\DOA2\\datahdd2.afs" kas00.xpr kas00.cat kas01.xpr kas01.cat -o out
    python afs_extract.py "D:\\...\\DOA2\\datahdd.afs" kasumi.bin -o out
"""
import os, struct, sys


def read_index(f):
    f.seek(0)
    head = f.read(8)
    if head[:3] != b"AFS":
        raise SystemExit("not an AFS archive")
    n = struct.unpack("<I", head[4:8])[0]
    toc = [struct.unpack("<II", f.read(8)) for _ in range(n)]
    noff, nlen = struct.unpack("<II", f.read(8))
    names = [None] * n
    if noff and nlen == n * 48:
        f.seek(noff)
        blob = f.read(nlen)
        names = [blob[i * 48:i * 48 + 32].split(b"\0")[0].decode("latin-1") for i in range(n)]
    return toc, names


def main(argv):
    out = "extracted"
    args = []
    it = iter(argv)
    for a in it:
        if a == "-o":
            out = next(it)
        else:
            args.append(a)
    if len(args) < 2:
        print(__doc__)
        return 1
    arc, rest = args[0], args[1:]
    with open(arc, "rb") as f:
        toc, names = read_index(f)
        if rest == ["--list"]:
            for i, ((off, ln), nm) in enumerate(zip(toc, names)):
                print("%5d %10d %s" % (i, ln, nm))
            return 0
        if rest == ["--all"]:
            want = list(range(len(toc)))
        else:
            lookup = {}
            for i, nm in enumerate(names):
                lookup.setdefault((nm or "").lower(), []).append(i)
            want = []
            for r in rest:
                hit = lookup.get(r.lower())
                if not hit:
                    print("NOT FOUND:", r)
                else:
                    want += hit  # duplicates (e.g. dmy.bin) all extracted
        os.makedirs(out, exist_ok=True)
        for i in want:
            off, ln = toc[i]
            f.seek(off)
            name = names[i] or ("entry_%05d.bin" % i)
            dest = os.path.join(out, name)
            if os.path.exists(dest):  # never silently overwrite a duplicate name
                dest = os.path.join(out, "%05d_%s" % (i, name))
            with open(dest, "wb") as o:
                remaining = ln
                while remaining:
                    chunk = f.read(min(remaining, 1 << 20))
                    if not chunk:
                        break
                    o.write(chunk)
                    remaining -= len(chunk)
            print("wrote", dest, ln)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
