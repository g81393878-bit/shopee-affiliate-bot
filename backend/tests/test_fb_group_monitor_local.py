# -*- coding: utf-8 -*-
"""Unit tests for Local Facebook Group Monitor Script (Milestone 4).

Verifies:
1. CLI Argument Parsing: --sample, --mock, --group-id, --group-url, --api-url, --token, --interval, --once, --dry-run.
2. Token Loading: Precedence across CLI args, env vars (CRON_TOKEN, ADMIN_DASHBOARD_PASSWORD), and .env files.
3. Deduplication Memory (SeenPostTracker): In-memory filtering, disk persistence (save_state, load_state), and idempotency.
4. Sample Dataset & Schema Compliance: Schema validation against Pydantic LeadIngestPayload & LeadIngestItem.
5. API Submission & Error Handling: Success 200, HTTP 401 Unauthorized, HTTP 500 Server Error, ConnectionError, and TimeoutError.
6. End-to-End Monitor Iteration: Dry-run and live integration with FastAPI TestClient and social demand radar endpoint.
7. Main CLI Execution: Clean exit code on single run (--once) and keyboard interrupt.
8. Single-Instance Lock: Acquire/release, block live holder, overwrite stale lock, pid-timeout hung-lock break.
9. Process Cleanup: _kill_chrome_tree / _sweep_orphan_drivers with mocked subprocess.
"""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import MagicMock, patch
import urllib.error

import pytest
from fastapi.testclient import TestClient

# Ensure tools directory is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TOOLS_DIR = PROJECT_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import fb_group_monitor_local as monitor
from app import schemas
from app.main import app


@pytest.fixture
def test_client():
    token = os.getenv("CRON_TOKEN") or "test_radar_token"
    client = TestClient(app)
    client.headers.update({"X-Admin-Token": token})
    return client


# ===========================================================================
# 1. Test CLI Argument Parsing
# ===========================================================================
def test_parse_args_defaults():
    """Verifies default argument values when no flags are passed."""
    args = monitor.parse_args([])
    assert args.sample is False
    assert args.group_id is None
    assert args.group_name is None
    assert args.group_url is None
    assert args.api_url == monitor.DEFAULT_API_URL
    assert args.token is None
    assert args.interval == monitor.DEFAULT_INTERVAL_SECONDS
    assert args.once is False
    assert args.dry_run is False
    assert args.state_file is None
    assert args.limit is None
    assert args.verbose is False


def test_parse_args_custom_flags():
    """Verifies custom flags parsing."""
    args = monitor.parse_args([
        "--sample",
        "--group-id", "grp_moms_th",
        "--group-name", "กลุ่มแม่และเด็ก",
        "--group-url", "https://facebook.com/groups/moms_th",
        "--api-url", "http://custom-backend:9000",
        "--token", "secret123",
        "--interval", "60",
        "--once",
        "--dry-run",
        "--state-file", "test_state.json",
        "--limit", "3",
        "--verbose",
    ])

    assert args.sample is True
    assert args.group_id == "grp_moms_th"
    assert args.group_name == "กลุ่มแม่และเด็ก"
    assert args.group_url == "https://facebook.com/groups/moms_th"
    assert args.api_url == "http://custom-backend:9000"
    assert args.token == "secret123"
    assert args.interval == 60
    assert args.once is True
    assert args.dry_run is True
    assert args.state_file == "test_state.json"
    assert args.limit == 3
    assert args.verbose is True


def test_parse_args_mock_alias():
    """Verifies --mock acts as alias for --sample."""
    args = monitor.parse_args(["--mock"])
    assert args.sample is True


# ===========================================================================
# 2. Test Token Loading Precedence
# ===========================================================================
def test_load_env_token_cli_precedence(monkeypatch):
    """Explicit CLI token takes highest precedence."""
    monkeypatch.setenv("CRON_TOKEN", "env_token")
    monkeypatch.setenv("ADMIN_DASHBOARD_PASSWORD", "env_password")
    assert monitor.load_env_token(cli_token="cli_token_value") == "cli_token_value"


