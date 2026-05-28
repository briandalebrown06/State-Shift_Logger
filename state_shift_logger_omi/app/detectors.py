from __future__ import annotations

import math
import re
from dataclasses import dataclass, asdict
from typing import Any

import numpy as np


@dataclass
class Marker:
    category: str
    label: str
    evidence: str
    weight: float


@dataclass
class TextAnalysis:
    score: float
    confidence: str
    explicit_log_request: bool
    grounding_request: bool
    markers: list[Marker]
    summary: str


@dataclass
class AudioFeatures:
    duration_seconds: float
    rms: float
    peak: float
    zero_crossing_rate: float
    estimated_pitch_hz: float | None


EXPLICIT_LOG_PATTERNS = [
    r"\bomi[, ]+(did|dissociation|state shift|switch|system)\s+log\b",
    r"\blog this\b.*\b(possible )?(switch|state shift|dissociation|blend|co-?front)",
    r"\bpossible switch\b",
    r"\bstate shift log\b",
    r"\bdid log\b",
]

GROUNDING_PATTERNS = [
    r"\bgrounding mode\b",
    r"\bground me\b",
    r"\bhelp me ground\b",
    r"\bi need to ground\b",
    r"\bi feel unsafe\b",
]

MARKER_PATTERNS: list[tuple[str, str, str, float]] = [
    ("memory_continuity", "memory gap language", r"\b(i don'?t remember|i can'?t remember|lost time|missing time|what did i just say|what was i saying|did i say that|when did that happen)\b", 0.25),
    ("dissociation", "distance from self", r"\b(far away|not in my body|watching myself|outside my body|automatic|not real|dreamlike|floaty|detached|zoned out)\b", 0.22),
    ("self_reference", "plural or shifted self-reference", r"\b(we|us|our|ourselves)\b", 0.10),
    ("system_language", "system/did terminology", r"\b(fronting|co-?fronting|blend(?:ing)?|switch(?:ed|ing)?|alter|headmate|part|system)\b", 0.22),
    ("state_description", "state/age/emotion shift language", r"\b(i feel little|childlike|younger|not like myself|not me|someone else|protective|blank|flat|shut down|shutdown)\b", 0.20),
    ("confusion", "orientation confusion", r"\b(where am i|what happened|how did i get here|what time is it|why am i here)\b", 0.25),
    ("trigger", "trigger language", r"\b(triggered|activated|set off|something changed|something shifted)\b", 0.15),
    ("voice", "voice change self-report", r"\b(my voice changed|voice sounds different|different voice|sound different|talking different|words changed)\b", 0.25),
    ("fatigue_stress", "fatigue/stress caveat marker", r"\b(exhausted|tired|fatigued|stressed|panicking|panic|overwhelmed|migraine|pain)\b", 0.08),
]


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def excerpt(text: str, max_len: int = 140) -> str:
    clean = re.sub(r"\s+", " ", text.strip())
    if len(clean) <= max_len:
        return clean
    return clean[: max_len - 1].rstrip() + "…"


def lexical_features(text: str) -> dict[str, float]:
    clean = text.strip()
    words = re.findall(r"\b[\w']+\b", clean.lower())
    if not words:
        return {
            "word_count": 0,
            "avg_word_len": 0,
            "caps_ratio": 0,
            "question_ratio": 0,
            "exclamation_ratio": 0,
            "first_person_singular": 0,
            "first_person_plural": 0,
        }

    alpha_chars = [ch for ch in clean if ch.isalpha()]
    caps = sum(1 for ch in alpha_chars if ch.isupper())
    return {
        "word_count": float(len(words)),
        "avg_word_len": float(sum(len(w) for w in words) / max(1, len(words))),
        "caps_ratio": float(caps / max(1, len(alpha_chars))),
        "question_ratio": float(clean.count("?") / max(1, len(clean))),
        "exclamation_ratio": float(clean.count("!") / max(1, len(clean))),
        "first_person_singular": float(sum(1 for w in words if w in {"i", "me", "my", "mine", "myself"}) / max(1, len(words))),
        "first_person_plural": float(sum(1 for w in words if w in {"we", "us", "our", "ours", "ourselves"}) / max(1, len(words))),
    }


