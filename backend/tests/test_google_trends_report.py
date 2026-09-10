import importlib.util
from pathlib import Path
from datetime import datetime, timezone

spec = importlib.util.spec_from_file_location("google_trends_report", Path(__file__).resolve().parents[2] / "tools/google_trends_report.py")
report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(report)


def test_rss_namespaces_and_volume():
    rows = report.parse_feed(b'<rss xmlns:ht="https://trends.google.com/trending/rss"><channel><item><title>iphone</title><ht:approx_traffic>20K+</ht:approx_traffic><ht:news_item><ht:news_item_url>https://example.com/news</ht:news_item_url></ht:news_item></item></channel></rss>')
    assert rows[0]["source_url"] == "https://example.com/news"
    assert report.traffic_number(rows[0]["traffic"]) == 20000
    assert report.traffic_number("unknown") is None


def test_rank_filters_duplicates_sensitive_topics_and_rewards_relevance():
    rows = [{"title": title, "traffic": "1K+", "published_at": "Thu, 10 Sep 2026 00:00:00 GMT"}
            for title in ["iphone", "iphone", "เลือกตั้ง", "old topic", "generic"]]
    ranked, excluded = report.rank_topics(rows, ["old topic"], datetime(2026, 9, 10, tzinfo=timezone.utc))
    assert excluded == 3
    assert [r["title"] for r in ranked] == ["iphone", "generic"]
    assert ranked[0]["score"] > ranked[1]["score"]


def test_missing_data_no_invented_volume_or_freshness():
    ranked, _ = report.rank_topics([{"title": "unknown"}])
    assert ranked[0]["score"] == 0
    assert ranked[0]["needs_review"]


def test_html_escapes_feed_text_and_rejects_script_urls():
    ranked, _ = report.rank_topics([{"title": "<script>alert(1)</script>", "source_url": "javascript:alert(1)"}])
    page = report.render_report({"topics": ranked, "fetched_at": "now", "fetched_count": 1, "excluded_count": 0})
    assert "<script>" not in page
    assert "javascript:" not in page
