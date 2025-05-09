
class Columns:
    DATE = "Date"
    TYPE = "Type"
    RANK = "Rank"
    SEEKINGALPHA_SYMBOL = "Seeking Alpha Symbol"
    COMPANY_NAME = "Company Name"
    QUANT = "Quant"
    RATING_SEEKING_ALPHA = "Seeking Alpha Rating"
    RATING_WALL_STREET = "Wall Street Rating"
    MARKET_CAP_MILLIONS = "Market Cap (Millions)"
    DIVIDEND_YIELD = "Dividend Yield"
    VALUATION = "Valuation"
    GROWTH = "Growth"
    PROFITABILITY = "Profitability"
    MOMENTUM = "Momentum"
    EPS_REVISION = "EPS Revision"


COLUMN_NAME_VARIANTS = {
    Columns.DATE: [Columns.DATE],
    Columns.TYPE: [Columns.TYPE],
    Columns.RANK: [Columns.RANK],
    Columns.SEEKINGALPHA_SYMBOL: [Columns.SEEKINGALPHA_SYMBOL, "Symbol"],
    Columns.COMPANY_NAME: [Columns.COMPANY_NAME],
    Columns.QUANT: [Columns.QUANT, "Quant Rating"],
    Columns.RATING_SEEKING_ALPHA: [Columns.RATING_SEEKING_ALPHA, "SA Analyst Ratings"],
    Columns.RATING_WALL_STREET: [Columns.RATING_WALL_STREET, "Wall Street Ratings"],
    Columns.MARKET_CAP_MILLIONS: [Columns.MARKET_CAP_MILLIONS, "Market Cap"],
    Columns.DIVIDEND_YIELD: [Columns.DIVIDEND_YIELD, "Div Yield"],
    Columns.VALUATION: [Columns.VALUATION, "Valuation"],
    Columns.GROWTH: [Columns.GROWTH, "Growth"],
    Columns.PROFITABILITY: [Columns.PROFITABILITY, "Profitability"],
    Columns.MOMENTUM: [Columns.MOMENTUM, "Momentum"],
    Columns.EPS_REVISION: [Columns.EPS_REVISION, "EPS Rev."],
}

def find_matching_value(row: dict, possible_names: list) -> str:
    """Find the first non-None value from the row using possible column names."""
    for name in possible_names:
        if name in row and row[name] is not None:
            return row[name]
    return ""
