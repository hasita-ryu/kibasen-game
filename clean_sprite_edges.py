import struct
import sys
import zlib
from pathlib import Path

PNG_SIG = b"\x89PNG\r\n\x1a\n"


def read_chunks(data):
    pos = len(PNG_SIG)
    chunks = []
    while pos < len(data):
        size = struct.unpack(">I", data[pos : pos + 4])[0]
        kind = data[pos + 4 : pos + 8]
        payload = data[pos + 8 : pos + 8 + size]
        chunks.append((kind, payload))
        pos += 12 + size
    return chunks


def unfilter_scanlines(raw, width, height, channels):
    stride = width * channels
    rows = []
    pos = 0
    previous = [0] * stride

    for _ in range(height):
        filter_type = raw[pos]
        pos += 1
        row = list(raw[pos : pos + stride])
        pos += stride

        for i in range(stride):
            left = row[i - channels] if i >= channels else 0
            up = previous[i]
            up_left = previous[i - channels] if i >= channels else 0

            if filter_type == 1:
                row[i] = (row[i] + left) & 255
            elif filter_type == 2:
                row[i] = (row[i] + up) & 255
            elif filter_type == 3:
                row[i] = (row[i] + ((left + up) // 2)) & 255
            elif filter_type == 4:
                p = left + up - up_left
                pa = abs(p - left)
                pb = abs(p - up)
                pc = abs(p - up_left)
                predictor = left if pa <= pb and pa <= pc else up if pb <= pc else up_left
                row[i] = (row[i] + predictor) & 255

        rows.append(row)
        previous = row

    return rows


def write_png(path, width, height, rgba_rows):
    def chunk(kind, payload):
        return (
            struct.pack(">I", len(payload))
            + kind
            + payload
            + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
        )

    raw = bytearray()
    for row in rgba_rows:
        raw.append(0)
        raw.extend(row)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    data = PNG_SIG
    data += chunk(b"IHDR", ihdr)
    data += chunk(b"IDAT", zlib.compress(bytes(raw), 9))
    data += chunk(b"IEND", b"")
    path.write_bytes(data)


def removable_bg(r, g, b, a, aggressive=False):
    if a < 8:
        return True
    brightest = max(r, g, b)
    darkest = min(r, g, b)
    if aggressive:
        return (darkest > 85 and brightest - darkest < 135) or (r > 165 and g > 165 and b > 165)
    return (darkest > 145 and brightest - darkest < 75) or (r > 210 and g > 210 and b > 210)


def load_png(path):
    data = path.read_bytes()
    if not data.startswith(PNG_SIG):
        raise ValueError(f"{path} is not a PNG")

    chunks = read_chunks(data)
    ihdr = next(payload for kind, payload in chunks if kind == b"IHDR")
    width, height, bit_depth, color_type, _, _, interlace = struct.unpack(">IIBBBBB", ihdr)
    if bit_depth != 8 or interlace != 0 or color_type not in (2, 6):
        raise ValueError(f"{path} must be 8-bit RGB or RGBA non-interlaced PNG")

    channels = 4 if color_type == 6 else 3
    compressed = b"".join(payload for kind, payload in chunks if kind == b"IDAT")
    rows = unfilter_scanlines(zlib.decompress(compressed), width, height, channels)

    rgba = []
    for row in rows:
        out = []
        for x in range(width):
            base = x * channels
            r, g, b = row[base], row[base + 1], row[base + 2]
            a = row[base + 3] if channels == 4 else 255
            out.extend((r, g, b, a))
        rgba.append(out)

    return width, height, rgba


def clean(path):
    width, height, rows = load_png(path)
    transparent = [[False] * width for _ in range(height)]
    queue = []

    for x in range(width):
        queue.append((x, 0))
        queue.append((x, height - 1))
    for y in range(height):
        queue.append((0, y))
        queue.append((width - 1, y))

    while queue:
        x, y = queue.pop()
        if x < 0 or y < 0 or x >= width or y >= height or transparent[y][x]:
            continue

        base = x * 4
        r, g, b, a = rows[y][base : base + 4]
        if not removable_bg(r, g, b, a):
            continue

        transparent[y][x] = True
        rows[y][base + 3] = 0
        queue.extend(((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)))

    for _ in range(14):
        to_clear = []
        for y in range(1, height - 1):
            for x in range(1, width - 1):
                base = x * 4
                r, g, b, a = rows[y][base : base + 4]
                if a == 0 or not removable_bg(r, g, b, a, aggressive=True):
                    continue
                if (
                    rows[y][(x - 1) * 4 + 3] == 0
                    or rows[y][(x + 1) * 4 + 3] == 0
                    or rows[y - 1][base + 3] == 0
                    or rows[y + 1][base + 3] == 0
                ):
                    to_clear.append((x, y))

        for x, y in to_clear:
            rows[y][x * 4 + 3] = 0

    # Final hard pass: any pale/gray pixel close to transparency is almost
    # certainly checkerboard residue from the generator export.
    for _ in range(4):
        to_clear = []
        for y in range(2, height - 2):
            for x in range(2, width - 2):
                base = x * 4
                r, g, b, a = rows[y][base : base + 4]
                if a == 0:
                    continue

                close_to_alpha = False
                for dy in range(-2, 3):
                    for dx in range(-2, 3):
                        if rows[y + dy][(x + dx) * 4 + 3] == 0:
                            close_to_alpha = True
                            break
                    if close_to_alpha:
                        break

                brightest = max(r, g, b)
                darkest = min(r, g, b)
                pale_or_gray = (darkest > 75 and brightest - darkest < 150) or (r > 150 and g > 150 and b > 150)
                if close_to_alpha and pale_or_gray:
                    to_clear.append((x, y))

        for x, y in to_clear:
            rows[y][x * 4 + 3] = 0

    write_png(path, width, height, rows)


if __name__ == "__main__":
    for file_name in sys.argv[1:]:
        clean(Path(file_name))
        print(f"cleaned {file_name}")
