# State Shift Logger for Omi

A private Omi integration app for tracking **possible** state shifts, dissociation markers, switching/blending/co-fronting cues, shutdown markers, or self-reported DID/system state changes.

This app is intentionally cautious. It does **not** diagnose, identify alters/headmates, or claim that a switch definitely happened. It only flags possible patterns and helps create structured logs.

## What it does

- Receives Omi real-time transcript webhook events.
- Looks for possible state-shift markers in wording, self-reference, pronouns, memory-continuity language, dissociation language, and explicit commands like:
  - "Omi, DID log"
  - "Omi, state shift log"
  - "Omi, log this as a possible switch"
- Optionally receives raw audio bytes and extracts non-identifying audio features:
  - chunk duration
  - RMS energy
  - peak amplitude
  - zero-crossing rate
  - rough pitch estimate when possible
- Stores structured local logs in SQLite.
- Optionally creates Omi memories for explicit logs.
- Optionally returns proactive notification prompts to Omi.

## Safety guardrails

This is for self-tracking and reflection only.

It does not:
- diagnose DID or dissociation
- identify who is fronting
- prove that a switch happened
- provide emergency mental health care
- replace a clinician, therapist, neurologist, psychiatrist, or crisis support

Language is always "possible marker," not proof.

## Files

```text
app/
  main.py              FastAPI routes
  config.py            environment settings
  detectors.py         transcript + audio analysis
  omi_client.py        optional Omi memory creation
  storage.py           SQLite persistence
  schemas.py           pydantic models/helpers
scripts/
  smoke_test.py        local test script
tests/
  test_detectors.py    basic detector tests
static/
  icon.png             app icon
  icon.svg             editable vector icon
omi_listing.md         paste-ready Omi app listing fields
.env.example           environment template
requirements.txt       Python dependencies
Dockerfile             container deploy
Procfile               Render/Railway style launch
render.yaml            Render blueprint starter
```

## Quick local start

```bash
python -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env

uvicorn app.main:app --reload --port 8000
```

Open:

```text
http://127.0.0.1:8000/healthz
```

## Test the webhook locally

In another terminal:

```bash
python scripts/smoke_test.py
```

Or use curl:

```bash
curl -X POST "http://127.0.0.1:8000/webhook?uid=test-user&session_id=test-session" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id":"test-session",
    "segments":[
      {"text":"I feel far away from myself.", "speaker":"SPEAKER_00", "is_user":true},
      {"text":"Omi DID log. I do not remember what I just said.", "speaker":"SPEAKER_00", "is_user":true}
    ]
  }'
```

## Deploy

Any HTTPS host that can run FastAPI works:

- Render
- Railway
- Fly.io
- Replit Deployments
- a VPS
- Docker-compatible hosts

Omi integration webhooks need a public HTTPS URL.

Example public webhook:

```text
https://your-domain.com/webhook
```

If you set `WEBHOOK_SHARED_SECRET`, use:

```text
https://your-domain.com/webhook?token=YOUR_SECRET
```

Audio endpoint:

```text
https://your-domain.com/audio?token=YOUR_SECRET
```

Setup-completed endpoint:

```text
https://your-domain.com/setup-completed
```

## Environment variables

See `.env.example`.

Important ones:

```text
WEBHOOK_SHARED_SECRET=
ADMIN_TOKEN=
OMI_APP_ID=
OMI_API_KEY=
CREATE_OMI_MEMORY_ON_EXPLICIT_LOG=true
CREATE_OMI_MEMORY_ON_HIGH_CONFIDENCE=false
NOTIFY_THRESHOLD=0.55
LOG_THRESHOLD=0.65
DATABASE_PATH=./state_shift_logger.sqlite3
```

### Omi memory creation

To let this app create Omi memories, set:

```text
OMI_APP_ID=your_omi_app_id
OMI_API_KEY=your_omi_app_api_key
CREATE_OMI_MEMORY_ON_EXPLICIT_LOG=true
```

By default, the app only creates Omi memories when the user explicitly says a logging phrase such as "Omi DID log" or "log this."

## Omi app form fields

See `omi_listing.md`.

Suggested capability:

```text
External Integration
Smart Notifications
```

Suggested trigger:

```text
transcript_processed
```

Suggested scopes:

```text
Create memories: ON, if you want Omi memories created
Read conversations: ON, if available and needed
Read memories: optional
Create conversations: OFF
Read tasks: OFF
```

## Privacy notes

- Raw audio is not stored by default.
- SQLite logs are stored locally on your server.
- Do not make this public until you have tested it carefully.
- Keep `OMI_API_KEY` and `WEBHOOK_SHARED_SECRET` out of GitHub.
- Use a private repo while testing.

## Admin endpoints

If `ADMIN_TOKEN` is set, use:

```bash
curl "https://your-domain.com/logs?uid=test-user" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN"
```

Without `ADMIN_TOKEN`, admin endpoints are disabled by default.

## Next upgrades

Good next-version ideas:

1. Add a tiny private web dashboard.
2. Add encrypted log storage.
3. Add user-controlled retention and delete/export.
4. Add "known parts/headmates" only if the user explicitly configures them.
5. Add better audio baselines after several days of recordings.
6. Add a therapy-ready weekly export.
7. Add a "do not analyze, just ground me" mode.
