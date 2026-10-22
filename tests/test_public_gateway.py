import stat
import tempfile
import unittest
from pathlib import Path

from hopline.cli import _loopback
from hopline.config import HoplineConfig


def _write(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    return path


class PublicGatewayConfigTests(unittest.TestCase):
    def test_gateway_may_bind_publicly(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = _write(
                Path(directory) / "c.toml",
                'static_nodes = ["vless://00000000-0000-4000-8000-000000000001@h.test:443"]\n'
                '[hopline]\ngateway_host = "0.0.0.0"\n[auth]\npassword = "x"\n',
            )
            config = HoplineConfig.from_file(path)
            self.assertEqual(config.gateway_host, "0.0.0.0")

    def test_metrics_and_control_stay_localhost_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = _write(
                Path(directory) / "c.toml",
                'static_nodes = ["vless://00000000-0000-4000-8000-000000000001@h.test:443"]\n'
                '[hopline]\ngateway_host = "0.0.0.0"\n[auth]\npassword = "x"\n'
                '[health]\nmetrics_enabled = true\nmetrics_host = "0.0.0.0"\n',
            )
            with self.assertRaises(ValueError):
                HoplineConfig.from_file(path)

    def test_internal_probe_uses_loopback_for_wildcard_bind(self) -> None:
        self.assertEqual(_loopback("0.0.0.0"), "127.0.0.1")
        self.assertEqual(_loopback("::"), "127.0.0.1")
        self.assertEqual(_loopback("127.0.0.1"), "127.0.0.1")
        self.assertEqual(_loopback("10.0.0.5"), "10.0.0.5")


if __name__ == "__main__":
    unittest.main()
