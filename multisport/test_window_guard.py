import unittest
from datetime import datetime, timedelta, timezone

from window_guard import planned_wait


class WindowGuardTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2030, 1, 1, 12, tzinfo=timezone.utc)

    def data(self, target, mode="PREGAME_WINDOWS", reason="PREGAME_WINDOW"):
        return {"platformFeed": {"refreshMode": mode, "refreshReason": reason,
                                 "nextRefreshAt": target.isoformat()}}

    def test_waits_for_near_future_pregame_window(self):
        self.assertEqual(planned_wait(self.data(self.now + timedelta(minutes=90)), self.now), 5405)

    def test_does_not_wait_for_past_or_distant_window(self):
        self.assertIsNone(planned_wait(self.data(self.now - timedelta(seconds=1)), self.now))
        self.assertIsNone(planned_wait(self.data(self.now + timedelta(minutes=106)), self.now))

    def test_does_not_wait_for_budget_interval_or_invalid_metadata(self):
        self.assertIsNone(planned_wait(self.data(self.now + timedelta(minutes=10), reason="DAILY_BUDGET"), self.now))
        self.assertIsNone(planned_wait(self.data(self.now + timedelta(minutes=10), mode="INTERVAL"), self.now))
        self.assertIsNone(planned_wait({"platformFeed": {"refreshMode": "PREGAME_WINDOWS",
                                                          "refreshReason": "PREGAME_WINDOW",
                                                          "nextRefreshAt": "invalid"}}, self.now))


if __name__ == "__main__":
    unittest.main()
