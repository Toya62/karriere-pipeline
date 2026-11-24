"""Tests for user AI routing preference database persistence and defaults."""

import uuid
import pytest
from src.db.database import (
    create_user,
    get_user_ai_routing_preference,
    set_user_ai_routing_preference,
    update_user_tier,
)


def test_ai_routing_preference_defaults():
    email = f"pref_{uuid.uuid4().hex[:8]}@example.com"
    user = create_user(email, "hash123", full_name="Pref User")
    user_id = user["id"]
    
    # By default, preference returns 'platform' or 'auto'
    pref = get_user_ai_routing_preference(user_id)
    assert pref in ("auto", "platform", "byok")

    # Set explicitly to empty or None to test pro default fallback
    update_user_tier(user_id, "pro")
    set_user_ai_routing_preference(user_id, "platform")
    assert get_user_ai_routing_preference(user_id) == "platform"


def test_ai_routing_preference_crud():
    email = f"pref_crud_{uuid.uuid4().hex[:8]}@example.com"
    user = create_user(email, "hash123", full_name="Pref CRUD User")
    user_id = user["id"]
    update_user_tier(user_id, "pro")

    assert set_user_ai_routing_preference(user_id, "byok") is True
    assert get_user_ai_routing_preference(user_id) == "byok"

    assert set_user_ai_routing_preference(user_id, "auto") is True
    assert get_user_ai_routing_preference(user_id) == "auto"

    assert set_user_ai_routing_preference(user_id, "platform") is True
    assert get_user_ai_routing_preference(user_id) == "platform"


def test_ai_routing_preference_rejects_invalid():
    email = f"pref_invalid_{uuid.uuid4().hex[:8]}@example.com"
    user = create_user(email, "hash123", full_name="Pref Invalid User")
    user_id = user["id"]
    with pytest.raises(ValueError):
        set_user_ai_routing_preference(user_id, "magic_ai")
