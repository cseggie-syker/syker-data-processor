"""Web-focused DTL processing pipeline.

This module provides a side-effect free API that accepts uploaded files,
decodes recognised Syker Systems ``.dtl`` datasets, and returns a ZIP
archive as bytes. It is designed for use in server/cloud environments where
writing to user-specific directories (e.g. ``~/Downloads``) is not possible.

Typical usage within a web request handler::

    from backend.dtl_processor_web import DTLWebProcessor, UploadedItem

    processor = DTLWebProcessor()
    uploaded = [UploadedItem(filename=file.filename, content=file_bytes)]
    result = processor.process_uploads(uploaded)

    return Response(
        result.zip_bytes,
        headers={
            "Content-Disposition": f"attachment; filename={result.zip_filename}"
        },
        media_type="application/zip",
    )

The implementation mirrors the behaviour of ``dtl_processor_streamlined``
while removing console prints, replacing filesystem-dependent exports with
temporary directories, and returning rich metadata for UI display.
"""

from __future__ import annotations

import io
import os
import shutil
import struct
import tempfile
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Dict, Iterable, List, Mapping, Optional

import pandas as pd


class DTLProcessingError(RuntimeError):
    """Raised when processing fails in a way that should surface to callers."""


@dataclass
class UploadedItem:
    """Represents a single file received from an HTTP upload."""

    filename: str
    content: bytes


@dataclass
class FileDiscovery:
    """Metadata returned after scanning for ``.dtl`` files."""

    type_counts: Dict[str, int]
    total_recognized: int
    unrecognized_count: int
    found_files: Dict[str, List[Dict[str, object]]]

    @property
    def total_files(self) -> int:
        return self.total_recognized + self.unrecognized_count


@dataclass
class DecodedFile:
    """Holds decoded dataframe data and related metadata."""

    dataframe: pd.DataFrame
    file_type: str
    source_file: Path
    original_filename: str
    base_filename: str
    record_count: int

    @property
    def is_empty(self) -> bool:
        return self.dataframe.empty


@dataclass
class ExportedFile:
    """Represents an Excel file that will be placed inside the ZIP archive."""

    file_type: str
    relative_path: Path
    record_count: int


@dataclass
class ProcessingSummary:
    """High-level statistics used for UI or logging."""

    recognized_files: int
    unrecognized_files: int
    files_by_type: Dict[str, int]
    empty_files: List[str]
    failed_files: List[str]


@dataclass
class ProcessingResult:
    """Returned to the caller once processing completes."""

    zip_filename: str
    zip_bytes: bytes
    summary: ProcessingSummary
    exported_files: List[ExportedFile]