def style_shift_score(current_text: str, previous_texts: list[str]) -> tuple[float, list[Marker]]:
    """Simple, cautious style shift signal.

    This is intentionally weak because style can change for many ordinary reasons.
    """
    if not previous_texts:
        return 0.0, []

    current = lexical_features(current_text)
    previous_blob = "\n".join(previous_texts[-5:])
    previous = lexical_features(previous_blob)

    markers: list[Marker] = []
    score = 0.0

    if previous["word_count"] >= 20 and current["word_count"] >= 5:
        plural_delta = abs(current["first_person_plural"] - previous["first_person_plural"])
        caps_delta = abs(current["caps_ratio"] - previous["caps_ratio"])
        q_delta = abs(current["question_ratio"] - previous["question_ratio"])
        ex_delta = abs(current["exclamation_ratio"] - previous["exclamation_ratio"])

        if plural_delta > 0.04:
            markers.append(Marker("style_shift", "self-reference distribution changed", f"plural pronoun ratio changed by {plural_delta:.2f}", 0.08))
            score += 0.08

        if caps_delta > 0.15:
            markers.append(Marker("style_shift", "capitalization energy changed", f"caps ratio changed by {caps_delta:.2f}", 0.05))
            score += 0.05

        if q_delta > 0.03:
            markers.append(Marker("style_shift", "question pattern changed", f"question mark ratio changed by {q_delta:.2f}", 0.05))
            score += 0.05

        if ex_delta > 0.03:
            markers.append(Marker("style_shift", "exclamation pattern changed", f"exclamation ratio changed by {ex_delta:.2f}", 0.04))
            score += 0.04

    return min(score, 0.18), markers


def analyze_transcript(text: str, previous_texts: list[str] | None = None) -> TextAnalysis:
    previous_texts = previous_texts or []
    raw = text or ""
    clean = normalize_text(raw)

    markers: list[Marker] = []
    score = 0.0

    explicit_log_request = any(re.search(pattern, clean, flags=re.IGNORECASE) for pattern in EXPLICIT_LOG_PATTERNS)
    grounding_request = any(re.search(pattern, clean, flags=re.IGNORECASE) for pattern in GROUNDING_PATTERNS)

    if explicit_log_request:
        markers.append(Marker("explicit_request", "user asked to log a DID/state-shift event", "explicit logging phrase detected", 0.45))
        score += 0.45

    if grounding_request:
        markers.append(Marker("grounding", "user asked for grounding support", "grounding phrase detected", 0.30))
        score += 0.30

    for category, label, pattern, weight in MARKER_PATTERNS:
        matches = list(re.finditer(pattern, clean, flags=re.IGNORECASE))
        if matches:
            sample = matches[0].group(0)
            # Count repeated matches lightly, but cap the contribution.
            contribution = min(weight + (len(matches) - 1) * 0.04, weight + 0.12)
            markers.append(Marker(category, label, sample, contribution))
            score += contribution

    shift_score, shift_markers = style_shift_score(raw, previous_texts)
    markers.extend(shift_markers)
    score += shift_score

    # A cautious cap. Explicit logs can reach high confidence. Pure heuristics need multiple markers.
    score = min(score, 1.0)

    if explicit_log_request or score >= 0.78:
        confidence = "high"
    elif score >= 0.55:
        confidence = "medium"
    elif score >= 0.35:
        confidence = "low"
    else:
        confidence = "none"

    if not markers:
        summary = "No clear state-shift markers detected."
    else:
        top = sorted(markers, key=lambda m: m.weight, reverse=True)[:3]
        summary = "Possible markers: " + "; ".join(f"{m.label}" for m in top)

    return TextAnalysis(
        score=round(score, 3),
        confidence=confidence,
        explicit_log_request=explicit_log_request,
        grounding_request=grounding_request,
        markers=markers,
        summary=summary,
    )


