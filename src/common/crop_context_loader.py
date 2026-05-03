"""Runtime loader for generated SA2 crop context CSV data.

This module only reads ``data/meta/crop_context_sa2.csv``. It does not wire
crop context into the risk engine or publisher.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional, Union


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CROP_CONTEXT_PATH = (
    REPO_ROOT / "data" / "meta" / "crop_context_sa2.csv"
)

REQUIRED_COLUMNS = [
    "sa2_code",
    "station_sa2_5dig16",
    "sa2_name",
    "state",
    "financial_year",
    "crop",
    "area_ha",
    "production_t",
    "yield_t_ha",
    "area_share",
    "area_rse",
    "production_rse",
    "yield_rse",
    "source_dataset",
    "source_commodity_area",
    "source_commodity_production",
    "source_commodity_yield",
    "boundary_status",
    "notes",
]


@dataclass(frozen=True)
class CropContextRecord:
    """One row from ``crop_context_sa2.csv`` with typed numeric measures."""

    sa2_code: str
    station_sa2_5dig16: str
    sa2_name: str
    state: str
    financial_year: str
    crop: str
    area_ha: Optional[float]
    production_t: Optional[float]
    yield_t_ha: Optional[float]
    area_share: Optional[float]
    area_rse: str
    production_rse: str
    yield_rse: str
    source_dataset: str
    source_commodity_area: str
    source_commodity_production: str
    source_commodity_yield: str
    boundary_status: str
    notes: str

    @classmethod
    def from_csv_row(cls, row: dict[str, str]) -> "CropContextRecord":
        """Build a record while preserving code and RSE fields as strings."""
        return cls(
            sa2_code=_text(row, "sa2_code"),
            station_sa2_5dig16=_text(row, "station_sa2_5dig16"),
            sa2_name=_text(row, "sa2_name"),
            state=_text(row, "state"),
            financial_year=_text(row, "financial_year"),
            crop=_text(row, "crop"),
            area_ha=_optional_float(row, "area_ha"),
            production_t=_optional_float(row, "production_t"),
            yield_t_ha=_optional_float(row, "yield_t_ha"),
            area_share=_optional_float(row, "area_share"),
            area_rse=_text(row, "area_rse"),
            production_rse=_text(row, "production_rse"),
            yield_rse=_text(row, "yield_rse"),
            source_dataset=_text(row, "source_dataset"),
            source_commodity_area=_text(row, "source_commodity_area"),
            source_commodity_production=_text(
                row, "source_commodity_production"
            ),
            source_commodity_yield=_text(row, "source_commodity_yield"),
            boundary_status=_text(row, "boundary_status"),
            notes=_text(row, "notes"),
        )


class CropContextLookup:
    """Convenience index for loaded crop context records."""

    def __init__(self, records: Iterable[CropContextRecord]):
        self.records = list(records)
        self._by_sa2_code: dict[str, list[CropContextRecord]] = {}
        self._by_station_sa2: dict[str, list[CropContextRecord]] = {}
        self._by_state: dict[str, list[CropContextRecord]] = {}

        for record in self.records:
            if record.sa2_code:
                self._by_sa2_code.setdefault(
                    record.sa2_code, []
                ).append(record)
            self._by_station_sa2.setdefault(
                record.station_sa2_5dig16, []
            ).append(record)
            self._by_state.setdefault(record.state, []).append(record)

    def for_sa2_code(
        self,
        sa2_code: str,
        crop: Optional[str] = None,
        financial_year: Optional[str] = None,
    ) -> list[CropContextRecord]:
        """Return records for a full 9-digit ABS SA2 code."""
        return _filter_records(
            self._by_sa2_code.get(str(sa2_code), []),
            crop=crop,
            financial_year=financial_year,
        )

    def for_station_sa2(
        self,
        station_sa2_5dig16: str,
        crop: Optional[str] = None,
        financial_year: Optional[str] = None,
    ) -> list[CropContextRecord]:
        """Return records for a station metadata ``SA2_5DIG16`` code."""
        return _filter_records(
            self._by_station_sa2.get(str(station_sa2_5dig16), []),
            crop=crop,
            financial_year=financial_year,
        )

    def for_state(
        self,
        state: str,
        crop: Optional[str] = None,
        financial_year: Optional[str] = None,
    ) -> list[CropContextRecord]:
        """Return records for an Australian state name."""
        return _filter_records(
            self._by_state.get(state, []),
            crop=crop,
            financial_year=financial_year,
        )

    def get_by_sa2_crop(
        self,
        sa2_code: str,
        crop: str,
        financial_year: Optional[str] = None,
    ) -> Optional[CropContextRecord]:
        """Return one SA2/crop record, or ``None`` when absent."""
        return _one_or_none(
            self.for_sa2_code(
                sa2_code, crop=crop, financial_year=financial_year
            )
        )

    def get_by_station_sa2_crop(
        self,
        station_sa2_5dig16: str,
        crop: str,
        financial_year: Optional[str] = None,
    ) -> Optional[CropContextRecord]:
        """Return one station-SA2/crop record, or ``None`` when absent."""
        return _one_or_none(
            self.for_station_sa2(
                station_sa2_5dig16, crop=crop, financial_year=financial_year
            )
        )

    def crops_for_station_sa2(
        self,
        station_sa2_5dig16: str,
        financial_year: Optional[str] = None,
    ) -> dict[str, CropContextRecord]:
        """Return ``{crop: record}`` for a station SA2 code."""
        records = self.for_station_sa2(
            station_sa2_5dig16, financial_year=financial_year
        )
        result = {}
        for record in records:
            if record.crop in result:
                raise ValueError(
                    "Multiple crop context records matched; specify "
                    "financial_year."
                )
            result[record.crop] = record
        return result


def crop_context_exists(
    path: Union[Path, str] = DEFAULT_CROP_CONTEXT_PATH,
) -> bool:
    """Return whether the generated crop context CSV is present."""
    return Path(path).exists()


def load_crop_context(
    path: Union[Path, str] = DEFAULT_CROP_CONTEXT_PATH,
) -> list[CropContextRecord]:
    """Load ``crop_context_sa2.csv`` and return typed records.

    Raises:
        FileNotFoundError: if the generated CSV is absent.
        ValueError: if required columns are missing or numeric values are
            invalid.
    """
    csv_path = Path(path)
    if not csv_path.exists():
        raise FileNotFoundError(
            f"Crop context CSV not found: {csv_path}. "
            "Run scripts/build_crop_context.py to generate it."
        )

    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        _validate_columns(reader.fieldnames, csv_path)
        return [CropContextRecord.from_csv_row(row) for row in reader]


def load_crop_context_lookup(
    path: Union[Path, str] = DEFAULT_CROP_CONTEXT_PATH,
) -> CropContextLookup:
    """Load crop context records and return an indexed lookup helper."""
    return CropContextLookup(load_crop_context(path))


def _validate_columns(fieldnames: Optional[list[str]], path: Path) -> None:
    present = set(fieldnames or [])
    missing = [column for column in REQUIRED_COLUMNS if column not in present]
    if missing:
        raise ValueError(
            f"{path} is missing required columns: {', '.join(missing)}"
        )


def _text(row: dict[str, str], field: str) -> str:
    value = row.get(field)
    return "" if value is None else value


def _optional_float(row: dict[str, str], field: str) -> Optional[float]:
    raw = (row.get(field) or "").strip()
    if raw == "":
        return None
    try:
        return float(raw)
    except ValueError as exc:
        message = f"Invalid numeric value for {field}: {raw!r}"
        raise ValueError(message) from exc


def _filter_records(
    records: Iterable[CropContextRecord],
    crop: Optional[str] = None,
    financial_year: Optional[str] = None,
) -> list[CropContextRecord]:
    result = list(records)
    if crop is not None:
        result = [record for record in result if record.crop == crop]
    if financial_year is not None:
        result = [
            record
            for record in result
            if record.financial_year == financial_year
        ]
    return result


def _one_or_none(
    records: list[CropContextRecord],
) -> Optional[CropContextRecord]:
    if not records:
        return None
    if len(records) > 1:
        keys = sorted({record.financial_year for record in records})
        raise ValueError(
            "Multiple crop context records matched; specify financial_year. "
            f"Available financial years: {', '.join(keys)}"
        )
    return records[0]
