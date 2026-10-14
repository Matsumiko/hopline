import subprocess
import unittest
from pathlib import Path


class DeploymentTests(unittest.TestCase):
    def test_service_unit_has_private_runtime_boundaries(self) -> None:
        unit = Path("packaging/hopline.service").read_text(encoding="utf-8")
        self.assertIn("Environment=PYTHONPATH=/opt/hopline/app", unit)
        self.assertIn("ReadWritePaths=/var/lib/hopline", unit)
        self.assertIn("ReadOnlyPaths=/etc/hopline /opt/hopline/app", unit)
        self.assertIn("NoNewPrivileges=true", unit)
        self.assertIn("ProtectSystem=strict", unit)

    def test_systemd_accepts_service_unit(self) -> None:
        result = subprocess.run(
            ["systemd-analyze", "verify", "packaging/hopline.service"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
