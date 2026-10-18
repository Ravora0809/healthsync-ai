from app.services.vaccination import _suggestions


def test_vaccination_card_suggestions_need_review():
    result = _suggestions("VACCINATION CARD\nHepatitis B\nDose 2\nDate: 2025-02-10\nNext due 2025-08-10")
    assert result["suggested_name"] == "Hepatitis B"
    assert result["suggested_date_received"] == "2025-02-10"
    assert result["suggested_next_due"] == "2025-08-10"
    assert result["suggested_dose"] == "2"
    assert result["needs_review"] is True


def test_vaccination_suggestions_do_not_invent_dates_or_names():
    result = _suggestions("A faded card with handwriting that cannot be read")
    assert result["suggested_name"] == ""
    assert result["suggested_date_received"] == ""
    assert result["suggested_next_due"] == ""
    assert result["needs_review"] is True
