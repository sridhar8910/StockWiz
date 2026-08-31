from sqlalchemy.orm import Session
from app.models.folio import Folio, FolioStock

FOLIOS_DATA = [
    {
        "name": "Alpha Growth",
        "stocks": [
            {"ticker": "RELIANCE", "base_quantity": 2.0},
            {"ticker": "TCS", "base_quantity": 1.0},
            {"ticker": "INFY", "base_quantity": 1.0},
            {"ticker": "HDFCBANK", "base_quantity": 2.0},
            {"ticker": "ICICIBANK", "base_quantity": 2.0},
            {"ticker": "SBIN", "base_quantity": 3.0},
            {"ticker": "BHARTIARTL", "base_quantity": 1.0},
            {"ticker": "LT", "base_quantity": 1.0},
            {"ticker": "ITC", "base_quantity": 2.0},
            {"ticker": "MARUTI", "base_quantity": 1.0},
            {"ticker": "AXISBANK", "base_quantity": 2.0},
            {"ticker": "SUNPHARMA", "base_quantity": 1.0},
        ],
    },
    {
        "name": "Bluechip Core",
        "stocks": [
            {"ticker": "RELIANCE", "base_quantity": 3.0},
            {"ticker": "TCS", "base_quantity": 2.0},
            {"ticker": "INFY", "base_quantity": 2.0},
            {"ticker": "HDFCBANK", "base_quantity": 3.0},
            {"ticker": "ICICIBANK", "base_quantity": 2.0},
            {"ticker": "SBIN", "base_quantity": 1.0},
            {"ticker": "BHARTIARTL", "base_quantity": 1.0},
            {"ticker": "LT", "base_quantity": 2.0},
            {"ticker": "ITC", "base_quantity": 3.0},
            {"ticker": "MARUTI", "base_quantity": 1.0},
            {"ticker": "AXISBANK", "base_quantity": 1.0},
            {"ticker": "SUNPHARMA", "base_quantity": 1.0},
        ],
    },
    {
        "name": "India Momentum",
        "stocks": [
            {"ticker": "SBIN", "base_quantity": 4.0},
            {"ticker": "RELIANCE", "base_quantity": 2.0},
            {"ticker": "TATAMOTORS", "base_quantity": 3.0},
            {"ticker": "ADANIENT", "base_quantity": 1.0},
            {"ticker": "LTIM", "base_quantity": 2.0},
            {"ticker": "COALINDIA", "base_quantity": 5.0},
            {"ticker": "NTPC", "base_quantity": 4.0},
            {"ticker": "ONGC", "base_quantity": 3.0},
            {"ticker": "POWERGRID", "base_quantity": 4.0},
            {"ticker": "SUNPHARMA", "base_quantity": 2.0},
            {"ticker": "TATASTEEL", "base_quantity": 5.0},
            {"ticker": "HAL", "base_quantity": 2.0},
        ],
    },
    {
        "name": "Dividend Leaders",
        "stocks": [
            {"ticker": "ITC", "base_quantity": 4.0},
            {"ticker": "COALINDIA", "base_quantity": 6.0},
            {"ticker": "RECLTD", "base_quantity": 5.0},
            {"ticker": "PFC", "base_quantity": 5.0},
            {"ticker": "IOC", "base_quantity": 8.0},
            {"ticker": "BPCL", "base_quantity": 6.0},
            {"ticker": "HINDUNILVR", "base_quantity": 2.0},
            {"ticker": "TCS", "base_quantity": 2.0},
            {"ticker": "INFY", "base_quantity": 2.0},
            {"ticker": "HDFCBANK", "base_quantity": 1.0},
            {"ticker": "HINDZINC", "base_quantity": 4.0},
            {"ticker": "GAIL", "base_quantity": 5.0},
        ],
    },
    {
        "name": "Tech Innovators",
        "stocks": [
            {"ticker": "TCS", "base_quantity": 2.0},
            {"ticker": "INFY", "base_quantity": 3.0},
            {"ticker": "WIPRO", "base_quantity": 4.0},
            {"ticker": "HCLTECH", "base_quantity": 3.0},
            {"ticker": "TECHM", "base_quantity": 2.0},
            {"ticker": "LTIM", "base_quantity": 2.0},
            {"ticker": "PERSISTENT", "base_quantity": 3.0},
            {"ticker": "COFORGE", "base_quantity": 2.0},
            {"ticker": "KPITTECH", "base_quantity": 4.0},
            {"ticker": "TATAELXSI", "base_quantity": 2.0},
            {"ticker": "LTTS", "base_quantity": 2.0},
            {"ticker": "OFSS", "base_quantity": 1.0},
        ],
    },
    {
        "name": "Consumer Power",
        "stocks": [
            {"ticker": "HINDUNILVR", "base_quantity": 2.0},
            {"ticker": "ITC", "base_quantity": 3.0},
            {"ticker": "NESTLEIND", "base_quantity": 1.0},
            {"ticker": "BRITANNIA", "base_quantity": 2.0},
            {"ticker": "TATACONSUM", "base_quantity": 3.0},
            {"ticker": "ASIANPAINT", "base_quantity": 2.0},
            {"ticker": "TITAN", "base_quantity": 2.0},
            {"ticker": "MARUTI", "base_quantity": 1.0},
            {"ticker": "M&M", "base_quantity": 2.0},
            {"ticker": "TATAMOTORS", "base_quantity": 2.0},
            {"ticker": "BAJAJ-AUTO", "base_quantity": 1.0},
            {"ticker": "EICHERMOT", "base_quantity": 1.0},
        ],
    },
    {
        "name": "Value Select",
        "stocks": [
            {"ticker": "SBIN", "base_quantity": 3.0},
            {"ticker": "HDFCBANK", "base_quantity": 2.0},
            {"ticker": "ICICIBANK", "base_quantity": 2.0},
            {"ticker": "AXISBANK", "base_quantity": 2.0},
            {"ticker": "BOB", "base_quantity": 4.0},
            {"ticker": "CANBK", "base_quantity": 5.0},
            {"ticker": "UNIONBANK", "base_quantity": 6.0},
            {"ticker": "PNB", "base_quantity": 8.0},
            {"ticker": "HINDALCO", "base_quantity": 3.0},
            {"ticker": "TATASTEEL", "base_quantity": 4.0},
            {"ticker": "JSWSTEEL", "base_quantity": 2.0},
            {"ticker": "SAIL", "base_quantity": 5.0},
        ],
    },
]

