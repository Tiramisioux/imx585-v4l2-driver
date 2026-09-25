#!/usr/bin/env python3
"""WP-585-9 hardware gate: does a Clear HDR take hold a picture or the OB pedestal?

Reads cinepi-raw DNGs (IFD0 is the raw frame: one uncompressed strip,
BitsPerSample 12 packed MSB-first two pixels per three bytes, or 16 as
little-endian words) and prints, per frame:

  fill       the most common sample value, and the share of pixels at it
  distinct   the number of distinct sample values
  flat rows  the share of rows whose mean sits within one code of the fill
  p1/p50/p99 sample percentiles

and a verdict, on WP-585-8's own criteria (its broken RAW16 takes were 98.8 to
99.5 percent at the fixed pedestal with row means flat after the first OB rows;
its real takes had thousands of distinct values and every row distinct):

  PEDESTAL   fill >= 90 %  or  distinct <= 64  or  flat rows >= 90 %
  REAL       fill <= 50 %  and distinct >= 1000  and flat rows <= 10 %
  UNCLEAR    anything in between: look at the frame, and at the controls

The first --skip-rows rows are left out of the statistics (the OB rows a
Clear HDR frame carries at the top; 24 covers the 20 the sensor emits) and
reported separately as "top rows", so a take that is pedestal everywhere
except its OB band still reads PEDESTAL.

Usage:
    pedestal_check.py [--skip-rows N] [--frames N] PATH [PATH ...]

PATH is a .dng file or a take directory; from a directory, --frames (default 3)
frames spread evenly across the take are used. Needs numpy.
"""
import argparse
import os
import struct
import sys

try:
    import numpy as np
except ImportError:  # pragma: no cover - the message is the point
    sys.exit("pedestal_check.py needs numpy (python3 -m pip install numpy)")

TYPE_SIZE = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 6: 1, 7: 1, 8: 2, 9: 4, 10: 8, 11: 4, 12: 8}
TYPE_FMT = {1: "B", 3: "H", 4: "I", 6: "b", 8: "h", 9: "i"}

TAG_WIDTH, TAG_HEIGHT, TAG_BITS, TAG_COMPRESSION = 256, 257, 258, 259
TAG_STRIP_OFFSETS, TAG_SPP, TAG_STRIP_BYTES = 273, 277, 279
TAG_BLACK_LEVEL, TAG_WHITE_LEVEL = 0xC61A, 0xC61D


def read_ifd0(path):
    """The tags of IFD0 that describe the raw strip, as a dict."""
    with open(path, "rb") as fh:
        header = fh.read(8)
        if header[:4] != b"II*\0":
            raise ValueError("not a little-endian TIFF/DNG")
        ifd = struct.unpack("<I", header[4:8])[0]
        fh.seek(ifd)
        count = struct.unpack("<H", fh.read(2))[0]
        entries = fh.read(12 * count)
        tags = {}
        for i in range(count):
            tag, typ, cnt, raw = struct.unpack_from("<HHI4s", entries, 12 * i)
            size = TYPE_SIZE.get(typ, 1) * cnt
            if size <= 4:
                payload = raw[:size]
            else:
                fh.seek(struct.unpack("<I", raw)[0])
                payload = fh.read(size)
            if typ == 5 and cnt >= 1:  # RATIONAL: first value only
                num, den = struct.unpack_from("<II", payload, 0)
                tags[tag] = num / den if den else float("nan")
            elif typ in TYPE_FMT:
                vals = struct.unpack_from("<" + TYPE_FMT[typ] * cnt, payload, 0)
                tags[tag] = list(vals) if cnt > 1 else vals[0]
        return tags


