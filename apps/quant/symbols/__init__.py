# Everything about telling which company a ticker belongs to:
#   edgar.py    - downloads/caches the SEC ticker -> CIK mapping (permanent company ids)
#   matching.py - share-class rules (GOOG/GOOGL etc.) so those never get merged
#   dumps.py    - read/write helpers for the dump CSV files