def seed_data(db: Session) -> None:
    """
    Ensures all 7 required Folios exist and each has a complete 12-stock composition.
    Heals any missing or partially initialized Folios.
    """
    for folio_info in FOLIOS_DATA:
        stocks = folio_info["stocks"]
        if len(stocks) != 12:
            raise ValueError(f"Folio '{folio_info['name']}' must contain exactly 12 stocks, found {len(stocks)}")
        
        tickers = [s["ticker"].strip().upper() for s in stocks]
        if len(set(tickers)) != 12:
            raise ValueError(f"Folio '{folio_info['name']}' contains duplicate stock tickers")

        for s in stocks:
            if not s["ticker"] or not s["ticker"].strip():
                raise ValueError("Stock ticker cannot be empty")
            if s["base_quantity"] <= 0:
                raise ValueError(f"Base quantity for {s['ticker']} in {folio_info['name']} must be positive")

        folio = db.query(Folio).filter(Folio.name == folio_info["name"]).first()
        if not folio:
            folio = Folio(name=folio_info["name"])
            db.add(folio)
            db.flush()
            for stock_info in folio_info["stocks"]:
                stock = FolioStock(
                    folio_id=folio.id,
                    ticker=stock_info["ticker"].strip().upper(),
                    base_quantity=float(stock_info["base_quantity"]),
                )
                db.add(stock)
        else:
            # Verify and heal stock count if needed
            current_stock_count = db.query(FolioStock).filter(FolioStock.folio_id == folio.id).count()
            if current_stock_count == 0:
                for stock_info in folio_info["stocks"]:
                    stock = FolioStock(
                        folio_id=folio.id,
                        ticker=stock_info["ticker"].strip().upper(),
                        base_quantity=float(stock_info["base_quantity"]),
                    )
                    db.add(stock)
    
    db.commit()
