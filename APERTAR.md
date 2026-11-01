# IMX585 driver for Apertar

This is the page for people running the IMX585 on an Apertar camera (Raspberry
Pi 5 or CM5, Apertar-Core). It covers which branch to install, what goes in
`config.txt`, and which sensor modes the driver offers. `README.md` stays the
reference for everything else (overlay options, link frequencies, sync modes,
Clear HDR background).

## Which branch

Use **`cinemate-port`**. It is `cinemate-modes` (the IMX585 modes of the
CineMate stack) brought onto the Apertar history: the mode tables, the overlay
and the tools are the same as on `cinemate-modes`. It replaces the older
Apertar driver (the `apertar` branch, as shipped on the Apertar-Beta 1.6.0
image).

## Install (on the Pi)

The driver lives in `~/drivers/imx585-v4l2-driver`. If it is not there yet:

```bash
mkdir -p ~/drivers
git clone https://github.com/Tiramisioux/imx585-v4l2-driver.git ~/drivers/imx585-v4l2-driver
```

Then, every time you install or update:

```bash
cd ~/drivers/imx585-v4l2-driver
git fetch
git checkout cinemate-port
git pull
./setup.sh
```

`setup.sh` removes any earlier DKMS copy of the module, then builds and
installs this one for the running kernel; its post-install step
(`dkms.postinst`) builds the `imx585` overlay from `imx585-overlay.dts`. It
needs `dkms`, `git` and the kernel headers, and a kernel of 6.12 or newer (the
driver uses `<linux/unaligned.h>`). Reboot afterwards.

## config.txt

On Raspberry Pi OS Bookworm the file is `/boot/firmware/config.txt` (older
images used `/boot/config.txt`). Turn camera auto-detect off and load the
overlay:

```
camera_auto_detect=0
dtoverlay=imx585[,cam0][,mono][,ccmp]
```

The brackets are optional parameters, comma separated:

| Parameter | When to use it |
| --------- | -------------- |
| `cam0` | The camera is on the CAM0 connector. Leave it out for CAM1. |
| `mono` | The sensor is the monochrome variant. |
| `ccmp` | Mono only: enables 12-bit Clear HDR (CCMP). The colour sensor has it on already, so it needs no `ccmp`. |

Examples:

```
# colour sensor on CAM1
dtoverlay=imx585

# colour sensor on CAM0
dtoverlay=imx585,cam0

# mono sensor on CAM0 with 12-bit Clear HDR
dtoverlay=imx585,cam0,mono,ccmp
```

After a reboot, `dmesg | grep imx585` should show the probe lines, including
`ClearHDR 12-bit CCMP: enabled (colour: default-on)` on a colour sensor and
`ClearHDR 12-bit CCMP: disabled (mono: opt-in via ccmp overlay param)` on a
mono sensor that was not given `ccmp`.

Mono 16-bit (Y16) additionally needs the rp1-cfe `csi_dt` fix described in
`README.md`; without it RAW16 buffers arrive scrambled.

### Settings to leave alone

- **`link-frequency`**: the overlay default is `720000000` (1440 Mbps/lane),
  which is inside the RP1 D-PHY limit of 1500 Mbps/lane. Do not add a
  `link-frequency=` parameter. The two highest rates in `README.md`
  (`891000000` and `1039500000`) run the link out of spec.
- **`clearhdr_windowed_binning`**: this module parameter stays off (its
  default). It is a hardware-gate test switch for `tools/clearhdr-gate/`. Turned
  on, it adds the 33 windowed 2x2 crops to the 12-bit Clear HDR family, and
  nobody has validated them there: at 16-bit, windowed 2x2 reads back as the
  black-level pedestal, and the one earlier 12-bit observation was invalid
  colour. Do not put `options imx585 clearhdr_windowed_binning=1` in
  `/etc/modprobe.d`; if a file with that line exists, remove it and reboot.

## Modes

The driver has four mode families. Which one is offered depends on the pixel
format and on Clear HDR (the `WIDE_DYNAMIC_RANGE` control, "WDR"). Clear HDR
off gives the two SDR families, Clear HDR on gives the two Clear HDR families.
Counts are for the colour sensor and come from the mode tables in `imx585.c`:

