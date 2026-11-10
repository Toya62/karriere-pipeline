import pytest
from src.automation.form_filler import fuzzy_score, OPTION_SELECTORS, ATSFormFiller, load_candidate_profile


def test_fuzzy_score():
    # Exact match
    assert fuzzy_score("Germany", "Germany") == 1.0
    assert fuzzy_score("yes", "YES") == 1.0

    # Substring match
    assert fuzzy_score("Germany", "Germany (+49)") == 0.8
    assert fuzzy_score("M.Sc.", "M.Sc. Computer Science") == 0.8

    # Word overlap
    score = fuzzy_score("driver license", "valid driver license required")
    assert score >= 0.3

    # Zero overlap
    assert fuzzy_score("Python", "Java Spring Boot") == 0.0
    assert fuzzy_score("", "Germany") == 0.0


def test_option_selectors():
    assert ".select__option" in OPTION_SELECTORS
    assert '[role="option"]' in OPTION_SELECTORS
    assert "div[data-value]" in OPTION_SELECTORS


def test_candidate_profile_and_filler_init():
    candidate = load_candidate_profile()
    filler = ATSFormFiller(candidate)
    assert filler.candidate is not None
    assert "email" in filler.candidate
    assert "phone" in filler.candidate
    assert filler.candidate.get("city") == "Essen"
    assert filler.candidate.get("postal_code") == "45144"
    assert "Kerckhoff Str" in filler.candidate.get("street", "")


@pytest.mark.anyio
async def test_react_safe_fill_mock():
    from unittest.mock import AsyncMock, MagicMock
    filler = ATSFormFiller()
    mock_page = MagicMock()
    mock_loc = MagicMock()
    mock_loc.count = AsyncMock(return_value=1)
    mock_loc.is_visible = AsyncMock(return_value=True)
    mock_loc.evaluate = AsyncMock(return_value=None)
    mock_page.locator.return_value.first = mock_loc

    results = {"filled_fields": []}
    ok = await filler._react_safe_fill(mock_page, "input[name='first_name']", "Toyanath", "First Name", results)
    assert ok is True
    assert len(results["filled_fields"]) == 1
    assert results["filled_fields"][0]["value"] == "Toyanath"
    mock_loc.evaluate.assert_awaited_once()


@pytest.mark.anyio
async def test_workday_radio_questions_mock():
    from unittest.mock import AsyncMock, MagicMock
    filler = ATSFormFiller({"work_auth_eu": True})
    mock_page = MagicMock()

    # Create mock fieldset
    mock_fs = MagicMock()
    mock_fs.is_visible = AsyncMock(return_value=True)
    mock_fs.text_content = AsyncMock(return_value="Are you legally authorized to work in Germany?")

    mock_radio_yes = MagicMock()
    mock_radio_yes.is_checked = AsyncMock(return_value=False)
    mock_radio_yes.click = AsyncMock()
    mock_radio_yes.get_attribute = AsyncMock(return_value="Yes")
    mock_radio_yes.locator.return_value.text_content = AsyncMock(return_value="Yes")

    mock_radio_no = MagicMock()
    mock_radio_no.is_checked = AsyncMock(return_value=False)
    mock_radio_no.click = AsyncMock()
    mock_radio_no.get_attribute = AsyncMock(return_value="No")
    mock_radio_no.locator.return_value.text_content = AsyncMock(return_value="No")

    mock_fs.locator.return_value.all = AsyncMock(return_value=[mock_radio_yes, mock_radio_no])
    mock_page.locator.return_value.all = AsyncMock(return_value=[mock_fs])

    results = {"filled_fields": []}
    count = await filler._handle_workday_radio_questions(mock_page, results)
    assert count == 1
    assert results["filled_fields"][0]["value"] == "Yes"
    mock_radio_yes.click.assert_awaited_once()