def audio_features_from_pcm16(audio_bytes: bytes, sample_rate: int) -> AudioFeatures:
    if not audio_bytes:
        return AudioFeatures(0.0, 0.0, 0.0, 0.0, None)

    # Omi sends PCM16 little-endian, mono.
    samples = np.frombuffer(audio_bytes, dtype="<i2")
    if samples.size == 0:
        return AudioFeatures(0.0, 0.0, 0.0, 0.0, None)

    x = samples.astype(np.float32) / 32768.0
    duration = float(samples.size / max(1, sample_rate))
    rms = float(np.sqrt(np.mean(np.square(x))))
    peak = float(np.max(np.abs(x)))

    signs = np.signbit(x)
    zcr = float(np.mean(signs[1:] != signs[:-1])) if x.size > 1 else 0.0

    pitch = estimate_pitch_hz(x, sample_rate)

    return AudioFeatures(
        duration_seconds=round(duration, 3),
        rms=round(rms, 5),
        peak=round(peak, 5),
        zero_crossing_rate=round(zcr, 5),
        estimated_pitch_hz=round(pitch, 2) if pitch else None,
    )


def estimate_pitch_hz(x: np.ndarray, sample_rate: int) -> float | None:
    """Rough pitch estimate using FFT autocorrelation.

    This is not a clinical or biometric identity feature. It is a rough signal only.
    """
    if x.size < sample_rate // 2:
        return None

    # Use at most 2 seconds from the middle to keep this cheap.
    max_n = min(x.size, sample_rate * 2)
    start = max(0, (x.size - max_n) // 2)
    y = x[start : start + max_n].astype(np.float32)

    if np.max(np.abs(y)) < 0.02:
        return None

    y = y - np.mean(y)
    # Hann window to reduce edge artifacts.
    y *= np.hanning(y.size).astype(np.float32)

    n = int(2 ** math.ceil(math.log2(max(2, y.size * 2))))
    spectrum = np.fft.rfft(y, n=n)
    corr = np.fft.irfft(spectrum * np.conj(spectrum), n=n)[: y.size]
    if corr[0] <= 0:
        return None
    corr = corr / corr[0]

    min_hz, max_hz = 60, 350
    min_lag = int(sample_rate / max_hz)
    max_lag = int(sample_rate / min_hz)

    if max_lag >= corr.size:
        return None

    region = corr[min_lag:max_lag]
    if region.size == 0:
        return None

    lag = int(np.argmax(region) + min_lag)
    confidence = float(corr[lag])

    if confidence < 0.18:
        return None

    return float(sample_rate / lag)


def audio_shift_marker(current: AudioFeatures, previous: AudioFeatures | None) -> tuple[float, list[Marker]]:
    """Compare current audio chunk to a recent previous chunk.

    This is intentionally conservative. Audio differences can be fatigue, distance from mic,
    background noise, device placement, pain, anxiety, excitement, or room acoustics.
    """
    if previous is None:
        return 0.0, []

    markers: list[Marker] = []
    score = 0.0

    if previous.rms > 0.005 and current.rms > 0.005:
        ratio = current.rms / previous.rms
        if ratio > 2.5 or ratio < 0.4:
            markers.append(Marker("audio_shift", "speaking energy changed", f"RMS ratio {ratio:.2f}", 0.08))
            score += 0.08

    if current.estimated_pitch_hz and previous.estimated_pitch_hz:
        diff = abs(current.estimated_pitch_hz - previous.estimated_pitch_hz)
        if diff >= 45:
            markers.append(Marker("audio_shift", "rough pitch estimate changed", f"pitch estimate changed by {diff:.1f} Hz", 0.08))
            score += 0.08

    if previous.zero_crossing_rate > 0:
        zratio = current.zero_crossing_rate / previous.zero_crossing_rate
        if zratio > 2.0 or zratio < 0.5:
            markers.append(Marker("audio_shift", "audio texture changed", f"zero-crossing ratio {zratio:.2f}", 0.05))
            score += 0.05

    return min(score, 0.18), markers


def markers_to_dicts(markers: list[Marker]) -> list[dict[str, Any]]:
    return [asdict(marker) for marker in markers]
