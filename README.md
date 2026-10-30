# led-badge-writer

Write text and images to LED name badges: serial M1-8 badges (12x48) and USB HID B1248 badges (11x44, `0483:5750`).

```
$ led-badge-writer --hid --text --font pixel --preview "Hello World"
Slot 1: 56 px wide (display is 44 px; | marks its right edge)
············································|············
█···█·······█·█···········█···█············█|·····█······
█···█·······█·█···········█···█············█|·····█······
█···█··███··█·█··███······█···█··███··█·██·█|··██·█······
█████·█···█·█·█·█···█·····█·█·█·█···█·██···█|·█··██······
█···█·█████·█·█·█···█·····█·█·█·█···█·█····█|·█···█······
█···█·█·····█·█·█···█·····█·█·█·█···█·█····█|·█···█······
█···█··███··█·█··███·······█·█···███··█····█|··████······
············································|············
············································|············
············································|············
Total: 7 of 64 columns used.
```

## Table of Contents

- [Background](#background)
- [Install](#install)
- [Usage](#usage)
  - [Text](#text)
  - [Images](#images)
  - [Display options](#display-options)
  - [Previewing](#previewing)
  - [Command reference](#command-reference)
- [Supported Devices](#supported-devices)
- [Protocol](#protocol)
- [Maintainers](#maintainers)
- [Thanks](#thanks)
- [Contributing](#contributing)
- [License](#license)

## Background

Cheap programmable LED name badges usually ship with Windows-only software. This tool writes to them from the command line on Linux (and anywhere else Python runs).

It is a fork of [m1-8-writer](https://github.com/amane-katagiri/m1-8-writer) by [Amane Katagiri](https://github.com/amane-katagiri), which reverse-engineered the serial M1-8 protocol. This fork adds:

- **Text rendering**: write text directly, without making an image first.
- **Built-in pixel fonts** drawn for 11–12 pixel displays, plus support for any TrueType/OpenType font.
- **USB HID badges** (B1248, `0483:5750`).
- **Alignment**: center or right-align content narrower than the display.
- **Terminal preview**: see exactly what will be written before writing it.

## Install

Requires Python 3.7 or later.

```
pip install git+https://github.com/jpdenzer/led-badge-writer.git
```

For USB HID badges, install with HID support (adds [hidapi](https://pypi.org/project/hidapi/)):

```
pip install "led-badge-writer[hid] @ git+https://github.com/jpdenzer/led-badge-writer.git"
```

This installs the `led-badge-writer` command. The original `m18write` command is also installed and works the same way.

### Linux permissions for HID badges

Allow non-root access to the badge with a udev rule, then replug it:

```
echo 'SUBSYSTEMS=="usb", ATTRS{idVendor}=="0483", ATTRS{idProduct}=="5750", MODE="0666"' | sudo tee /etc/udev/rules.d/99-led-badge.rules
sudo udevadm control --reload-rules && sudo udevadm trigger
```

### WSL

WSL does not see USB devices by default. Attach the badge from Windows with [usbipd-win](https://github.com/dorssel/usbipd-win), in PowerShell:

```
usbipd list
usbipd attach --wsl --busid <BUSID>
```

### From a clone

To work on the code, install it in editable mode so changes take effect without reinstalling:

```
git clone https://github.com/jpdenzer/led-badge-writer.git
cd led-badge-writer
pip install --user -e ".[hid]"
```

## Usage

Add `--hid` for USB HID badges; leave it out for serial M1-8 badges. Each positional argument goes to its own slot (up to 8).

### Text

```
led-badge-writer --hid --text "Hello World"
```

Several messages, one per slot:

```
led-badge-writer --hid --text "Hello" "Nice to meet you"
```

Choose a font with `--font`:

| Font | Description |
|---|---|
| *(default)* | Pillow's built-in bitmap font |
| `pixel` | 5x7 proportional font with descenders (g, j, p, q, y) |
| `bold` | `pixel` with thicker strokes |
| `tiny` | 3x5 capitals; fits about twice as much text |
| *path to a file* | Any TrueType/OpenType font, sized to fit the display unless `--font-size` is given |

```
led-badge-writer --hid --text --font bold "Hello World"
led-badge-writer --hid --text --font /usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf "Hello World"
```

The built-in fonts cover all printable ASCII characters; any other character is shown as `?`.

### Images

Pass image paths instead of text. Images are scaled to the height of the display and converted to black and white (pixels brighter than `--threshold`, default 128, are lit).

```
led-badge-writer --hid image1.png image2.png
```

### Display options

Each slot has its own options; the number is the slot (`--speed1` for slot 1, `--speed2` for slot 2, and so on).

| Option | Values | Effect |
|---|---|---|
| `--speedN` | `1`–`8` | Scroll/animation speed (8 is fastest) |
| `--motionN` | `left`, `right`, `up`, `down`, `freeze`, `animation`, `snow`, `curtain`, `laser` | How the slot is shown (`laser` is serial only) |
| `--blinkN` | | Blink the slot |
| `--borderN` | | Show an animated border |

Options for all slots:

| Option | Values | Effect |
|---|---|---|
| `--align` | `left` (default), `center`, `right` | Position of content narrower than the display |
| `--brightness` | `1`–`4` (default `4`) | Brightness (serial only) |

Examples:

```
led-badge-writer --hid --text --speed1 7 --motion1 snow --border1 "Hello World"
led-badge-writer --hid --text --font bold --align center --motion1 freeze "HI!"
led-badge-writer --hid --text --blink1 --motion2 right "Hello" "World"
```

### Previewing

Show what would be written in the terminal, without writing to the badge:

```
led-badge-writer --hid --text --font pixel --preview "Hello World"
```

`|` marks the right edge of the display; anything to its right scrolls into view. With `--hid`, the last line shows how many of the 64 available columns are used.

To save PNG previews that look like the badge instead, use `--save-preview` (files are named `preview_1_0.png` and so on; change this with `--savepath1` to `--savepath8`).

### Command reference

```
led-badge-writer -h
```

| Option | Default | Description |
|---|---|---|
| `-T`, `--text` | | Treat arguments as text instead of image paths |
| `-f`, `--font` | Pillow bitmap font | Built-in font name or font file |
| `-s`, `--font-size` | fit to display | Size for a font file |
| `-a`, `--align` | `left` | Alignment of narrow content |
| `--hid` | | Write to a USB HID badge |
| `-d`, `--device` | `/dev/ttyUSB0` | Serial port (serial badges) |
| `-b`, `--baud` | `1200` | Baud rate (serial badges) |
| `-l`, `--lines` | 12 (11 with `--hid`) | Display height in pixels |
| `-w`, `--width` | 48 (44 with `--hid`) | Display width in pixels |
| `-t`, `--threshold` | `128` | Brightness above which a pixel is lit |
| `--brightness` | `4` | Brightness 1–4 (serial only) |
| `-p`, `--preview` | | Print a preview instead of writing |
| `--save-preview` | | Save PNG previews instead of writing |

## Supported Devices

### Serial M1-8 badges

- 12x48 LED matrix.
- Shows "M1-8" at startup.
- Comes with the Windows programs "LED Display" or "Mini LED Display".

### USB HID badges (B1248)

- 11x44 LED matrix.
- Shows up as USB device `0483:5750` (STMicroelectronics, "LED badge -- mini LED display -- 11x44") rather than a serial port.
- All slots together can be at most 64 columns (512 pixels) wide.
- Brightness and `laser` motion are not supported.

## Protocol

### Serial (M1-8)

The payload is a header followed by the bitmaps.

#### Header

```python
[
    0x41, 0x68, 0x65, 0x6c, 0x6c, 0x6f,  # magic number: Ahello
    0x00,  # brightness: the brightest 0x00 --- 0x01 --- 0x02 --- 0x03 the dimmest
    0x00,  # NOP
    # slot 1-8 have their own display modes
    # 0b10000000: show border
    # 0b01110000: speed
    # 0b00001000: blink
    # 0b00000111: motion (left/right/up/down/freeze/animation/snow/curtain)
    0b00110000,  # mode of slot 1
    0b00110110,  # mode of slot 2
    0b00110111,  # mode of slot 3
    0b00110000,  # mode of slot 4
    0b00110000,  # mode of slot 5
    0b00110100,  # mode of slot 6
    0b00110110,  # mode of slot 7
    0b00110111,  # mode of slot 8
    0x00,  # NOP
    # number of columns (8 pixels/column) and offset of slot 1-8
    0x00, 0, 0x00, 1,  # columns and offset of slot 1 bitmap
    0x00, 1, 0x00, 2,  # columns and offset of slot 2 bitmap
    0x00, 3, 0x00, 3,  # columns and offset of slot 3 bitmap
    0x00, 6, 0x00, 4,  # columns and offset of slot 4 bitmap
    0x00, 10, 0x00, 5,  # columns and offset of slot 5 bitmap
    0x00, 15, 0x00, 6,  # columns and offset of slot 6 bitmap
    0x00, 21, 0x00, 7,  # columns and offset of slot 7 bitmap
    0x00, 28, 0x00, 8,  # columns and offset of slot 8 bitmap
    # laser mode of slot 1-8
    # 0b00000001: laser on slot 1
    # 0b00000010: laser on slot 2
    # ...
    # 0b10000000: laser on slot 8
    # motion of laser mode slot must be 000 (otherwise stop on the slot)
    0b00001000,
    0x00, 0x00, 0x00, 0x00,  # NOP
]
```

#### Body

Bitmap data are split line by line from the top, and each line is split every 8 pixels from the left. Each 8 pixels are one byte, with the leftmost pixel in the high-order bit.

```python
# a 32px (=8*4) wide bitmap
[
    0b10101010, packet_002, packet_003, packet_004,  # line 1
    packet_005, packet_006, packet_007, packet_008,  # line 2
    packet_009, packet_010, packet_011, packet_012,  # line 3
    #         ... line by line ...
    0b10001000, 0b11001100, 0b11110000, 0b10110111
]
```

The first byte `0b10101010` represents `* * * * ` in the top left corner and the last byte `0b10110111` represents `* ** ***` in the bottom right corner (`*` is a lit pixel).

All bitmaps are written in parallel, line by line from the top (`bitmap_03_line_02` is the 2nd line of the 3rd bitmap):

```python
# 4 bitmaps
[
    bitmap_01_line_01, bitmap_02_line_01, bitmap_03_line_01, bitmap_04_line_01,
    bitmap_01_line_02, bitmap_02_line_02, bitmap_03_line_02, bitmap_04_line_02,
    bitmap_01_line_03, bitmap_02_line_03, bitmap_03_line_03, bitmap_04_line_03,
    #                          ... line by line ...
    bitmap_01_line_nn, bitmap_02_line_nn, bitmap_03_line_nn, bitmap_04_line_nn,
]
```

**Note**: 32 null bytes must be inserted after the first 16 bytes of the body.

### USB HID (B1248)

The badge takes 14 HID reports of 64 bytes each (each sent with a leading report ID of `0x00`), zero-padded:

1. `Hello`
2. Slot configuration: `0x00`, the mode byte of each of the 8 slots (same layout as the serial header), `0x00`, then for each slot `0x08`, column offset, `0x00`, number of columns.
3. One report per line (11 in all): the bytes of that line for every slot, side by side, in the same 8-pixels-per-byte format as the serial body. This is why all slots together are limited to 64 columns.
4. An all-zero report.

See [cat-in-136's write-up](https://cat-in-136.github.io/2020/07/b1248-led-name-badge-protocol-reverse-engineering.html) for the reverse-engineering details.

## Maintainers

- [Juan Denzer](https://github.com/jpdenzer) (this fork)

## Thanks

- [Amane Katagiri](https://github.com/amane-katagiri): original author of [m1-8-writer](https://github.com/amane-katagiri/m1-8-writer) and of the M1-8 protocol work.
- [cat-in-136](https://github.com/cat-in-136): [B1248 protocol reverse engineering](https://cat-in-136.github.io/2020/07/b1248-led-name-badge-protocol-reverse-engineering.html) and [led-name-badge](https://github.com/cat-in-136/led-name-badge).
- [Dave Akerman](http://www.daveakerman.com/?p=1440): early notes on these badges.

## Contributing

Issues and pull requests are welcome at [jpdenzer/led-badge-writer](https://github.com/jpdenzer/led-badge-writer/issues).

The code includes small built-in examples that double as tests. Run them with:

```
python3 -c "import doctest, m18writer.writer as w, m18writer.fonts as f; print(doctest.testmod(w), doctest.testmod(f))"
```

## License

[MIT](LICENSE) © 2020 Amane Katagiri, © 2026 Juan Denzer
