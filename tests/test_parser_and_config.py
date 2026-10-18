import unittest

from hopline.models import Node
from hopline.parser import parse_share_link, parse_vless
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
    def test_trojan_preserves_non_uuid_password(self) -> None:
        node = parse_share_link(
            "trojan://provider-password@edge.example.test:443"
            "?security=tls&type=ws&path=%2Fedge&sni=edge.example.test"
        )
        self.assertEqual(node.uuid, "provider-password")
        self.assertEqual(build_config([node], listen_port=18771)["outbounds"][0]["password"], "provider-password")
    def test_vless_and_vmess_transport_metadata_reaches_singbox(self) -> None:
        vless = parse_vless(
            "vless://00000000-0000-4000-8000-000000000004@edge.example.test:443"
            "?security=tls&sni=edge.example.test&type=ws&path=%2Fedge&host=edge.example.test"
            "&packet_encoding=xudp&flow=xtls-rprx-vision#VLESS"
        )
        vmess = parse_share_link(
            "vmess://00000000-0000-4000-8000-000000000005@edge.example.test:443"
            "?security=tls&sni=edge.example.test&type=ws&path=%2Fedge&host=edge.example.test"
            "&aid=7#VMess"
        )
        self.assertEqual(vless.packet_encoding, "xudp")
        self.assertEqual(vless.flow, "xtls-rprx-vision")
        self.assertEqual(vmess.alter_id, 7)
        config = build_config([vless, vmess], listen_port=18771)
        outbounds = {item["tag"]: item for item in config["outbounds"]}
        self.assertEqual(outbounds[vless.id]["packet_encoding"], "xudp")
        self.assertEqual(outbounds[vless.id]["flow"], "xtls-rprx-vision")
        self.assertEqual(outbounds[vmess.id]["alter_id"], 7)

    def test_transport_metadata_survives_registry_roundtrip(self) -> None:
        from hopline.registry import SQLiteRegistry

        node = parse_vless(
            "vless://00000000-0000-4000-8000-000000000006@edge.example.test:443"
            "?security=tls&type=ws&packet_encoding=xudp&flow=vision"
        )
        registry = SQLiteRegistry(":memory:")
        registry.replace_subscription("fixture", "hash", [node])
        restored = registry.list_nodes()[0]
        self.assertEqual(restored.packet_encoding, "xudp")
        self.assertEqual(restored.flow, "vision")
        registry.close()

    def test_reality_grpc_and_flow_match_nekobox_mapping(self) -> None:
        link = (
            "vless://00000000-0000-4000-8000-000000000007@edge.example.test:443"
            "?security=reality&sni=real.example.test&pbk=public-key&sid=abcd"
            "&fp=chrome&alpn=h2%2Chttp%2F1.1&type=grpc&serviceName=edge"
            "&flow=xtls-rprx-vision-udp443#Reality"
        )
        node = parse_vless(link)
        self.assertTrue(node.tls)
        self.assertEqual(node.transport_type, "grpc")
        self.assertEqual(node.service_name, "edge")
        self.assertEqual(node.flow, "xtls-rprx-vision-udp443")
        outbound = build_config([node], listen_port=18771)["outbounds"][0]
        self.assertEqual(outbound["packet_encoding"], "xudp")
        self.assertEqual(outbound["flow"], "xtls-rprx-vision")
        self.assertEqual(outbound["transport"], {"type": "grpc", "service_name": "edge"})
        self.assertEqual(outbound["tls"]["reality"], {"enabled": True, "public_key": "public-key", "short_id": "abcd"})
        self.assertEqual(outbound["tls"]["utls"], {"enabled": True, "fingerprint": "chrome"})
        self.assertEqual(outbound["tls"]["alpn"], ["h2", "http/1.1"])

    def test_unsupported_fingerprint_is_normalized_for_singbox(self) -> None:
        plain = parse_vless(
            "vless://00000000-0000-4000-8000-0000000000a1@edge.example.test:443"
            "?security=tls&sni=edge.example.test&fp=unsafe"
        )
        plain_outbound = build_config([plain], listen_port=18771)["outbounds"][0]
        self.assertNotIn("utls", plain_outbound["tls"])
        reality = parse_vless(
            "vless://00000000-0000-4000-8000-0000000000a2@edge.example.test:443"
            "?security=reality&sni=real.example.test&pbk=public-key&sid=abcd&fp=unsafe"
        )
        reality_outbound = build_config([reality], listen_port=18771)["outbounds"][0]
        self.assertEqual(reality_outbound["tls"]["utls"], {"enabled": True, "fingerprint": "chrome"})
        supported = parse_vless(
            "vless://00000000-0000-4000-8000-0000000000a3@edge.example.test:443"
            "?security=tls&sni=edge.example.test&fp=FireFox"
        )
        supported_outbound = build_config([supported], listen_port=18771)["outbounds"][0]
        self.assertEqual(supported_outbound["tls"]["utls"], {"enabled": True, "fingerprint": "firefox"})

    def test_websocket_early_data_and_h2_mapping(self) -> None:
        node = parse_share_link(
            "vmess://00000000-0000-4000-8000-000000000008@edge.example.test:443"
            "?security=tls&type=h2&path=%2Fsocket%3Fed%3D2048&host=edge.example.test"
        )
        self.assertEqual(node.transport_type, "http")
        outbound = build_config([node], listen_port=18771)["outbounds"][0]
        self.assertEqual(outbound["transport"]["type"], "http")
        self.assertEqual(outbound["transport"]["path"], "/socket?ed=2048")


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
            if "auth_user" in rule
        }
        self.assertEqual(routes, {"node-a": "node-a", "node-b": "node-b"})
        self.assertEqual(config["outbounds"][0]["tag"], "node-a")
        self.assertEqual(config["outbounds"][1]["tag"], "node-b")

    def test_config_routes_node_domains_direct_and_uses_remote_dns(self) -> None:
        nodes = [
            parse_vless(
                "vless://00000000-0000-4000-8000-000000000033@relay-a.example.test:443"
                "?security=tls&type=ws&path=%2Fnode-a&host=relay-a.example.test"
            ),
            parse_vless(
                "vless://00000000-0000-4000-8000-000000000034@relay-b.example.test:443"
                "?security=tls&type=ws&path=%2Fnode-b&host=relay-b.example.test"
            ),
        ]
        config = build_config(
            nodes,
            listen_port=18771,
            credentials={nodes[0].id: "secret-a", nodes[1].id: "secret-b"},
        )

        self.assertEqual(config["dns"]["final"], "dns-direct")
        self.assertEqual(
            config["dns"]["servers"],
            [
                {
                    "type": "tls",
                    "tag": f"dns-remote-{nodes[0].id}",
                    "server": "8.8.8.8",
                    "detour": nodes[0].id,
                    "domain_resolver": "dns-direct",
                },
                {
                    "type": "tls",
                    "tag": f"dns-remote-{nodes[1].id}",
                    "server": "8.8.8.8",
                    "detour": nodes[1].id,
                    "domain_resolver": "dns-direct",
                },
                {"type": "local", "tag": "dns-direct"},
            ],
        )
        self.assertEqual(
            config["dns"]["rules"],
            [
                {
                    "action": "route",
                    "domain": ["relay-a.example.test", "relay-b.example.test"],
                    "server": "dns-direct",
                },
                {"auth_user": [nodes[0].id], "server": f"dns-remote-{nodes[0].id}"},
                {"auth_user": [nodes[1].id], "server": f"dns-remote-{nodes[1].id}"},
            ],
        )
        self.assertEqual(config["route"]["default_domain_resolver"], "dns-direct")
        self.assertEqual(
            config["inbounds"][0]["users"],
            [
                {"username": nodes[0].id, "password": "secret-a"},
                {"username": nodes[1].id, "password": "secret-b"},
            ],
        )
        auth_routes = [rule for rule in config["route"]["rules"] if "auth_user" in rule]
        self.assertEqual(
            auth_routes,
            [
                {"inbound": ["mixed-in"], "auth_user": [nodes[0].id], "outbound": nodes[0].id},
                {"inbound": ["mixed-in"], "auth_user": [nodes[1].id], "outbound": nodes[1].id},
            ],
        )

    def test_config_resolves_relay_domains_locally_without_remote_dns_loop(self) -> None:
        node = parse_vless(
            "vless://00000000-0000-4000-8000-000000000033@relay.example.test:443"
            "?security=tls&type=ws&path=%2Fnode&host=relay.example.test"
        )
        config = build_config([node], listen_port=18771)
        self.assertEqual(config["dns"]["final"], "dns-direct")
        self.assertEqual(config["dns"]["rules"][0]["server"], "dns-direct")
        self.assertEqual(config["dns"]["rules"][1], {"auth_user": [node.id], "server": f"dns-remote-{node.id}"})
        self.assertEqual(config["outbounds"][0]["domain_resolver"], "dns-direct")
        self.assertEqual(config["route"]["default_domain_resolver"], "dns-direct")

    def test_shadowsocks_v2ray_plugin_is_preserved_for_singbox(self) -> None:
        link = (
            "ss://bm9uZTphMGJlZGNkOS01OTQ4LTQzNzItODlkNy05MTlkNTJkYmRmOTM="
            "@relay.example.test:443"
            "?plugin=v2ray-plugin%3Btls%3Bmux%3D0%3Bmode%3Dwebsocket%3Bpath%3D%2F185.82.218.224-443"
            "%3Bhost%3Drelay.example.test"
        )
        node = parse_share_link(link)
        self.assertEqual(node.plugin, "v2ray-plugin")
        self.assertEqual(
            node.plugin_opts,
            "tls;mux=0;mode=websocket;path=/185.82.218.224-443;host=relay.example.test",
        )
        outbound = build_config([node], listen_port=18771)["outbounds"][0]
        self.assertEqual(outbound["plugin"], "v2ray-plugin")
        self.assertEqual(outbound["plugin_opts"], node.plugin_opts)

if __name__ == "__main__":
    unittest.main()
