"""
Unit tests for standards-based form filler engine:
- Telephony parsing (Google libphonenumber style: dial code, national digits, international, e164)
- German address deconstruction (street name vs house number, blank line 2, postal code, city, state)
- ISO-3166-1 Country synonym resolution (Deutschland, Germany, DE, DEU)
- ISO-3166-2 German Federal States resolution (Nordrhein-Westfalen, NRW, postal code inference)
"""

import pytest
from src.automation.form_filler import (
    parse_phone_number,
    parse_address,
    get_country_aliases,
    get_state_aliases,
    load_candidate_profile,
    ISO_COUNTRIES,
    ISO_GERMAN_STATES,
)


def test_parse_phone_number_german_mobile():
    phone_info = parse_phone_number("+49 159 063 77419")
    assert phone_info["dial_code"] == "+49"
    assert phone_info["dial_code_digits"] == "49"
    assert phone_info["national_digits"] == "15906377419"
    assert phone_info["leading_zero"] == "015906377419"
    assert phone_info["e164"] == "+4915906377419"
    assert "159 063 77419" in phone_info["international"]


def test_parse_phone_number_leading_zero():
    phone_info = parse_phone_number("015906377419")
    assert phone_info["dial_code"] == "+49"
    assert phone_info["dial_code_digits"] == "49"
    assert phone_info["national_digits"] == "15906377419"
    assert phone_info["e164"] == "+4915906377419"


def test_parse_phone_number_double_zero_prefix():
    phone_info = parse_phone_number("0049 159 063 77419")
    assert phone_info["dial_code"] == "+49"
    assert phone_info["national_digits"] == "15906377419"
    assert phone_info["e164"] == "+4915906377419"


def test_parse_address_german_street_and_number():
    candidate = {
        "street": "Kerckhoff Str. 146",
        "location": "Kerckhoff Str. 146, 45144 Essen",
        "postal_code": "45144",
        "city": "Essen",
        "country": "Germany",
    }
    addr = parse_address(candidate)
    assert addr["line1"] == "Kerckhoff Str. 146"
    assert addr["street_name"] == "Kerckhoff Str."
    assert addr["house_number"] == "146"
    assert addr["line2"] == ""  # Never duplicates line 1
    assert addr["postal_code"] == "45144"
    assert addr["city"] == "Essen"
    assert addr["state"] == "Nordrhein-Westfalen"
    assert "nordrhein-westfalen" in addr["state_aliases"]
    assert "nrw" in addr["state_aliases"]


def test_parse_address_from_location_fallback():
    candidate = {
        "street": "",
        "location": "Kerckhoff Str. 146, 45144 Essen",
    }
    addr = parse_address(candidate)
    assert addr["street_name"] == "Kerckhoff Str."
    assert addr["house_number"] == "146"
    assert addr["postal_code"] == "45144"
    assert addr["city"] == "Essen"


def test_get_country_aliases():
    de_aliases = get_country_aliases("Germany")
    assert "deutschland" in de_aliases
    assert "germany" in de_aliases
    assert "de" in de_aliases
    assert "deu" in de_aliases

    # Test reverse lookup from "Deutschland"
    de_aliases_rev = get_country_aliases("Deutschland")
    assert "germany" in de_aliases_rev

    # Test ISO 2-letter code
    de_aliases_code = get_country_aliases("DE")
    assert "deutschland" in de_aliases_code


def test_get_state_aliases_and_postal_inference():
    # Direct match
    nrw_aliases = get_state_aliases("Nordrhein-Westfalen")
    assert "nrw" in nrw_aliases
    assert "nordrhein-westfalen" in nrw_aliases

    # Postal code inference (PLZ 4xxxx -> NRW)
    inferred_nrw = get_state_aliases("", "45144")
    assert "nrw" in inferred_nrw

    # Postal code inference (PLZ 8xxxx -> Bayern)
    inferred_by = get_state_aliases("", "80331")
    assert "bayern" in inferred_by


def test_load_candidate_profile_structured_attributes():
    profile = load_candidate_profile()
    assert profile["full_name"] == "Toyanath Pandey"
    assert profile["first_name"] == "Toyanath"
    assert profile["last_name"] == "Pandey"
    assert "phone_info" in profile
    assert profile["phone_info"]["dial_code"] == "+49"
    assert "addr_info" in profile
    assert profile["addr_info"]["street_name"] == "Kerckhoff Str."
    assert profile["addr_info"]["house_number"] == "146"
    assert profile["addr_info"]["line2"] == ""
    assert "country_aliases" in profile
    assert "deutschland" in profile["country_aliases"]
