"""
Progress Scanner Service
Scans PES files from Local/Dropbox and queries Lemiex API for order status
"""

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Dict, Iterable, List, Optional, Protocol, Sequence

import requests

# Constants
API_ENDPOINT = "https://manage.lemiex.us/api/orders/process-order"
MAX_QUERY_LENGTH = 4000
DROPBOX_API_BASE = "https://api.dropboxapi.com/2"
DROPBOX_TOKEN_BASE = "https://manage.lemiex.us/api/telegram"
DROPBOX_TOKEN_TIMEOUT = 25

LOGGER = logging.getLogger("progress_scanner")


@dataclass(frozen=True)
class PesEntry:
    """Represents a PES file discovered on disk."""
    date_folder: str
    station: str
    order_id: str
    path: str


@dataclass
class OrderStatus:
    """Normalized status returned by the Lemiex API."""
    order_id: str
    done_items: int
    total_items: int
    pending_items: List[str] = field(default_factory=list)
    raw: Optional[dict] = None

    @property
    def completion(self) -> float:
        if self.total_items <= 0:
            return 0.0
        return min(1.0, max(0.0, self.done_items / self.total_items))

    def to_dict(self):
        """Convert to dict matching Textual display logic"""
        if self.pending_items:
            pending_str = ", ".join(self.pending_items)
            status_text = f"{self.order_id} -> {pending_str}"
        else:
            status_text = f"{self.order_id} -> all items complete"

        return {
            "id": self.order_id,
            "status_text": status_text,
            "missing_items": self.pending_items,
            # Keeping these for potential use, though user emphasized missing_items
            "done_items": self.done_items,
            "total_items": self.total_items
        }


@dataclass
class StationProgress:
    name: str
    orders: List[OrderStatus]

    def to_dict(self):
        # Filter only pending orders for the list
        pending_orders = [o for o in self.orders if o.pending_items]
        
        # Calculate totals for the station
        total_items = sum(o.total_items for o in self.orders)
        done_items = sum(o.done_items for o in self.orders)
        
        return {
            "name": self.name.strip('/'),  # Clean up name if it has trailing slash
            "has_pending": len(pending_orders) > 0,
            "stats": {
                "total": total_items,
                "done": done_items,
                "total_orders": len(self.orders),
                "pending_orders_count": len(pending_orders)
            },
            "pending_orders": [order.to_dict() for order in pending_orders]
        }


@dataclass
class DateProgress:
    name: str
    stations: List[StationProgress]
    done_items: int
    total_items: int
    completed_orders: int
    total_orders: int

    @property
    def completion(self) -> float:
        if self.total_items <= 0:
            return 0.0
        return min(1.0, max(0.0, self.done_items / self.total_items))

    def to_dict(self):
        return {
            "date": self.name,
            "stats": {
                "total_orders": self.total_orders,
                "done_orders": self.completed_orders,
                "total_items": self.total_items,
                "done_items": self.done_items,
                "percent": round(self.completion * 100, 1)
            },
            "stations": [station.to_dict() for station in self.stations]
        }


@dataclass
class ProgressSnapshot:
    dates: List[DateProgress]
    missing_ids: List[str]

    @property
    def order_count(self) -> int:
        return sum(len(station.orders) for date in self.dates for station in date.stations)

    @property
    def overall_completion(self) -> float:
        total_done = sum(date.done_items for date in self.dates)
        total_items = sum(date.total_items for date in self.dates)
        if total_items <= 0:
            return 0.0
        return min(1.0, max(0.0, total_done / total_items))

    def to_dict(self, source: str = "Unknown"):
        total_items = sum(date.total_items for date in self.dates)
        done_items = sum(date.done_items for date in self.dates)
        
        return {
            "summary": {
                "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "total_dates": len(self.dates),
                "total_orders": self.order_count,
                "total_items": total_items,
                "done_items": done_items,
                "percent_complete": round(self.overall_completion * 100, 1),
                "source": source
            },
            "dates": [date.to_dict() for date in self.dates]
        }


class ScannerProtocol(Protocol):
    """Minimal interface required for a PES scanner."""
    def scan(self) -> List[PesEntry]:
        ...


