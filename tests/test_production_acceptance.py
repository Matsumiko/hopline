import json
import unittest
from types import SimpleNamespace

from hopline.health import HealthState
from hopline.models import Node
from tools.production_acceptance import public_result, select_healthy_samples


class ProductionAcceptanceTests(unittest.TestCase):
    def test_selects_only_healthy_nodes_with_protocol_cap(self) -> None:
        nodes = [
            Node("ss-1", "ss", "ss.example", 443, "ss-secret"),
            Node("ss-2", "ss", "ss2.example", 443, "ss-secret-2"),
            Node("vless-1", "vless", "vless.example", 443, "vless-secret"),
            Node("vmess-1", "vmess", "vmess.example", 443, "vmess-secret"),
            Node("trojan-1", "trojan", "trojan.example", 443, "trojan-secret"),
        ]
        health = {
            "ss-1": SimpleNamespace(state=HealthState.HEALTHY),
            "ss-2": SimpleNamespace(state=HealthState.DEAD),
            "vless-1": SimpleNamespace(state=HealthState.HEALTHY),
            "vmess-1": SimpleNamespace(state=HealthState.DEGRADED),
            "trojan-1": SimpleNamespace(state=HealthState.HEALTHY),
        }

        selected = select_healthy_samples(nodes, health, 1)

        self.assertEqual([node.id for node in selected["shadowsocks"]], ["ss-1"])
        self.assertEqual([node.id for node in selected["vless"]], ["vless-1"])
        self.assertEqual([node.id for node in selected["trojan"]], ["trojan-1"])
        self.assertEqual(selected["vmess"], [])

    def test_public_result_redacts_connection_parameters(self) -> None:
        result = SimpleNamespace(
            protocol="vless",
            node_id="node-1",
            status=200,
            exit_ip="203.0.113.8",
            latency_ms=42.5,
            success=True,
            error=None,
        )

        encoded = json.dumps(public_result(result), sort_keys=True)

        self.assertIn("node-1", encoded)
        self.assertIn("203.0.113.8", encoded)
        self.assertNotIn("secret", encoded)
        self.assertNotIn("example", encoded)
        self.assertNotIn("443", encoded)


if __name__ == "__main__":
    unittest.main()
