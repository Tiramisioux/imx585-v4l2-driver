# Kernel Driver for IMX585

This guide provides detailed instructions on how to install the IMX585 kernel driver on a Linux system, specifically Raspbian.

## Special Thanks

Special thanks to Soho-enterprise for the additional register info.  
Special thanks to Sasha Shturma's Raspberry Pi CM4 Сarrier with Hi-Res MIPI Display project, the DKMS install script is adapted from the github project page: https://github.com/renetec-io/cm4-panel-jdi-lt070me05000

## Prerequisites

Before you begin the installation process, please ensure the following prerequisites are met:

- **Kernel version**: You should be running on a Linux kernel version 6.12 or newer. You can verify your kernel version by executing `uname -r` in your terminal.

- **Development tools**: Essential tools such as `gcc`, `dkms`, and `linux-headers` are required for compiling a kernel module. If not already installed, these can be installed using the package manager with the following command:
  
   ```bash 
   sudo apt install linux-headers dkms git
   ```
   
## Installation Steps

### Setting Up the Tools

First, install the necessary tools (`linux-headers`, `dkms`, and `git`) if you haven't done so:

```bash 
sudo apt install linux-headers dkms git
```

### Fetching the Source Code

Clone the repository to your local machine and navigate to the cloned directory:

```bash
git clone https://github.com/will127534/imx585-v4l2-driver.git
cd imx585-v4l2-driver/
```

### Compiling and Installing the Kernel Driver

To compile and install the kernel driver, execute the provided installation script:

```bash 
./setup.sh
```

### Updating the Boot Configuration

Edit the boot configuration file using the following command:

```bash
sudo nano /boot/config.txt
```

In the opened editor, locate the line containing `camera_auto_detect` and change its value to `0`. Then, add the line `dtoverlay=imx585`. So, it will look like this:

```
camera_auto_detect=0
dtoverlay=imx585
```

After making these changes, save the file and exit the editor.

Remember to reboot your system for the changes to take effect.

## dtoverlay options

### cam0

If the camera is attached to cam0 port, append the dtoverlay with `,cam0` like this:  
```
camera_auto_detect=0
dtoverlay=imx585,cam0
```

### always-on

If you want to keep the camera power always on (Useful for debugging HW issues, specifically this will set CAM_GPIO to high constantly), append the dtoverlay with `,always-on` like this:  
```
camera_auto_detect=0
dtoverlay=imx585,always-on
```

### mono

If you are using a monochrome varient, append the dtoverlay with `,mono` like this:  
```
camera_auto_detect=0
dtoverlay=imx585,mono
```

### Lane Count

If you want to use 2-lane for IMX585, append the dtoverlay with `,2lane` like this:  
```
camera_auto_detect=0
dtoverlay=imx585,2lane
```

### link-frequency

If you want to change the default link frequency of 1440Mbps/lane (720Mhz), you can chage it like the following:
```
camera_auto_detect=0
dtoverlay=imx585,link-frequency=297000000
```
Here is a list of available frequencies:
| Valid Frequency Value | Mbps/Lane | Max Framerate with 4K 12bit + 4 lane | Max Framerate with 4K 12bit + 2 lane |
| -------- | -------- | -------- | -------- |
| 297000000|594 Mbps/Lane| 20.8 fps | 10.4 fps|
| 360000000|720 Mbps/Lane| 25.0 fps | 12.5 fps|
| 445500000|891 Mbps/Lane| 30.0 fps | 15.0 fps|
| 594000000|1188 Mbps/Lane| 41.7 fps| 20.8 fps|
| 720000000|1440 Mbps/Lane| 50.0 fps | 25.0 fps|
| 891000000|1782 Mbps/Lane| 60.0 fps | 30.0 fps|
| 1039500000|2079 Mbps/Lane| 75.0 fps | 37.5 fps|

Notes that by default RPI5/RP1 has a limit of 400Mpix/s processing speed, without overclocking RP1 (hence the Camera Frontend) you will be limited to ~43.8 FPS @ 4K.  
For ClearHDR mode the framerate will be half, for 1080P 2x2 binned the framerate will be double.  
1188 Mhz (2376 Mbps/lane) is also in the driver but RPI4 doesn't supports it from testing and RPI5 experience framedrop.  

### Sync-Mode

