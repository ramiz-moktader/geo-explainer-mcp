"""Stand-in XYZ tile server for offline tests: `python tests/fake_tile_server.py PORT [delay_s] [stall_pct]`.

Serves generated 256x256 "terrain" PNGs. `delay_s` simulates network latency per tile and
`stall_pct` makes that share of requests hang for 25 s, like a throttled connection.
"""
import random
import struct
import sys
import time
import zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np

DELAY = float(sys.argv[2]) if len(sys.argv) > 2 else 0.0
STALL = float(sys.argv[3]) if len(sys.argv) > 3 else 0.0


def png(z: int, x: int, y: int) -> bytes:
    rng = np.random.default_rng(z * 1_000_003 + x * 1009 + y)
    yy, xx = np.mgrid[0:256, 0:256]
    base = np.array([40 + (x * 53) % 90, 70 + (y * 37) % 90, 50 + (z * 29) % 80])
    img = base[None, None, :] + (np.sin(xx / 17 + x) * 18 + np.cos(yy / 23 + y) * 18)[..., None]
    img = np.clip(img + rng.normal(0, 14, (256, 256, 3)), 0, 255).astype(np.uint8)
    img[0, :, :] = img[:, 0, :] = 255  # tile edges, to see seams and missing tiles
    raw = b"".join(b"\x00" + img[r].tobytes() for r in range(256))

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 256, 256, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 1)) + chunk(b"IEND", b""))


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self):  # noqa: N802
        z, x, y = (int(p) for p in self.path.split("?")[0].strip("/").split("/")[:3])
        time.sleep(25 if random.random() * 100 < STALL else DELAY)
        data = png(z, x, y)
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    srv = ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), H)
    srv.daemon_threads = True
    srv.serve_forever()
