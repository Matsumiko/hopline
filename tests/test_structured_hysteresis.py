import json
import unittest

from hopline.registry import SQLiteRegistry
from hopline.syncer import Syncer


VLESS = "vless://00000000-0000-4000-8000-000000000021@a.example.test:443?security=tls&sni=a.example.test&type=ws&path=%2Fa#A"


class StructuredHysteresisTests(unittest.TestCase):
    def test_singbox_json_outbounds_are_parsed(self) -> None:
        body = json.dumps({
            "outbounds": [
                {
                    "type": "vless",
                    "tag": "json-a",
                    "server": "a.example.test",
                    "server_port": 443,
                    "uuid": "00000000-0000-4000-8000-000000000021",
                    "tls": {"enabled": True, "server_name": "a.example.test"},
                    "transport": {"type": "ws", "path": "/a", "headers": {"Host": "a.example.test"}},
                },
                {"type": "direct", "tag": "ignored"},
            ]
        }).encode()
        result = Syncer(SQLiteRegistry(":memory:")).sync_text("json", body)
        self.assertEqual(result.parsed_nodes, 1)
        self.assertEqual(result.invalid_entries, 0)

    def test_clash_yaml_proxies_are_parsed(self) -> None:
        body = b"""proxies:\n  - name: yaml-a\n    type: trojan\n    server: a.example.test\n    port: 443\n    password: 00000000-0000-4000-8000-000000000022\n    sni: a.example.test\n    network: ws\n    ws-opts:\n      path: /a\n      headers:\n        Host: a.example.test\n"""
        result = Syncer(SQLiteRegistry(":memory:")).sync_text("yaml", body)
        self.assertEqual(result.parsed_nodes, 1)
        self.assertEqual(result.invalid_entries, 0)

    def test_node_is_removed_after_three_missing_snapshots(self) -> None:
        registry = SQLiteRegistry(":memory:")
        syncer = Syncer(registry)
        syncer.sync_text("source", VLESS.encode())
        for attempt in (1, 2):
            result = syncer.sync_text("source", b"invalid")
            self.assertFalse(result.changed)
            self.assertEqual(len(registry.list_nodes()), 1, attempt)
        result = syncer.sync_text("source", b"invalid")
        self.assertTrue(result.used_last_valid)
        self.assertEqual(len(registry.list_nodes()), 1)
        registry.replace_subscription("source", "empty", [])
        registry.replace_subscription("source", "empty", [])
        registry.replace_subscription("source", "empty", [])
        self.assertEqual(registry.list_nodes(), [])


if __name__ == "__main__":
    unittest.main()
