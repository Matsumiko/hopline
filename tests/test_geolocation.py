import unittest

from hopline.geolocation import GeolocationResolver, GeoLookupError, GeoResult, default_providers, fetch_exit_ip, is_fresh
from hopline.models import Node
from hopline.registry import SQLiteRegistry


IP = "104.28.156.33"


class GeolocationTests(unittest.TestCase):
    def test_checkip_response_is_normalized(self) -> None:
        payload = {
            "code": "OK",
            "data": {
                "ip": IP,
                "country_code": "ca",
                "ip_location": "Canada,Ontario,Toronto",
                "asn": "AS13335",
                "organization": "Cloudflare",
            },
        }
        result = GeolocationResolver(fetch=lambda _url, _headers: payload, clock=lambda: 123.0).resolve(IP)
        self.assertEqual((result.ip, result.country_code, result.provider), (IP, "CA", "checkip"))
        self.assertEqual(result.country, "Canada,Ontario,Toronto")
        self.assertEqual(result.checked_at, 123.0)

    def test_falls_back_to_ipcc_after_checkip_failure(self) -> None:
        calls: list[str] = []
        responses = [
            {"code": "RATE_LIMIT", "data": {}},
            {
                "code": 200,
                "msg": "SUCCESS",
                "data": {
                    "geolocation": {"ip": IP, "country_code": "FR", "country": "France", "organization": "Example"},
                    "asn": {"asn": "AS64500"},
                },
            },
        ]

        def fetch(url: str, _headers: tuple[tuple[str, str], ...]) -> dict:
            calls.append(url)
            return responses.pop(0)

        result = GeolocationResolver(fetch=fetch).resolve(IP)
        self.assertEqual(result.provider, "ipcc")
        self.assertEqual(result.country_code, "FR")
        self.assertEqual(len(calls), 2)

    def test_falls_back_to_cekipsaya_lookup_with_referer(self) -> None:
        calls: list[tuple[str, tuple[tuple[str, str], ...]]] = []

        def fetch(url: str, headers: tuple[tuple[str, str], ...]) -> dict:
            calls.append((url, headers))
            if "checkip.com" in url or "ip.cc" in url:
                raise OSError("provider unavailable")
            return {"ip": IP, "country": "Poland (PL)", "asn": "AS13335", "org": "Cloudflare, Inc."}

        result = GeolocationResolver(fetch=fetch).resolve(IP)
        self.assertEqual((result.provider, result.country_code, result.country), ("cekipsaya", "PL", "Poland (PL)"))
        self.assertIn(("Referer", "https://cekipsaya.com/cek-ip-saya/"), calls[-1][1])
        self.assertIn("action=lookup", calls[-1][0])
        self.assertIn("target=104.28.156.33", calls[-1][0])

    def test_falls_back_to_ipwho_after_other_providers_fail(self) -> None:
        def fetch(url: str, _headers: tuple[tuple[str, str], ...]) -> dict:
            if "ipwho.is" not in url:
                raise OSError("provider unavailable")
            return {
                "success": True,
                "ip": IP,
                "country_code": "DE",
                "country": "Germany",
                "connection": {"asn": 3320, "org": "Example ISP"},
            }

        result = GeolocationResolver(fetch=fetch).resolve(IP)
        self.assertEqual((result.provider, result.country_code, result.country), ("ipwho", "DE", "Germany"))

    def test_fetch_exit_ip_uses_node_route_credentials(self) -> None:
        captured: list[tuple[str, str, float]] = []

        def fetch(url: str, proxy: str, timeout: float) -> bytes:
            captured.append((url, proxy, timeout))
            return b'{"ip":"203.0.113.8"}'

        ip = fetch_exit_ip(
            proxy_host="127.0.0.1",
            proxy_port=18770,
            proxy_username="node-a",
            proxy_password="local-secret",
            target_url="https://api.example.test/ip?format=json",
            timeout=4,
            fetch=fetch,
        )
        self.assertEqual(ip, "203.0.113.8")
        self.assertEqual(captured[0][0], "https://api.example.test/ip?format=json")
        self.assertIn("node-a", captured[0][1])
        self.assertIn("local-secret", captured[0][1])

    def test_fetch_exit_ip_rejects_invalid_response_without_secret_in_error(self) -> None:
        def fetch(_url: str, _proxy: str, _timeout: float) -> bytes:
            return b"not-an-ip"

        with self.assertRaises(GeoLookupError) as raised:
            fetch_exit_ip(
                proxy_host="127.0.0.1",
                proxy_port=18770,
                proxy_username="node-a",
                proxy_password="local-secret",
                fetch=fetch,
            )
        self.assertNotIn("local-secret", str(raised.exception))

    def test_registry_persists_only_non_secret_geolocation_metadata(self) -> None:
        registry = SQLiteRegistry(":memory:")
        registry.replace_subscription("fixture", "hash", [Node("node-a", "vless", "relay.test", 443, "secret-uuid")])
        registry.save_geolocation(
            "node-a",
            GeoResult(IP, "PL", "Poland (PL)", "AS13335", "Cloudflare, Inc.", "cekipsaya", 42.0),
        )
        record = registry.geolocation_record("node-a")
        self.assertEqual(record["country_code"], "PL")
        self.assertEqual(record["provider"], "cekipsaya")
        self.assertNotIn("secret-uuid", dict(record).values())
        registry.close()

    def test_freshness_rejects_expired_and_future_results(self) -> None:
        result = GeoResult(IP, "ID", "Indonesia", None, None, "checkip", 100.0)
        self.assertTrue(is_fresh(result, now=159.0, max_age=60.0))
        self.assertFalse(is_fresh(result, now=160.1, max_age=60.0))
        self.assertFalse(is_fresh(result, now=99.0, max_age=60.0))

    def test_rejects_mismatched_provider_ip(self) -> None:
        with self.assertRaises(GeoLookupError):
            GeolocationResolver(
                providers=(default_providers()[0],),
                fetch=lambda _url, _headers: {"code": "OK", "data": {"ip": "1.1.1.1", "country_code": "US"}},
            ).resolve(IP)

    def test_does_not_include_input_or_credentials_in_failure(self) -> None:
        with self.assertRaises(GeoLookupError) as raised:
            GeolocationResolver(
                providers=(default_providers()[0],),
                fetch=lambda _url, _headers: {"code": "NO", "message": "bad"},
            ).resolve(IP)
        self.assertNotIn(IP, str(raised.exception))
        self.assertNotIn("password", str(raised.exception).lower())


if __name__ == "__main__":
    unittest.main()
