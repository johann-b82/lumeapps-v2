from __future__ import annotations
import time
import frappe

LUA = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local data = redis.call('HMGET', key, 'tokens', 'ts')
local tokens = tonumber(data[1])
local ts = tonumber(data[2])
if tokens == nil then
  tokens = capacity
  ts = now
end
local delta = math.max(0, now - ts)
tokens = math.min(capacity, tokens + delta * refill)
local wait = 0
if tokens >= 1 then
  tokens = tokens - 1
else
  wait = (1 - tokens) / refill
  tokens = 0
  now = now + wait
end
redis.call('HMSET', key, 'tokens', tokens, 'ts', now)
redis.call('EXPIRE', key, 60)
return tostring(wait)
"""


class TokenBucket:
    def __init__(self, key: str, capacity: int, refill_per_sec: float):
        self.key = f"wa_bucket:{key}"
        self.capacity = capacity
        self.refill = refill_per_sec
        self._client = frappe.cache()
        self._script = self._client.register_script(LUA)

    def acquire(self) -> None:
        wait_s = float(
            self._script(keys=[self.key], args=[self.capacity, self.refill, time.time()])
        )
        if wait_s > 0:
            time.sleep(wait_s)
