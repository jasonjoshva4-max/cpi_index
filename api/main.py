"""FastAPI application for APIx real-time airfare price index."""
import csv
import io
import logging
from datetime import datetime
from typing import Any, Literal

from fastapi import Depends, FastAPI, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from apix.config import DEFAULT_BASE_DATE
from apix.db.database import get_db, init_db
from apix.db.models import (
    Anomaly,
    ApixDaily,
    FareClean,
    RouteIndex,
    RouteModel,
    Volatility,
)

logger = logging.getLogger(__name__)

# Initialize database schema
init_db()

app = FastAPI(
    title="APIx Airfare Price Index API",
    description="Real-time airfare price index REST API service.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)


# --- Pydantic Schema Models ---

class Metadata(BaseModel):
    n_obs: int = Field(..., description="Total observation count")
    n_cells: int = Field(..., description="Active elementary cell count")
    base_period: str = Field(DEFAULT_BASE_DATE, description="Base index reference date")
    label: Literal["observed", "estimated", "signal"] = Field("estimated", description="Data provenance label")



class IndexLevelResponse(BaseModel):
    date: str
    level: float
    base_fare_level: float | None = None
    tax_level: float | None = None
    change_pct: float | None = None
    metadata: Metadata


class DailyIndexItem(BaseModel):
    date: str
    level: float
    base_fare_level: float | None = None
    tax_level: float | None = None
    n_cells: int


class DailyIndexResponse(BaseModel):
    data: list[DailyIndexItem]
    metadata: Metadata


class RouteItem(BaseModel):
    route_id: str
    origin: str
    destination: str
    weight: float
    dgca_pax: float
    latest_level: float | None = None
    volatility_band: str | None = "Low"



class RoutesResponse(BaseModel):
    routes: list[RouteItem]
    metadata: Metadata


# --- Helper Functions ---

def get_total_obs_count(db: Session, date_str: str | None = None) -> int:
    query = db.query(FareClean)
    if date_str:
        query = query.filter(FareClean.search_date == date_str)
    return query.count()


# --- API Endpoints ---

@app.get("/api/index", response_model=IndexLevelResponse)
def get_latest_index(db: Session = Depends(get_db)):
    """Returns the latest National APIx level, base-fare series, and percentage change vs previous period."""
    latest = db.query(ApixDaily).order_by(ApixDaily.date.desc()).first()

    if not latest:
        # Fallback response for un-populated database state
        n_obs = get_total_obs_count(db)
        return IndexLevelResponse(
            date=DEFAULT_BASE_DATE,
            level=100.0,
            base_fare_level=100.0,
            tax_level=0.0,
            change_pct=0.0,
            metadata=Metadata(n_obs=n_obs, n_cells=0, base_period=DEFAULT_BASE_DATE, label="estimated"),
        )

    # Compute % change vs previous daily entry if available
    prev = db.query(ApixDaily).filter(ApixDaily.date < latest.date).order_by(ApixDaily.date.desc()).first()
    change_pct = 0.0
    if prev and prev.level > 0:
        change_pct = round(((latest.level - prev.level) / prev.level) * 100.0, 2)

    n_obs = get_total_obs_count(db, latest.date)

    return IndexLevelResponse(
        date=latest.date,
        level=latest.level,
        base_fare_level=latest.base_fare_level,
        tax_level=latest.tax_level,
        change_pct=change_pct,
        metadata=Metadata(
            n_obs=n_obs,
            n_cells=latest.n_cells,
            base_period=DEFAULT_BASE_DATE,
            label="estimated",
        ),
    )


@app.get("/api/index/daily")
def get_daily_index(
    start: str | None = Query(None, description="Start date filter (YYYY-MM-DD)"),
    end: str | None = Query(None, description="End date filter (YYYY-MM-DD)"),
    format: str | None = Query(None, description="Response format: 'json' or 'csv'"),
    db: Session = Depends(get_db),
):
    """Returns daily APIx index series with optional date range filters and CSV export variant."""
    query = db.query(ApixDaily)

    if start:
        query = query.filter(ApixDaily.date >= start)
    if end:
        query = query.filter(ApixDaily.date <= end)

    records = query.order_by(ApixDaily.date.asc()).all()

    # If format is csv, return CSV stream
    if format and format.lower() == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["date", "level", "base_fare_level", "tax_level", "n_cells"])
        for r in records:
            writer.writerow([r.date, r.level, r.base_fare_level or "", r.tax_level or "", r.n_cells])

        return Response(
            content=output.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=apix_daily.csv"},
        )

    items = [
        DailyIndexItem(
            date=r.date,
            level=r.level,
            base_fare_level=r.base_fare_level,
            tax_level=r.tax_level,
            n_cells=r.n_cells,
        )
        for r in records
    ]

    n_obs = get_total_obs_count(db)
    total_cells = sum(r.n_cells for r in records) if records else 0

    return DailyIndexResponse(
        data=items,
        metadata=Metadata(
            n_obs=n_obs,
            n_cells=total_cells,
            base_period=DEFAULT_BASE_DATE,
            label="estimated",
        ),
    )


