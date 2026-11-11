"""Language detection utilities for CV, cover letter, and email generation."""

import re

GERMAN_STOPWORDS = {
    "und", "der", "die", "das", "mit", "für", "von", "im", "in", "zu",
    "den", "dem", "des", "ein", "eine", "einer", "eines", "einem", "einen",
    "wir", "sie", "ihr", "ihre", "ihren", "ihrem", "ihrer", "ihres",
    "sich", "auf", "ist", "sind", "nicht", "bei", "als", "auch", "nach",
    "aus", "durch", "über", "haben", "hat", "werden", "wird", "können",
    "bewerbung", "aufgaben", "anforderungen", "profil", "kenntnisse",
    "wünschenswert", "berufserfahrung", "standort", "entwickler", "vollzeit",
    "teilzeit", "abgeschlossenes", "studium", "mitarbeiter", "unser", "unsere",
    "ihrem", "ihrer", "erfahrung", "bereich", "unternehmen", "bringen", "bietet"
}

ENGLISH_STOPWORDS = {
    "the", "and", "of", "to", "in", "with", "for", "you", "your", "will",
    "that", "is", "are", "our", "this", "have", "has", "from", "as", "at",
    "on", "by", "an", "be", "we", "team", "work", "role", "about",
    "responsibilities", "requirements", "qualifications", "experience",
    "developer", "engineer", "software", "looking", "skills", "full-time",
    "opportunity", "join", "what", "how", "apply", "building", "systems",
    "strong", "working", "degree", "platform", "production", "stack"
}


def detect_language(title: str = "", description: str = "", default: str = "de") -> str:
    """Detect whether German ('de') or English ('en') should be used.
    
    Uses token-based stopword and keyword frequency analysis. If English tokens
    exceed German tokens, returns 'en'. Otherwise defaults to German (DACH market default).
    """
    combined = f"{title} {description}".lower()
    words = re.findall(r"\b[a-zäöüß]+\b", combined)
    if not words:
        return default

    de_count = sum(1 for w in words if w in GERMAN_STOPWORDS)
    en_count = sum(1 for w in words if w in ENGLISH_STOPWORDS)

    # German-specific umlauts and ß provide strong signal
    german_char_hits = len(re.findall(r"[äöüß]", combined))
    if german_char_hits >= 2:
        de_count += 3

    if en_count > de_count:
        return "en"
    if de_count > en_count:
        return "de"
    return default

