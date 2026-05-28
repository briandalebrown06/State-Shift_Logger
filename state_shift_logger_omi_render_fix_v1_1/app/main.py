from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse

from app.config import settings
from app.detectors import (
    analyze_transcript,
    audio_features_from_pcm16,
    audio_shift_marker,
    excerpt,
    markers_to_dicts,
)
from app.omi_client import OmiClient
from app.schemas import extract_segments, user_text_from_segments
from app.storage import Storage

app = FastAPI(
    title="State Shift Logger for Omi",
    description="Private cautious logger for possible DID/dissociation state-shift markers.",
    version="0.1.0",
)

storage = Storage(settings.database_path)
omi = OmiClient()


def validate_webhook_token(token: str | None, request: Request) -> None:
    if not settings.webhook_shared_secret:
        return

    header_token = request.headers.get("x-state-shift-token")
    if token == settings.webhook_shared_secret or header_token == settings.webhook_shared_secret:
        return

    raise HTTPException(status_code=401, detail="Invalid webhook token")


def validate_admin(request: Request) -> None:
    if not settings.admin_token:
        raise HTTPException(status_code=403, detail="Admin endpoints disabled. Set ADMIN_TOKEN to enable.")

    authorization = request.headers.get("authorization", "")
    expected = f"Bearer {settings.admin_token}"
    if authorization != expected:
        raise HTTPException(status_code=401, detail="Invalid admin token")


def notification_prompt(analysis_summary: str, grounding_request: bool = False) -> str:
    if grounding_request:
        return (
            "You are a gentle grounding assistant. Tell {{user_name}} you noticed they may want grounding support. "
            "Use warm, non-alarming language. Ask them to name where they are, feel their feet, take one slow breath, "
            "and say they can log this only if they want. Keep it under 70 words."
        )

    return (
        "You are a careful self-tracking assistant for {{user_name}}. "
        "Gently say you noticed a possible state-shift or dissociation marker. "
        "Do not diagnose. Do not say they switched. Ask if they want to log it. "
        f"Detected context: {analysis_summary}. Keep it under 65 words."
    )


def build_memory_content(
    text: str,
    analysis_summary: str,
    score: float,
    confidence: str,
    markers: list[dict[str, Any]],
) -> str:
    marker_lines = "\n".join(
        f"- {m.get('label', 'marker')} ({m.get('category', 'unknown')}): {m.get('evidence', '')}"
        for m in markers[:8]
    )
    return (
        "Possible state-shift / dissociation marker log.\n"
        "This is not a diagnosis and does not prove a switch occurred.\n\n"
        f"Confidence: {confidence}\n"
        f"Score: {score}\n"
        f"Summary: {analysis_summary}\n\n"
        f"Markers:\n{marker_lines or '- none'}\n\n"
        f"Context excerpt:\n{excerpt(text, 500)}"
    )


@app.get("/", response_class=HTMLResponse)
async def home() -> str:
    return """
    <html>
      <head><title>State Shift Logger</title></head>
      <body style="font-family: -apple-system, BlinkMacSystemFont, sans-serif; max-width: 760px; margin: 40px auto; line-height: 1.5;">
        <h1>State Shift Logger</h1>
        <p>Private Omi integration for logging <strong>possible</strong> state-shift, dissociation, blending, co-fronting, or switching markers.</p>
        <p>This tool does not diagnose or identify alters/headmates. It only helps organize self-tracking notes.</p>
        <ul>
          <li><code>POST /webhook</code> for Omi transcript events</li>
          <li><code>POST /audio</code> for optional PCM16 audio feature extraction</li>
          <li><code>GET /setup-completed</code> for Omi setup check</li>
          <li><code>GET /healthz</code> for uptime checks</li>
        </ul>
      </body>
    </html>
    """


@app.get("/healthz")
async def healthz() -> dict[str, Any]:
    return {
        "status": "ok",
        "app": "state-shift-logger",
        "omi_memory_configured": omi.configured,
    }


@app.get("/setup-completed")
async def setup_completed(uid: str | None = None) -> dict[str, bool]:
    # Private v1 has no OAuth or per-user setup requirement.
    return {"is_setup_completed": True}


