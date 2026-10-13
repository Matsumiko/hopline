import unittest

from hopline.models import Node
from hopline.parser import parse_vless
from hopline.singbox import build_config


VLESS = (
    "vless://00000000-0000-4000-8000-000000000003@edge.example.test:443"
    "?security=tls&sni=edge.example.test&type=ws&path=%2Fedge&host=edge.example.test"
    "#Japan%20edge"
)


class ParserConfigTests(unittest.TestCase):
    def test_parse_vless_preserves_transport_and_stable_id(self) -> None:
        node = parse_vless(VLESS, source="fixture")
        self.assertEqual(node.uuid, "00000000-0000-4000-8000-000000000003")
        self.assertEqual(node.protocol, "vless")
        self.assertEqual(node.server, "edge.example.test")
        self.assertEqual(node.port, 443)
        self.assertEqual(node.sni, "edge.example.test")
        self.assertEqual(node.path, "/edge")
        self.assertEqual(node.host, "edge.example.test")
        self.assertEqual(node.name, "Japan edge")
        self.assertEqual(len(node.id), 12)
        self.assertEqual(node.id, parse_vless(VLESS, source="other").id)

    def test_config_routes_each_auth_user_to_its_node(self) -> None:
        nodes = [
            Node(
                id="node-a",
                protocol="vless",
                server="a.example.test",
                port=443,
                uuid="00000000-0000-4000-8000-000000000001",
                tls=True,
                sni="a.example.test",
                transport_type="ws",
                path="/a",
                host="a.example.test",
            ),
            Node(
                id="node-b",
                protocol="vless",
                server="b.example.test",
                port=443,
                uuid="00000000-0000-4000-8000-000000000002",
                tls=True,
                sni="b.example.test",
                transport_type="ws",
                path="/b",
                host="b.example.test",
            ),
        ]

        config = build_config(
            nodes,
            listen_port=18771,
            credentials={"node-a": "secret-a", "node-b": "secret-b"},
        )

        self.assertEqual(config["inbounds"][0]["listen_port"], 18771)
        self.assertEqual(
            {user["username"] for user in config["inbounds"][0]["users"]},
            {"node-a", "node-b"},
        )
        routes = {
            rule["auth_user"][0]: rule["outbound"]
            for rule in config["route"]["rules"]
        }
        self.assertEqual(routes, {"node-a": "node-a", "node-b": "node-b"})
        self.assertEqual(config["outbounds"][0]["tag"], "node-a")
        self.assertEqual(config["outbounds"][1]["tag"], "node-b")


if __name__ == "__main__":
    unittest.main()