The driver exposes three sync modes, selectable via dtoverlay parameters:
| Mode                  | Description |
|-----------------------|-------------|
| **internal-leader** (default) | Sensor runs from its own internal clock and outputs both `XVS` (vertical sync) and `XHS` (horizontal sync). Other cameras can lock onto these signals. |
| **internal-follower** | Sensor still uses its own clock, but takes in an external `XVS` signal. It aligns vertical sync to this input by adding or subtracting a horizontal sync pulse. |
| **external**          | Sensor clock and timing are fully driven by external `XVS` and `XHS` signals. Both syncs are inputs, no outputs are generated. |

See [here](https://github.com/will127534/StarlightEye/wiki/IMX585-Camera-Clock-Synchronization-Guide) for the full guide.


### mix usage

Last note is that all the options can be used at the same time, the dtoverlay will looks like this:
```
camera_auto_detect=0
dtoverlay=imx585,mono,always-on,cam0,link-frequency=297000000
```
Imaging how many config I need to test.


---

## CineMate branch (`cinemate-7modes`)

A hybrid of the `6.12.y` snapshot and the INNO-MAKER v1.0 / upstream `main`
lineage, built for the CineMate stack. It takes `main`'s clean WINMODE
geometry (active-area dims, OB stripped at the sensor), its RAW10 4K mode
and its dedicated 16-bit Clear HDR mode entry, and restores the mode
coverage `6.12.y` had — binned Clear HDR in both depths — for seven modes.

### Mode matrix

`cinepi-raw --list-cameras` is run twice by CineMate's sensor detection,
once plain and once with `--hdr sensor`; the seven modes are the union.

| # | Size | Depth | WDR | Notes |
| - | ---- | ----- | --- | ----- |
| 1 | 1920x1080 | 12-bit | off | 2x2 binned, SDR |
| 2 | 3840x2160 | 12-bit | off | all-pixel, SDR |
| 3 | 3840x2160 | 10-bit | off | all-pixel RAW10, up to 90 fps at 2079 Mbps/lane |
| 4 | 1920x1080 | 12-bit | on  | binned Clear HDR + CCMP — colour only |
| 5 | 3840x2160 | 12-bit | on  | all-pixel Clear HDR + CCMP |
| 6 | 1920x1100 | 16-bit | on  | binned Clear HDR, linear — colour only; 1080 active + 2x10 OB |
| 7 | 3840x2200 | 16-bit | on  | all-pixel Clear HDR, linear; 2160 active + 2x20 OB |

The 16-bit modes advertise the OB padding because the sensor keeps
prepending its optical-black rows in RAW16 regardless of WINMODE. The
buffer is sized so a centered aspect crop lands exactly on the OB count
and discards it.

Mono keeps modes 1, 2, 3, 5 and 7. Binned Clear HDR returns pure BLC on
the mono variant (pixel-confirmed at 12-bit), so both binned HDR entries
are colour-only. 12-bit CCMP Clear HDR is default-on for colour and stays
opt-in on mono via the `ccmp` dtoverlay parameter.

Mono 16-bit additionally requires the rp1-cfe `csi_dt` fix for the Y16
entry in `cfe_fmts.h`, which must be re-applied after every kernel
upgrade — without it, RAW16 buffers arrive scrambled.

### Behaviour at the top link frequency

`6.12.y` produces distorted frames at 1039500000 (2079 Mbps/lane). That is
the old `HMAX_table_4lane_4K` entry of 440, which is too aggressive for
RAW12 on the Pi 5/RP1 path, and the absence of any Clear HDR floor — a
Clear HDR frame at HMAX 440 loses roughly 94% of its rows. Commit
`c0f5404` in this lineage replaces both: RAW12 gets the verified-clean 472,
and Clear HDR is floored at HMAX 550 regardless of link rate. So every
Clear HDR mode on this branch runs at 2079 Mbps/lane with exactly the same
sensor line timing it uses at 1782, and only the D-PHY runs faster. No
further driver change is needed for 12-bit Clear HDR at the top rate.

What the driver cannot fix: 1782 and 2079 Mbps/lane exceed the RP1 D-PHY
1500 Mbps/lane limit by 19% and 39%. The receiver logs `DPHY: Datarate
… out of range`, clamps `hsfreqrange` to the 1450-1500 code and streams on
silicon margin. Residual artifacts that only appear at 2079 and scale with
word width — for example speckle in 16-bit highlights — are physical-layer
symptoms, not timing, and have no register-level remedy. Use 1440 Mbps/lane
for anything that has to be reliable.

Direct `hmax`, `vmax` and `shr` V4L2 controls are exposed, so a suspected
timing limit can be tested live with `v4l2-ctl` before it is written into
a table.
