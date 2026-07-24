from trading_bot.kis_rate_limit import KisRequestLimiter


def test_shared_limiter_spaces_requests_from_multiple_consumers() -> None:
    now = [10.0]
    sleeps: list[float] = []

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        now[0] += seconds

    limiter = KisRequestLimiter(1.0, clock=lambda: now[0], sleeper=sleep)
    limiter.acquire()
    limiter.acquire()

    assert sleeps == [1.0]
