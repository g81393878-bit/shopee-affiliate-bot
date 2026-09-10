from tools.performance_learner import build_report, metric_score


def test_metric_score_rewards_observed_results_and_confidence():
    assert metric_score(10000, 500, 50, 1000) > metric_score(100, 1, 0, 0)
    assert 0 <= metric_score(10000, 500, 50, 1000) <= 100


def test_metric_score_handles_empty_and_invalid_values():
    assert metric_score() == 0
    assert metric_score(-1, -2, -3, -4) == 0


def test_report_is_factual_when_no_logs_exist():
    report = build_report({"products": {}})
    assert "ยังไม่มี performance log" in report
    assert "ยอดดู: 0" in report


def test_report_ranks_highest_product_first():
    data = {"products": {
        "2": {"name": "สินค้าสอง", "score": 10, "views": 10, "clicks": 1, "orders": 0, "commission": 0},
        "1": {"name": "สินค้าหนึ่ง", "score": 90, "views": 100, "clicks": 20, "orders": 5, "commission": 50},
    }}
    report = build_report(data)
    assert report.index("รหัส 1") < report.index("รหัส 2")