class PesScanner:
    """Walks the embroidery root folder and finds PES files."""

    PES_FOLDER_NAME = "pes"
    PES_SUFFIX = ".pes"

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def scan(self) -> List[PesEntry]:
        if not self.root.exists():
            LOGGER.warning("Root path does not exist: %s", self.root)
            return []

        entries: List[PesEntry] = []
        for date_dir in sorted(p for p in self.root.iterdir() if p.is_dir()):
            date_folder = date_dir.name
            for station_dir in sorted(p for p in date_dir.iterdir() if p.is_dir()):
                pes_dir = station_dir / self.PES_FOLDER_NAME
                if not pes_dir.is_dir():
                    continue
                for pes_file in sorted(
                    p for p in pes_dir.rglob(f"*{self.PES_SUFFIX}") if p.is_file()
                ):
                    order_id = self._extract_order_id(pes_file.name)
                    if not order_id:
                        continue
                    station_name = f"{station_dir.name}/"
                    entries.append(
                        PesEntry(
                            date_folder=date_folder,
                            station=station_name,
                            order_id=order_id,
                            path=str(pes_file),
                        )
                    )
        return entries

    @staticmethod
    def _extract_order_id(filename: str) -> Optional[str]:
        parts = filename.split("_", 1)
        if not parts:
            return None
        candidate = parts[0]
        return candidate if candidate.isdigit() else None


class DropboxClient:
    """Minimal Dropbox API client for listing folder contents."""

    def __init__(self, access_token: str, timeout: int = 30) -> None:
        self.access_token = access_token
        self.timeout = timeout
        self.session = requests.Session()

    def iter_entries(self, path: str, recursive: bool = True) -> Iterable[dict]:
        api_path = path if path and path != "/" else ""
        payload: dict = {
            "path": api_path,
            "recursive": recursive,
            "include_non_downloadable_files": True,
        }
        url = f"{DROPBOX_API_BASE}/files/list_folder"
        while True:
            response = self.session.post(
                url,
                headers=self._headers(),
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
            for entry in data.get("entries", []):
                yield entry
            if not data.get("has_more"):
                break
            payload = {"cursor": data["cursor"]}
            url = f"{DROPBOX_API_BASE}/files/list_folder/continue"

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }


class DropboxTokenProvider:
    """Manages Dropbox tokens retrieved via a Lemiex API key."""

    def __init__(self, initial_token: Optional[str], api_key: Optional[str]) -> None:
        self._token = (initial_token or "").strip() or None
        self._api_key = (api_key or "").strip() or None

    def ensure_token(self) -> Optional[str]:
        if self._token:
            return self._token
        return self.refresh(force_reset=False)

    def refresh(self, force_reset: bool = False) -> Optional[str]:
        if not self._api_key:
            return None
        token = fetch_dropbox_token_from_key(
            self._api_key,
            timeout=DROPBOX_TOKEN_TIMEOUT,
            force_reset=force_reset,
        )
        if token:
            self._token = token
        return self._token

    @property
    def can_refresh(self) -> bool:
        return bool(self._api_key)


