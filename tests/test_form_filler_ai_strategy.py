import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.automation.form_filler import ATSFormFiller

@pytest.mark.anyio
async def test_form_filler_ai_strategy():
    filler = ATSFormFiller()
    mock_page = MagicMock()
    mock_page.evaluate = AsyncMock(return_value=[
        {"field_id": "ai_f_0", "tag": "input", "type": "text", "label": "Full Name", "options": []}
    ])
    mock_locator = MagicMock()
    mock_locator.count = AsyncMock(return_value=1)
    mock_locator.is_visible = AsyncMock(return_value=True)
    mock_locator.fill = AsyncMock()
    mock_page.locator.return_value.first = mock_locator

    mock_resolutions = {
        "success": True,
        "resolutions": [
            {"field_id": "ai_f_0", "action": "set_value", "value": "Toyanath Pandey", "confidence": 1.0}
        ]
    }

    with patch("src.ai.form_resolver.resolve_form_fields", return_value=mock_resolutions):
        results = {"filled_fields": [], "attached_files": []}
        await filler._fill_with_ai(mock_page, "https://jobs.example.com/123", None, None, results)
        assert len(results["filled_fields"]) == 1
        assert results["filled_fields"][0]["value"] == "Toyanath Pandey"
        mock_locator.fill.assert_awaited_once_with("Toyanath Pandey")