@app.get("/api/routes", response_model=RoutesResponse)
def get_routes_list(db: Session = Depends(get_db)):
    """Returns route list with weights and latest route-level index levels."""
    db_routes = db.query(RouteModel).filter(RouteModel.active == True).all()

    items = []
    total_n_cells = 0

    for r in db_routes:
        latest_r_idx = (
            db.query(RouteIndex)
            .filter(RouteIndex.route_id == r.route_id)
            .order_by(RouteIndex.date.desc())
            .first()
        )
        latest_level = latest_r_idx.level if latest_r_idx else 100.0

        latest_vol = (
            db.query(Volatility)
            .filter(Volatility.route_id == r.route_id)
            .order_by(Volatility.window_end.desc())
            .first()
        )
        vol_band = latest_vol.band if latest_vol else "Low"

        items.append(
            RouteItem(
                route_id=r.route_id,
                origin=r.origin,
                destination=r.destination,
                weight=r.weight,
                dgca_pax=r.dgca_pax,
                latest_level=latest_level,
                volatility_band=vol_band,
            )
        )


    n_obs = get_total_obs_count(db)
    latest_daily = db.query(ApixDaily).order_by(ApixDaily.date.desc()).first()
    if latest_daily:
        total_n_cells = latest_daily.n_cells

    return RoutesResponse(
        routes=items,
        metadata=Metadata(
            n_obs=n_obs,
            n_cells=total_n_cells,
            base_period=DEFAULT_BASE_DATE,
            label="estimated",
        ),
    )


# --- Quality Models ---


class QualitySourceItem(BaseModel):
    source: str
    total_quotes: int
    available_quotes: int
    sold_out_quotes: int
    outliers_count: int
    coverage_pct: float


class QualityResponse(BaseModel):
    total_quotes: int
    active_cells: int
    missing_cells: int
    outliers_count: int
    sources: list[QualitySourceItem]
    metadata: Metadata


@app.get("/api/quality", response_model=QualityResponse)
def get_data_quality_metrics(db: Session = Depends(get_db)):
    """Returns data quality stats: coverage by source, missing cells, outliers count, and status."""
    total_quotes = db.query(FareClean).count()
    outliers_count = db.query(FareClean).filter(FareClean.outlier_flag == True).count()

    latest_daily = db.query(ApixDaily).order_by(ApixDaily.date.desc()).first()
    active_cells = latest_daily.n_cells if latest_daily else 0

    # Total theoretical cells = 6 routes x 7 active sources x 5 windows = 210 cells
    total_expected_cells = 210
    missing_cells = max(0, total_expected_cells - active_cells)

    # Breakdown by carrier/source
    distinct_carriers = db.query(FareClean.carrier).distinct().all()
    sources_data = []

    for (carrier,) in distinct_carriers:
        carrier_total = db.query(FareClean).filter(FareClean.carrier == carrier).count()
        carrier_avail = db.query(FareClean).filter(FareClean.carrier == carrier, FareClean.status == "available").count()
        carrier_sold = db.query(FareClean).filter(FareClean.carrier == carrier, FareClean.status == "sold_out").count()
        carrier_outliers = db.query(FareClean).filter(FareClean.carrier == carrier, FareClean.outlier_flag == True).count()

        cov_pct = round((carrier_avail / carrier_total * 100.0), 2) if carrier_total > 0 else 0.0

        sources_data.append(
            QualitySourceItem(
                source=carrier,
                total_quotes=carrier_total,
                available_quotes=carrier_avail,
                sold_out_quotes=carrier_sold,
                outliers_count=carrier_outliers,
                coverage_pct=cov_pct,
            )
        )

    return QualityResponse(
        total_quotes=total_quotes,
        active_cells=active_cells,
        missing_cells=missing_cells,
        outliers_count=outliers_count,
        sources=sources_data,
        metadata=Metadata(
            n_obs=total_quotes,
            n_cells=active_cells,
            base_period=DEFAULT_BASE_DATE,
            label="observed",
        ),
    )


# --- Anomaly & Volatility Models ---

class AnomalyItem(BaseModel):
    route_id: str
    date: str
    lead_days: int
    score: float
    pct_from_expected: float
    direction: str
    flag: bool


