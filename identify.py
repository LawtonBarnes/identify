#!/usr/bin/env python3
"""IDENTIFY -- labels a Pi's own screen so CRT layouts and cabling are
easy to work out: page 1 is the Pi's short name huge over black, page 2
is its full name, IP, screen resolution, disk space and USB devices,
page 3 (MOCKUP) is a full-screen design mockup for this screen from
mockups/<label>.png (P1-P4 at 720x480, QUAD.png at 1024x768 for the
whole wall) -- a place to park future-app ideas and see them on the real
CRTs. Swap the PNGs to show a different mockup.

Not a channel app. STRINGS runs it temporarily in place of whatever
app is assigned (its /identify endpoint, broadcast to the whole fleet
from SCRUTE's IDENTIFY menu row) and puts the assigned app back
afterward -- state.json is never touched. While it runs, STRINGS
rewrites CONTROL_PATH to flip the page or color, which this picks up
within a quarter second without restarting.

QUAD (the 2x2 wall's 1024x768 frame) splits into four quadrants, one
per CRT, labeled Q1-Q4; page 2 repeats the full info in each.

Framebuffer/console code is copied from thunderstruck.py rather than
shared, per this fleet's no-shared-library convention.
"""
import argparse
import fcntl
import json
import mmap
import os
import re
import shutil
import signal
import socket
import struct
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame  # noqa: E402  (must come after SDL env vars are set)

VERSION = "1.1"

BASE_DIR = Path(__file__).resolve().parent
FONT_PATH = BASE_DIR / "RobotoMono-Bold.ttf"
MOCKUP_DIR = BASE_DIR / "mockups"
PAGES = (1, 2, 3)
CONTROL_PATH = Path("/tmp/identify.json")  # written by STRINGS
CONTROL_POLL_SECONDS = 0.25
INFO_REFRESH_SECONDS = 5  # re-gather page 2 info (a USB device plugged in mid-cabling shows up)

BLACK = (0, 0, 0)
# Same three looks as SCRUTE's COLOR_SCHEMES (AMBER ALERT, GREEN
# MANALISHI, NOIR) -- SCRUTE sends whichever one it's showing.
COLORS = {
    "orange": (0xFF, 0xA5, 0x00),
    "green": (0x00, 0xFF, 0x00),
    "white": (0xFF, 0xFF, 0xFF),
}
DEFAULT_COLOR = "orange"

LABEL_SIZE = 350  # page 1 on a single screen
QUAD_LABEL_SIZE = 200  # page 1, one per quadrant
INFO_SAFE = 0.10  # page 2 margin on each side (composite overscan)
INFO_MAX_SIZE = 72
INFO_MIN_SIZE = 10
INFO_LINE_GAP = 0.25  # fraction of a line's height

# Hostname (lowercase, letters/digits only) -> short label.
SHORT_NAMES = {
    "puppet1": "P1",
    "puppet2": "P2",
    "puppet3": "P3",
    "puppet4": "P4",
    "masterofpuppets": "MP",
    "quad": "QUAD",
}
QUAD_HOSTS = {"quad"}
QUADRANTS = ["Q1", "Q2", "Q3", "Q4"]  # top-left, top-right, bottom-left, bottom-right

# lsusb entries that are part of every Pi 3B+ rather than something
# plugged in: the root hub, the two onboard USB hubs and the onboard
# LAN7800 Ethernet chip.
BUILTIN_USB = {"0424:2514", "0424:7800"}
BUILTIN_USB_VENDORS = {"1d6b"}

KDSETMODE = 0x4B3A
KD_TEXT = 0x00
KD_GRAPHICS = 0x01
FBIO_WAITFORVSYNC = 0x40044620


# --- What this Pi is ---------------------------------------------------

def host_key(hostname):
    return re.sub(r"[^a-z0-9]", "", hostname.lower())


def short_name(hostname):
    return SHORT_NAMES.get(host_key(hostname), hostname.upper()[:4])


def get_ip_address():
    try:
        out = subprocess.run(["hostname", "-I"], capture_output=True, text=True, timeout=2).stdout
        return out.split()[0]
    except (OSError, IndexError, subprocess.SubprocessError):
        return "NO IP"


def get_disk():
    try:
        du = shutil.disk_usage("/")
    except OSError:
        return "?"
    gb = 1024 ** 3
    return f"{du.free / gb:.1f}G FREE OF {du.total / gb:.0f}G"


def get_usb_devices():
    try:
        out = subprocess.run(["lsusb"], capture_output=True, text=True, timeout=3).stdout
    except (OSError, subprocess.SubprocessError):
        return ["LSUSB FAILED"]
    devices = []
    for line in out.splitlines():
        m = re.match(r"Bus \d+ Device \d+: ID ([0-9a-f]{4}):([0-9a-f]{4})\s*(.*)", line)
        if not m:
            continue
        vid, pid, name = m.groups()
        if vid in BUILTIN_USB_VENDORS or f"{vid}:{pid}" in BUILTIN_USB:
            continue
        devices.append(name.strip() or f"ID {vid}:{pid}")
    return sorted(devices)


