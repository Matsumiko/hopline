import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INSTALLER = ROOT / "packaging" / "install.sh"


class InstallerTests(unittest.TestCase):
    def setUp(self) -> None:
        if os.geteuid() != 0:
            self.skipTest("installer test requires root")
        self.tmp = Path(tempfile.mkdtemp(prefix="hopline-install-"))
        for name in ("app", "cfg", "state", "backups", "units"):
            (self.tmp / name).mkdir()

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, **env_overrides: str) -> subprocess.CompletedProcess:
        env = dict(
            os.environ,
            APP_DIR=str(self.tmp / "app"),
            CONFIG_DIR=str(self.tmp / "cfg"),
            STATE_DIR=str(self.tmp / "state"),
            BACKUP_DIR=str(self.tmp / "backups"),
            UNIT_DIR=str(self.tmp / "units"),
            HOPLINE_INSTALL_START="0",
            SERVICE_USER="hopline",
            **env_overrides,
        )
        return subprocess.run(
            ["bash", str(INSTALLER)], env=env, capture_output=True, text=True, timeout=120
        )

    def test_install_is_idempotent_and_preserves_config(self) -> None:
        first = self._run()
        self.assertEqual(first.returncode, 0, first.stderr)
        config = self.tmp / "cfg" / "hopline.toml"
        self.assertTrue(config.is_file())
        self.assertEqual(config.stat().st_mode & 0o777, 0o600)
        original = config.read_bytes()

        second = self._run()
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertIn("config preserved", second.stdout)
        self.assertEqual(config.read_bytes(), original, "installer must never overwrite config")
        self.assertEqual(len(list((self.tmp / "backups").iterdir())), 2)

    def test_installer_writes_unit_without_touching_systemd(self) -> None:
        result = self._run()
        self.assertEqual(result.returncode, 0, result.stderr)
        unit = self.tmp / "units" / "hopline.service"
        self.assertTrue(unit.is_file())
        self.assertIn("systemd not touched", result.stdout)

    def test_installer_rejects_missing_source(self) -> None:
        result = self._run(SOURCE_DIR=str(self.tmp / "does-not-exist"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("source tree not found", result.stderr)


if __name__ == "__main__":
    unittest.main()
