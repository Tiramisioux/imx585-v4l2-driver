#!/usr/bin/env python3
"""Replay imx585_check_mode_table() over the C mode tables, on the host.

Every check below is a line-for-line port of the driver's probe-time audit
(imx585.c, imx585_check_mode_table) plus imx585_program_window()'s alignment
predicate. G2/G3 for WP-585-9: the audit only warns at insmod on real
hardware, so this is how a desk review sees the same warnings.
"""
import re, sys, pathlib

SRC = pathlib.Path(__file__).resolve().parents[1] / "imx585.c"
W, H = 3840, 2160          # IMX585_PIXEL_ARRAY_{WIDTH,HEIGHT}
LEFT = 8                   # IMX585_PIXEL_ARRAY_LEFT
TOP4K = 20                 # IMX585_PIXEL_ARRAY_TOP_4K

def const_ints(src):
    """#define NAME <int> -- so the parser reads the file's own constants."""
    out = {}
    for n, v in re.findall(r"#define\s+(IMX585_[A-Z0-9_]+)\s+\(?(\d+)\)?\s*$", src, re.M):
        out[n] = int(v)
    return out

def num(tok, consts):
    tok = tok.strip()
    if re.fullmatch(r"-?\d+", tok):
        return int(tok)
    # evaluate the simple arithmetic the table actually uses
    expr = tok
    for name, val in sorted(consts.items(), key=lambda kv: -len(kv[0])):
        expr = expr.replace(name, str(val))
    if re.fullmatch(r"[\d\s()+\-*/]+", expr):
        return int(eval(expr))
    raise ValueError(tok)

def parse_table(src, name, consts):
    m = re.search(r"static struct imx585_mode %s\[\]\s*=\s*\{" % name, src)
    if not m:
        sys.exit("table %s not found" % name)
    i, depth, start = m.end() - 1, 0, m.end() - 1
    while True:
        if src[i] == "{": depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0: break
        i += 1
    body = src[start + 1:i]
    # split top-level entries
    entries, depth, buf = [], 0, ""
    for ch in body:
        if ch == "{":
            depth += 1
            if depth == 1: buf = ""; continue
        elif ch == "}":
            depth -= 1
            if depth == 0: entries.append(buf); continue
        if depth >= 1: buf += ch
    modes = []
    for e in entries:
        e = re.sub(r"/\*.*?\*/", " ", e, flags=re.S)
        d = {"windowed": bool(re.search(r"\.windowed\s*=\s*true", e)),
             "raw16": bool(re.search(r"\.raw16\s*=\s*true", e)),
             "binning": 1, "min_vmax_default": 0}
        b = re.search(r"\.binning\s*=\s*(\d+)", e)
        if b: d["binning"] = int(b.group(1))
        v = re.search(r"\.min_vmax_default\s*=\s*([^,]+),", e)
        if v: d["min_vmax_default"] = num(v.group(1), consts)
        for k in ("width", "height"):
            mm = re.search(r"\.%s\s*=\s*([^,]+)," % k, e)
            d[k] = num(mm.group(1), consts)
        c = re.search(r"\.crop\s*=\s*\{(.*?)\}", e, re.S)
        crop = {}
        for k in ("left", "top", "width", "height"):
            mm = re.search(r"\.%s\s*=\s*([^,}]+)" % k, c.group(1))
            crop[k] = num(mm.group(1), consts)
        d["crop"] = crop
        modes.append(d)
    return modes

def audit(table, name):
    warns = []
    def warn(i, m, msg):
        warns.append("%s[%u] %ux%u: %s" % (name, i, m["width"], m["height"], msg))
    for i, m in enumerate(table):
        c = m["crop"]
        if m["windowed"]:
            sw, sh = c["width"], c["height"]
            hst, vst = LEFT + c["left"], 12 + c["top"]
            if (sw < 64 or sw > W or sh < 239 or sh > H or (hst & 1)
                    or (sw & 15) or (vst & 3) or (sh & 3) or not hst):
                warn(i, m, "window fails imx585_program_window()'s alignment check")
        vwidth = c["height"] + (TOP4K if m["raw16"] else 0)
        if m["windowed"]:
            required = vwidth + 70                      # IMX585_CROP_VMAX
            floor = m["min_vmax_default"] or required
            if floor < required:
                warn(i, m, "VMAX floor %u is below the window's required %u" % (floor, required))
        if c["left"] + c["width"] > W or c["top"] + c["height"] > H:
            warn(i, m, "crop rectangle leaves the pixel array")
        if m["raw16"]:
            exp = (c["height"] // 2 + TOP4K) if m["binning"] == 2 else (c["height"] + 2 * TOP4K)
            if m["height"] != exp:
                warn(i, m, "RAW16 advertised height %u != delivered %u" % (m["height"], exp))
        if m["raw16"] and m["windowed"] and m["binning"] == 2:
            warn(i, m, "windowed 2x2 RAW16 reads back as OB pedestal on hw (WP-585-8)")
        for j in range(i):
            if table[j]["width"] == m["width"] and table[j]["height"] == m["height"]:
                warn(i, m, "duplicate advertised size, also at [%u]" % j)
                break
        # Not in the C audit: the crop-domain invariant documented above
        # supported_modes[]. A desk review should still hold the table to it.
        if m["raw16"]:
            exp_ch = (m["height"] - TOP4K) * 2 if m["binning"] == 2 else m["height"] - 2 * TOP4K
        else:
            exp_ch = m["height"] * m["binning"]
        exp_cw = m["width"] * m["binning"]
        if c["width"] != exp_cw or c["height"] != exp_ch:
            warn(i, m, "crop %ux%u breaks the domain invariant (expected %ux%u)"
                 % (c["width"], c["height"], exp_cw, exp_ch))
    return warns

src = SRC.read_text()
consts = const_ints(src)
total = 0
for name in ("supported_modes", "supported_10bit_modes"):
    table = parse_table(src, name, consts)
    warns = audit(table, name)
    total += len(warns)
    print("%s: %d entries, %d warnings" % (name, len(table), len(warns)))
    for w in warns:
        print("  WARN " + w)
print("\n%s" % ("AUDIT CLEAN" if total == 0 else "%d WARNINGS" % total))
sys.exit(1 if total else 0)
