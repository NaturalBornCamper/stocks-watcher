# Everything about telling which company a ticker belongs to:
#   edgar.py    - downloads/caches the SEC ticker -> CIK mapping (permanent company ids)
#   matching.py - rules for spotting the same company under two different tickers

# The curated list of ticker renames. Written by `find_symbol_changes
# --write-renames` and applied to the dump CSVs by `clean_dumps`. It lives in
# data_dumps/ (not data_dumps/seeking_alpha/) so the import and dump-reorganise
# globs never pick it up.
SYMBOL_RENAMES_FILE = "data_dumps/_symbol_renames.csv"