def test_load_env_token_cron_token_precedence(monkeypatch):
    """CRON_TOKEN takes precedence over ADMIN_DASHBOARD_PASSWORD."""
    monkeypatch.setenv("CRON_TOKEN", "my_cron_token")
    monkeypatch.setenv("ADMIN_DASHBOARD_PASSWORD", "my_password")
    assert monitor.load_env_token(cli_token=None) == "my_cron_token"


def test_load_env_token_from_env_file(monkeypatch):
    """Loads token from .env file when environment variables are empty."""
    monkeypatch.delenv("CRON_TOKEN", raising=False)
    monkeypatch.delenv("ADMIN_DASHBOARD_PASSWORD", raising=False)

    with tempfile.TemporaryDirectory() as tmpdir:
        fake_env = Path(tmpdir) / ".env"
        fake_env.write_text("CRON_TOKEN=file_cron_token_999\n", encoding="utf-8")

        token = monitor.load_env_token(cli_token=None, env_path=str(fake_env))
        assert token == "file_cron_token_999"


# ===========================================================================
# 3. Test Deduplication Memory (SeenPostTracker)
# ===========================================================================
def test_seen_post_tracker_in_memory():
    """Tests in-memory deduplication and filtering."""
    tracker = monitor.SeenPostTracker()
    assert tracker.count == 0
    assert not tracker.is_seen("post_1")

    tracker.mark_seen("post_1")
    assert tracker.is_seen("post_1")
    assert tracker.count == 1

    tracker.mark_seen_many(["post_2", "post_3", "post_1"])
    assert tracker.count == 3
    assert tracker.is_seen("post_2")
    assert tracker.is_seen("post_3")

    candidates = [
        {"fb_post_id": "post_1", "text": "seen"},
        {"fb_post_id": "post_4", "text": "unseen"},
        {"fb_post_id": "post_2", "text": "seen"},
        {"fb_post_id": "post_5", "text": "unseen"},
    ]

    unseen = tracker.filter_unseen(candidates)
    assert len(unseen) == 2
    assert [p["fb_post_id"] for p in unseen] == ["post_4", "post_5"]

    tracker.clear()
    assert tracker.count == 0
    assert not tracker.is_seen("post_1")


