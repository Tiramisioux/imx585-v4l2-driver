#!/usr/bin/env python3
"""
G3 gate for WP-585-9 (1920/2048 sensor-window crop family).

Host-side replay of the *exact* reject predicate imx585_program_window()
applies to every `.windowed = true` mode entry before it will write the
WINMODE/PIX_H*/PIX_V* registers -- see imx585.c around imx585_program_window()
and its read-only twin imx585_check_mode_table(). Both live copies of this
predicate must stay identical to this script; if they diverge, re-copy the
condition from imx585.c rather than editing it here from memory.

This program does not build or load the kernel module (that needs a Pi -- see
G1/G4 in RESULTS.md). It only proves that every mode-table entry this branch
adds -- and, for a sanity net, every entry the branch already shipped -- would
not be silently rejected by the sensor-window alignment check at stream-on.

Usage: python3 tools/check_window_alignment.py [path-to-imx585.c]
Exit status is non-zero if any windowed entry fails.
"""
import re
import sys
from pathlib import Path

PIXEL_ARRAY_WIDTH = 3840
PIXEL_ARRAY_HEIGHT = 2160
PIXEL_ARRAY_LEFT = 8

CROP_RE = re.compile(
    r"\.crop\s*=\s*\{\s*\.left\s*=\s*(\d+)\s*,\s*\.top\s*=\s*(\d+)\s*,"
    r"\s*\.width\s*=\s*(\d+)\s*,\s*\.height\s*=\s*(\d+)\s*\}"
)


def find_entries(src: str):
    """Yield (advertised_width, advertised_height, windowed, crop) for every
    mode-table struct entry in the file, in source order."""
    entries = []
    i = 0
    while True:
        m = re.search(r"\.width\s*=\s*(\d+)\s*,\s*\.height\s*=\s*(\d+)\s*,\s*\.hmax_div", src[i:])
        if not m:
            break
        start = i + m.start()
        end_marker = src.index("\t},\n", start)
        block = src[start:end_marker]
        adv_w, adv_h = int(m.group(1)), int(m.group(2))
        windowed = ".windowed = true" in block
        cm = CROP_RE.search(block)
        crop = tuple(int(x) for x in cm.groups()) if cm else None
        entries.append((adv_w, adv_h, windowed, crop))
        i = end_marker + 4
    return entries


def check_window(crop):
    """Replay imx585_program_window()'s reject condition exactly."""
    left, top, width, height = crop
    hst = PIXEL_ARRAY_LEFT + left
    vst = 12 + top
    reject = (
        width < 64 or width > PIXEL_ARRAY_WIDTH
        or height < 239 or height > PIXEL_ARRAY_HEIGHT
        or (hst & 1) or (width & 15) or (vst & 3)
        or (height & 3) or not hst
    )
    return (not reject), hst, vst


# The new entries this branch (feature/window-crops-1920-2048) adds, called
# out explicitly by advertised (width, height) so a reviewer can see at a
# glance which rows are new vs. inherited from experimental-cropped-modes-v2.
NEW_WIDTHS = (1920, 2048, 960, 1024)


def main():
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "imx585.c")
    src = path.read_text()
    entries = find_entries(src)

    windowed = [e for e in entries if e[2]]
    print(f"{len(entries)} mode-table entries found, {len(windowed)} windowed.\n")

    failures = 0
    new_count = 0
    print(f"{'width':>6} {'height':>7} {'crop':>22} {'hst':>5} {'vst':>5}  result  new?")
    print("-" * 70)
    for adv_w, adv_h, is_windowed, crop in entries:
        if not is_windowed:
            continue
        ok, hst, vst = check_window(crop)
        is_new = adv_w in NEW_WIDTHS
        if is_new:
            new_count += 1
        tag = "NEW" if is_new else ""
        status = "PASS" if ok else "FAIL"
        if not ok:
            failures += 1
        crop_str = f"{crop[2]}x{crop[3]}@({crop[0]},{crop[1]})"
        print(f"{adv_w:>6} {adv_h:>7} {crop_str:>22} {hst:>5} {vst:>5}  {status:<6}  {tag}")

    print("-" * 70)
    print(f"{new_count} entries at a new width (1920/2048/960/1024) checked.")
    if failures:
        print(f"\n{failures} FAILURE(S) -- imx585_program_window() would reject these at stream-on.")
        sys.exit(1)
    print("\nAll windowed entries pass imx585_program_window()'s alignment check.")


if __name__ == "__main__":
    main()
