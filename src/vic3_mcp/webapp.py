"""FastAPI app: metrics dashboard + chat + advice board."""

from __future__ import annotations

import json
import queue
import threading

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from vic3_mcp.agent import chat_events
from vic3_mcp.hub import HUB
from vic3_mcp.llm_settings import load_settings, public_settings, save_settings
from vic3_mcp.paths import PACKAGE_ROOT

load_dotenv(PACKAGE_ROOT / ".env")

WEB_DIR = PACKAGE_ROOT / "web"

app = FastAPI(title="Vic3 Advisor", version="0.1.0")


class RefreshBody(BaseModel):
    save: str | None = None
    force: bool = False


class SettingsBody(BaseModel):
    base_url: str | None = None
    api_key: str | None = None
    model: str | None = None
    auto_refresh_sec: int | None = Field(default=None, ge=5, le=300)


class ChatBody(BaseModel):
    messages: list[dict] = Field(default_factory=list)


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/status")
def status():
    return HUB.status()


@app.post("/api/refresh")
def refresh(body: RefreshBody | None = None):
    body = body or RefreshBody()
    try:
        return HUB.refresh(body.save, force=body.force)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, str(exc)) from exc


@app.get("/api/refresh/stream")
def refresh_stream(force: bool = False, save: str | None = None):
    events: queue.Queue = queue.Queue()

    def on_progress(pct: int, label: str) -> None:
        events.put(("progress", {"pct": pct, "label": label}))

    def work() -> None:
        try:
            result = HUB.refresh(save, force=force, on_progress=on_progress)
            events.put(("done", result))
        except Exception as exc:  # noqa: BLE001
            events.put(("error", {"message": str(exc)}))

    threading.Thread(target=work, daemon=True).start()

    def gen():
        yield f"event: progress\ndata: {json.dumps({'pct': 1, 'label': '开始读取'}, ensure_ascii=False)}\n\n"
        while True:
            kind, data = events.get()
            payload = json.dumps(data, ensure_ascii=False, default=str)
            yield f"event: {kind}\ndata: {payload}\n\n"
            if kind in ("done", "error"):
                break

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/dashboard")
def dashboard():
    if HUB.dashboard is None:
        HUB.refresh()
    return {"dashboard": HUB.dashboard, "board": HUB.board, "status": HUB.status()}


@app.get("/api/settings")
def get_settings():
    return public_settings()


@app.put("/api/settings")
def put_settings(body: SettingsBody):
    save_settings(body.model_dump(exclude_none=True))
    return public_settings()


@app.get("/api/models")
def list_models():
    from openai import OpenAI

    s = load_settings()
    if not s.get("api_key"):
        raise HTTPException(400, "未配置 API Key")
    client = OpenAI(api_key=s["api_key"], base_url=s["base_url"], timeout=30.0)
    try:
        resp = client.models.list()
        ids = [m.id for m in resp.data]
        ids.sort()
        return {"models": ids}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, str(exc)) from exc


@app.post("/api/chat")
def chat(body: ChatBody):
    def gen():
        try:
            for ev in chat_events(body.messages):
                payload = json.dumps(ev.get("data"), ensure_ascii=False, default=str)
                yield f"event: {ev['event']}\ndata: {payload}\n\n"
        except Exception as exc:  # noqa: BLE001
            err = json.dumps({"message": str(exc)}, ensure_ascii=False)
            yield f"event: error\ndata: {err}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


@app.get("/")
def index():
    page = WEB_DIR / "index.html"
    if not page.exists():
        raise HTTPException(404, "web/index.html missing")
    return FileResponse(page)


def main() -> None:
    import uvicorn

    uvicorn.run("vic3_mcp.webapp:app", host="127.0.0.1", port=8765, reload=False)


if __name__ == "__main__":
    main()
