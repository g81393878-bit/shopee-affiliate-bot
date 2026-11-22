"""Local SkillClaw proxy/evolver using the existing Groq failover gateway."""
import asyncio
import json
import logging
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException, Request

ROOT = Path(__file__).resolve().parents[3]
STATE = ROOT / ".local/skillclaw_runtime"
PORT = 30000
GROUP = "pakhem-content"
logger = logging.getLogger(__name__)


def local_token():
    STATE.mkdir(parents=True, exist_ok=True)
    path = STATE / "token"
    if not path.exists():
        try:
            with path.open("x", encoding="utf-8") as stream:
                stream.write(secrets.token_urlsafe(32))
        except FileExistsError:
            pass
    return path.read_text(encoding="utf-8").strip()


def route_content_clients(clients, kind):
    """Only content callers opt in; direct clients remain available on proxy failure."""
    import os
    if os.getenv("PYTEST_CURRENT_TEST") or not (STATE / "enabled").exists():
        return clients
    from openai import OpenAI
    import uuid
    return [OpenAI(base_url=f"http://127.0.0.1:{PORT}/v1", api_key=local_token(),
                   timeout=50, max_retries=0,
                   default_headers={"X-Session-Id": f"{kind}-{uuid.uuid4().hex}",
                                    "X-Session-Done": "true"})] + list(clients)


def forward_groq(body):
    from app.services.llm_clients import groq_clients, call_with_backoff
    payload = dict(body)
    payload["stream"] = False
    # Upstream summarizer requests 100,000 output tokens even when configured
    # lower. Bound both spellings at the provider gateway.
    for field in ("max_tokens", "max_completion_tokens"):
        if field in payload:
            payload[field] = min(int(payload[field]), 8192)
    for client in groq_clients():
        try:
            response = call_with_backoff(
                lambda: client.with_options(timeout=40, max_retries=0).chat.completions.create(**payload),
                circuit_key=client.api_key)
            return response.model_dump(mode="json")
        except Exception as exc:
            if getattr(exc, "status_code", None) == 400:
                raise HTTPException(400, "Invalid model request; not a key failure") from None
            logger.warning("SkillClaw upstream attempt failed (%s)", type(exc).__name__)
    raise HTTPException(502, "Configured Groq providers unavailable")


def create_app():
    from skillclaw.config import SkillClawConfig
    from skillclaw.api_server import SkillClawAPIServer
    from evolve_server.core.config import EvolveServerConfig
    from evolve_server.engines.workflow import EvolveServer
    from app.config import settings

    token = local_token()
    cfg = SkillClawConfig(proxy_host="127.0.0.1", proxy_port=PORT, proxy_api_key=token,
        claw_type="none", configure_openclaw=False, use_prm=False, use_skills=False,
        record_enabled=True, record_dir=str(STATE / "records"),
        llm_api_base=f"http://127.0.0.1:{PORT}/upstream/v1", llm_api_key=token,
        llm_model_id="", sharing_enabled=True, sharing_backend="local",
        sharing_local_root=str(STATE / "shared"), sharing_group_id=GROUP,
        sharing_user_alias="content-producer", sharing_skill_reload_mode="off",
        max_context_tokens=64000)
    proxy = SkillClawAPIServer(cfg)
    evolve_cfg = EvolveServerConfig(storage_backend="local", local_root=str(STATE / "shared"),
        group_id=GROUP, llm_api_key=token, llm_base_url=cfg.llm_api_base,
        llm_model=settings.GROQ_MODEL, llm_max_tokens=4096, evolve_batch_size=3,
        use_session_judge=True, use_skill_verifier=True, skill_verifier_min_score=0.85,
        reject_rewrite=True, publish_mode="direct", http_port=0,
        history_path=str(STATE / "evolve_history.jsonl"),
        processed_log_path=str(STATE / "evolve_processed.json"))
    evolver = EvolveServer(evolve_cfg)
    lock = asyncio.Lock()
    app = proxy.app
    app.state.evolver = evolver
    app.state.proxy_config = cfg
    app.state.last_cycle = None
    original_lifespan = app.router.lifespan_context

    async def cycle():
        if lock.locked():
            raise HTTPException(409, "Evolution already running")
        async with lock:
            summary = await evolver.run_once()
            app.state.last_cycle = summary
            (STATE / "last_cycle.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
            return summary

    async def learn_loop():
        # At most four automatic batches per UTC day, persisted across restarts.
        while True:
            await asyncio.sleep(60)
            queue = STATE / "shared" / GROUP / "sessions"
            if not any(queue.glob("*.json")):
                continue
            day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            counter = STATE / f"cycles-{day}.json"
            count = json.loads(counter.read_text()) if counter.exists() else 0
            if count >= 4 or lock.locked():
                continue
            counter.write_text(json.dumps(count + 1))
            try:
                await cycle()
            except Exception as exc:
                logger.warning("Evolution cycle failed (%s)", type(exc).__name__)
            await asyncio.sleep(540)

    @asynccontextmanager
    async def lifespan(application):
        async with original_lifespan(application):
            worker = asyncio.create_task(learn_loop())
            try:
                yield
            finally:
                worker.cancel()
                await asyncio.gather(worker, return_exceptions=True)
    app.router.lifespan_context = lifespan

    def authorize(request):
        if not secrets.compare_digest(request.headers.get("authorization", ""), f"Bearer {token}"):
            raise HTTPException(401, "Unauthorized")

    @app.post("/upstream/v1/chat/completions")
    async def upstream(request: Request):
        authorize(request)
        return await asyncio.to_thread(forward_groq, await request.json())

    @app.get("/project/status")
    async def status(request: Request):
        authorize(request)
        return {"proxy": "ready", "evolver": "running" if lock.locked() else "idle",
                "routing_enabled": (STATE / "enabled").exists(), "storage": "local",
                "pending_sessions": len(list((STATE / "shared" / GROUP / "sessions").glob("*.json"))),
                "learned_skills": len(list((STATE / "shared" / GROUP / "skills").glob("*/SKILL.md"))),
                "last_cycle": app.state.last_cycle}

    @app.post("/project/evolve")
    async def evolve(request: Request):
        authorize(request)
        return await cycle()

    @app.post("/project/stop")
    async def stop(request: Request):
        authorize(request)
        (STATE / "enabled").unlink(missing_ok=True)
        callback = getattr(app.state, "stop_callback", None)
        if callback:
            callback()
        return {"stopping": True}
    return app
