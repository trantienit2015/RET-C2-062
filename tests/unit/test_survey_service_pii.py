# RET-C2-062 - Unit tests: PII / credential redaction helpers (framework detectors + residual phone pattern)

from src.services import survey_service as svc


def _strip(comment: str) -> tuple[str, int]:
    cleaned, count = svc.strip_pii([{"likert": {}, "comment": comment}])
    return cleaned[0]["comment"], count


def test_email_is_redacted():
    text, count = _strip("連絡先 taro@example.com です")
    assert "taro@example.com" not in text
    assert count == 1


def test_hyphenated_and_compact_phone_numbers_are_redacted():
    text, _ = _strip("電話 03-1234-5678 または 0312345678 まで")
    assert "03-1234-5678" not in text
    assert "0312345678" not in text


def test_card_number_and_jwt_are_redacted():
    text, _ = _strip("カード 4111 1111 1111 1111 / token eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.sig")
    assert "4111 1111 1111 1111" not in text
    assert "eyJhbGci" not in text


def test_title_case_words_and_scores_are_not_redacted():
    text, count = _strip("Great Service でした。満足度 4 点")
    assert text == "Great Service でした。満足度 4 点"
    assert count == 0


def test_contains_pii_on_aggregate_report():
    assert svc.contains_pii('{"summary": "contact taro@example.com"}') is True
    assert svc.contains_pii('{"summary": "当期の調査回答は2件", "negative_rate": 0.5}') is False
