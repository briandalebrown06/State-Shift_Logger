# Omi App Listing: State Shift Logger

## App Name

```text
State Shift Logger
```

## Category

```text
Health
```

If Omi offers "Wellness," use that instead if you want softer wording.

## Description

```text
State Shift Logger helps track possible dissociation, switching, blending, shutdown, or identity-state shifts by looking for changes in wording, self-reference, pronouns, emotional tone, memory-continuity language, and user-spoken logging cues.

It does not diagnose, identify alters, or claim that a switch definitely occurred. It gently flags possible markers and helps create structured private logs for reflection, therapy, and self-understanding.
```

## Capabilities

Use:

```text
External Integration: ON
Smart Notifications: ON
Chat: OFF for v1
Conversations: optional
```

## Scopes

Start with the smallest useful set:

```text
Create conversations: OFF
Create memories: ON
Read conversations: ON if required by Omi for transcript context
Read memories: optional
Read tasks: OFF
```

## Trigger Event

Use the real-time transcript trigger if available:

```text
transcript_processed
```

or:

```text
Real-time Transcript
```

For audio testing later, create a separate app or endpoint using:

```text
audio_bytes
```

## App Home URL

```text
https://YOUR_DOMAIN.com/
```

## Webhook URL / External Integration URL

```text
https://YOUR_DOMAIN.com/webhook
```

If using a shared secret:

```text
https://YOUR_DOMAIN.com/webhook?token=YOUR_SECRET
```

## Setup Instructions

```text
Install this private app to help track possible dissociation or state-shift markers. The app may analyze transcript patterns such as pronoun changes, wording shifts, self-reference changes, memory-continuity language, and self-reported cues.

It does not diagnose DID, identify who is fronting, or claim that a switch definitely occurred. It only logs possible markers when the user asks to log an event or when a strong marker pattern appears.

Useful phrases:
- "Omi, DID log"
- "Omi, state shift log"
- "Omi, log this as a possible switch"
- "Omi, I feel dissociated"
- "Omi, grounding mode"

Keep this app private while testing.
```

## Setup Completed URL

```text
https://YOUR_DOMAIN.com/setup-completed
```

## Auth URL

Leave blank for private v1.

## Chat Tools Manifest URL

Leave blank for v1.

## GitHub Repository URL

```text
https://github.com/YOUR_USERNAME/state-shift-logger
```

## Make Public

```text
OFF
```

## Paid App

```text
OFF
```