class DropboxPesScanner:
    """Scans PES files stored in Dropbox using the Dropbox API."""

    def __init__(self, token_provider: DropboxTokenProvider, root_path: str) -> None:
        self.token_provider = token_provider
        self.path_candidates = self._build_path_candidates(root_path)

    def scan(self) -> List[PesEntry]:
        token = self.token_provider.ensure_token()
        if not token:
            LOGGER.error("No Dropbox token available; skipping Dropbox scan")
            return []

        client = DropboxClient(token)
        for idx, api_path in enumerate(self.path_candidates):
            try:
                entries = self._scan_with_client(client, api_path)
            except requests.HTTPError as exc:
                if self._should_reset_token(exc):
                    LOGGER.warning("Dropbox access error (%s); attempting token reset", exc)
                    new_token = self.token_provider.refresh(force_reset=True)
                    if new_token and new_token != token:
                        return self.scan()
                    LOGGER.error("Dropbox scan failed after token reset: %s", exc)
                    return []
                if self._is_path_not_found(exc) and api_path:
                    LOGGER.warning(
                        "Dropbox path %s not found; retrying from root",
                        api_path,
                    )
                    continue
                LOGGER.error("Failed to scan Dropbox: %s", exc)
                return []
            except Exception as exc:
                LOGGER.error("Failed to scan Dropbox: %s", exc)
                return []

            if entries:
                LOGGER.info(
                    "Dropbox path %s produced %d PES files",
                    api_path or "/",
                    len(entries),
                )
                return entries

            if idx < len(self.path_candidates) - 1:
                LOGGER.info(
                    "Dropbox path %s returned 0 PES files; trying fallback root",
                    api_path or "/",
                )
                continue

            LOGGER.warning(
                "Dropbox path %s returned 0 PES files; check folder contents",
                api_path or "/",
            )
            return []

        return []

    def _scan_with_client(self, client: DropboxClient, api_path: str) -> List[PesEntry]:
        entries: List[PesEntry] = []
        count = 0
        LOGGER.info("Starting recursive scan of Dropbox path: %s", api_path or "/")
        for metadata in client.iter_entries(api_path):
            count += 1
            if count % 100 == 0:
                LOGGER.info("Scanned %d entries from Dropbox...", count)
            if metadata.get(".tag") != "file":
                continue
            name = metadata.get("name", "")
            if not name.lower().endswith(PesScanner.PES_SUFFIX):
                continue
            path_display = metadata.get("path_display")
            if not path_display:
                continue
            rel_parts = self._relative_parts(path_display)
            if rel_parts is None:
                continue
            date_folder, station_name, order_id = rel_parts
            if not order_id:
                continue
            entries.append(
                PesEntry(
                    date_folder=date_folder,
                    station=station_name,
                    order_id=order_id,
                    path=path_display,
                )
            )
        return entries

    def _should_reset_token(self, exc: Exception) -> bool:
        if not isinstance(exc, requests.HTTPError):
            return False
        if not self.token_provider.can_refresh:
            return False
        status = getattr(exc.response, "status_code", None)
        return status in {401, 403}

    def _relative_parts(self, path_display: str) -> Optional[tuple[str, str, str]]:
        parts = [part for part in PurePosixPath(path_display).parts if part and part != "/"]
        if len(parts) < 4:
            return None
        parts_lower = [part.lower() for part in parts]
        if "pes" not in parts_lower:
            return None
        pes_index = parts_lower.index("pes")
        if pes_index < 2 or pes_index >= len(parts) - 1:
            return None
        date_folder = parts[pes_index - 2]
        station_name = f"{parts[pes_index - 1]}/"
        order_id = PesScanner._extract_order_id(parts[-1])
        if not order_id:
            return None
        return date_folder, station_name, order_id

    @staticmethod
    def _normalize_root(path: Optional[str]) -> str:
        if not path:
            return ""
        cleaned = path.replace("\\", "/").strip() or "/"
        if not cleaned.startswith("/"):
            cleaned = "/" + cleaned
        return "" if cleaned == "/" else cleaned

    @staticmethod
    def _build_path_candidates(path: Optional[str]) -> List[str]:
        normalized = DropboxPesScanner._normalize_root(path)
        candidates: List[str] = []
        if normalized:
            candidates.append(normalized)
        candidates.append("")
        # Preserve order but drop duplicates
        seen: set[str] = set()
        ordered: List[str] = []
        for candidate in candidates:
            if candidate not in seen:
                seen.add(candidate)
                ordered.append(candidate)
        return ordered

    @staticmethod
    def _is_path_not_found(exc: Exception) -> bool:
        if not isinstance(exc, requests.HTTPError):
            return False
        response = exc.response
        if not response or response.status_code != 409:
            return False
        try:
            payload = response.json()
        except ValueError:
            return False
        if not isinstance(payload, dict):
            return False
        summary = payload.get("error_summary", "")
        if isinstance(summary, str) and "path/not_found" in summary:
            return True
        error = payload.get("error")
        if isinstance(error, dict):
            tag = error.get(".tag")
            if tag == "path":
                path_info = error.get("path")
                if isinstance(path_info, dict) and path_info.get(".tag") == "not_found":
                    return True
        return False


def fetch_dropbox_token_from_key(
    api_key: str,
    timeout: int = DROPBOX_TOKEN_TIMEOUT,
    force_reset: bool = False,
) -> Optional[str]:
    """Retrieve a Dropbox API token using the Lemiex key service."""
    if not api_key:
        return None

    endpoints = ["resetToken", "getToken"] if force_reset else ["getToken", "resetToken"]
    for endpoint in endpoints:
        url = f"{DROPBOX_TOKEN_BASE}/{endpoint}"
        token = _request_token(url, api_key, timeout)
        if token:
            return token

    LOGGER.error("Failed to obtain Dropbox token via Lemiex endpoints")
    return None


def _request_token(url: str, api_key: str, timeout: int) -> Optional[str]:
    params = {"key": api_key}
    try:
        response = requests.get(url, params=params, timeout=timeout)
    except Exception as exc:
        LOGGER.error("Token request to %s failed: %s", url, exc)
        return None

    token = _extract_token(response)
    if token:
        LOGGER.info("Retrieved Dropbox token via %s", url)
        return token

    LOGGER.error(
        "Token request to %s returned status %s without a token",
        url,
        response.status_code,
    )
    return None


