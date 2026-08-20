"""Official Fama/French daily factor ingestion."""

import csv
import hashlib
import io
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from uuid import uuid4

from .models import FactorObservation
from .store import MarketStore


FRENCH_DAILY_URL = (
    "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
    "F-F_Research_Data_Factors_daily_CSV.zip"
)


def parse_french_daily_factors(
    raw_csv: bytes,
    *,
    source: str,
    received_at: datetime,
    source_content_hash: str | None = None,
) -> tuple[FactorObservation, ...]:
    content_hash = source_content_hash or hashlib.sha256(raw_csv).hexdigest()
    text = raw_csv.decode("utf-8-sig", errors="replace")
    observations = []
    for row in csv.reader(io.StringIO(text)):
        if len(row) < 5 or len(row[0].strip()) != 8 or not row[0].strip().isdigit():
            continue
        session = datetime.strptime(row[0].strip(), "%Y%m%d").date()
        values = [float(value.strip()) / 100.0 for value in row[1:5]]
        observations.append(
            FactorObservation(
                session_date=session,
                market_excess_return=values[0],
                smb=values[1],
                hml=values[2],
                risk_free_rate=values[3],
                source=source,
                received_at=received_at,
                source_content_hash=content_hash,
            )
        )
    if not observations:
        raise ValueError("Fama/French daily factor file contains no observations")
    return tuple(observations)


def parse_french_factor_archive(
    raw_archive: bytes,
    *,
    received_at: datetime,
) -> tuple[FactorObservation, ...]:
    content_hash = hashlib.sha256(raw_archive).hexdigest()
    with zipfile.ZipFile(io.BytesIO(raw_archive)) as archive:
        names = [name for name in archive.namelist() if name.casefold().endswith(".csv")]
        if len(names) != 1:
            raise ValueError("Fama/French archive must contain one CSV file")
        raw_csv = archive.read(names[0])
    return parse_french_daily_factors(
        raw_csv,
        source="ken_french_us_3_factor_daily",
        received_at=received_at,
        source_content_hash=content_hash,
    )


class FrenchFactorCollector:
    def __init__(
        self,
        *,
        raw_root: str | Path,
        store: MarketStore,
        open_url=urlopen,
        timeout: float = 30,
    ) -> None:
        self.raw_root = Path(raw_root)
        self.store = store
        self.open_url = open_url
        self.timeout = timeout

    def collect(self) -> tuple[FactorObservation, ...]:
        request = Request(FRENCH_DAILY_URL, headers={"User-Agent": "financial-event-model/0.1"})
        with self.open_url(request, timeout=self.timeout) as response:
            body = response.read()
            received_at = datetime.now(timezone.utc)
        content_hash = hashlib.sha256(body).hexdigest()
        destination = (
            self.raw_root / "ken_french" / content_hash[:2] / f"{content_hash}.zip"
        )
        if not destination.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_name(f"{destination.name}.{uuid4().hex}.tmp")
            temporary.write_bytes(body)
            temporary.replace(destination)
        factors = parse_french_factor_archive(body, received_at=received_at)
        self.store.put_factors(factors)
        return factors