def gather_info(width, height):
    hostname = socket.gethostname()
    return {
        "hostname": hostname.upper(),
        "ip": get_ip_address(),
        "res": f"{width}x{height}",
        "disk": get_disk(),
        "usb": get_usb_devices(),
    }


# --- Drawing -----------------------------------------------------------

_font_cache = {}


def font(size):
    if size not in _font_cache:
        _font_cache[size] = pygame.font.Font(str(FONT_PATH), size)
    return _font_cache[size]


def blit_centered(canvas, surf, rect):
    """Centers the visible ink of `surf` (not its line box, which has
    descender space under the digits) in `rect`."""
    ink = surf.get_bounding_rect()
    x = rect.x + (rect.w - ink.w) // 2 - ink.x
    y = rect.y + (rect.h - ink.h) // 2 - ink.y
    canvas.blit(surf, (x, y))


def regions(width, height, quad):
    if not quad:
        return [pygame.Rect(0, 0, width, height)]
    hw, hh = width // 2, height // 2
    return [pygame.Rect(0, 0, hw, hh), pygame.Rect(hw, 0, width - hw, hh),
            pygame.Rect(0, hh, hw, height - hh), pygame.Rect(hw, hh, width - hw, height - hh)]


INDENT = " " * 5  # lines up with the values after "DISK "


def info_lines(label, info, quad):
    head = f"{info['hostname']} {label}" if quad else info["hostname"]
    usb = info["usb"] or ["NONE"]
    lines = [
        head,
        f"IP   {info['ip']}",
        f"RES  {info['res']}",
        f"DISK {info['disk']}",
        f"USB  {usb[0]}",
    ] + [INDENT + d for d in usb[1:]]
    return [line.upper() for line in lines]


def wrap(lines, cols):
    """Word-wraps each line to `cols` characters, continuation lines
    indented under the value column. Returns None if a word can't fit."""
    out = []
    for line in lines:
        while len(line) > cols:
            cut = line.rfind(" ", len(INDENT) + 1, cols + 1)
            if cut <= len(INDENT):
                return None
            out.append(line[:cut].rstrip())
            line = INDENT + line[cut:].strip()
        out.append(line)
    return out


