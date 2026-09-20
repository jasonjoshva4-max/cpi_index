"""Data models for APIx airfare index scraper."""
from dataclasses import asdict, dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class Route:
    origin: str
    destination: str

    def __str__(self) -> str:
        return f"{self.origin}-{self.destination}"


@dataclass
class Job:
    route: Route
    source: str
    lead_days: int
    travel_date: str  # YYYY-MM-DD
    search_ts: str    # ISO 8601 string
    job_id: str | None = None

    def __post_init__(self):
        if not self.job_id:
            self.job_id = f"{self.source}_{self.route.origin}_{self.route.destination}_T{self.lead_days}_{self.travel_date}"


AvailabilityFlag = Literal["available", "sold_out", "cancelled", "not_shown"]


@dataclass
class AirfareRecord:
    carrier: str
    flight_no: str
    origin: str
    destination: str
    dep_time: str
    arr_time: str
    stops: int
    fare_class: str | None
    base_fare: float | None
    taxes: float | None
    udf: float | None
    convenience_fee: float | None
    total_fare: float
    source: str
    search_ts: str
    travel_date: str
    lead_days: int
    availability_flag: AvailabilityFlag

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class JobResult:
    job: Job
    status: Literal["success", "failed", "captcha_blocked", "robots_disallowed", "robots_unverified"]
    records: list[AirfareRecord] = field(default_factory=list)
    reason_code: str | None = None
    error_message: str | None = None


@dataclass
class RunMetrics:
    jobs_attempted: int = 0
    jobs_succeeded: int = 0
    parse_errors: int = 0
    captcha_backoffs: int = 0

    def summary_line(self) -> str:
        return (
            f"Run Completed | Jobs Attempted: {self.jobs_attempted} | "
            f"Jobs Succeeded: {self.jobs_succeeded} | "
            f"Parse Errors: {self.parse_errors} | "
            f"CAPTCHA Backoffs: {self.captcha_backoffs}"
        )
