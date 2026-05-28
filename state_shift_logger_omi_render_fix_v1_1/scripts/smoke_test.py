import json
import urllib.request

payload = {
    "session_id": "local-smoke-test",
    "segments": [
        {
            "text": "I feel far away from myself and I don't remember what I was saying.",
            "speaker": "SPEAKER_00",
            "is_user": True,
        },
        {
            "text": "Omi DID log this as a possible switch marker.",
            "speaker": "SPEAKER_00",
            "is_user": True,
        },
    ],
}

req = urllib.request.Request(
    "http://127.0.0.1:8000/webhook?uid=test-user&session_id=local-smoke-test",
    data=json.dumps(payload).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST",
)

with urllib.request.urlopen(req) as response:
    print(response.status)
    print(response.read().decode("utf-8"))
