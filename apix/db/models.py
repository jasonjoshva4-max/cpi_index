"""SQLAlchemy ORM models for APIx analytical database."""
from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Float,
    Index,
    Integer,
    String,
    UniqueConstraint,
)

from apix.db.database import Base


class RawQuote(Base):
    """Raw scraped JSON records prior to cleaning."""

    __tablename__ = "raw_quotes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String, nullable=False, index=True)
    source = Column(String, nullable=False, index=True)
    payload = Column(JSON, nullable=False)
    scraped_at = Column(String, nullable=False)


class FareClean(Base):
    """Cleaned, validated, and normalized airfare quotes."""

    __tablename__ = "fares_clean"

    quote_id = Column(String, primary_key=True)
    route_id = Column(String, nullable=False, index=True)
    carrier = Column(String, nullable=False, index=True)
    flight_no = Column(String, nullable=False)
    lead_days = Column(Integer, nullable=False, index=True)
    fare_type = Column(String, nullable=False, default="economy")
    base_fare = Column(Float, nullable=True)
    taxes = Column(Float, nullable=True)
    udf = Column(Float, nullable=True)
    conv_fee = Column(Float, nullable=True)
    total_fare = Column(Float, nullable=False)
    search_date = Column(String, nullable=False, index=True)  # YYYY-MM-DD
    travel_date = Column(String, nullable=False, index=True)  # YYYY-MM-DD
    stops = Column(Integer, nullable=False, default=0)
    dep_band = Column(String, nullable=False)  # early_morning, morning, afternoon, evening, night
    status = Column(String, nullable=False, default="available")  # available, sold_out, cancelled
    outlier_flag = Column(Boolean, nullable=False, default=False)
    run_id = Column(String, nullable=False, index=True)

    __table_args__ = (
        Index(
            "idx_fares_clean_lookup",
            "route_id",
            "search_date",
            "lead_days",
            "carrier",
        ),
    )


class RouteModel(Base):
    """Air route metadata and DGCA traffic weights."""

    __tablename__ = "routes"

    route_id = Column(String, primary_key=True)  # e.g., DEL-BOM
    origin = Column(String, nullable=False)
    destination = Column(String, nullable=False)
    dgca_pax = Column(Float, nullable=False, default=1.0)
    weight = Column(Float, nullable=False, default=1.0)  # Normalized weight
    active = Column(Boolean, nullable=False, default=True)


class PriceRelative(Base):
    """Computed price relatives per cell and date."""

    __tablename__ = "price_relatives"

    id = Column(Integer, primary_key=True, autoincrement=True)
    cell_id = Column(String, nullable=False, index=True)
    date = Column(String, nullable=False, index=True)  # YYYY-MM-DD
    relative = Column(Float, nullable=False)
    base_relative = Column(Float, nullable=True)
    n_obs = Column(Integer, nullable=False, default=1)

    __table_args__ = (
        UniqueConstraint("cell_id", "date", name="uq_price_relatives_cell_date"),
    )


class ApixDaily(Base):
    """Daily national APIx price index."""

    __tablename__ = "apix_daily"

    date = Column(String, primary_key=True)  # YYYY-MM-DD
    level = Column(Float, nullable=False)
    base_fare_level = Column(Float, nullable=True)
    tax_level = Column(Float, nullable=True)
    n_cells = Column(Integer, nullable=False)


class ApixWeekly(Base):
    """Weekly national APIx price index rollup."""

    __tablename__ = "apix_weekly"

    date = Column(String, primary_key=True)  # YYYY-MM-DD (end of week)
    level = Column(Float, nullable=False)
    base_fare_level = Column(Float, nullable=True)
    tax_level = Column(Float, nullable=True)
    n_cells = Column(Integer, nullable=False)


class ApixMonthly(Base):
    """Monthly national APIx price index rollup."""

    __tablename__ = "apix_monthly"

    date = Column(String, primary_key=True)  # YYYY-MM
    level = Column(Float, nullable=False)
    base_fare_level = Column(Float, nullable=True)
    tax_level = Column(Float, nullable=True)
    n_cells = Column(Integer, nullable=False)


