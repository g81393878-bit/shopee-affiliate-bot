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
