"""P21 temporary negative test: never merge this canary into main."""
import unittest

class TestP21RedCanary(unittest.TestCase):
    def test_required_checks_reject_failed_ci(self):
        self.fail("P21_EXPECTED_RED_CI_CANARY_DO_NOT_MERGE")