def test_seen_post_tracker_file_persistence():
    """Tests saving and reloading state from JSON file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_file = Path(tmpdir) / "seen_state.json"
        tracker1 = monitor.SeenPostTracker(state_file=str(state_file), auto_load=False)
        tracker1.mark_seen_many(["p1", "p2", "p3"])
        success = tracker1.save_state()
        assert success is True
        assert state_file.exists()

        # Load in new tracker instance
        tracker2 = monitor.SeenPostTracker(state_file=str(state_file), auto_load=True)
        assert tracker2.count == 3
        assert tracker2.is_seen("p1")
        assert tracker2.is_seen("p2")
        assert tracker2.is_seen("p3")
        assert not tracker2.is_seen("p4")


# ===========================================================================
# 4. Test Sample Dataset & Pydantic Schema Compliance
# ===========================================================================
def test_sample_posts_generation():
    """Verifies sample posts content and override options."""
    samples = monitor.get_sample_posts()
    assert len(samples) >= 6

    # Verify presence of high demand and low demand posts
    post_texts = " ".join([p["post_text"] for p in samples])
    assert "ชุดคลุมท้อง" in post_texts
    assert "หูฟังบลูทูธ" in post_texts
    assert "เตือนภัยมิจฉาชีพ" in post_texts

    # Test limit and group override
    custom_samples = monitor.get_sample_posts(
        group_id="custom_grp",
        group_name="Custom Group",
        group_url="https://fb.com/custom",
        limit=2,
    )
    assert len(custom_samples) == 2
    assert custom_samples[0]["group_id"] == "custom_grp"
    assert custom_samples[0]["group_name"] == "Custom Group"
    assert custom_samples[0]["group_url"] == "https://fb.com/custom"


def test_build_lead_payload_schema_compliance():
    """Verifies built payload strictly matches Pydantic LeadIngestPayload schema."""
    samples = monitor.get_sample_posts(limit=3)
    payload_dict = monitor.build_lead_payload(samples)

    assert "leads" in payload_dict
    assert len(payload_dict["leads"]) == 3

    # Validate against backend Pydantic model
    validated_payload = schemas.LeadIngestPayload(**payload_dict)
    assert len(validated_payload.leads) == 3

    for item in validated_payload.leads:
        assert isinstance(item, schemas.LeadIngestItem)
        assert item.fb_post_id.startswith("fb_sample_")
        assert item.post_url.startswith("https://")
        assert len(item.post_text) > 0


# ===========================================================================
# 5. Test API Submission & Error Handling
# ===========================================================================
def test_submit_leads_to_api_with_test_client(test_client):
    """Tests successful submission using in-process FastAPI TestClient."""
    samples = monitor.get_sample_posts(limit=2)
    payload = monitor.build_lead_payload(samples)

    token = os.getenv("CRON_TOKEN") or "test_radar_token"
    res = monitor.submit_leads_to_api(
        api_url="http://testserver",
        token=token,
        payload=payload,
        client=test_client,
    )

    assert res["ok"] is True
    assert res["status_code"] == 200
    assert res["data"] is not None
    assert res["data"]["total_received"] == 2


def test_submit_leads_to_api_unauthorized_with_test_client(monkeypatch):
    """Tests 401 Unauthorized handling when secret token is required and invalid."""
    secret = "strict_secret_for_test"
    monkeypatch.setenv("CRON_TOKEN", secret)
    monkeypatch.setenv("ADMIN_DASHBOARD_PASSWORD", secret)

    raw_client = TestClient(app)
    samples = monitor.get_sample_posts(limit=1)
    payload = monitor.build_lead_payload(samples)

    res = monitor.submit_leads_to_api(
        api_url="http://testserver",
        token="wrong_token",
        payload=payload,
        client=raw_client,
    )

    assert res["ok"] is False
    assert res["status_code"] == 401
    assert "HTTP 401" in res["error"]


def test_submit_leads_urllib_http_error():
    """Tests urllib HTTPError handling (mocked)."""
    payload = {"leads": []}
    mock_err = urllib.error.HTTPError(
        url="http://127.0.0.1:8000/api/admin/facebook-radar/leads",
        code=500,
        msg="Internal Server Error",
        hdrs={},
        fp=MagicMock(read=lambda: b'{"detail": "DB Error"}'),
    )

    with patch("urllib.request.urlopen", side_effect=mock_err):
        res = monitor.submit_leads_to_api(
            api_url="http://127.0.0.1:8000",
            token="any_token",
            payload=payload,
        )
        assert res["ok"] is False
        assert res["status_code"] == 500
        assert res["error"] == "HTTP 500"
        assert "DB Error" in str(res["detail"])


def test_submit_leads_urllib_connection_error():
    """Tests urllib connection error handling (offline backend)."""
    payload = {"leads": []}
    mock_err = urllib.error.URLError(reason="Connection refused")

    with patch("urllib.request.urlopen", side_effect=mock_err):
        res = monitor.submit_leads_to_api(
            api_url="http://127.0.0.1:8000",
            token="any_token",
            payload=payload,
        )
        assert res["ok"] is False
        assert res["error"] == "ConnectionError"
        assert "Connection refused" in res["detail"]


def test_submit_leads_urllib_timeout_error():
    """Tests network timeout error handling."""
    payload = {"leads": []}
    mock_err = TimeoutError("Connection timed out")

    with patch("urllib.request.urlopen", side_effect=mock_err):
        res = monitor.submit_leads_to_api(
            api_url="http://127.0.0.1:8000",
            token="any_token",
            payload=payload,
            timeout=5,
        )
        assert res["ok"] is False
        assert res["error"] == "TimeoutError"


# ===========================================================================
# 6. Test End-to-End Monitor Iteration
# ===========================================================================
def test_run_monitor_iteration_dry_run():
    """Tests single iteration in dry-run mode."""
    tracker = monitor.SeenPostTracker()
    res = monitor.run_monitor_iteration(
        api_url="http://127.0.0.1:8000",
        token="test_token",
        tracker=tracker,
        sample_mode=True,
        dry_run=True,
        limit=3,
    )

    assert res["ok"] is True
    assert res["dry_run"] is True
    assert res["total_scanned"] == 3
    assert res["unseen_count"] == 3
    assert res["ingested_count"] == 3
    assert tracker.count == 3

    # Subsequent run should detect all as seen
    res2 = monitor.run_monitor_iteration(
        api_url="http://127.0.0.1:8000",
        token="test_token",
        tracker=tracker,
        sample_mode=True,
        dry_run=True,
        limit=3,
    )
    assert res2["ok"] is True
    assert res2["unseen_count"] == 0


def test_run_monitor_iteration_live_with_test_client(test_client):
    """Tests single iteration submitting to FastAPI TestClient."""
    tracker = monitor.SeenPostTracker()
    res = monitor.run_monitor_iteration(
        api_url="http://testserver",
        token=os.getenv("CRON_TOKEN") or "test_radar_token",
        tracker=tracker,
        sample_mode=True,
        dry_run=False,
        limit=3,
        client=test_client,
    )

    assert res["ok"] is True
    assert res["dry_run"] is False
    assert res["total_scanned"] == 3
    assert res["unseen_count"] == 3
    assert res["ingested_count"] == 3
    assert tracker.count == 3


# ===========================================================================
# 7. Test Main CLI Execution
# ===========================================================================
def test_main_cli_sample_dry_run_once():
    """Tests running main() with --sample --dry-run --once."""
    exit_code = monitor.main(["--sample", "--dry-run", "--once", "--limit", "2"])
    assert exit_code == 0


def test_main_cli_keyboard_interrupt():
    """Tests graceful exit on KeyboardInterrupt."""
    with patch("fb_group_monitor_local.run_monitor_iteration", side_effect=KeyboardInterrupt):
        exit_code = monitor.main(["--sample", "--once"])
        assert exit_code == 0


# ===========================================================================
# 8. Test Single-Instance Lock
# ===========================================================================
def test_acquire_monitor_lock_and_release():
    """Lock can be acquired, then released by its owner."""
    with tempfile.TemporaryDirectory() as tmp:
        lock = os.path.join(tmp, "monitor.lock")
        ok, msg = monitor._acquire_monitor_lock(lock)
        assert ok is True
        assert msg == ""
        assert os.path.exists(lock)

        # Releasing a lock owned by the current PID removes it.
        monitor._release_monitor_lock(lock)
        assert not os.path.exists(lock)


def test_acquire_monitor_lock_blocks_live_holder():
    """A lock held by a live PID is refused and left untouched."""
    with tempfile.TemporaryDirectory() as tmp:
        lock = os.path.join(tmp, "monitor.lock")
        Path(lock).write_text(str(os.getpid()), encoding="utf-8")

        ok, msg = monitor._acquire_monitor_lock(lock)
        assert ok is False
        assert "PID" in msg
        # The original lock file must not be overwritten.
        assert Path(lock).read_text(encoding="utf-8").strip() == str(os.getpid())


def test_acquire_monitor_lock_overwrites_stale_lock():
    """A lock held by a dead PID is treated as stale and overwritten."""
    with tempfile.TemporaryDirectory() as tmp:
        lock = os.path.join(tmp, "monitor.lock")
        Path(lock).write_text("999999999", encoding="utf-8")  # not a valid/possible PID

        ok, _ = monitor._acquire_monitor_lock(lock)
        assert ok is True
        assert Path(lock).read_text(encoding="utf-8").strip() == str(os.getpid())
        monitor._release_monitor_lock(lock)


def test_acquire_monitor_lock_pid_timeout_breaks_hung_lock():
    """A lock held by a long-running (hung) process is broken when --pid-timeout is set."""
    with tempfile.TemporaryDirectory() as tmp:
        lock = os.path.join(tmp, "monitor.lock")
        Path(lock).write_text("4242", encoding="utf-8")

        with patch("fb_group_monitor_local._is_pid_alive", return_value=True), \
             patch("fb_group_monitor_local._process_age_seconds", return_value=7200.0):  # 2h old
            ok, msg = monitor._acquire_monitor_lock(lock, pid_timeout_minutes=10)

        assert ok is True
        assert "hung" in msg or "เกิน" in msg
        # The lock now belongs to us.
        assert Path(lock).read_text(encoding="utf-8").strip() == str(os.getpid())
        monitor._release_monitor_lock(lock)


def test_acquire_monitor_lock_pid_timeout_keeps_young_lock():
    """A lock held by a recent process is still refused even with --pid-timeout."""
    with tempfile.TemporaryDirectory() as tmp:
        lock = os.path.join(tmp, "monitor.lock")
        Path(lock).write_text("4242", encoding="utf-8")

        with patch("fb_group_monitor_local._is_pid_alive", return_value=True), \
             patch("fb_group_monitor_local._process_age_seconds", return_value=60.0):  # 1 min old
            ok, msg = monitor._acquire_monitor_lock(lock, pid_timeout_minutes=10)

        assert ok is False
        assert "PID" in msg
        # The original lock file must be left untouched.
        assert Path(lock).read_text(encoding="utf-8").strip() == "4242"


def test_process_age_seconds_returns_positive_for_live_process():
    """The current (live) process has a positive age in seconds."""
    age = monitor._process_age_seconds(os.getpid())
    assert age is not None
    assert age > 0


# ===========================================================================
# 9. Test Process Cleanup (_kill_chrome_tree / _sweep_orphan_drivers)
# ===========================================================================
def test_sweep_orphan_drivers_kills_matching_processes():
    """Windows: every undetected_chromedriver.exe row is force-killed via taskkill /T /F."""
    fake_tasklist = (
        '"undetected_chromedriver.exe","1111","Console","1","10,000 K"\r\n'
        '"undetected_chromedriver.exe","2222","Console","1","10,000 K"\r\n'
    )
    with patch.object(os, "name", "nt"), patch("subprocess.run") as mock_run:
        # 1st call = tasklist enumeration; 2nd/3rd = taskkill per matching PID.
        mock_run.side_effect = [MagicMock(stdout=fake_tasklist), MagicMock(), MagicMock()]

        killed = monitor._sweep_orphan_drivers()

        assert killed == 2
        assert mock_run.call_count == 3
        assert mock_run.call_args_list[0].args[0][0] == "tasklist"
        kill_pids = [c.args[0][2] for c in mock_run.call_args_list[1:]]
        assert kill_pids == ["1111", "2222"]
        for c in mock_run.call_args_list[1:]:
            assert c.args[0][:2] == ["taskkill", "/PID"]
            assert c.args[0][3:] == ["/T", "/F"]


def test_sweep_orphan_drivers_ignores_non_driver_processes():
    """chrome.exe (the user's own browser) must never be killed."""
    fake_tasklist = '"chrome.exe","3333","Console","1","10,000 K"\r\n'
    with patch.object(os, "name", "nt"), patch("subprocess.run") as mock_run:
        mock_run.side_effect = [MagicMock(stdout=fake_tasklist)]

        killed = monitor._sweep_orphan_drivers()

        assert killed == 0
        assert mock_run.call_count == 1  # only the tasklist call, no taskkill


def test_sweep_orphan_drivers_noop_on_non_windows():
    """Non-Windows platforms skip the sweep entirely."""
    with patch.object(os, "name", "posix"), patch("subprocess.run") as mock_run:
        killed = monitor._sweep_orphan_drivers()

        assert killed == 0
        mock_run.assert_not_called()


def test_kill_chrome_tree_windows_force_kills_driver_tree():
    """Windows: quit the browser, then taskkill /PID <driver> /T /F."""
    driver = MagicMock()
    driver.service.process.pid = 4242

    with patch.object(os, "name", "nt"), patch("subprocess.run") as mock_run:
        monitor._kill_chrome_tree(driver)

    driver.quit.assert_called_once()
    mock_run.assert_called_once_with(
        ["taskkill", "/PID", "4242", "/T", "/F"],
        capture_output=True,
        timeout=10,
    )


def test_kill_chrome_tree_unix_terminates_driver_process():
    """Unix: quit the browser, then terminate the chromedriver process."""
    driver = MagicMock()
    with patch.object(os, "name", "posix"):
        monitor._kill_chrome_tree(driver)

    driver.quit.assert_called_once()
    driver.service.process.terminate.assert_called_once()


def test_kill_chrome_tree_without_pid_does_not_crash():
    """A driver without a usable PID still gets quit, and never reaches taskkill."""
    driver = MagicMock()
    driver.service.process.pid = None
    with patch.object(os, "name", "nt"), patch("subprocess.run") as mock_run:
        monitor._kill_chrome_tree(driver)  # must not raise

    driver.quit.assert_called_once()
    mock_run.assert_not_called()