def load_frame(path):
    tags = read_ifd0(path)
    width, height, bits = tags[TAG_WIDTH], tags[TAG_HEIGHT], tags[TAG_BITS]
    if tags.get(TAG_COMPRESSION, 1) != 1:
        raise ValueError(f"compressed DNG (Compression {tags[TAG_COMPRESSION]}), expected 1")
    if tags.get(TAG_SPP, 1) != 1:
        raise ValueError(f"SamplesPerPixel {tags[TAG_SPP]}, expected 1")
    offsets = tags[TAG_STRIP_OFFSETS]
    counts = tags[TAG_STRIP_BYTES]
    if isinstance(offsets, list):
        offset, nbytes = offsets[0], sum(counts)   # cinepi-raw writes one strip; tolerate contiguous strips
    else:
        offset, nbytes = offsets, counts
    with open(path, "rb") as fh:
        fh.seek(offset)
        data = fh.read(nbytes)
    if bits == 16:
        img = np.frombuffer(data, dtype="<u2", count=width * height).reshape(height, width)
    elif bits == 12:
        if width % 2:
            raise ValueError("odd width in a packed 12-bit DNG")
        stride = width * 3 // 2
        rows = np.frombuffer(data, dtype=np.uint8, count=stride * height).reshape(height, width // 2, 3)
        b0 = rows[..., 0].astype(np.uint16)
        b1 = rows[..., 1].astype(np.uint16)
        b2 = rows[..., 2].astype(np.uint16)
        img = np.empty((height, width), dtype=np.uint16)
        img[:, 0::2] = (b0 << 4) | (b1 >> 4)
        img[:, 1::2] = ((b1 & 0x0F) << 8) | b2
    else:
        raise ValueError(f"BitsPerSample {bits} is not handled (12 and 16 are)")
    return img, tags


def analyse(img, skip_rows):
    body = img[skip_rows:] if skip_rows < img.shape[0] else img
    top = img[:skip_rows] if skip_rows and skip_rows < img.shape[0] else None
    values, counts = np.unique(body, return_counts=True)
    fill = int(values[counts.argmax()])
    fill_share = float(counts.max()) / body.size
    distinct = int(values.size)
    row_means = body.mean(axis=1)
    flat_share = float(np.mean(np.abs(row_means - fill) < 1.0))
    p1, p50, p99 = (float(x) for x in np.percentile(body, (1, 50, 99)))
    if fill_share >= 0.90 or distinct <= 64 or flat_share >= 0.90:
        verdict = "PEDESTAL"
    elif fill_share <= 0.50 and distinct >= 1000 and flat_share <= 0.10:
        verdict = "REAL"
    else:
        verdict = "UNCLEAR"
    return {
        "fill": fill, "fill_share": fill_share, "distinct": distinct,
        "flat_share": flat_share, "p1": p1, "p50": p50, "p99": p99,
        "top_mean": float(top.mean()) if top is not None else None,
        "verdict": verdict,
    }


def pick_frames(path, frames):
    if os.path.isdir(path):
        names = sorted(n for n in os.listdir(path) if n.lower().endswith(".dng"))
        if not names:
            raise ValueError(f"no .dng files in {path}")
        if len(names) <= frames:
            picks = names
        else:
            picks = [names[int(round(i * (len(names) - 1) / (frames - 1)))] for i in range(frames)] if frames > 1 else [names[len(names) // 2]]
        return [os.path.join(path, n) for n in dict.fromkeys(picks)]
    return [path]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--skip-rows", type=int, default=24, help="top rows left out of the statistics (default 24)")
    ap.add_argument("--frames", type=int, default=3, help="frames per take directory (default 3)")
    ap.add_argument("paths", nargs="+")
    args = ap.parse_args(argv)

    header = (f"{'frame':<44} {'size':>10} {'bits':>4} {'black':>6} {'fill':>6} {'fill %':>7} "
              f"{'distinct':>8} {'flat %':>7} {'p1':>6} {'p50':>6} {'p99':>6} {'top':>7}  verdict")
    print(header)
    print("-" * len(header))
    verdicts = {}
    for path in args.paths:
        try:
            files = pick_frames(path, args.frames)
        except ValueError as exc:
            print(f"{path}: {exc}")
            continue
        for f in files:
            try:
                img, tags = load_frame(f)
                r = analyse(img, args.skip_rows)
            except (OSError, ValueError, KeyError, struct.error) as exc:
                print(f"{f}: cannot read ({exc})")
                continue
            label = f if len(f) <= 44 else "..." + f[-41:]
            black = tags.get(TAG_BLACK_LEVEL)
            top = "-" if r["top_mean"] is None else f"{r['top_mean']:7.1f}"
            print(f"{label:<44} {img.shape[1]:>5}x{img.shape[0]:<4} {tags[TAG_BITS]:>4} "
                  f"{'-' if black is None else int(black):>6} {r['fill']:>6} {100 * r['fill_share']:>6.1f}% "
                  f"{r['distinct']:>8} {100 * r['flat_share']:>6.1f}% {r['p1']:>6.0f} {r['p50']:>6.0f} {r['p99']:>6.0f} {top:>7}  {r['verdict']}")
            verdicts.setdefault(path, []).append(r["verdict"])
    if verdicts:
        print()
        for path, vs in verdicts.items():
            summary = "PEDESTAL" if all(v == "PEDESTAL" for v in vs) else "REAL" if all(v == "REAL" for v in vs) else "UNCLEAR"
            print(f"{summary:<9} {path}  ({', '.join(vs)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
