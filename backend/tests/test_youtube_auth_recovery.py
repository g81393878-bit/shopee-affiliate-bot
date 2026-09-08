import sys
from pathlib import Path
from unittest.mock import Mock
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
import youtube_uploader as yt


@pytest.fixture
def setup(tmp_path, monkeypatch):
    for name in ('log', 'notify_telegram', 'set_last_successful_channel', 'increment_channel_counter'):
        monkeypatch.setattr(yt, name, Mock())
    monkeypatch.setattr(yt, 'HEALTH_FILE', tmp_path / 'health.json')
    monkeypatch.setattr(yt, 'get_channel_info', lambda _: {'title': 'channel'})
    monkeypatch.setattr(yt, 'get_next_channel_rotation', lambda t: (t, 0))
    tokens = []
    for n in (1, 2):
        p = tmp_path / f'token{n}.json'
        p.write_text('{}')
        tokens.append({'id': n, 'name': str(n), 'path': p})
    monkeypatch.setattr(yt, 'get_token_files', lambda: tokens)
    video = tmp_path / 'clip.mp4'
    video.write_bytes(b'video')
    return video, tokens


def test_failover_persists_cooldown(setup, monkeypatch):
    video, _ = setup
    auth = Mock(side_effect=[yt.ReauthorizationRequired('invalid_grant'), object(), object()])
    monkeypatch.setattr(yt, 'get_authenticated_service', auth)
    monkeypatch.setattr(yt, 'upload_shorts_to_channel', Mock(return_value='url'))
    assert yt.upload_shorts(str(video))[0]['id'] == 2
    yt.notify_telegram.reset_mock()
    assert yt.upload_shorts(video)[0]['id'] == 2
    assert auth.call_count == 3
    yt.notify_telegram.assert_not_called()


def test_all_fail_retains_video_and_throttles(setup, monkeypatch):
    video, _ = setup
    auth = Mock(side_effect=RuntimeError('uploadLimitExceeded'))
    monkeypatch.setattr(yt, 'get_authenticated_service', auth)
    assert yt.upload_shorts(video) == []
    assert video.read_bytes() == b'video'
    assert 'ยังไม่มี' in yt.notify_telegram.call_args.args[0]
    yt.notify_telegram.reset_mock()
    assert yt.upload_shorts(video) == []
    assert auth.call_count == 2
    yt.notify_telegram.assert_not_called()


def test_new_token_bypasses_cooldown(setup, monkeypatch):
    import os
    video, tokens = setup
    monkeypatch.setattr(yt, 'get_authenticated_service', Mock(side_effect=yt.ReauthorizationRequired('bad')))
    yt.upload_shorts(video)
    p = tokens[0]['path']
    os.utime(p, ns=(p.stat().st_atime_ns, p.stat().st_mtime_ns + 1000000))
    auth = Mock(return_value=object())
    monkeypatch.setattr(yt, 'get_authenticated_service', auth)
    monkeypatch.setattr(yt, 'upload_shorts_to_channel', Mock(return_value='url'))
    assert yt.upload_shorts(video)[0]['id'] == 1
    assert auth.call_count == 1


def test_revoked_token_does_not_open_browser(tmp_path, monkeypatch):
    from google.oauth2.credentials import Credentials
    from google.auth.exceptions import RefreshError
    from google_auth_oauthlib.flow import InstalledAppFlow
    token = tmp_path / 'token.json'
    token.write_text('original')
    creds = Mock(valid=False, refresh_token='mock')
    creds.refresh.side_effect = RefreshError('invalid_grant')
    monkeypatch.setattr(Credentials, 'from_authorized_user_file', Mock(return_value=creds))
    flow = Mock()
    monkeypatch.setattr(InstalledAppFlow, 'from_client_secrets_file', flow)
    with pytest.raises(yt.ReauthorizationRequired):
        yt.get_authenticated_service(token)
    flow.assert_not_called()
    assert token.read_text() == 'original'


def test_transient_refresh_retries(tmp_path, monkeypatch):
    from google.oauth2.credentials import Credentials
    from google.auth.exceptions import TransportError
    import googleapiclient.discovery
    token = tmp_path / 'token.json'
    token.write_text('old')
    creds = Mock(valid=False, refresh_token='mock')
    def refresh(_):
        if creds.refresh.call_count == 1:
            raise TransportError('offline')
        creds.valid = True
    creds.refresh.side_effect = refresh
    creds.to_json.return_value = '{"refreshed":true}'
    monkeypatch.setattr(Credentials, 'from_authorized_user_file', Mock(return_value=creds))
    monkeypatch.setattr(googleapiclient.discovery, 'build', Mock(return_value='service'))
    monkeypatch.setattr(yt.time, 'sleep', Mock())
    monkeypatch.setattr(yt, 'log', Mock())
    assert yt.get_authenticated_service(token) == 'service'
    assert creds.refresh.call_count == 2
    assert token.read_text() == '{"refreshed":true}'


def test_wrong_channel_preserves_token(tmp_path, monkeypatch):
    from google_auth_oauthlib.flow import InstalledAppFlow
    import googleapiclient.discovery
    token = tmp_path / 'token.json'
    token.write_text('original')
    secret = tmp_path / 'secret.json'
    secret.write_text('{}')
    monkeypatch.setattr(yt, 'CLIENT_SECRET_FILE', secret)
    flow = Mock()
    flow.run_local_server.return_value = Mock(valid=True)
    monkeypatch.setattr(InstalledAppFlow, 'from_client_secrets_file', Mock(return_value=flow))
    service = Mock()
    service.channels.return_value.list.return_value.execute.return_value = {'items': [{'snippet': {'customUrl': '@wrong'}}]}
    monkeypatch.setattr(googleapiclient.discovery, 'build', Mock(return_value=service))
    with pytest.raises(yt.ReauthorizationRequired):
        yt.get_authenticated_service(token, interactive=True, expected_handle='@goodthings-w4e')
    assert token.read_text() == 'original'
