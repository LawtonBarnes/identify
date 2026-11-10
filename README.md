# IDENTIFY

> **Fleet-only:** needs STRINGS on every Pi and SCRUTE on MP. Not useful on a single Pi.

A cabling helper for the METAL SHOP Raspberry Pi CRT fleet (see [mcbrain](https://github.com/LawtonBarnes/mcbrain)). Turn it on from CENTRAL SCRUTINIZER and every Pi labels its own screen at once, so you can see which Pi feeds which CRT.

- **Page 1:** the Pi's short name (P1–P4) in huge Roboto Mono Bold over black. QUAD, which drives the 2x2 wall at 1024x768, shows Q1–Q4, one per quadrant (top-left, top-right, bottom-left, bottom-right). Behind the label is a safe-area chart:
  - **Screen edge:** an outline in the label color. Anything cut off there is lost to overscan.
  - **Safe areas:** dimmer action-safe and title-safe boxes. 4:3 screens use the classic 90% / 80%. 16:9 screens (HIDEF, shown as HD) use SMPTE ST 2046-1's 93% / 90%, plus dashed 4:3 center-cut lines.
  - **QUAD:** gets a separate chart per quadrant, since each one is its own CRT.
  - **Line width:** 2 px on SD and 4 px at 1080, so 1080i doesn't flicker them.
- **Sizes:** text scales with the screen height, so 1080-line screens match the 480-line ones.
- **Page 2:** full hostname, IP address, screen resolution, free disk space and the USB devices plugged in (the Pi 3B+'s own hubs and Ethernet chip are left out). The text is sized to fit, and long device names wrap. On QUAD the info repeats in all four quadrants.
- **Page 3 (MOCKUP):** a full-screen design mockup for this screen, from `mockups/<label>.png`: `P1.png`–`P4.png` at 720x480, `QUAD.png` at 1024x768 for the whole wall, and `HD.png` at 1920x1080 for HIDEF (none yet, so it shows NO MOCKUP HD). It's a place to park future-app ideas and see them on the real CRTs. Swap the PNGs to show a different mockup (currently NERD-E, 2026-11-07). Other sizes are scaled to fit.

Colors follow SCRUTE's current look: orange, green or white.

## How it runs

IDENTIFY isn't a channel app, and it's never assigned. SCRUTE's IDENTIFY menu row sends `POST /identify` to STRINGS on every Pi:

| Request | Effect |
| --- | --- |
| `{"on": true, "page": 1, "color": "orange"}` (page 1–3) | Stops the assigned app and runs IDENTIFY in its place. If IDENTIFY is already up, it just changes the page or color. |
| `{"on": false}` | Stops IDENTIFY and brings the assigned app back. |

`state.json` (the saved assignment) is never touched. If no `/identify` call arrives for 15 minutes, STRINGS restores the assigned app on its own. STRINGS writes the page and color to `/tmp/identify.json`, and `identify.py` checks it four times a second, so flipping pages doesn't restart anything. MP doesn't run this app: SCRUTE draws MP's own label itself.

### Remote (on MP, while IDENTIFY is up)

- Right / Down: next page (1 → 2 → 3 → 1) on every screen; Left / Up: previous page
- BACK or Home: end IDENTIFY everywhere
- Power: the usual fleet power dialog

If a Pi can't be reached, SCRUTE lists it in red along the bottom of MP's screen.

## Install

```sh
sudo git clone https://github.com/LawtonBarnes/identify /opt/identify
sudo chown -R metalshop:metalshop /opt/identify
sudo install -m 755 /opt/identify/identify-launcher /usr/local/bin/identify
```

Needs `python3-pygame` and `python3-numpy`, plus STRINGS 1.13 or later.

`python3 identify.py --snapshot out.png [--page 2|3] [--size 1024x768] [--host quad] [--color green]` renders to a PNG without touching the framebuffer.

## Credits

Font: Roboto Mono by The Roboto Mono Project Authors (SIL Open Font License, `OFL-RobotoMono.txt`), as a static Bold (wght 700) instance cut from the variable font with fontTools.
