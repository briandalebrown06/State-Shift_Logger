from app.detectors import analyze_transcript


def test_explicit_log_request_scores_high():
    result = analyze_transcript("Omi DID log this. I do not remember what I just said.")
    assert result.explicit_log_request is True
    assert result.score >= 0.55
    assert result.confidence in {"medium", "high"}


def test_neutral_text_no_markers():
    result = analyze_transcript("I am going to the store to buy coffee.")
    assert result.score < 0.35
    assert result.confidence == "none"


def test_grounding_request():
    result = analyze_transcript("Omi grounding mode. I feel far away.")
    assert result.grounding_request is True
    assert result.score >= 0.30
