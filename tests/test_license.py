import unittest
from datetime import datetime, timedelta
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


if __name__ == "__main__":
    unittest.main()