def _extract_token(response: requests.Response) -> Optional[str]:
    try:
        data = response.json()
    except ValueError:
        LOGGER.error("Token response from %s was not JSON", response.url)
        return None

    if not isinstance(data, dict):
        LOGGER.error("Token response from %s was not a JSON object", response.url)
        return None

    for key in ("DROPBOX_ACCESS_TOKEN", "access_token", "token", "DROPBOX_TOKEN"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


class LemiexClient:
    """Thin wrapper around the Lemiex API with response normalization and caching."""

    def __init__(self, base_url: str = API_ENDPOINT) -> None:
        self.base_url = base_url.rstrip("?")
        self.session = requests.Session()
        self.cache: Dict[str, OrderStatus] = {}

    def clear_cache(self) -> None:
        self.cache.clear()

    def lookup(self, ids: Iterable[str]) -> Dict[str, OrderStatus]:
        normalized_ids = [str(order_id) for order_id in ids if order_id]
        result: Dict[str, OrderStatus] = {}
        ids_to_fetch = [order_id for order_id in normalized_ids if order_id not in self.cache]

        for chunk in self._chunk_ids(ids_to_fetch):
            try:
                response = self.session.get(
                    self.base_url,
                    params={"ids": ",".join(chunk)},
                    timeout=15,
                )
                response.raise_for_status()
                payload = response.json()
                parsed = self._parse_payload(payload)
                self.cache.update(parsed)
            except Exception as exc:
                LOGGER.error("Failed to fetch Lemiex data: %s", exc)
                break

        for order_id in normalized_ids:
            status = self.cache.get(order_id)
            if status:
                result[order_id] = status

        return result

    @staticmethod
    def _chunk_ids(ids: Sequence[str]) -> List[List[str]]:
        chunks: List[List[str]] = []
        current: List[str] = []
        current_len = 0
        for order_id in ids:
            projected = len(order_id) if not current else len(order_id) + 1
            if current and current_len + projected > MAX_QUERY_LENGTH:
                chunks.append(current)
                current = [order_id]
                current_len = len(order_id)
            else:
                current.append(order_id)
                current_len += projected
        if current:
            chunks.append(current)
        return chunks

    def _parse_payload(self, payload: object) -> Dict[str, OrderStatus]:
        items: List[dict] = []
        if isinstance(payload, dict):
            if isinstance(payload.get("orders"), list):
                items = payload["orders"]
            elif isinstance(payload.get("data"), list):
                items = payload["data"]
            else:
                items = [
                    {"id": key, **value}
                    for key, value in payload.items()
                    if isinstance(key, (str, int)) and isinstance(value, dict)
                ]
        elif isinstance(payload, list):
            items = [item for item in payload if isinstance(item, dict)]

        parsed: Dict[str, OrderStatus] = {}
        for item in items:
            status = self._parse_single_order(item)
            if status:
                parsed[status.order_id] = status
        return parsed

    def _parse_single_order(self, data: dict) -> Optional[OrderStatus]:
        order_id = data.get("id") or data.get("order_id") or data.get("orderId")
        if order_id is None:
            return None
        order_id = str(order_id)

        # New API Format Handler (Flow based)
        if "flow" in data and isinstance(data["flow"], dict):
            flow = data["flow"]
            is_produced = str(flow.get("status")) == "1"
            
            done_items = 1 if is_produced else 0
            total_items = 1
            
            pending_items = []
            if not is_produced:
                current = data.get("current_step") or "pending"
                pending_items = [current]
                
            return OrderStatus(
                order_id=order_id,
                done_items=done_items,
                total_items=total_items,
                pending_items=pending_items,
                raw=data,
            )

        items = data.get("items") or data.get("line_items") or []
        items_list = items if isinstance(items, list) else []
        pending_from_api = data.get("pending_items") or data.get("open_items")

        done_candidates = (
            data.get("done_items"),
            data.get("done"),
            data.get("fulfilled"),
            data.get("produced"),
            data.get("complete"),
        )
        done_items = next((int(value) for value in done_candidates if isinstance(value, int)), None)

        if done_items is None and items_list:
            done_items = sum(1 for item in items_list if self._item_is_complete(item))
        if done_items is None:
            done_items = 0

        total_candidates = (
            data.get("total_items"),
            data.get("items_total"),
            data.get("ordered_items"),
            data.get("total"),
            len(items_list) or None,
        )
        total_items = next((int(value) for value in total_candidates if isinstance(value, int) and value > 0), None)
        if total_items is None:
            total_items = max(done_items, len(items_list), 0)

        pending_items: List[str]
        if isinstance(pending_from_api, list):
            pending_items = [str(item) for item in pending_from_api]
        elif isinstance(pending_from_api, str):
            pending_items = [pending_from_api]
        elif items_list:
            pending_items = self._pending_from_items(items_list)
        else:
            pending_items = [
                self._item_label(item, index)
                for index, item in enumerate(items_list)
                if not self._item_is_complete(item)
            ]

        return OrderStatus(
            order_id=order_id,
            done_items=done_items,
            total_items=total_items,
            pending_items=pending_items,
            raw=data,
        )

    @staticmethod
    def _item_is_complete(item: object) -> bool:
        if not isinstance(item, dict):
            return False
        status_value = str(item.get("status", "")).lower()
        if status_value in {"done", "complete", "completed", "fulfilled", "produced", "1", "true"}:
            return True

        metas = item.get("order_item_metas")
        if isinstance(metas, list) and metas:
            return all(LemiexClient._meta_is_complete(meta) for meta in metas)
        return False

    @staticmethod
    def _meta_is_complete(meta: object) -> bool:
        if not isinstance(meta, dict):
            return False
        status_value = str(meta.get("status", "")).lower()
        return status_value in {"1", "true", "done", "complete", "completed", "fulfilled", "produced"}

    @staticmethod
    def _pending_from_items(items_list: List[object]) -> List[str]:
        pending: List[str] = []
        for item_index, item in enumerate(items_list):
            if LemiexClient._item_is_complete(item):
                continue
            label_prefix = f"Item{item_index + 1}"
            metas = item.get("order_item_metas") if isinstance(item, dict) else None
            if isinstance(metas, list) and metas:
                for meta_index, meta in enumerate(metas):
                    if LemiexClient._meta_is_complete(meta):
                        continue
                    side = str(meta.get("meta_key") or meta.get("type") or f"side{meta_index + 1}")
                    pending.append(f"{label_prefix}/{side}")
            else:
                pending.append(label_prefix)
        return pending

    @staticmethod
    def _item_label(item: object, index: int) -> str:
        if isinstance(item, dict):
            return str(
                item.get("name")
                or item.get("sku")
                or item.get("description")
                or f"item {index + 1}"
            )
        return f"item {index + 1}"


class ProgressCollector:
    """Combines scanner data with Lemiex statuses."""

    def __init__(self, scanner: ScannerProtocol, client: LemiexClient) -> None:
        self.scanner = scanner
        self.client = client

    def collect(self) -> ProgressSnapshot:
        entries = self.scanner.scan()
        ids = sorted({entry.order_id for entry in entries})
        LOGGER.info("Found %d unique Order IDs. Querying API...", len(ids))
        statuses = self.client.lookup(ids) if ids else {}

        date_map: Dict[str, dict] = {}
        missing_ids: List[str] = []

        seen_station_ids: set[tuple[str, str, str]] = set()

        for entry in entries:
            key = (entry.date_folder, entry.station, entry.order_id)
            if key in seen_station_ids:
                continue
            seen_station_ids.add(key)

            date_bucket = date_map.setdefault(
                entry.date_folder,
                {
                    "stations": defaultdict(list),
                    "counted_ids": set(),
                    "done": 0,
                    "total": 0,
                    "orders_done": 0,
                    "orders_total": 0,
                },
            )

            status = statuses.get(entry.order_id)
            if status is None:
                status = OrderStatus(
                    order_id=entry.order_id,
                    done_items=0,
                    total_items=0,
                    pending_items=["Awaiting API response"],
                )
                missing_ids.append(entry.order_id)

            station_list: List[OrderStatus] = date_bucket["stations"][entry.station]
            station_list.append(status)

            if entry.order_id not in date_bucket["counted_ids"]:
                date_bucket["counted_ids"].add(entry.order_id)
                date_bucket["done"] += status.done_items
                date_bucket["total"] += status.total_items
                date_bucket["orders_total"] += 1

                order_done = False
                if status.total_items > 0:
                    order_done = status.done_items >= status.total_items
                elif not status.pending_items:
                    order_done = True
                if order_done:
                    date_bucket["orders_done"] += 1

        date_progress: List[DateProgress] = []
        for date_name, payload in sorted(date_map.items()):
            stations = [
                StationProgress(name=station_name, orders=sorted(station_orders, key=lambda s: s.order_id))
                for station_name, station_orders in sorted(payload["stations"].items())
            ]
            date_progress.append(
                DateProgress(
                    name=date_name,
                    stations=stations,
                    done_items=payload["done"],
                    total_items=payload["total"],
                    completed_orders=payload["orders_done"],
                    total_orders=payload["orders_total"],
                )
            )

        return ProgressSnapshot(dates=date_progress, missing_ids=sorted(set(missing_ids)))
