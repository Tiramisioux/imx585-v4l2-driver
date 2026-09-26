# WP-585-9 hardware gate: windowed 2x2 crops in 12-bit Clear HDR

## The question

Can the IMX585 read a **sensor-windowed, 2x2-binned** window out correctly in
**12-bit Clear HDR (CCMP)**, or does it return the optical-black pedestal the
way it does at RAW16?

WP-585-8 (2026-09-21) settled the RAW16 half on hardware: every windowed 2x2
RAW16 crop reads back as the OB pedestal, while the same window unbinned and
the full field binned both read back real images. Nothing has tested the
12-bit half, and the one observation on record points the same way (the
1440x1080 HDR-12 entry's comment: a windowed 2x2 at that size "produced
invalid colour data on hardware").

Until this gate is run, the driver keeps the twelve windowed 2x2 crops
(1080x1080, 1488x1080, 1920x1036, 1920x1016, 1920x1012, 1920x960, 1920x872,
1920x864, 1920x816, 1920x804, 1920x768, 1920x752) out of the 12-bit Clear HDR
range. They stay in SDR. The `clearhdr_windowed_binning` module parameter
re-opens the range for exactly this test.

## What you need

- A colour IMX585 on a Pi 5 or CM5 with this driver branch installed.
- CineMate `dev` with `image_capture.hdr.imx585_clear_hdr_12bit` set to `true`
  in `settings.jsonc`, so the 12-bit Clear HDR modes can be selected. The
  16-bit parser fix is not needed for this test.
- The Clear HDR blend at menu 5, which CineMate sets when a Clear HDR mode is
  selected. Do not change thresholds, blend or gain adder between takes.
- One static, well-lit scene with detail across the frame. Same lens, same
  ISO, same shutter for every take.

## Steps

1. Install the branch and open the gate:

   ```sh
   cd ~/imx585-v4l2-driver
   git fetch origin
   git checkout wp-585-9-clearhdr12-gate
   ./setup.sh
   echo 'options imx585 clearhdr_windowed_binning=1' | sudo tee /etc/modprobe.d/imx585-gate.conf
   sudo reboot
   ```

2. Check the gate is open. `dmesg | grep imx585` shows
   `clearhdr_windowed_binning=1: offering the windowed 2x2 crops in 12-bit Clear HDR ...`,
   and `cinepi-raw --list-cameras` lists 1920x960 and 1080x1080 under
   `CLEAR HDR / SENSOR HDR` in the `'SRGGB12_CSI2P'` block.

3. Record the four takes, about 50 frames each, without touching the scene or
   the exposure between them. Select each mode in CineMate's settings pane
   (they are the 12-bit HDR rows) and record.

   | Take | Select (12-bit HDR) | Sensor window | Binning | Role |
   | --- | --- | --- | --- | --- |
   | 1 | 1920x960 | (0, 120)/3840x1920 | 2x2 | candidate, vertical window |
   | 2 | 1080x1080 | (840, 0)/2160x2160 | 2x2 | candidate, horizontal window |
   | 3 | 3840x1920 | (0, 120)/3840x1920 | 1x1 | control: take 1's window, unbinned |
   | 4 | 1920x1080 | full field | 2x2 | control: binned, not windowed (shipped, proven) |

4. Analyse the takes. On the Pi or on any machine with the DNGs and numpy:

   ```sh
   python3 tools/clearhdr-gate/pedestal_check.py /media/RAW/<take1> /media/RAW/<take2> /media/RAW/<take3> /media/RAW/<take4>
   ```

   For each frame it prints the most common sample value and the share of
   pixels at it, the number of distinct values, the share of rows whose mean
   sits at that value, percentiles, the mean of the top OB rows, and a
   verdict (`PEDESTAL`, `REAL`, `UNCLEAR`). The criteria are WP-585-8's:
   its broken takes were 98.8 to 99.5 percent at the fixed pedestal with row
   means flat after the first OB rows; its real takes had thousands of
   distinct values. The controls must come out `REAL`; if they do not, the
   scene or exposure is wrong, not the sensor.

5. Close the gate again whatever the result:

   ```sh
   sudo rm /etc/modprobe.d/imx585-gate.conf
   sudo reboot
   ```

## The decision

- **Takes 1 and 2 both `REAL`**, comparable to takes 3 and 4: windowed 2x2
  Clear HDR-12 works. In `imx585.c`, make the 12-bit Clear HDR range end at
  `IMX585_MODE_4K_16BIT_HDR` unconditionally (drop the
  `clearhdr_windowed_binning` ternary in `get_mode_table()`), remove the
  module parameter and its probe warning, keep the table order and the
  `static_assert`s, and rewrite the WP-585-9 comments to record the result,
  the numbers and the date. The RAW16 rule from WP-585-8 stays as it is.
- **Either candidate `PEDESTAL`**: the gate stays. Rewrite the WP-585-9
  comments from "pending gate" to "hardware-confirmed" with the numbers and
  the date, remove the module parameter (the question is answered), and add a
  predicate to `imx585_check_mode_table()` that warns on any windowed 2x2
  entry inside a Clear HDR range, mirroring the WP-585-8 one for RAW16.
- **`UNCLEAR`** on a candidate while the controls are `REAL`: look at the
  frames (CineMate's DNG preview, or any raw viewer). A picture with the
  right framing at low contrast is `REAL`; a flat field with the OB band at
  the top is `PEDESTAL`. Re-run with a brighter scene before deciding.

Record the numbers in the commit message and in the handbook's hardware log,
next to WP-585-8's.
