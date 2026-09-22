import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import cheviplus_license as lic


class LicenseStateTests(unittest.TestCase):
    def _record(self, status=lic.STATUS_ACTIVE, valid_until=None, last_seen=None):
        now = datetime(2026, 8, 11, 12, 0, 0)
        return {
            "version": 1,
            "workstation_id": "CP-TEST",
            "status": status,
            "valid_until": (valid_until or now + timedelta(days=30)).isoformat(timespec="seconds"),
            "activated_at": now.isoformat(timespec="seconds"),
            "last_seen_at": last_seen.isoformat(timespec="seconds") if last_seen else None,
            "last_verified_at": now.isoformat(timespec="seconds"),
            "source": "test",
        }

    def test_active_license_allows_processing(self):
        now = datetime(2026, 8, 11, 12, 0, 0)
        data = self._record(valid_until=now + timedelta(days=30))
        with patch.object(lic, "load_license", return_value=data), patch.object(lic, "save_license"):
            _, state, allowed = lic.license_state(now)
        self.assertEqual(state, "active")
        self.assertTrue(allowed)

    def test_expired_license_blocks_after_grace(self):
        now = datetime(2026, 8, 11, 12, 0, 0)
        data = self._record(valid_until=now - timedelta(days=lic.GRACE_DAYS + 1))
        with patch.object(lic, "load_license", return_value=data), patch.object(lic, "save_license"):
            _, state, allowed = lic.license_state(now)
        self.assertEqual(state, "expired")
        self.assertFalse(allowed)

    def test_grace_period_allows_processing(self):
        now = datetime(2026, 8, 11, 12, 0, 0)
        data = self._record(valid_until=now - timedelta(days=2))
        with patch.object(lic, "load_license", return_value=data), patch.object(lic, "save_license"):
            _, state, allowed = lic.license_state(now)
        self.assertEqual(state, "grace")
        self.assertTrue(allowed)

    def test_suspended_license_blocks(self):
        now = datetime(2026, 8, 11, 12, 0, 0)
        data = self._record(status=lic.STATUS_SUSPENDED)
        with patch.object(lic, "load_license", return_value=data), patch.object(lic, "save_license"):
            _, state, allowed = lic.license_state(now)
        self.assertEqual(state, "suspended")
        self.assertFalse(allowed)

    def test_clock_rollback_blocks(self):
        now = datetime(2026, 8, 11, 12, 0, 0)
        data = self._record(last_seen=now + timedelta(days=1))
        with patch.object(lic, "load_license", return_value=data), patch.object(lic, "save_license"):
            _, state, allowed = lic.license_state(now)
        self.assertEqual(state, "clock_rollback")
        self.assertFalse(allowed)

    def test_initial_package_binds_to_current_pc(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            package = tmp / "CPS-000002.cpslicense"
            license_file = tmp / "license.json"
            payload = {
                "version": 3,
                "license_number": "CPS-000002",
                "workstation_name": "ДРАЙВ ТАЙМ — 1",
                "token": "test-token",
                "months": 6,
                "issued_at": "2026-08-13T11:51:12",
                "server_ready": True,
            }
            payload["signature"] = lic._sign_payload(payload)
            package.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            with patch.object(lic, "_license_path", return_value=license_file), \
                 patch.object(lic, "_machine_fingerprint", return_value="PC-FINGERPRINT"), \
                 patch.object(lic, "load_stats", return_value={"workstation_id": "CP-TEST"}):
                result = lic._bind_from_package(package)
            self.assertEqual(result["license_number"], "CPS-000002")
            self.assertEqual(result["machine_fingerprint"], "PC-FINGERPRINT")
            self.assertTrue(license_file.exists())
            self.assertFalse(package.exists())

    def test_renewal_file_cannot_be_used_for_first_activation(self):
        with tempfile.TemporaryDirectory() as tmp:
            package = Path(tmp) / "renewal.cpslicense"
            payload = {
                "version": 4,
                "type": "renewal",
                "renewal": True,
                "license_number": "CPS-000002",
                "workstation_name": "ДРАЙВ ТАЙМ — 1",
                "token": "test-token",
                "months": 6,
                "issued_at": "2026-08-14T12:00:00",
                "server_ready": True,
            }
            payload["signature"] = lic._sign_payload(payload)
            package.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "файл продления"):
                lic._bind_from_package(package)


if __name__ == "__main__":
    unittest.main()
