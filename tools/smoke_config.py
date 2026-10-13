from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from hopline.models import Node
from hopline.singbox import build_config


nodes = [
    Node(
        id="node-a",
        protocol="vless",
        server="edge-a.example.test",
        port=443,
        uuid="00000000-0000-4000-8000-000000000001",
        tls=True,
        sni="edge-a.example.test",
        transport_type="ws",
        path="/a",
        host="edge-a.example.test",
    )
]
config = build_config(nodes, listen_port=18971, credentials={"node-a": "fixture-secret"})
with tempfile.TemporaryDirectory(prefix="hopline-config-smoke-") as directory:
    path = Path(directory) / "config.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    result = subprocess.run(["sing-box", "check", "-c", str(path)], check=False)
    if result.returncode:
        raise SystemExit(result.returncode)
    print("config-generator=passed sing-box-check=passed secret=fixture-only")
