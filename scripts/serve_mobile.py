"""
scripts/serve_mobile.py

Lightweight static server for browsing exports/mobile_viewer on smartphones over local Wi-Fi.
"""

import http.server
import socket
import socketserver
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
TARGET_DIR = ROOT_DIR / "exports" / "mobile_viewer"


def get_local_ip() -> str:
    """Find local network IP."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 1))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


def run_server(port: int = 8080) -> None:
    """Serve exports/mobile_viewer directory on port."""
    if not TARGET_DIR.exists():
        print(f"Error: {TARGET_DIR} does not exist. Please run scripts/generate_mobile_viewer.py first.")
        sys.exit(1)

    ip = get_local_ip()
    handler = http.server.SimpleHTTPRequestHandler

    class CustomHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(TARGET_DIR), **kwargs)

    print("\n" + "=" * 65)
    print(" [MOBILE VIEWER SERVER STARTED]")
    print(f" Document Root: {TARGET_DIR}")
    print("=" * 65)
    print(f" PC Browser:     http://localhost:{port}")
    print(f" Smartphone URL: http://{ip}:{port}")
    print(f" (Ensure your smartphone is connected to the same Wi-Fi)")
    print("=" * 65 + "\n")

    try:
        with socketserver.TCPServer(("0.0.0.0", port), CustomHandler) as httpd:
            httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")


if __name__ == "__main__":
    port_arg = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    run_server(port=port_arg)
