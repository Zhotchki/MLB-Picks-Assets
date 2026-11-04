import subprocess
import unittest
from unittest.mock import patch
import refresh_watch


class PublicationRetryTests(unittest.TestCase):
    def publish_with_failures(self, failures):
        pushes = []
        def run(command):
            if command[:2] == ['git', 'push']:
                pushes.append(command)
                if len(pushes) <= failures:
                    raise subprocess.CalledProcessError(1, command)
        with patch.object(refresh_watch, 'run', side_effect=run), patch.object(refresh_watch.subprocess, 'run') as diff, patch.object(refresh_watch.time, 'sleep') as sleep:
            diff.return_value.returncode = 1
            if failures >= 3:
                with self.assertRaises(subprocess.CalledProcessError):
                    refresh_watch.publish()
            else:
                refresh_watch.publish()
            self.assertEqual(len(pushes), min(failures + 1, 3))
            self.assertEqual(sleep.call_count, min(failures, 2))

    def test_transient_push_recovers(self):
        self.publish_with_failures(1)

    def test_persistent_failure_stops_after_three_attempts(self):
        self.publish_with_failures(3)
