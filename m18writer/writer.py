#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
from dataclasses import dataclass
from enum import IntEnum
import itertools
import logging
from logging import getLogger, StreamHandler
import math
from pathlib import Path
from typing import List, Optional

import numpy as np
from PIL import Image, ImageDraw, ImageFont
import serial

from .fonts import BUILTIN_FONTS

logger = getLogger(__name__)
stream_handler = StreamHandler()
stream_handler.setLevel(logging.DEBUG)
logger.setLevel(logging.DEBUG)
logger.addHandler(stream_handler)


SLOT_MAX = 8
COLUMNS_MAX = 255
PIXEL_PER_COLUMN = 8
MAGIC_NUMBER = [0x41, 0x68, 0x65, 0x6c, 0x6c, 0x6f]
PREVIEW_PIXEL_GAP = (14, 14)
# B1248: 11x44 badge with USB HID interface
HID_VENDOR_ID = 0x0483
HID_PRODUCT_ID = 0x5750
HID_LINES = 11
HID_WIDTH = 44
HID_REPORT_SIZE = 64


class Brightness(IntEnum):
    BRIGHTEST = 0
    BRIGHTER = 1
    DIMMER = 2
    DIMMEST = 3


class Speed(IntEnum):
    SPEED_0 = 0
    SPEED_1 = 1
    SPEED_2 = 2
    SPEED_3 = 3
    SPEED_4 = 4
    SPEED_5 = 5
    SPEED_6 = 6
    SPEED_7 = 7


class Motion(IntEnum):
    LEFT = 0b000
    RIGHT = 0b001
    UP = 0b010
    DOWN = 0b011
    FREEZE = 0b100
    ANIMATION = 0b101
    SNOW = 0b110
    CURTAIN = 0b111
    LASER = 0b1000


@dataclass
class Slot:
    bitmap: bytes = b""
    columns: int = 0
    border: bool = False
    blink: bool = False
    speed: Speed = Speed.SPEED_4
    motion: Motion = Motion.LEFT

    def get_mode(self):
        return (
            0b10000000 * self.border
            + 0b00010000 * self.speed
            + 0b00001000 * self.blink
            + (0b00000111 & self.motion)
        )


def _build_header(brightness: Brightness, slot_list: List[Slot]) -> bytes:
    slot_list = (slot_list + [Slot() for x in range(SLOT_MAX)])[:SLOT_MAX]

    mode_list = [m.get_mode() for m in slot_list]
    # 7-0 -> mode 8-1: laser(on motion=0)/freeze(on motion!=0)
    laser = sum([int(x.motion == Motion.LASER) << i for i, x in enumerate(slot_list)])
    columns_list = [x.columns for x in slot_list]
    column_offset_list = [0] + list(itertools.accumulate([x.columns for x in slot_list]))
    if max(columns_list) > 0xffff:
        raise RuntimeError(
            "Columns must be less than 65536: {}".format(columns_list)
        )
    if max(column_offset_list) > 0xffff:
        raise RuntimeError(
            "Column offset must be less than 65536: {}".format(column_offset_list)
        )

    return bytes([
        *MAGIC_NUMBER,
        brightness,
        0x00,
        *mode_list,
        0x00,
        *itertools.chain.from_iterable([
            [(column_offset_list[x] >> 8) & 0xff, column_offset_list[x] & 0xff,
             (columns_list[x] >> 8) & 0xff, columns_list[x] & 0xff]
            for x in range(SLOT_MAX)
        ]),
        laser,
        0x00, 0x00, 0x00, 0x00,
    ])


def _build_body(slot_list: List[Slot]) -> bytes:
    return bytes(itertools.chain.from_iterable([
        itertools.chain.from_iterable(x)
        for x in zip(*[zip(*[iter(x.bitmap)] * x.columns) for x in slot_list])
    ]))


def _fit_image(image: Image.Image, lines: int) -> Image.Image:
    image = image.convert("L")
    return image.resize((int(image.width * (lines / image.height)), lines), Image.BICUBIC)


def image_to_slot(image: Image.Image, lines: int, threshold: int, **mode) -> Slot:
    image = _fit_image(image, lines)
    columns = min(COLUMNS_MAX, math.ceil(image.width / PIXEL_PER_COLUMN))
    pixel_list = bytes(
        [1 if x > threshold else 0
         for x in image.crop((0, 0, columns * PIXEL_PER_COLUMN, image.height)).tobytes()]
    )
    bitmap = bytes(
        [sum([x << i for i, x in enumerate(reversed(pixel_list[x:(x + PIXEL_PER_COLUMN)]))])
         for x in range(0, len(pixel_list), PIXEL_PER_COLUMN)]
    )
    return Slot(bitmap=bitmap, columns=columns, **mode)


