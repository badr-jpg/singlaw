from datetime import datetime
from zoneinfo import ZoneInfo

from app.crawler import CrawlWindow, SSOCrawler

SGT = ZoneInfo("Asia/Singapore")


def at(h, m):
    return datetime(2026, 8, 11, h, m, tzinfo=SGT)


def test_window_open_only_0500_to_0700_sgt():
    w = CrawlWindow("05:00", "07:00", "Asia/Singapore")
    assert not w.is_open(at(4, 59))
    assert w.is_open(at(5, 0))
    assert w.is_open(at(6, 59))
    assert not w.is_open(at(7, 0))  # hard kill boundary
    assert not w.is_open(at(15, 0))


def test_window_respects_timezone():
    w = CrawlWindow("05:00", "07:00", "Asia/Singapore")
    # 22:30 UTC == 06:30 SGT next day → open
    utc = datetime(2026, 8, 10, 22, 30, tzinfo=ZoneInfo("UTC"))
    assert w.is_open(utc)


def test_seconds_until_close_and_open():
    w = CrawlWindow("05:00", "07:00", "Asia/Singapore")
    assert w.seconds_until_close(at(6, 0)) == 3600
    assert w.seconds_until_close(at(8, 0)) == 0
    assert w.seconds_until_open(at(4, 0)) == 3600
    assert w.seconds_until_open(at(8, 0)) == 21 * 3600  # tomorrow 05:00


class ClosedWindow(CrawlWindow):
    def is_open(self, at=None):
        return False


async def test_sync_refuses_outside_window(ctx):
    crawler = SSOCrawler(ctx, window=ClosedWindow())
    result = await crawler.sync()
    assert result["started"] is False
    assert "05:00" in result["reason"]
    assert result["fetched"] == 0