class RouteIndex(Base):
    """Route-level price index."""

    __tablename__ = "route_index"

    id = Column(Integer, primary_key=True, autoincrement=True)
    route_id = Column(String, nullable=False, index=True)
    date = Column(String, nullable=False, index=True)
    level = Column(Float, nullable=False)
    base_fare_level = Column(Float, nullable=True)

    __table_args__ = (
        UniqueConstraint("route_id", "date", name="uq_route_index_route_date"),
    )


class DgcaReference(Base):
    """DGCA official passenger fare reference benchmarks."""

    __tablename__ = "dgca_reference"

    id = Column(Integer, primary_key=True, autoincrement=True)
    month = Column(String, nullable=False, index=True)  # YYYY-MM
    route_or_national = Column(String, nullable=False)
    avg_fare = Column(Float, nullable=False)


class Anomaly(Base):
    """Flagged fare surges and anomalies per route and lead window."""

    __tablename__ = "anomalies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    route_id = Column(String, nullable=False, index=True)
    date = Column(String, nullable=False, index=True)  # YYYY-MM-DD
    lead_days = Column(Integer, nullable=False, index=True)
    score = Column(Float, nullable=False)  # robust_z
    pct_from_expected = Column(Float, nullable=False)
    direction = Column(String, nullable=False)  # surge or drop
    flag = Column(Boolean, nullable=False, default=True)


class Volatility(Base):
    """Route volatility score and tercile band rankings."""

    __tablename__ = "volatility"

    id = Column(Integer, primary_key=True, autoincrement=True)
    route_id = Column(String, nullable=False, index=True)
    window_end = Column(String, nullable=False, index=True)  # YYYY-MM-DD
    value = Column(Float, nullable=False)  # std(ln(p_t / p_{t-1}))
    band = Column(String, nullable=False)  # High, Medium, Low


class EventModel(Base):
    """Curated events calendar (festivals, holidays, disruptions, weather)."""

    __tablename__ = "events"

    event_id = Column(String, primary_key=True)
    date_start = Column(String, nullable=False, index=True)  # YYYY-MM-DD
    date_end = Column(String, nullable=False, index=True)    # YYYY-MM-DD
    type = Column(String, nullable=False)  # festival, holiday, disruption, weather, news
    region = Column(String, nullable=False, index=True)  # DEL, BOM, CCU, MAA, BLR, HYD, National
    source = Column(String, nullable=False)
    note = Column(String, nullable=True)


class MacroSeries(Base):
    """Macroeconomic indicator series (ATF, Brent Crude, USD/INR)."""

    __tablename__ = "macro_series"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(String, nullable=False, index=True)  # YYYY-MM-DD
    series = Column(String, nullable=False, index=True)  # atf_price_kl, brent_crude_bbl, usdinr_rate
    value = Column(Float, nullable=False)

    __table_args__ = (
        UniqueConstraint("date", "series", name="uq_macro_series_date_series"),
    )


class ForecastRun(Base):
    """Persisted forecast outputs, interval spreads, and accuracy scores against baselines."""

    __tablename__ = "forecasts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_date = Column(String, nullable=False, index=True)    # YYYY-MM-DD
    target_date = Column(String, nullable=False, index=True) # YYYY-MM-DD
    route_id = Column(String, nullable=True, index=True)    # Route ID or None for National
    level = Column(Float, nullable=False)                   # Point forecast
    lower = Column(Float, nullable=False)                   # Lower interval bound
    upper = Column(Float, nullable=False)                   # Upper interval bound
    model = Column(String, nullable=False)                  # Model identifier or 'seasonal_naive'
    beats_baselines = Column(Boolean, nullable=False, default=True)
    mae = Column(Float, nullable=True)
    mape = Column(Float, nullable=True)



