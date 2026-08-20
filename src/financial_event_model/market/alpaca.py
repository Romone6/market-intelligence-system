"""Credential-gated Alpaca daily-bar collector."""

import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import uuid4
from zoneinfo import ZoneInfo

import exchange_calendars as xcals

from .models import CorporateAction, MarketBar
from .store import MarketStore


class AlpacaDailyBarCollector:
    endpoint = "https://data.alpaca.markets/v2/stocks/bars"
    corporate_actions_endpoint = "https://data.alpaca.markets/v1/corporate-actions"

    def __init__(
        self,
        *,
        api_key: str,
        api_secret: str,
        raw_root: str | Path,
        store: MarketStore,
        open_url: Callable[..., Any] = urlopen,
        timeout: float = 30,
    ) -> None:
        if not api_key.strip() or not api_secret.strip():
            raise ValueError("Alpaca credentials are required")
        self.api_key = api_key
        self.api_secret = api_secret
        self.raw_root = Path(raw_root)
        self.raw_root.mkdir(parents=True, exist_ok=True)
        self.store = store
        self.open_url = open_url
        self.timeout = timeout
        self.calendar = xcals.get_calendar("XNYS")
        self.market_timezone = ZoneInfo("America/New_York")

    def collect(
        self,
        *,
        symbols: dict[str, str],
        start: date,
        end: date,
        feed: str,
    ) -> tuple[MarketBar, ...]:
        if end < start:
            raise ValueError("end must not precede start")
        if feed not in {"sip", "iex"}:
            raise ValueError("feed must be sip or iex")
        normalized = {symbol.upper(): security_id for symbol, security_id in symbols.items()}
        raw, raw_hashes, raw_received = self._fetch_pages(
            symbols=tuple(sorted(normalized)),
            start=start,
            end=end,
            adjustment="raw",
            feed=feed,
        )
        adjusted, adjusted_hashes, adjusted_received = self._fetch_pages(
            symbols=tuple(sorted(normalized)),
            start=start,
            end=end,
            adjustment="all",
            feed=feed,
        )
        received_at = max(raw_received, adjusted_received)
        dataset_hash = hashlib.sha256(
            "".join((*raw_hashes, *adjusted_hashes)).encode("ascii")
        ).hexdigest()
        adjusted_by_key = {
            (symbol, item["t"]): item
            for symbol, items in adjusted.items()
            for item in items
        }
        bars = []
        for symbol, items in raw.items():
            if symbol not in normalized:
                continue
            for item in items:
                matching = adjusted_by_key.get((symbol, item["t"]))
                if matching is None:
                    continue
                source_timestamp = _parse_datetime(item["t"])
                session_date = source_timestamp.astimezone(self.market_timezone).date()
                session = self.calendar.date_to_session(session_date, direction="none")
                session_open = self.calendar.session_open(session).to_pydatetime()
                bars.append(
                    MarketBar(
                        security_id=normalized[symbol],
                        symbol=symbol,
                        session_date=session_date,
                        timestamp=session_open,
                        source_timestamp=source_timestamp,
                        open=float(item["o"]),
                        high=float(item["h"]),
                        low=float(item["l"]),
                        close=float(item["c"]),
                        volume=int(item["v"]),
                        adjusted_open=float(matching["o"]),
                        adjusted_high=float(matching["h"]),
                        adjusted_low=float(matching["l"]),
                        adjusted_close=float(matching["c"]),
                        adjustment_factor=float(matching["c"]) / float(item["c"]),
                        trading_status="unknown",
                        source=f"alpaca:{feed}:raw+all",
                        source_received_at=received_at,
                        source_content_hash=dataset_hash,
                    )
                )
        result = tuple(sorted(bars, key=lambda bar: (bar.security_id, bar.session_date)))
        self.store.put_bars(result)
        return result

    def collect_corporate_actions(
        self,
        *,
        symbols: dict[str, str],
        start: date,
        end: date,
    ) -> tuple[CorporateAction, ...]:
        normalized = {symbol.upper(): security_id for symbol, security_id in symbols.items()}
        actions: list[CorporateAction] = []
        page_token: str | None = None
        while True:
            parameters = {
                "symbols": ",".join(sorted(normalized)),
                "start": start.isoformat(),
                "end": end.isoformat(),
                "region": "us",
                "data_quality": "complete",
                "limit": "1000",
                "sort": "asc",
            }
            if page_token is not None:
                parameters["page_token"] = page_token
            url = f"{self.corporate_actions_endpoint}?{urlencode(parameters)}"
            request = Request(
                url,
                headers={
                    "APCA-API-KEY-ID": self.api_key,
                    "APCA-API-SECRET-KEY": self.api_secret,
                    "Accept": "application/json",
                },
            )
            requested_at = datetime.now(timezone.utc)
            with self.open_url(request, timeout=self.timeout) as response:
                body = response.read()
                received_at = datetime.now(timezone.utc)
                status = int(response.status)
            content_hash = hashlib.sha256(body).hexdigest()
            local_path = self._store_raw(body, content_hash)
            self.store.record_request(
                request_url=url,
                adjustment="corporate_actions",
                feed="n/a",
                requested_at=requested_at,
                response_received_at=received_at,
                http_status=status,
                content_hash=content_hash,
                local_path=local_path,
            )
            payload = json.loads(body)
            groups = payload.get("corporate_actions") if isinstance(payload, dict) else None
            if not isinstance(groups, dict):
                raise ValueError("Alpaca corporate-actions response has an invalid shape")
            for group_name, items in groups.items():
                if not isinstance(items, list):
                    raise ValueError("Alpaca corporate-action group must be a list")
                action_type = group_name[:-1] if group_name.endswith("s") else group_name
                for item in items:
                    symbol = _action_symbol(item)
                    effective = _action_effective_date(item)
                    if symbol not in normalized or effective is None:
                        continue
                    actions.append(
                        CorporateAction(
                            action_id=str(item["id"]),
                            security_id=normalized[symbol],
                            symbol=symbol,
                            action_type=action_type,
                            effective_date=effective,
                            announced_at=None,
                            first_observed_at=received_at,
                            source="alpaca:corporate_actions:complete",
                            source_content_hash=content_hash,
                            source_payload=item,
                        )
                    )
            page_token = payload.get("next_page_token")
            if not page_token:
                break
        result = tuple(sorted(actions, key=lambda item: (item.effective_date, item.action_id)))
        self.store.put_corporate_actions(result)
        return result

    def _fetch_pages(
        self,
        *,
        symbols: tuple[str, ...],
        start: date,
        end: date,
        adjustment: str,
        feed: str,
    ) -> tuple[dict[str, list[dict[str, Any]]], tuple[str, ...], datetime]:
        combined: dict[str, list[dict[str, Any]]] = {}
        hashes: list[str] = []
        latest_received: datetime | None = None
        page_token: str | None = None
        while True:
            parameters = {
                "symbols": ",".join(symbols),
                "timeframe": "1Day",
                "start": start.isoformat(),
                "end": end.isoformat(),
                "limit": "10000",
                "adjustment": adjustment,
                "feed": feed,
                "sort": "asc",
            }
            if page_token is not None:
                parameters["page_token"] = page_token
            url = f"{self.endpoint}?{urlencode(parameters)}"
            request = Request(
                url,
                headers={
                    "APCA-API-KEY-ID": self.api_key,
                    "APCA-API-SECRET-KEY": self.api_secret,
                    "Accept": "application/json",
                },
            )
            requested_at = datetime.now(timezone.utc)
            with self.open_url(request, timeout=self.timeout) as response:
                body = response.read()
                received_at = datetime.now(timezone.utc)
                status = int(response.status)
            content_hash = hashlib.sha256(body).hexdigest()
            local_path = self._store_raw(body, content_hash)
            self.store.record_request(
                request_url=url,
                adjustment=adjustment,
                feed=feed,
                requested_at=requested_at,
                response_received_at=received_at,
                http_status=status,
                content_hash=content_hash,
                local_path=local_path,
            )
            payload = json.loads(body)
            if not isinstance(payload, dict) or not isinstance(payload.get("bars"), dict):
                raise ValueError("Alpaca bars response has an invalid shape")
            for symbol, items in payload["bars"].items():
                if not isinstance(items, list):
                    raise ValueError("Alpaca symbol bars must be a list")
                combined.setdefault(symbol, []).extend(items)
            hashes.append(content_hash)
            latest_received = received_at
            page_token = payload.get("next_page_token")
            if not page_token:
                break
        if latest_received is None:
            raise AssertionError("Alpaca pagination returned no response")
        return combined, tuple(hashes), latest_received

    def _store_raw(self, body: bytes, content_hash: str) -> Path:
        destination = self.raw_root / "alpaca" / content_hash[:2] / f"{content_hash}.json"
        if destination.exists():
            return destination
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(f"{destination.name}.{uuid4().hex}.tmp")
        temporary.write_bytes(body)
        temporary.replace(destination)
        return destination


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("provider bar timestamp must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _action_symbol(item: dict[str, Any]) -> str:
    for key in ("symbol", "old_symbol", "acquiree_symbol"):
        value = item.get(key)
        if isinstance(value, str) and value:
            return value.upper()
    return ""


def _action_effective_date(item: dict[str, Any]) -> date | None:
    for key in ("ex_date", "effective_date", "process_date", "payable_date"):
        value = item.get(key)
        if isinstance(value, str) and value:
            return date.fromisoformat(value)
    return None