def load_image(path: str, lines: int, threshold: int, **mode) -> Slot:
    return image_to_slot(Image.open(path), lines, threshold, **mode)


def _draw_text(text: str, font) -> Image.Image:
    """Draw text without antialiasing and crop it to the lit pixels."""
    width, height = font.getmask(text).size
    width, height = max(width, 1), max(height, 1)
    # generous margin for glyphs which overhang their mask box
    canvas = Image.new("L", (width + height * 2, height * 3))
    draw = ImageDraw.Draw(canvas)
    draw.fontmode = "1"
    draw.text((height, height), text, fill=255, font=font)
    bbox = canvas.getbbox()
    return canvas.crop(bbox) if bbox else Image.new("L", (PIXEL_PER_COLUMN, 1))


def render_text(text: str, lines: int,
                font_path: Optional[str] = None, font_size: Optional[int] = None) -> Image.Image:
    """Render text as a bitmap image exactly `lines` pixels high.

    `font_path` may also be the name of a built-in pixel font (see `BUILTIN_FONTS`).
    Without `font_path`, Pillow's built-in bitmap font is used.
    Without `font_size`, the largest size that fits in `lines` is chosen.

    >>> render_text("Hello", 12).height
    12
    >>> render_text("Hello", 11, "pixel").size
    (21, 11)
    """
    if font_path in BUILTIN_FONTS:
        if font_size is not None:
            logger.warning("--font-size is ignored with built-in font %r.", font_path)
        glyphs = BUILTIN_FONTS[font_path].render(text)
    elif font_path is None:
        glyphs = _draw_text(text, ImageFont.load_default())
    elif font_size is not None:
        glyphs = _draw_text(text, ImageFont.truetype(font_path, font_size))
    else:
        for size in range(lines * 2, 0, -1):
            glyphs = _draw_text(text, ImageFont.truetype(font_path, size))
            if glyphs.height <= lines:
                break
    if glyphs.height > lines:
        logger.warning("Text is %d px high and will be scaled to %d lines.", glyphs.height, lines)
        return glyphs
    image = Image.new("L", (glyphs.width, lines))
    image.paste(glyphs, (0, (lines - glyphs.height) // 2))
    return image


def load_text(text: str, lines: int, threshold: int,
              font_path: Optional[str] = None, font_size: Optional[int] = None, **mode) -> Slot:
    return image_to_slot(render_text(text, lines, font_path, font_size), lines, threshold, **mode)


def align_image(image: Image.Image, lines: int, width: int, align: str = "left") -> Image.Image:
    """Pad an image narrower than the display to `width`, aligned left, center or right.

    >>> align_image(Image.new("L", (10, 11)), 11, 44, "center").size
    (44, 11)
    >>> align_image(Image.new("L", (50, 11)), 11, 44, "center").size
    (50, 11)
    """
    image = _fit_image(image, lines)
    if align == "left" or image.width >= width:
        return image
    canvas = Image.new("L", (width, lines))
    canvas.paste(image, ((width - image.width) // 2 if align == "center" else width - image.width, 0))
    return canvas


def slot_to_ascii(slot: Slot, width: int, on: str = "\u2588", off: str = "\u00b7") -> str:
    """Draw the bitmap of a slot as text; a bar marks the right edge of the display.

    >>> print(slot_to_ascii(Slot(bitmap=bytes([0b10100000, 0b11000000]), columns=1), 4, "#", "."))
    #.#.|....
    ##..|....
    """
    lines = len(slot.bitmap) // slot.columns if slot.columns else 0
    rows = []
    for line in range(lines):
        row = "".join(
            on if (x >> (PIXEL_PER_COLUMN - 1 - i)) & 1 else off
            for x in slot.bitmap[(line * slot.columns):((line + 1) * slot.columns)]
            for i in range(PIXEL_PER_COLUMN)
        )
        rows.append(row[:width] + "|" + row[width:] if len(row) > width else row)
    return "\n".join(rows)


def save_preview(path: str, lines: int, display_width: int, save_path: str):
    save_preview_image(Image.open(path), lines, display_width, save_path)


def save_preview_image(image: Image.Image, lines: int, display_width: int, save_path: str):
    image = _fit_image(image, lines)

    mask = np.array(Image.open(Path(__file__).parent / "mask.png"))
    display_size = (PREVIEW_PIXEL_GAP[1] * lines, PREVIEW_PIXEL_GAP[0] * display_width)
    for x in range(image.width // display_width + (1 if image.width % display_width else 0)):
        im = image.crop((x * display_width, 0, (x + 1) * display_width, lines))
        preview = np.zeros(display_size, dtype=np.uint8)
        for i, p in enumerate(im.tobytes()):
            submask = np.zeros(preview.shape, dtype=preview.dtype)
            offset_x = (i % display_width) * PREVIEW_PIXEL_GAP[0]
            offset_y = (i // display_width) * PREVIEW_PIXEL_GAP[1]
            submask[offset_y:(offset_y + mask.shape[0]),
                    offset_x:(offset_x + mask.shape[1])] = mask
            preview[submask != 0] = p
        Image.fromarray(preview).save(save_path.format(n=x))


def write_payload(brightness: Brightness, slot_list: List[Slot], device="/dev/ttyUSB0", baud=1200):
    header = _build_header(brightness, slot_list)
    body = _build_body(slot_list)
    payload = header + body[:16] + bytes([0 for x in range(32)]) + body[16:]
    m18 = serial.Serial(device, baud)
    m18.write(payload)


def _build_hid_reports(slot_list: List[Slot]) -> List[bytes]:
    """Build 64-byte reports for the B1248 HID badge.

    "Hello", slot configuration, one report per line (all bitmaps side by side)
    and a dummy line.

    >>> reports = _build_hid_reports([Slot(bitmap=bytes(range(11)), columns=1)])
    >>> len(reports), reports[0][:5], reports[1][:18].hex()
    (14, b'Hello', '004040404040404040000800000108010000')
    >>> [r[0] for r in reports[2:]]
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 0]
    """
    slot_list = (slot_list + [Slot() for x in range(SLOT_MAX)])[:SLOT_MAX]
    if any(x.motion == Motion.LASER for x in slot_list):
        raise RuntimeError("Laser motion is not supported on HID badge.")
    for x in slot_list:
        if x.columns and len(x.bitmap) != x.columns * HID_LINES:
            raise RuntimeError(f"Bitmaps must be {HID_LINES} lines high for HID badge.")
    columns_list = [x.columns for x in slot_list]
    column_offset_list = [0] + list(itertools.accumulate(columns_list))
    if column_offset_list[-1] > HID_REPORT_SIZE:
        raise RuntimeError(
            "Total columns must be {} or less (8 pixels/column): {}".format(
                HID_REPORT_SIZE, columns_list)
        )

    config = bytes([
        0x00,
        *[x.get_mode() for x in slot_list],
        0x00,
        *itertools.chain.from_iterable([
            [0x08, column_offset_list[x], 0x00, columns_list[x]]
            for x in range(SLOT_MAX)
        ]),
    ])
    lines = []
    for line in range(HID_LINES):
        report = bytearray(HID_REPORT_SIZE)
        for x, offset in zip(slot_list, column_offset_list):
            report[offset:(offset + x.columns)] = x.bitmap[(line * x.columns):((line + 1) * x.columns)]
        lines.append(bytes(report))
    return [
        b"Hello".ljust(HID_REPORT_SIZE, b"\x00"),
        config.ljust(HID_REPORT_SIZE, b"\x00"),
        *lines,
        bytes(HID_REPORT_SIZE),
    ]


def write_hid_payload(slot_list: List[Slot], vendor_id=HID_VENDOR_ID, product_id=HID_PRODUCT_ID):
    import hid

    reports = _build_hid_reports(slot_list)
    device = hid.device()
    try:
        device.open(vendor_id, product_id)
    except OSError as e:
        raise RuntimeError(
            f"Cannot open HID badge {vendor_id:04x}:{product_id:04x} "
            "(is it plugged in/attached, and do you have permission?)"
        ) from e
    try:
        for report in reports:
            # the first byte is report ID
            device.write(b"\x00" + report)
    finally:
        device.close()


def main():
    brightness_list = {
        "1": Brightness.DIMMEST,
        "2": Brightness.DIMMER,
        "3": Brightness.BRIGHTER,
        "4": Brightness.BRIGHTEST
    }
    speed_list = {
        "1": Speed.SPEED_0,
        "2": Speed.SPEED_1,
        "3": Speed.SPEED_2,
        "4": Speed.SPEED_3,
        "5": Speed.SPEED_4,
        "6": Speed.SPEED_5,
        "7": Speed.SPEED_6,
        "8": Speed.SPEED_7,
    }
    motion_list = {
        "left": Motion.LEFT,
        "right": Motion.RIGHT,
        "up": Motion.UP,
        "down": Motion.DOWN,
        "freeze": Motion.FREEZE,
        "animation": Motion.ANIMATION,
        "snow": Motion.SNOW,
        "curtain": Motion.CURTAIN,
        "laser": Motion.LASER
    }
    parser = argparse.ArgumentParser(description="Write text and images to LED name badges (serial M1-8 and USB HID B1248).")
    parser.add_argument("paths", metavar="path", type=str, nargs="+",
                        help=f"an image path for bitmap (able to write to slot 1-{SLOT_MAX}).")
    parser.add_argument("-T", "--text", action="store_true",
                        help="treat each path as text to display instead of an image path.")
    parser.add_argument("-f", "--font", type=str, default=None,
                        help="font for --text: a built-in pixel font ({}) or a TrueType/OpenType "
                             "font file (default: Pillow's bitmap font).".format(", ".join(BUILTIN_FONTS)))
    parser.add_argument("-s", "--font-size", type=int, default=None,
                        help="font size for a font file (default: largest size fitting the lines).")
    parser.add_argument("-a", "--align", default="left", choices=["left", "center", "right"],
                        help="align content narrower than the display (default: left).")
    parser.add_argument("--hid", action="store_true",
                        help=f"write to {HID_LINES}x{HID_WIDTH} USB HID badge "
                             f"({HID_VENDOR_ID:04x}:{HID_PRODUCT_ID:04x}) instead of serial badge.")
    parser.add_argument("-d", "--device", type=str, default="/dev/ttyUSB0",
                        help="tty of LED name badge.")
    parser.add_argument("-b", "--baud", type=int, default=1200,
                        help="baud rate of LED name badge.")
    parser.add_argument("-l", "--lines", type=int, default=None,
                        help=f"number of lines of LED name badge (default: 12, {HID_LINES} with --hid).")
    parser.add_argument("-w", "--width", type=int, default=None,
                        help=f"number of columns of LED name badge (default: 48, {HID_WIDTH} with --hid).")
    parser.add_argument("-t", "--threshold", type=int, default=128,
                        help="threshold of bitmap pixel to light LED.")
    parser.add_argument("--brightness", default=None, choices=brightness_list,
                        help="brightness of LED name badge (default: 4, unsupported with --hid).")
    parser.add_argument("-p", "--preview", action="store_true",
                        help="show what would be written in the terminal (skip writing payload).")
    parser.add_argument("--save-preview", action="store_true",
                        help="save preview images to --savepath1..8 (skip writing payload).")
    for x in range(SLOT_MAX):
        parser.add_argument(f"--border{x + 1}", action="store_true",
                            help=f"show border on slot 1-{SLOT_MAX}."
                                 if x == 0 else argparse.SUPPRESS)
        parser.add_argument(f"--blink{x + 1}", action="store_true",
                            help=f"blink bitmap on slot 1-{SLOT_MAX}."
                                 if x == 0 else argparse.SUPPRESS)
        parser.add_argument(f"--speed{x + 1}", choices=speed_list,
                            help=f"set speed on slot 1-{SLOT_MAX}."
                                 if x == 0 else argparse.SUPPRESS)
        parser.add_argument(f"--motion{x + 1}", choices=motion_list,
                            help=f"set motion on slot 1-{SLOT_MAX}."
                                 if x == 0 else argparse.SUPPRESS)
        parser.add_argument(f"--savepath{x + 1}", type=str, default=f"preview_{x + 1}_{{n}}.png",
                            help=f"path to save preview of image 1-{SLOT_MAX}."
                                 if x == 0 else argparse.SUPPRESS)

    args = parser.parse_args()
    if args.lines is None:
        args.lines = HID_LINES if args.hid else 12
    if args.width is None:
        args.width = HID_WIDTH if args.hid else 48
    if args.hid and args.brightness is not None:
        logger.warning("--brightness is not supported with --hid and is ignored.")
    brightness = brightness_list[args.brightness or "4"]
    if args.text:
        images = [render_text(x, args.lines, args.font, args.font_size) for x in args.paths]
    else:
        images = [Image.open(x) for x in args.paths]
    images = [align_image(x, args.lines, args.width, args.align) for x in images[:SLOT_MAX]]
    slot_list = [
        image_to_slot(
            x, args.lines, args.threshold,
            **{k: v for k, v in{
                "border": getattr(args, f"border{i + 1}"),
                "blink": getattr(args, f"blink{i + 1}"),
                "speed": speed_list.get(getattr(args, f"speed{i + 1}")),
                "motion": motion_list.get(getattr(args, f"motion{i + 1}"))
            }.items() if v is not None}
        )
        for i, x in enumerate(images)
    ]
    if args.preview:
        for i, slot in enumerate(slot_list):
            print(f"Slot {i + 1}: {slot.columns * PIXEL_PER_COLUMN} px wide "
                  f"(display is {args.width} px; | marks its right edge)")
            print(slot_to_ascii(slot, args.width))
        if args.hid:
            print(f"Total: {sum(x.columns for x in slot_list)} of {HID_REPORT_SIZE} columns used.")
    if args.save_preview:
        for i, image in enumerate(images):
            save_preview_image(image, args.lines, args.width, getattr(args, f"savepath{i + 1}"))
    if args.preview or args.save_preview:
        return
    if args.hid:
        write_hid_payload(slot_list)
    else:
        write_payload(brightness, slot_list, args.device, args.baud)


if __name__ == "__main__":
    import doctest
    doctest.testmod()
    main()
