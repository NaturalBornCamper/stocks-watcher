import re

# Legal-entity words that don't help tell two companies apart. Kept short on
# purpose: stripping more (like "holdings"/"group") would wrongly merge names
# such as "Graham Corporation" and "Graham Holdings Company".
NAME_SUFFIXES = [
    "incorporated", "inc", "corporation", "corp", "company", "co",
    "limited", "ltd", "plc", "llc", "lp", "ag", "sa", "nv", "se",
]


def normalize_company_name(name: str) -> str:
    """Reduce a company name to a compact matching key: lower-case it, drop any
    trailing legal suffixes (Inc, Corp, S.A. ...), then keep only letters and
    digits (no spaces or punctuation).
    Example: "Pratt & Whitney 1st Co." -> "prattwhitney1st"."""
    # Drop dots first so "S.A." / "Inc." become whole words, then split on
    # anything that is not a letter or digit.
    text = name.lower().replace(".", "")
    words = [word for word in re.split(r"[^a-z0-9]+", text) if word]

    # Remove trailing legal-form words (there can be more than one, e.g. "co inc")
    while words and words[-1] in NAME_SUFFIXES:
        words.pop()
    return "".join(words)


# Letters used to mark share classes (Class A/B/C, and K for Liberty-style tickers).
CLASS_LETTERS = {"A", "B", "C", "K"}


def is_share_class_pair(ticker_a: str, ticker_b: str) -> bool:
    """True only for clear share-class pairs of one company (BRK.A/BRK.B,
    PBR/PBR.A, FWONA/FWONK, NWS/NWSA). A sequential re-ticker like TLNE->TLN is
    left out on purpose so it still gets flagged as a possible change.

    This is only consulted once two tickers are already known to be the same
    company, so leaning on the class-letter rule below is safe."""
    a = ticker_a.upper()
    b = ticker_b.upper()
    if a == b:
        return False

    # Dotted class marker: identical apart from a trailing ".A" / ".B"
    base_a = re.sub(r"\.[A-Z]$", "", a)
    base_b = re.sub(r"\.[A-Z]$", "", b)
    if base_a == base_b:
        return True

    # Same-length tickers differing only in the final letter (FWONA / FWONK)
    if len(a) == len(b) and a[:-1] == b[:-1]:
        return True

    # One ticker is the other plus a trailing class letter (NWS/NWSA, FOX/FOXA).
    # The extra letter must be a known class letter, so TLN/TLNE stays excluded.
    short, long = sorted([a, b], key=len)
    if len(long) - len(short) == 1 and long.startswith(short) and long[-1] in CLASS_LETTERS:
        return True

    return False


def find_same_company(symbol, name, cik, stocks_by_cik, stocks_by_name):
    """Find a stock we already track that is the same company as this one.

    Prefers a CIK match (authoritative); falls back to an exact normalized-name
    match. Returns (matched_stock, matched_by) or (None, "")."""
    if cik:
        match = stocks_by_cik.get(cik)
        if match and match.symbol.upper() != symbol.upper():
            return match, "CIK"

    normalized = normalize_company_name(name)
    if normalized:
        match = stocks_by_name.get(normalized)
        if match and match.symbol.upper() != symbol.upper():
            # If both have a CIK and they differ, they are different companies
            # that merely share a name (e.g. the two "Independent Bank" firms).
            if cik and match.external_id and cik != match.external_id:
                return None, ""
            return match, "name"

    return None, ""


def review_for_match(symbol, matched_symbol, matched_name, matched_by):
    """Return (needs_review, note) describing how this stock relates to an
    existing one. Share-class pairs are noted but not flagged for review."""
    if is_share_class_pair(symbol, matched_symbol):
        return False, f"Share class of {matched_symbol} ({matched_name}) - same company, likely ignore."
    return True, f"Same company as {matched_symbol} ({matched_name}) - matched by {matched_by}."