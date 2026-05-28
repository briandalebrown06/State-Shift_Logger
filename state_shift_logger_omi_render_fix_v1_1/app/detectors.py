from __future__ import annotations

import array
import math
import re
import sys
from dataclasses import dataclass, asdict
from typing import Any


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
            contribution = min(weight + (len(matches) - 1) * 0.04, weight + 0.12)
            markers.append(Marker(category, label, sample, contribution))
            score += contribution

    shift_score, shift_markers = style_shift_score(raw, previous_texts)
    markers.extend(shift_markers)
    score += shift_score

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


def _pcm16_samples(audio_bytes: bytes) -> list[int]:
    if not audio_bytes:
        return []

    usable_len = len(audio_bytes) - (len(audio_bytes) % 2)
    raw = audio_bytes[:usable_len]

    samples = array.array("h")
    samples.frombytes(raw)

    if samples.itemsize != 2:
        return []
    if sys.byteorder != "little":
        samples.byteswap()

    return list(samples)


def audio_features_from_pcm16(audio_bytes: bytes, sample_rate: int) -> AudioFeatures:
    samples = _pcm16_samples(audio_bytes)
    n = len(samples)
    if n == 0 or sample_rate <= 0:
        return AudioFeatures(0.0, 0.0, 0.0, 0.0, None)

    duration = n / sample_rate
    peak_int = max(abs(s) for s in samples)
    peak = peak_int / 32768.0
    rms = math.sqrt(sum((s / 32768.0) ** 2 for s in samples) / n)

    crossings = 0
    prev_positive = samples[0] >= 0
    for sample in samples[1:]:
        positive = sample >= 0
        if positive != prev_positive:
            crossings += 1
        prev_positive = positive
    zcr = crossings / max(1, n - 1)

    pitch = estimate_pitch_hz(samples, sample_rate)

    return AudioFeatures(
        duration_seconds=round(duration, 3),
        rms=round(rms, 5),
        peak=round(peak, 5),
        zero_crossing_rate=round(zcr, 5),
        estimated_pitch_hz=round(pitch, 2) if pitch else None,
    )


def estimate_pitch_hz(samples: list[int], sample_rate: int) -> float | None:
    if len(samples) < sample_rate // 2 or sample_rate <= 0:
        return None

    max_n = min(len(samples), sample_rate)
    start = max(0, (len(samples) - max_n) // 2)
    window = samples[start : start + max_n]

    max_abs = max(abs(s) for s in window) if window else 0
    if max_abs < 700:
        return None

    mean = sum(window) / len(window)
    x = [(s - mean) / 32768.0 for s in window]

    min_hz, max_hz = 60, 350
    min_lag = max(1, int(sample_rate / max_hz))
    max_lag = min(len(x) - 1, int(sample_rate / min_hz))

    if max_lag <= min_lag:
        return None

    best_lag = None
    best_corr = -1.0

    for lag in range(min_lag, max_lag, 2):
        total = 0.0
        count = len(x) - lag
        if count <= 0:
            continue
        for i in range(count):
            total += x[i] * x[i + lag]
        corr = total / count
        if corr > best_corr:
            best_corr = corr
            best_lag = lag

    if best_lag is None or best_corr < 0.01:
        return None

    return sample_rate / best_lag


def audio_shift_marker(current: AudioFeatures, previous: AudioFeatures | None) -> tuple[float, list[Marker]]:
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
