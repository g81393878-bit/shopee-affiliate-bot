from types import SimpleNamespace

from reels_uploader.auto_product_reels import build_voice_script, local_product_score


def product(**overrides):
    values = dict(sales_count=0, rating=0, commission=0, affiliate_url="", image_url="")
    values.update(overrides)
    return SimpleNamespace(**values)


def test_local_score_rewards_real_commercial_signals():
    weak = product(sales_count=10, rating=3.5, commission=2)
    strong = product(sales_count=10000, rating=4.9, commission=30,
                     affiliate_url="https://s.shopee.co.th/abc",
                     image_url="https://cf.shopee.co.th/file/photo.jpg")
    assert local_product_score(strong) > local_product_score(weak)


def test_local_score_uses_demand_and_drop_without_ai_score():
    item = product(sales_count=100, rating=4.5, commission=10)
    item.ai_score = 100
    baseline = local_product_score(item)
    item.ai_score = 0
    assert local_product_score(item) == baseline
    assert local_product_score(item, latest_drop_pct=20, demand_score=80) > baseline


def test_product_voice_does_not_call_ai_by_default(monkeypatch):
    monkeypatch.delenv("PRODUCT_USE_AI", raising=False)
    monkeypatch.setattr("reels_uploader.auto_product_reels.generate_ai_voice_script",
                        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("AI called")))
    result = build_voice_script("สายชาร์จ Type C", 0, "ไอที", seed_id=1)
    assert "ราคา" not in result
    assert "ลิงก์ในแคปชั่น" in result
    assert result.startswith("สายไอทีต้องดู!")