| Family | Clear HDR | Modes | What is in it |
| ------ | --------- | ----- | ------------- |
| 12-bit SDR | off | 62 | 1920x1080 (2x2 binned), 3840x2160, 27 sensor-window crops at 1x1, 33 sensor-window crops at 2x2 |
| 10-bit SDR | off | 62 | 3840x2160, 1920x1080 (2x2 binned), 26 crops at 1x1, 34 crops at 2x2 |
| 12-bit Clear HDR (CCMP) | on | 29 | 1920x1080 (2x2 binned), 3840x2160 and the 27 crops at 1x1; no 2x2 crops |
| 16-bit Clear HDR (linear) | on | 34 | 3840x2200, 1920x1100 (2x2 binned) and 32 crops at 1x1 |

That is 187 modes across the four families, backed by 158 table entries: 96 in
`supported_modes[]` (the 12-bit and 16-bit families) and 62 in
`supported_10bit_modes[]`. The 29 modes of 12-bit Clear HDR are the first 29
entries of the 12-bit SDR family.

The crops are centred sensor windows framed for common aspect ratios (1:1 up
to 2.55:1). The 1x1 crops are 1440 to 3840 pixels wide, the 2x2 crops 960 to
1920 pixels wide. The 16-bit modes advertise extra rows because the sensor
prepends its optical-black (OB) rows in RAW16 regardless of windowing: 40 rows
at 1x1 and 20 at 2x2. So 3840x2200 is 2160 active rows plus 40, the binned
1920x1100 is 1080 plus 20, and the 3840x2112 crop is a 3840x2072 window plus 40.

On the **mono** sensor (`mono`):

| Family | Modes |
| ------ | ----- |
| 12-bit SDR (Y12) | 62 |
| 10-bit SDR (Y10) | 62 |
| 12-bit Clear HDR | 1 (3840x2160), only with `ccmp` |
| 16-bit Clear HDR (Y16) | 1 (3840x2200) |

Binned Clear HDR returns only the black-level pedestal on the mono variant, so
mono offers the 3840 all-pixel modes only in Clear HDR, and no crops.

The complete list is the `supported_modes[]` and `supported_10bit_modes[]`
tables in `imx585.c`. `python3 tools/replay_mode_table_audit.py imx585.c` prints
the entry count per table (96 and 62) and checks them against the table
invariants. It reports one known warning, `3840x2072` at entries 5 and 67: the
same advertised size in the 12-bit and 16-bit families, which are different
pixel formats looked up in their own ranges, so nothing is shadowed.

`README.md` has a mode matrix for the original seven-mode CineMate branch
(`cinemate-7modes`). That matrix, and the "seven modes" in its text, predate
the families above and are not the mode list of this branch.

### Sizes that changed from the older Apertar driver

The older Apertar driver (`apertar`, the Apertar-Beta 1.6.0 image) had two
sizes that are different here:

| Older Apertar driver | Now |
| -------------------- | --- |
| 3840x2076 | 3840x2072 |
| 1920x1038 | 1920x1036 |

The other older Apertar sizes (3840x2024 down to 3840x1504, 1920x1012 down to
1920x752) are still offered under the same advertised size. Anything saved
against the two old sizes, such as a stored mode selection or a lookup keyed on
the exact resolution, has to be moved to the new size.

## Validation

The 16-bit Clear HDR crops were validated on kernel 6.12.93. Kernels other
than 6.12.93 are not covered by that validation. This repository holds no
capture logs for it; what it does record is:

- `README.md`: a hardware pass on 2026-08-31 (CM5, kernel 6.12.93, colour
  sensor, `link-frequency=891000000` with `rp1-overclock`) of the seven original
  modes, including 16-bit Clear HDR.
- Commit `fdd767a`: hardware takes on 2026-09-21 showing that 1x1 RAW16 crops
  (2880x2200, 3840x1648) read back as real images, while windowed 2x2 RAW16
  crops read back as the pedestal (those entries were removed). The commit does
  not name the kernel.

## Logging

The driver logs one `Update minimum HMAX: ...` summary line each time an active
format is set or Clear HDR is toggled. The per-mode HMAX/VMAX lines (one per
table entry, 158 in all) are debug messages; to see them, with dynamic debug
enabled in the kernel:

```bash
echo 'module imx585 +p' | sudo tee /sys/kernel/debug/dynamic_debug/control
```
