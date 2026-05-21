import time
from frappe.tests.utils import FrappeTestCase
from whatsapp_broadcast.tasks.token_bucket import TokenBucket


class TestTokenBucket(FrappeTestCase):
    def setUp(self):
        self.bucket = TokenBucket(key=f"test_bucket_{time.time()}", capacity=5, refill_per_sec=5)

    def test_first_n_acquires_within_capacity_dont_sleep(self):
        start = time.monotonic()
        for _ in range(5):
            self.bucket.acquire()
        elapsed = time.monotonic() - start
        self.assertLess(elapsed, 0.1)

    def test_acquire_beyond_capacity_blocks_until_refill(self):
        for _ in range(5):
            self.bucket.acquire()
        start = time.monotonic()
        self.bucket.acquire()  # 6th must wait ~0.2s for 1 token
        elapsed = time.monotonic() - start
        self.assertGreaterEqual(elapsed, 0.15)
        self.assertLess(elapsed, 0.5)
