#!/usr/bin/env python3
"""
afs_survey.py - read-only survey of CRI AFS archives (DOA2 Ultimate).

Usage:
    python afs_survey.py "D:\\...\\DOA2\\datadvd.afs" [more.afs ...] [-o report.txt]
    python afs_survey.py "D:\\...\\DOA2" -o report.txt        (scans every .afs in the folder)

Writes nothing except the report. Paste the report (or attach it) back to Claude.
"""
import os, struct, sys, collections


def read_afs_index(f):
    f.seek(0)
    head = f.read(8)
    if head[:3] != b"AFS" or len(head) < 8:
        raise ValueError("not an AFS archive (magic %r)" % head[:4])
    count = struct.unpack("<I", head[4:8])[0]
    if count == 0 or count > 500000:
        raise ValueError("implausible entry count %d" % count)
    toc = f.read(8 * count)
    entries = [struct.unpack_from("<II", toc, i * 8) for i in range(count)]
    # optional filename table: (offset, length) pair right after the TOC
    names = [None] * count
    meta = [None] * count
    pair = f.read(8)
    if len(pair) == 8:
        noff, nlen = struct.unpack("<II", pair)
        if noff and nlen == count * 48:
            f.seek(noff)
            blob = f.read(nlen)
            if len(blob) == nlen:
                for i in range(count):
                    rec = blob[i * 48:(i + 1) * 48]
                    names[i] = rec[:32].split(b"\0")[0].decode("latin-1")
                    meta[i] = struct.unpack("<6HI", rec[32:48])
    return entries, names, meta


def classify(b):
    if len(b) < 4:
        return "tiny"
    m = b[:4]
    known = {
        b"AFS\0": "AFS", b"NJCM": "NJCM", b"NJTL": "NJTL", b"GJCM": "GJCM",
        b"GJTL": "GJTL", b"NMDM": "NMDM", b"NJBM": "NJBM", b"POF0": "POF0",
        b"XPR0": "XPR0", b"XPR1": "XPR1", b"RIFF": "RIFF", b"DDS ": "DDS",
        b"PVMH": "PVMH", b"GBIX": "GBIX", b"PVRT": "PVRT", b"\x89PNG": "PNG",
        b"OggS": "OGG", b"ADX\0": "ADX", b"\x80\x00": "ADX?",
    }
    if m in known:
        return known[m]
    if all(32 <= c < 127 for c in m):
        return "ascii:" + m.decode()
    return "bin:" + m.hex()


def survey(path, out, sample_per_kind=2):
    size = os.path.getsize(path)
    out.append("=" * 78)
    out.append("%s  (%d bytes)" % (os.path.basename(path), size))
    with open(path, "rb") as f:
        try:
            entries, names, meta = read_afs_index(f)
        except ValueError as e:
            out.append("  SKIP: %s" % e)
            f.seek(0)
            out.append("  first 64 bytes: " + f.read(64).hex(" "))
            return
        n = len(entries)
        out.append("  entries: %d   filename table: %s" %
                   (n, "yes" if names[0] is not None else "no"))
        kinds = collections.defaultdict(list)
        ext_count = collections.Counter()
        sizes = collections.Counter()
        for i, (off, ln) in enumerate(entries):
            f.seek(off)
            head = f.read(min(ln, 32))
            k = classify(head)
            kinds[k].append(i)
            if names[i]:
                ext_count[os.path.splitext(names[i])[1].lower()] += 1
            sizes[k] += ln
        if ext_count:
            out.append("  extensions: " + ", ".join("%s x%d" % kv for kv in ext_count.most_common()))
        out.append("  by header kind (count, total bytes):")
        for k, idx in sorted(kinds.items(), key=lambda kv: -len(kv[1])):
            out.append("    %-14s %6d  %12d" % (k, len(idx), sizes[k]))
        out.append("  first 40 entries (index, offset, size, name, header hex):")
        for i in range(min(40, n)):
            off, ln = entries[i]
            f.seek(off)
            out.append("    %5d  0x%08x %9d  %-24s %s" %
                       (i, off, ln, names[i] or "-", f.read(min(ln, 16)).hex(" ")))
        out.append("  samples of each header kind (32 bytes):")
        for k, idx in sorted(kinds.items(), key=lambda kv: -len(kv[1])):
            for i in idx[:sample_per_kind]:
                off, ln = entries[i]
                f.seek(off)
                out.append("    %-14s #%-5d %-22s %9d  %s" %
                           (k, i, names[i] or "-", ln, f.read(min(ln, 32)).hex(" ")))
        if names[0] is not None:
            out.append("  ALL filenames (index:name:size):")
            line = []
            for i in range(n):
                line.append("%d:%s:%d" % (i, names[i], entries[i][1]))
            out.append("    " + "  ".join(line))


def main(argv):
    outpath = None
    paths = []
    it = iter(argv)
    for a in it:
        if a == "-o":
            outpath = next(it)
        else:
            paths.append(a)
    if not paths:
        print(__doc__)
        return 1
    files = []
    for p in paths:
        if os.path.isdir(p):
            files += sorted(os.path.join(p, x) for x in os.listdir(p) if x.lower().endswith(".afs"))
        else:
            files.append(p)
    out = []
    for p in files:
        try:
            survey(p, out)
        except Exception as e:  # keep going on bad files
            out.append("%s: ERROR %r" % (p, e))
    text = "\n".join(out)
    if outpath:
        with open(outpath, "w", encoding="utf-8") as fh:
            fh.write(text)
        print("wrote %s (%d chars)" % (outpath, len(text)))
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
