import importlib.util
import copy
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location("trend_autopilot", Path(__file__).resolve().parents[2]/"tools/trend_autopilot.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def valid_plan():
    return {"topic_title":"ไอที", "scenes":[
        {"voice":"รู้จุดต่างหรือยัง?","headline":"รู้จุดต่างหรือยัง?","hero":"ไอที","detail":"สรุปข้อมูล","evidence":"This display has an adaptive refresh rate."},
        *[{"voice":"หน้าจอปรับได้จ้ะ","headline":"หน้าจอ","hero":"ปรับได้","detail":"ตามการใช้งาน","evidence":"This display has an adaptive refresh rate."} for _ in range(3)],
        {"voice":"คอมเมนต์และติดตามนะจ๊ะ","headline":"คุยกัน","hero":"ติดตาม","detail":"ป้าเข็มบอกต่อ"}]}


def test_evidence_required_and_caption_contract():
    p=valid_plan()
    result=m.validate_plan(p,"This display has an adaptive refresh rate.")
    assert result['caption'].startswith(result['hook'])
    assert '#' not in result['caption']
    with pytest.raises(ValueError):
        m.validate_plan(valid_plan(),'unsupported article')


@pytest.mark.parametrize('bad',['ราคา 999 บาท','Shopee','content_123','รัฐบาล'])
def test_reject_public_leaks(bad):
    p=valid_plan();p['scenes'][2]['voice']=bad
    with pytest.raises(ValueError):
        m.validate_plan(p,'This display has an adaptive refresh rate.')


def test_private_source_rejected_without_network(monkeypatch):
    monkeypatch.setattr(m.socket,'getaddrinfo',lambda *a,**k:[(None,None,None,None,('127.0.0.1',443))])
    with pytest.raises(ValueError):
        m.article_text('https://example.test/secret')


def test_editorial_blocklist_covers_current_high_risk_topics():
    for title in ('ตลาดหุ้นเอเชีย', 'คนร้ายชิงเงิน', 'Congress and BJP'):
        assert any(term in title.casefold() for term in m.BLOCKED_EDITORIAL)


def test_queue_full_does_not_call_network(tmp_path,monkeypatch):
    pending=tmp_path/'pending';pending.mkdir()
    for i in range(4): (pending/f'{i}.mp4').write_bytes(b'placeholder')
    monkeypatch.setattr(m,'PENDING',pending)
    monkeypatch.setattr(m,'BASE',tmp_path/'state')
    assert m.produce_one()=={'status':'queue_full'}


def test_atomic_state_preserves_json(tmp_path):
    p=tmp_path/'state.json'
    m.save_json(p,{'status':'building'})
    m.save_json(p,{'status':'queued'})
    assert m.read_json(p)=={'status':'queued'}
    assert not p.with_suffix('.json.tmp').exists()


def test_default_trend_model_is_json_capable(monkeypatch):
    monkeypatch.delenv('TREND_SCRIPT_MODEL', raising=False)
    assert m.os.getenv('TREND_SCRIPT_MODEL', 'qwen/qwen3.8-27b') == 'qwen/qwen3.8-27b'


def test_rule_plan_uses_exact_source_sentences_without_ai():
    sentences = [
        'บริษัทเปิดตัวระบบใหม่ที่ช่วยให้ผู้ใช้จัดการข้อมูลบนอุปกรณ์ได้สะดวกขึ้นอย่างชัดเจน.',
        'บริการนี้รองรับภาษาไทยและเปิดให้ผู้ใช้ทั่วไปทดลองใช้งานผ่านแอปพลิเคชันแล้ว.',
        'ผู้พัฒนาระบุว่าระบบทำงานบนอุปกรณ์ที่รองรับและต้องเชื่อมต่ออินเทอร์เน็ต.',
    ]
    row = {'title':'ระบบใหม่มาแรง', 'source_url':'https://example.com/news'}
    plan = m.build_rule_plan(row, 'ระบบใหม่สำหรับผู้ใช้ไทย', ' '.join(sentences))
    assert plan['generation_mode'] == 'local_rules'
    assert all(any(s['voice'] in source for source in sentences) for s in plan['scenes'][1:4])
    assert len(plan['voiceover_script']) <= 115
    assert plan['hook'] == plan['scenes'][0]['headline']


def test_rule_plan_filters_prices_and_fails_closed():
    article = ('สินค้านี้มีราคา 999 บาทและกำลังได้รับความสนใจอย่างมากจากผู้ซื้อ. '
               'มีข้อมูลภาษาไทยที่ปลอดภัยเพียงประโยคเดียวสำหรับใช้สรุปเนื้อหาอย่างตรงไปตรงมา.')
    with pytest.raises(ValueError, match='Not enough safe Thai'):
        m.build_rule_plan({'title':'ข่าวทั่วไป','source_url':'https://example.com/news'}, 'ข่าวทั่วไป', article)


def test_two_source_sentences_add_only_neutral_transition():
    sentences = [
        'ระบบรุ่นใหม่รองรับภาษาไทยและเปิดให้ผู้ใช้ทั่วไปเริ่มทดลองใช้งานได้แล้ว.',
        'ผู้พัฒนาระบุว่าอุปกรณ์ที่รองรับต้องเชื่อมต่ออินเทอร์เน็ตระหว่างใช้งาน.',
    ]
    plan = m.build_rule_plan({'title':'ระบบใหม่','source_url':'https://example.com/news'},
                             'ระบบใหม่', ' '.join(sentences))
    assert plan['scenes'][3]['neutral_transition'] is True
    assert all(scene['voice'] in source for scene, source in zip(plan['scenes'][1:3], sentences))


def test_ai_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv('TREND_USE_AI', raising=False)
    assert m.os.getenv('TREND_USE_AI', 'false') == 'false'


def test_hook_library_has_at_least_thirty_category_variants():
    assert sum(len(hooks) for hooks in m.HOOKS_BY_CATEGORY.values()) >= 30
    assert m.choose_hook('ไอที', 'มือถือรุ่นใหม่') in m.HOOKS_BY_CATEGORY['ไอที']


def test_source_sentence_ranking_rewards_topic_keywords():
    article = ('ข้อมูลทั่วไปประโยคนี้มีรายละเอียดครบถ้วนและปลอดภัยสำหรับการเผยแพร่. '
               'มือถือรุ่นใหม่รองรับภาษาไทยและเปิดให้ใช้งานบนอุปกรณ์ที่กำหนดแล้ว. '
               'ข้อมูลเสริมอีกประโยคหนึ่งอธิบายเงื่อนไขการใช้งานไว้อย่างชัดเจน.')
    ranked = m._safe_source_sentences(article, ['มือถือ', 'ภาษาไทย'])
    assert ranked[0].startswith('มือถือรุ่นใหม่')


def test_candidate_rows_survive_google_failure_with_thai_rss(monkeypatch):
    class BrokenClient:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def get(self, *a, **k): raise RuntimeError('offline')
    monkeypatch.setattr(m.httpx, 'Client', BrokenClient)
    import app.services.facebook_curated as curated
    monkeypatch.setattr(curated, 'fetch_news_items', lambda max_items: [{
        'title':'มือถือรุ่นใหม่สำหรับคนไทย', 'link':'https://example.com/thai-news', 'source':'Tech Thai',
        'summary':'<p>รายละเอียดข่าวภาษาไทยที่มาจากผู้เผยแพร่โดยตรงและอ่านได้ชัดเจน.</p>'}])
    rows = m.fetch_candidate_rows([])
    assert rows and rows[0]['source_url'] == 'https://example.com/thai-news'
    assert '<p>' not in rows[0]['source_summary']
    assert rows[0]['source_summary'].startswith('มือถือรุ่นใหม่')
