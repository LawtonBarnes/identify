# IDENTIFY

A cabling helper for the METAL SHOP Raspberry Pi CRT fleet (see [mcbrain](https://github.com/LawtonBarnes/mcbrain)). Turn it on from CENTRAL SCRUTINIZER and every Pi labels its own screen at once, so you can see which Pi feeds which CRT.

- **Page 1:** the Pi's short name (P1–P4) in huge Roboto Mono Bold over black. QUAD, which drives the 2x2 wall at 1024x768, shows Q1–Q4, one per quadrant (top-left, top-right, bottom-left, bottom-right).
- **Page 2:** full hostname, IP address, screen resolution, free disk space and the USB devices plugged in (the Pi 3B+'s own hubs and Ethernet chip are left out). The text is sized to fit, and long device names wrap. On QUAD the info repeats in all four quadrants.

Colors follow SCRUTE's current look: orange, green or white.

## How it runs

IDENTIFY isn't a channel app, and it's never assigned. SCRUTE's IDENTIFY menu row sends `POST /identify` to STRINGS on every Pi:

| Request | Effect |
| --- | --- |
| `{"on": true, "page": 1, "color": "orange"}` | Stops the assigned app and runs IDENTIFY in its place. If IDENTIFY is already up, it just changes the page or color. |
| `{"on": false}` | Stops IDENTIFY and brings the assigned app back. |

`state.json` (the saved assignment) is never touched. If no `/identify` call arrives for 15 minutes, STRINGS restores the assigned app on its own. STRINGS writes the page and color to `/tmp/identify.json`, and `identify.py` checks it four times a second, so flipping pages doesn't restart anything. MP doesn't run this app: SCRUTE draws MP's own label itself.

### Remote (on MP, while IDENTIFY is up)

- Left / Right / Up / Down: switch page 1 ⇄ 2 on every screen
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

`python3 identify.py --snapshot out.png [--page 2] [--size 1024x768] [--host quad] [--color green]` renders to a PNG without touching the framebuffer.

## Credits

Font: Roboto Mono by The Roboto Mono Project Authors (SIL Open Font License, `OFL-RobotoMono.txt`), as a static Bold (wght 700) instance cut from the variable font with fontTools.