def fit(lines, box):
    """Largest font size (and the lines wrapped for it) that fits `box`.
    Roboto Mono is monospaced, so one character width gives the column
    count; long USB names wrap rather than shrinking everything."""
    for size in range(INFO_MAX_SIZE, INFO_MIN_SIZE - 1, -1):
        f = font(size)
        wrapped = wrap(lines, box.w // f.size("M")[0])
        if wrapped is None:
            continue
        h = len(wrapped) * f.get_linesize() * (1 + INFO_LINE_GAP)
        if h <= box.h:
            return size, wrapped
    return INFO_MIN_SIZE, lines


def draw_info(canvas, lines, rect, color):
    box = rect.inflate(-int(rect.w * INFO_SAFE * 2), -int(rect.h * INFO_SAFE * 2))
    size, lines = fit(lines, box)
    f = font(size)
    step = int(f.get_linesize() * (1 + INFO_LINE_GAP))
    block_h = step * len(lines) - int(f.get_linesize() * INFO_LINE_GAP)
    block_w = max(f.size(line)[0] for line in lines)
    x = box.x + (box.w - block_w) // 2
    y = box.y + (box.h - block_h) // 2
    for line in lines:
        canvas.blit(f.render(line, True, color), (x, y))
        y += step


def draw_mockup(canvas, hostname, color):
    """Page 3: mockups/<label>.png scaled to fit (aspect kept), centered.
    QUAD gets one image for the whole 1024x768 wall, not per quadrant."""
    label = short_name(hostname)
    path = MOCKUP_DIR / f"{label}.png"
    try:
        img = pygame.image.load(str(path)).convert()
    except (pygame.error, FileNotFoundError):
        rect = canvas.get_rect()
        blit_centered(canvas, font(48).render(f"NO MOCKUP {label}", True, color), rect)
        return
    cw, ch = canvas.get_size()
    scale = min(cw / img.get_width(), ch / img.get_height())
    if scale != 1:
        img = pygame.transform.smoothscale(
            img, (round(img.get_width() * scale), round(img.get_height() * scale)))
    canvas.blit(img, ((cw - img.get_width()) // 2, (ch - img.get_height()) // 2))


def draw(canvas, page, color_name, hostname, info):
    canvas.fill(BLACK)
    color = COLORS.get(color_name, COLORS[DEFAULT_COLOR])
    if page == 3:
        draw_mockup(canvas, hostname, color)
        return
    quad = host_key(hostname) in QUAD_HOSTS
    rects = regions(*canvas.get_size(), quad)
    labels = QUADRANTS if quad else [short_name(hostname)]
    for label, rect in zip(labels, rects):
        if page == 2:
            draw_info(canvas, info_lines(label, info, quad), rect, color)
        else:
            size = QUAD_LABEL_SIZE if quad else LABEL_SIZE
            blit_centered(canvas, font(size).render(label, True, color), rect)


# --- Framebuffer (copied from thunderstruck.py) -------------------------

class FrameBuffer:
    def __init__(self, dev="/dev/fb0"):
        sys_dir = Path("/sys/class/graphics") / Path(dev).name
        self.width, self.height = (int(x) for x in (sys_dir / "virtual_size").read_text().split(","))
        self.bpp = int((sys_dir / "bits_per_pixel").read_text())
        if self.bpp not in (16, 32):
            raise RuntimeError(f"Unsupported framebuffer depth: {self.bpp}bpp")
        self.stride = int((sys_dir / "stride").read_text())
        self.row_bytes = self.width * self.bpp // 8
        self.fd = os.open(dev, os.O_RDWR)
        self.mm = mmap.mmap(self.fd, self.stride * self.height, mmap.MAP_SHARED,
                            mmap.PROT_WRITE | mmap.PROT_READ)
        self.rgb565 = pygame.Surface((self.width, self.height), 0, 16) if self.bpp == 16 else None

    def write_surface(self, surface):
        if self.bpp == 16:
            self.rgb565.blit(surface, (0, 0))
            raw = self.rgb565.get_buffer().raw
        else:
            arr = pygame.surfarray.pixels3d(surface).transpose(1, 0, 2)
            alpha = np.zeros((self.height, self.width, 1), dtype=np.uint8)
            raw = np.concatenate([arr[:, :, ::-1], alpha], axis=2).astype(np.uint8).tobytes()
            del arr
        try:
            fcntl.ioctl(self.fd, FBIO_WAITFORVSYNC, struct.pack("I", 0))
        except OSError:
            pass
        if self.stride == self.row_bytes:
            self.mm.seek(0)
            self.mm.write(raw)
        else:
            for y in range(self.height):
                self.mm.seek(y * self.stride)
                self.mm.write(raw[y * self.row_bytes:(y + 1) * self.row_bytes])

    def close(self):
        self.mm.close()
        os.close(self.fd)


# --- App ---------------------------------------------------------------

def read_control(default_page, default_color):
    try:
        data = json.loads(CONTROL_PATH.read_text())
    except (OSError, ValueError):
        return default_page, default_color
    page = data.get("page", default_page)
    color = data.get("color", default_color)
    return (page if page in PAGES else default_page), (color if color in COLORS else default_color)


class IdentifyApp:
    def __init__(self, page, color):
        self.default_page, self.default_color = page, color
        self._quit = False
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)
        pygame.display.init()
        pygame.font.init()
        self.fb = FrameBuffer()
        pygame.display.set_mode((self.fb.width, self.fb.height))  # headless (dummy driver)
        self.canvas = pygame.Surface((self.fb.width, self.fb.height))
        self.hostname = socket.gethostname()

        self.tty_fd = None
        self.console_graphics_mode = False
        try:
            self.tty_fd = os.open("/dev/tty", os.O_RDWR)
            fcntl.ioctl(self.tty_fd, KDSETMODE, KD_GRAPHICS)
            self.console_graphics_mode = True
        except OSError as exc:
            print(f"Console graphics mode not available: {exc}", file=sys.stderr)

    def _handle_signal(self, signum, frame):
        self._quit = True

    def run(self):
        shown = None
        info, info_at = None, 0.0
        try:
            while not self._quit:
                page, color = read_control(self.default_page, self.default_color)
                now = time.monotonic()
                if page == 2 and (info is None or now - info_at >= INFO_REFRESH_SECONDS):
                    info, info_at = gather_info(self.fb.width, self.fb.height), now
                key = (page, color, json.dumps(info) if page == 2 else None)
                if key != shown:
                    draw(self.canvas, page, color, self.hostname, info)
                    self.fb.write_surface(self.canvas)
                    shown = key
                time.sleep(CONTROL_POLL_SECONDS)
        finally:
            self.fb.close()
            if self.console_graphics_mode:
                fcntl.ioctl(self.tty_fd, KDSETMODE, KD_TEXT)
                os.write(self.tty_fd, b"\033[2J\033[H")
            if self.tty_fd is not None:
                os.close(self.tty_fd)
            pygame.quit()


def snapshot(path, size, page, color, hostname):
    pygame.display.init()
    pygame.font.init()
    pygame.display.set_mode((1, 1))
    canvas = pygame.Surface(size)
    info = gather_info(*size)
    info["hostname"] = hostname.upper()
    draw(canvas, page, color, hostname, info)
    pygame.image.save(canvas, path)
    print(f"saved {path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--page", type=int, choices=PAGES, default=1)
    parser.add_argument("--color", choices=sorted(COLORS), default=DEFAULT_COLOR)
    parser.add_argument("--snapshot", metavar="PNG", help="render to a PNG instead of the framebuffer")
    parser.add_argument("--size", default="720x480", help="snapshot size, WxH")
    parser.add_argument("--host", default=socket.gethostname(), help="snapshot as this hostname")
    args = parser.parse_args()
    if args.snapshot:
        w, h = (int(v) for v in args.size.lower().split("x"))
        snapshot(args.snapshot, (w, h), args.page, args.color, args.host)
    else:
        IdentifyApp(args.page, args.color).run()


if __name__ == "__main__":
    main()
