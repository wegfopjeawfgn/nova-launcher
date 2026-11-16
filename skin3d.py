"""A small orthographic 3D view of a Minecraft skin: turns the texture into coloured quads, far to near."""
import math

import skinlib

SIZE = skinlib.SIZE
# per face: normal, then how a texel (col, row) of the face maps onto the box: (origin corner, col step, row step)
_LIGHT = (-0.35, -0.6, 0.72)


def _box_faces(x0, y0, z0, x1, y1, z1):
    """Corners/axes of the six faces of a box. Each: (normal, origin, col_axis, row_axis) in model space."""
    w, h, d = x1 - x0, y1 - y0, z1 - z0
    return (
        ((0, 0, 1), (x0, y0, z1), (w, 0, 0), (0, h, 0)),      # front: col -> +x
        ((1, 0, 0), (x1, y0, z1), (0, 0, -d), (0, h, 0)),     # player's left: col 0 at the front edge
        ((0, 0, -1), (x1, y0, z0), (-w, 0, 0), (0, h, 0)),    # back: col 0 at the player's left
        ((-1, 0, 0), (x0, y0, z0), (0, 0, d), (0, h, 0)),     # player's right: col 0 at the back edge
        ((0, -1, 0), (x0, y0, z0), (w, 0, 0), (0, 0, d)),     # top: row 0 at the back
        ((0, 1, 0), (x0, y1, z1), (w, 0, 0), (0, 0, -d)),     # bottom: row 0 at the front
    )


def _rotate(point, yaw, pitch):
    x, y, z = point
    x, z = x * math.cos(yaw) + z * math.sin(yaw), -x * math.sin(yaw) + z * math.cos(yaw)
    y, z = y * math.cos(pitch) - z * math.sin(pitch), y * math.sin(pitch) + z * math.cos(pitch)
    return x, y, z


def _shade(normal, yaw, pitch):
    nx, ny, nz = _rotate(normal, yaw, pitch)
    dot = max(0.0, -(nx * _LIGHT[0] + ny * _LIGHT[1] + nz * _LIGHT[2]) / math.sqrt(sum(c * c for c in _LIGHT)))
    return 0.72 + 0.28 * dot, nz


def part_box(part, slim, grow):
    u, v, w, h, d, x, y = skinlib.PARTS[part]
    if slim and part in (2, 3):
        w = 3
        if part == 2:
            x += 1
    return x - grow, y - grow, -d / 2 - grow, x + w + grow, y + h + grow, d / 2 + grow


def scene(pixels, yaw=0.5, pitch=0.18, slim=False):
    """Quads to draw, far to near: [(points[(x, y)] * 4, (r, g, b, a))] in model pixels, centred on the body."""
    quads = []
    order = []
    for part in range(len(skinlib.PARTS)):
        box = part_box(part, slim, 0)
        centre = _rotate(((box[0] + box[3]) / 2, (box[1] + box[4]) / 2 - 16, 0), yaw, pitch)
        order.append((centre[2], part))
    for _, part in sorted(order):
        for overlay, grow in ((False, 0.0), (True, 0.45)):
            x0, y0, z0, x1, y1, z1 = part_box(part, slim, grow)
            for side, (normal, origin, col_axis, row_axis) in enumerate(_box_faces(x0, y0, z0, x1, y1, z1)):
                brightness, facing = _shade(normal, yaw, pitch)
                if facing <= 0.001:
                    continue
                u, v, w, h = skinlib.face(part, side, slim, overlay)
                for row in range(h):
                    for col in range(w):
                        index = ((v + row) * SIZE + u + col) * 4
                        red, green, blue, alpha = pixels[index:index + 4]
                        if not alpha:
                            continue
                        corners = []
                        for dc, dr in ((0, 0), (1, 0), (1, 1), (0, 1)):
                            fc, fr = (col + dc) / w, (row + dr) / h
                            p = tuple(origin[i] + col_axis[i] * fc + row_axis[i] * fr for i in range(3))
                            px, py, _ = _rotate((p[0], p[1] - 16, p[2]), yaw, pitch)
                            corners.append((px, py))
                        quads.append((corners, (red / 255 * brightness, green / 255 * brightness,
                                                blue / 255 * brightness, alpha / 255)))
    return quads
