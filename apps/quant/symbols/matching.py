import re

# Letters used to mark share classes (Class A/B/C, and K for Liberty-style tickers)
CLASS_LETTERS = {"A", "B", "C", "K"}


def is_share_class_pair(ticker_a: str, ticker_b: str) -> bool:
    """True only for clear share-class pairs of one company (BRK.A/BRK.B,
    PBR/PBR.A, FWONA/FWONK, NWS/NWSA). A sequential re-ticker like TLNE->TLN is
    left out on purpose so it still counts as a real ticker change.

    Only consulted once two tickers are already known to be the same company
    (same SEC id), so leaning on the class-letter rule below is safe."""
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