class AnomaliesResponse(BaseModel):
    anomalies: list[AnomalyItem]
    metadata: Metadata


class VolatilityItem(BaseModel):
    route_id: str
    window_end: str
    value: float
    band: str


class VolatilityResponse(BaseModel):
    volatility: list[VolatilityItem]
    metadata: Metadata


@app.get("/api/anomalies", response_model=AnomaliesResponse)
def get_flagged_anomalies(
    start: str | None = Query(None, description="Start date filter (YYYY-MM-DD)"),
    end: str | None = Query(None, description="End date filter (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
):
    """Returns list of flagged fare anomalies and price surges with date range filters."""
    query = db.query(Anomaly).filter(Anomaly.flag == True)
    if start:
        query = query.filter(Anomaly.date >= start)
    if end:
        query = query.filter(Anomaly.date <= end)

    records = query.order_by(Anomaly.date.desc()).all()

    items = [
        AnomalyItem(
            route_id=r.route_id,
            date=r.date,
            lead_days=r.lead_days,
            score=r.score,
            pct_from_expected=r.pct_from_expected,
            direction=r.direction,
            flag=r.flag,
        )
        for r in records
    ]

    n_obs = get_total_obs_count(db)
    latest_daily = db.query(ApixDaily).order_by(ApixDaily.date.desc()).first()
    active_cells = latest_daily.n_cells if latest_daily else 0

    return AnomaliesResponse(
        anomalies=items,
        metadata=Metadata(
            n_obs=n_obs,
            n_cells=active_cells,
            base_period=DEFAULT_BASE_DATE,
            label="estimated",
        ),
    )


@app.get("/api/volatility", response_model=VolatilityResponse)
def get_route_volatility_rankings(db: Session = Depends(get_db)):
    """Returns 14-day rolling route volatility scores and High/Medium/Low tercile bands."""
    latest_end = db.query(Volatility.window_end).order_by(Volatility.window_end.desc()).first()

    items = []
    if latest_end and latest_end[0]:
        records = (
            db.query(Volatility)
            .filter(Volatility.window_end == latest_end[0])
            .order_by(Volatility.value.desc())
            .all()
        )
        items = [
            VolatilityItem(
                route_id=r.route_id,
                window_end=r.window_end,
                value=r.value,
                band=r.band,
            )
            for r in records
        ]

    n_obs = get_total_obs_count(db)
    latest_daily = db.query(ApixDaily).order_by(ApixDaily.date.desc()).first()
    active_cells = latest_daily.n_cells if latest_daily else 0

    return VolatilityResponse(
        volatility=items,
        metadata=Metadata(
            n_obs=n_obs,
            n_cells=active_cells,
            base_period=DEFAULT_BASE_DATE,
            label="estimated",
        ),
    )


# --- Event & Signal Models ---

class EventSignalItem(BaseModel):
    signal_type: str
    event_id: str
    title: str
    date_range: str
    region: str
    source: str
    note: str | None = None
    label: Literal["signal"] = "signal"


class EventsResponse(BaseModel):
    signals: list[EventSignalItem]
    metadata: Metadata


@app.get("/api/events", response_model=EventsResponse)
def get_coinciding_events_and_signals(
    start: str | None = Query(None, description="Start date filter (YYYY-MM-DD)"),
    end: str | None = Query(None, description="End date filter (YYYY-MM-DD)"),
    route: str | None = Query(None, description="Route ID filter (e.g. DEL-BOM)"),
    db: Session = Depends(get_db),
):
    """Returns list of coinciding events and macro signals for a route and date range."""
    from apix.novelty.events import EventSignalMatcher

    matcher = EventSignalMatcher(db=db)
    target_date = start or DEFAULT_BASE_DATE

    signals_data = matcher.match_signals(route_id=route, target_date=target_date, window_days=2)

    items = [
        EventSignalItem(
            signal_type=s["signal_type"],
            event_id=s["event_id"],
            title=s["title"],
            date_range=s["date_range"],
            region=s["region"],
            source=s["source"],
            note=s.get("note"),
            label="signal",
        )
        for s in signals_data
    ]

    n_obs = get_total_obs_count(db)
    latest_daily = db.query(ApixDaily).order_by(ApixDaily.date.desc()).first()
    active_cells = latest_daily.n_cells if latest_daily else 0

    return EventsResponse(
        signals=items,
        metadata=Metadata(
            n_obs=n_obs,
            n_cells=active_cells,
            base_period=DEFAULT_BASE_DATE,
            label="signal",
        ),
    )


# --- Attribution & Forecast Models ---

class Level1DecompositionItem(BaseModel):
    total_change: float
    route_mix_contribution: float
    carrier_mix_contribution: float
    lead_time_mix_contribution: float
    base_vs_taxes_contribution: float
    residual: float


class AttributionResponse(BaseModel):
    start_date: str
    end_date: str
    level1_decomposition: Level1DecompositionItem
    level2_signals: list[dict[str, Any]]
    level3_causal_regression: dict[str, Any]
    metadata: Metadata


class ForecastPointItem(BaseModel):
    target_date: str
    level: float
    lower: float
    upper: float
    model: str
    beats_baselines: bool


class ForecastResponse(BaseModel):
    run_date: str
    route_id: str | None = None
    horizon_days: int
    chosen_model: str
    beats_baselines: bool
    evaluation_metrics: dict[str, Any]
    forecast_points: list[ForecastPointItem]
    metadata: Metadata


@app.get("/api/attribution", response_model=AttributionResponse)
def get_price_change_attribution(
    start: str | None = Query(None, description="Start date (YYYY-MM-DD)"),
    end: str | None = Query(None, description="End date (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
):
    """Returns 3-level price movement attribution with un-fudged residual and sample-size gated regression."""
    from apix.novelty.attribution import AttributionEngine

    engine = AttributionEngine(db=db)
    start_dt_str = start or DEFAULT_BASE_DATE
    end_dt_str = end or datetime.now().strftime("%Y-%m-%d")

    res = engine.analyze_attribution(start_dt_str, end_dt_str)

    n_obs = get_total_obs_count(db)
    latest_daily = db.query(ApixDaily).order_by(ApixDaily.date.desc()).first()
    active_cells = latest_daily.n_cells if latest_daily else 0

    return AttributionResponse(
        start_date=res["start_date"],
        end_date=res["end_date"],
        level1_decomposition=Level1DecompositionItem(**res["level1_decomposition"]),
        level2_signals=res["level2_signals"],
        level3_causal_regression=res["level3_causal_regression"],
        metadata=Metadata(
            n_obs=n_obs,
            n_cells=active_cells,
            base_period=DEFAULT_BASE_DATE,
            label="estimated",
        ),
    )


@app.get("/api/forecast", response_model=ForecastResponse)
def get_apix_forecast(
    route: str | None = Query(None, description="Route ID filter (e.g. DEL-BOM)"),
    horizon: int = Query(7, description="Forecast horizon in days (1-30)"),
    db: Session = Depends(get_db),
):
    """Returns walk-forward forecast, interval bounds, and side-by-side evaluation against baselines."""
    from apix.novelty.forecast import WalkForwardForecaster

    forecaster = WalkForwardForecaster(db=db)
    res = forecaster.evaluate_and_forecast(route_id=route, horizon=horizon)

    n_obs = get_total_obs_count(db)
    latest_daily = db.query(ApixDaily).order_by(ApixDaily.date.desc()).first()
    active_cells = latest_daily.n_cells if latest_daily else 0

    points = [ForecastPointItem(**p) for p in res["forecast_points"]]

    return ForecastResponse(
        run_date=res["run_date"],
        route_id=res["route_id"],
        horizon_days=res["horizon_days"],
        chosen_model=res["chosen_model"],
        beats_baselines=res["beats_baselines"],
        evaluation_metrics=res["evaluation_metrics"],
        forecast_points=points,
        metadata=Metadata(
            n_obs=n_obs,
            n_cells=active_cells,
            base_period=DEFAULT_BASE_DATE,
            label="estimated",
        ),
    )


# --- Backtest Models ---

class BacktestResponse(BaseModel):
    dgca_backtest: dict[str, Any]
    internal_consistency: dict[str, Any]
    index_sensitivity: dict[str, Any]
    metadata: Metadata


@app.get("/api/backtest", response_model=BacktestResponse)
def get_backtest_report(db: Session = Depends(get_db)):
    """Returns DGCA monthly benchmark correlation, internal airline-vs-OTA quote consistency, and lead-time sensitivity analysis."""
    from apix.index.backtest import BacktestEngine

    engine = BacktestEngine(db=db)
    res = engine.run_full_backtest()

    n_obs = get_total_obs_count(db)
    latest_daily = db.query(ApixDaily).order_by(ApixDaily.date.desc()).first()
    active_cells = latest_daily.n_cells if latest_daily else 0

    return BacktestResponse(
        dgca_backtest=res["dgca_backtest"],
        internal_consistency=res["internal_consistency"],
        index_sensitivity=res["index_sensitivity"],
        metadata=Metadata(
            n_obs=n_obs,
            n_cells=active_cells,
            base_period=DEFAULT_BASE_DATE,
            label="estimated",
        ),
    )