class DTLWebProcessor:
    """Expose the streamlined DTL pipeline for server-side usage."""

    def __init__(self, *, timezone_override: Optional[timezone] = timezone.utc):
        self.tz = timezone_override or timezone.utc

    @staticmethod
    def _get_file_type_definitions() -> Dict[str, tuple[str, int]]:
        return {
            "co2days": ("*DataLogCO2Days.dtl", 39),
            "co2months": ("*DataLogCO2Months.dtl", 44),
            "co2year": ("*DataLogCO2Year.dtl", 43),
            "doorclose": ("*DataLogDoorClose.dtl", 46),
            "doordays": ("*DataLogDoorDays.dtl", 39),
            "doormonth": ("*DataLogDoorMonth.dtl", 44),
            "dooropen": ("*DataLogDoorOpen.dtl", 46),
            "dooryear": ("*DataLogDoorYear.dtl", 43),
            "wastedays": ("*DataLogWasteDays.dtl", 39),
            "wastemont": ("*DataLogWasteMont.dtl", 44),
            "wasteyear": ("*DataLogWasteYear.dtl", 43),
            "weightdiff": ("*DataLogWeighDiff.dtl", 46),
            "trendtemp": ("*TrendTemperature.dtl", 46),
            "weightday": ("*WeightDay.dtl", 46),
        }

    def _count_file_types_recursively(self, directory_path: Path) -> FileDiscovery:
        file_types = self._get_file_type_definitions()
        type_counts: Dict[str, int] = {key: 0 for key in file_types}
        found_files: Dict[str, List[Dict[str, object]]] = {key: [] for key in file_types}
        unrecognized_count = 0
        total_recognized = 0

        for root, _, files in os.walk(directory_path):
            root_path = Path(root)
            for filename in files:
                if not filename.lower().endswith(".dtl"):
                    continue

                full_path = root_path / filename
                recognized = False
                for file_type, (pattern, header_length) in file_types.items():
                    if fnmatch(filename, pattern):
                        type_counts[file_type] += 1
                        found_files[file_type].append(
                            {
                                "path": full_path,
                                "filename": filename,
                                "header_length": header_length,
                            }
                        )
                        total_recognized += 1
                        recognized = True
                        break

                if not recognized:
                    unrecognized_count += 1

        return FileDiscovery(
            type_counts=type_counts,
            total_recognized=total_recognized,
            unrecognized_count=unrecognized_count,
            found_files=found_files,
        )

    @staticmethod
    def _decode_dtl_packet(packet: bytes, *, use_integer_encoding: bool = False, tz: timezone) -> Optional[Dict[str, object]]:
        if len(packet) != 9:
            return None

        try:
            unix_timestamp = struct.unpack("<I", packet[0:4])[0]
            ms_data = packet[4]
            if use_integer_encoding:
                data_value = struct.unpack("<i", packet[5:9])[0]
            else:
                data_value = struct.unpack("<f", packet[5:9])[0]

            dt = datetime.fromtimestamp(unix_timestamp, tz=tz)

            return {
                "date_full": dt.strftime("%Y-%m-%d"),
                "time_full": dt.strftime("%H:%M:%S"),
                "ms": ms_data * 10,
                "value": data_value,
            }
        except (struct.error, OSError, ValueError):
            return None

    @staticmethod
    def _validate_dtl_file(filepath: Path, header_length: int) -> bool:
        try:
            if not filepath.exists():
                return False

            file_size = filepath.stat().st_size
            if file_size < header_length:
                return False

            remaining_bytes = file_size - header_length
            return remaining_bytes % 9 == 0
        except OSError:
            return False

    def _parse_dtl_file(self, filepath: Path, header_length: int, file_type: str) -> pd.DataFrame:
        door_patterns = ["DataLogDoorDays", "DataLogDoorMonth", "DataLogDoorYear"]
        use_integer_encoding = any(pattern in filepath.name for pattern in door_patterns)

        if not self._validate_dtl_file(filepath, header_length):
            return pd.DataFrame(columns=["date_full", "time_full", "ms", "value"])

        records: List[Dict[str, object]] = []

        try:
            with filepath.open("rb") as file:
                file.seek(header_length)
                while True:
                    packet = file.read(9)
                    if len(packet) < 9:
                        break

                    decoded = self._decode_dtl_packet(packet, use_integer_encoding=use_integer_encoding, tz=self.tz)
                    if decoded is not None:
                        records.append(decoded)

        except (OSError, IOError):
            return pd.DataFrame(columns=["date_full", "time_full", "ms", "value"])

        if not records:
            return pd.DataFrame(columns=["date_full", "time_full", "ms", "value"])

        df = pd.DataFrame(records)
        df = df.sort_values(["date_full", "time_full"]).reset_index(drop=True)
        return df[["date_full", "time_full", "ms", "value"]]

    def _decode_all_files(self, discovery: FileDiscovery) -> Dict[str, DecodedFile]:
        decoded_results: Dict[str, DecodedFile] = {}

        for file_type, files_list in discovery.found_files.items():
            if not files_list:
                continue

            for file_info in files_list:
                filepath = Path(file_info["path"])  # type: ignore[index]
                header_length = int(file_info["header_length"])  # type: ignore[index]

                df = self._parse_dtl_file(filepath, header_length, file_type)

                original_filename = Path(file_info["filename"]).name  # type: ignore[index]
                base_filename = Path(original_filename).stem

                decoded_results[base_filename] = DecodedFile(
                    dataframe=df,
                    file_type=file_type,
                    source_file=filepath,
                    original_filename=original_filename,
                    base_filename=base_filename,
                    record_count=len(df),
                )

        return decoded_results

    @staticmethod
    def _sanitize_archive_label(label: str) -> str:
        sanitized = re.sub(r"[^A-Za-z0-9_-]+", "-", label.strip())
        sanitized = re.sub(r"-{2,}", "-", sanitized).strip("-_")
        return sanitized or "Syker_Processed_Data"

    @staticmethod
    def _column_mapping(file_type: str) -> Dict[str, str]:
        value_columns = {
            "co2days": "CO2 Emissions Prevented (kg)",
            "co2months": "CO2 Emissions Prevented (kg)",
            "co2year": "CO2 Emissions Prevented (kg)",
            "doorclose": "Instances of Door Closures",
            "doordays": "Instances of Door Actions",
            "doormonth": "Door Openings per Day",
            "dooropen": "Instances of Door Openings",
            "dooryear": "Door Openings per Day",
            "wastedays": "Cummulative Waste per Day (kg)",
            "wastemont": "Total Waste per Day (kg)",
            "wasteyear": "Total Waste per day (kg)",
            "weightdiff": "Weight Difference across door open and close (kg)",
            "trendtemp": "Recorded Temperature (°C)",
            "weightday": "Recorded Weight (kg)",
        }

        mapping = {
            "date_full": "Date",
            "time_full": "Time",
            "ms": "Milliseconds",
            "value": value_columns.get(file_type, "Value"),
        }
        return mapping

    def _export_to_excel(
        self,
        decoded_data: Mapping[str, DecodedFile],
        output_root: Path,
        *,
        custom_columns: Optional[Dict[str, str]] = None,
    ) -> tuple[List[ExportedFile], Dict[str, int]]:
        try:
            import openpyxl  # noqa: F401
        except ImportError as exc:
            raise DTLProcessingError(
                "openpyxl is required to export Excel files. Install it via 'pip install openpyxl'."
            ) from exc

        files_by_type: Dict[str, int] = {}
        exported_files: List[ExportedFile] = []

        for decoded in decoded_data.values():
            type_folder = output_root / decoded.file_type
            type_folder.mkdir(parents=True, exist_ok=True)

            if decoded.dataframe.empty:
                df_export = decoded.dataframe.copy()
            else:
                column_mapping = self._column_mapping(decoded.file_type)
                if custom_columns:
                    column_mapping.update(custom_columns)
                df_export = decoded.dataframe.rename(columns=column_mapping)

            excel_path = type_folder / f"{decoded.base_filename}.xlsx"
            df_export.to_excel(excel_path, index=False, engine="openpyxl")

            files_by_type.setdefault(decoded.file_type, 0)
            files_by_type[decoded.file_type] += 1

            exported_files.append(
                ExportedFile(
                    file_type=decoded.file_type,
                    relative_path=excel_path.relative_to(output_root.parent),
                    record_count=decoded.record_count,
                )
            )

        return exported_files, files_by_type

    @staticmethod
    def _build_zip_bytes(folder_path: Path, archive_name: str) -> bytes:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for file in folder_path.rglob("*"):
                if file.is_file():
                    relative = Path(archive_name) / file.relative_to(folder_path)
                    zip_file.write(file, relative.as_posix())
        buffer.seek(0)
        return buffer.getvalue()

    def process_directory(
        self,
        directory: Path,
        *,
        custom_columns: Optional[Dict[str, str]] = None,
        archive_label: Optional[str] = None,
    ) -> ProcessingResult:
        if not directory.exists() or not directory.is_dir():
            raise DTLProcessingError(f"Directory '{directory}' does not exist or is not a directory.")

        discovery = self._count_file_types_recursively(directory)

        if discovery.total_recognized == 0:
            raise DTLProcessingError("No recognised .dtl files were found in the uploaded data.")

        decoded = self._decode_all_files(discovery)

        timestamp = datetime.now().strftime("%Y%m%d")
        base_label_input = archive_label or "Syker_Processed_Data"
        base_label = self._sanitize_archive_label(base_label_input)
        folder_name = f"{base_label}-Converted{timestamp}"
        export_root = directory / folder_name
        export_root.mkdir(parents=True, exist_ok=True)

        exported_files, files_by_type = self._export_to_excel(
            decoded,
            export_root,
            custom_columns=custom_columns,
        )

        empty_files = [decoded.original_filename for decoded in decoded.values() if decoded.is_empty]
        failed_files: List[str] = []

        zip_filename = f"{folder_name}.zip"
        zip_bytes = self._build_zip_bytes(export_root, folder_name)

        summary = ProcessingSummary(
            recognized_files=discovery.total_recognized,
            unrecognized_files=discovery.unrecognized_count,
            files_by_type=files_by_type,
            empty_files=empty_files,
            failed_files=failed_files,
        )

        return ProcessingResult(
            zip_filename=zip_filename,
            zip_bytes=zip_bytes,
            summary=summary,
            exported_files=exported_files,
        )

    def process_uploads(
        self,
        uploads: Iterable[UploadedItem],
        *,
        custom_columns: Optional[Dict[str, str]] = None,
        archive_label: Optional[str] = None,
    ) -> ProcessingResult:
        uploads = list(uploads)
        if not uploads:
            raise DTLProcessingError("At least one file must be uploaded for processing.")

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            uploads_root = temp_path / "uploads"
            uploads_root.mkdir(parents=True, exist_ok=True)

            self._materialise_uploads(uploads, uploads_root)

            result = self.process_directory(
                uploads_root,
                custom_columns=custom_columns,
                archive_label=archive_label,
            )

            return result

    @staticmethod
    def _materialise_uploads(uploads: Iterable[UploadedItem], destination_root: Path) -> None:
        for index, item in enumerate(uploads):
            filename = item.filename or f"upload_{index}.dtl"

            buffer = io.BytesIO(item.content)
            if DTLWebProcessor._is_zip_content(buffer):
                buffer.seek(0)
                subfolder = destination_root / Path(f"archive_{index}")
                subfolder.mkdir(parents=True, exist_ok=True)
                with zipfile.ZipFile(buffer) as zf:
                    DTLWebProcessor._safe_extract_zip(zf, subfolder)
                continue

            relative_path = DTLWebProcessor._safe_relative_path(filename)
            target_path = destination_root / relative_path
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_bytes(item.content)

    @staticmethod
    def _is_zip_content(buffer: io.BytesIO) -> bool:
        try:
            return zipfile.is_zipfile(buffer)
        finally:
            buffer.seek(0)

    @staticmethod
    def _safe_relative_path(filename: str) -> Path:
        pure_path = PurePosixPath(filename)
        normalized_parts = [part for part in pure_path.parts if part not in ("..", "")]
        if not normalized_parts:
            normalized_parts = ["unnamed_uploaded_file.dtl"]
        return Path(*normalized_parts)

    @staticmethod
    def _safe_extract_zip(zf: zipfile.ZipFile, destination: Path) -> None:
        for member in zf.infolist():
            member_path = destination / DTLWebProcessor._safe_relative_path(member.filename)
            if member.is_dir():
                member_path.mkdir(parents=True, exist_ok=True)
            else:
                member_path.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member) as source, member_path.open("wb") as target:
                    shutil.copyfileobj(source, target)


def fnmatch(filename: str, pattern: str) -> bool:
    """Wrapper for fnmatch.fnmatch to avoid repeated imports."""

    from fnmatch import fnmatch as _fnmatch

    return _fnmatch(filename, pattern)