@app.post("/webhook")
async def webhook(
    request: Request,
    uid: str | None = None,
    session_id: str | None = None,
    token: str | None = Query(default=None),
) -> JSONResponse:
    validate_webhook_token(token, request)

    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON payload: {exc}") from exc

    if isinstance(payload, dict):
        session_id = session_id or payload.get("session_id") or payload.get("id")

    segments = extract_segments(payload)
    text = user_text_from_segments(segments)

    if not text.strip():
        return JSONResponse({"session_id": session_id, "status": "no_text"})

    previous = storage.recent_texts(uid, session_id, limit=5)
    analysis = analyze_transcript(text, previous_texts=previous)
    markers = markers_to_dicts(analysis.markers)

    should_log_locally = (
        analysis.explicit_log_request
        or analysis.score >= settings.log_threshold
        or analysis.grounding_request
    )

    omi_memory_created = False
    if should_log_locally and uid:
        should_create_omi_memory = (
            (analysis.explicit_log_request and settings.create_omi_memory_on_explicit_log)
            or (analysis.score >= settings.log_threshold and settings.create_omi_memory_on_high_confidence)
        )
        if should_create_omi_memory:
            content = build_memory_content(
                text=text,
                analysis_summary=analysis.summary,
                score=analysis.score,
                confidence=analysis.confidence,
                markers=markers,
            )
            try:
                omi_memory_created = await omi.create_memory(
                    uid=uid,
                    content=content,
                    tags=["state_shift_logger", "possible_state_shift", analysis.confidence],
                )
            except Exception:
                # Never break Omi transcription if memory creation fails.
                omi_memory_created = False

    if should_log_locally:
        storage.save_state_shift_log(
            uid=uid,
            session_id=session_id,
            source="transcript",
            score=analysis.score,
            confidence=analysis.confidence,
            markers=markers,
            context_excerpt=excerpt(text, 500),
            omi_memory_created=omi_memory_created,
        )

    should_notify = (
        analysis.score >= settings.notify_threshold
        or analysis.grounding_request
    ) and storage.notification_allowed(uid, session_id, settings.notification_cooldown_seconds)

    storage.save_transcript_event(
        uid=uid,
        session_id=session_id,
        text=text,
        score=analysis.score,
        confidence=analysis.confidence,
        markers=markers,
        notification_sent=should_notify,
    )

    response: dict[str, Any] = {
        "session_id": session_id,
        "status": "ok",
        "analysis": {
            "score": analysis.score,
            "confidence": analysis.confidence,
            "explicit_log_request": analysis.explicit_log_request,
            "grounding_request": analysis.grounding_request,
            "summary": analysis.summary,
            "markers": markers,
            "local_log_created": should_log_locally,
            "omi_memory_created": omi_memory_created,
        },
    }

    if should_notify:
        response["notification"] = {
            "prompt": notification_prompt(analysis.summary, grounding_request=analysis.grounding_request),
            "params": ["user_name", "user_context"],
        }

    return JSONResponse(response)


@app.post("/audio")
async def audio(
    request: Request,
    uid: str | None = None,
    session_id: str | None = None,
    sample_rate: int = 16000,
    token: str | None = Query(default=None),
) -> dict[str, Any]:
    validate_webhook_token(token, request)

    content_type = request.headers.get("content-type", "")
    if "application/octet-stream" not in content_type and content_type:
        # Be permissive for test tools, but note it.
        pass

    audio_bytes = await request.body()
    features = audio_features_from_pcm16(audio_bytes, sample_rate=sample_rate)
    previous = storage.previous_audio_features(uid, session_id)
    shift_score, shift_markers = audio_shift_marker(features, previous)

    storage.save_audio_features(uid=uid, session_id=session_id, sample_rate=sample_rate, features=features)

    if settings.store_raw_audio:
        raw_dir = Path(settings.raw_audio_dir)
        raw_dir.mkdir(parents=True, exist_ok=True)
        safe_uid = (uid or "unknown").replace("/", "_")
        safe_session = (session_id or "unknown").replace("/", "_")
        raw_path = raw_dir / f"{safe_uid}_{safe_session}_{storage.now_iso().replace(':', '-')}.pcm16"
        raw_path.write_bytes(audio_bytes)

    if shift_score > 0:
        markers = markers_to_dicts(shift_markers)
        storage.save_state_shift_log(
            uid=uid,
            session_id=session_id,
            source="audio_features",
            score=shift_score,
            confidence="low",
            markers=markers,
            context_excerpt="Audio feature shift only; no transcript text attached.",
            omi_memory_created=False,
        )

    return {
        "status": "ok",
        "features": features.__dict__,
        "audio_shift_score": round(shift_score, 3),
        "audio_shift_markers": markers_to_dicts(shift_markers),
        "note": "Audio features are weak context markers only, not proof of a switch.",
    }


@app.get("/logs")
async def logs(
    request: Request,
    uid: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    validate_admin(request)
    limit = max(1, min(limit, 200))
    return {"logs": storage.get_logs(uid=uid, limit=limit)}


@app.post("/prune")
async def prune(request: Request) -> dict[str, Any]:
    validate_admin(request)
    return {"deleted": storage.prune_old(settings.retention_days)}


@app.post("/manual-analyze")
async def manual_analyze(request: Request) -> dict[str, Any]:
    validate_admin(request)
    payload = await request.json()
    text = str(payload.get("text", ""))
    previous = payload.get("previous_texts") or []
    if not isinstance(previous, list):
        previous = []
    analysis = analyze_transcript(text, previous_texts=[str(item) for item in previous])
    return {
        "score": analysis.score,
        "confidence": analysis.confidence,
        "explicit_log_request": analysis.explicit_log_request,
        "grounding_request": analysis.grounding_request,
        "summary": analysis.summary,
        "markers": markers_to_dicts(analysis.markers),
    }
