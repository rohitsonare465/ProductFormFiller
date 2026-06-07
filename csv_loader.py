"""CSV loading and validation for the product form workflow."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd


CSV_COLUMNS: list[str] = [
    "SKU",
    "ASIN",
    "Product Title",
    "Brand",
    "Manufacturer",
    "Model",
    "Category",
    "Short Desc",
    "Long Desc",
    "Search Keywords",
    "Generic",
    "Target",
    "Use",
    "MRP",
    "Selling",
    "Discount",
    "Stock",
    "MOQ",
    "Fulfillment",
    "Weight",
    "Length",
    "Width",
    "Height",
    "Handling",
    "Main Image",
    "Img1",
    "Img2",
    "Img3",
    "Video",
    "Color",
    "Material",
    "Variant",
    "HSN",
    "Origin",
    "Warranty",
    "Safety",
    "Cert",
    "Disclaimer",
    "Return",
    "GST",
    "Barcode",
]

FORM_FIELDS: list[str] = [
    "SKU",
    "ASIN",
    "Product Title",
    "Brand",
    "Manufacturer",
    "Model",
    "Category",
    "Short Description",
    "Long Description",
    "Search Keywords",
    "Generic Keywords",
    "Target Audience",
    "Intended Use",
    "MRP",
    "Selling Price",
    "Discount Percentage",
    "Available Stock",
    "MOQ",
    "Fulfillment Method",
    "Package Weight",
    "Package Length",
    "Package Width",
    "Package Height",
    "Handling Time",
    "Main Image Url",
    "Image1Url",
    "Image2Url",
    "Image3Url",
    "Video Url",
    "Colour",
    "Material",
    "Size Variant",
    "Hsn Code",
    "Country Of Origin",
    "Warranty Details",
    "Safety Information",
    "Certification Details",
    "Legal Disclaimer",
    "Return Policy",
    "GST Percent",
    "Barcode",
]

CSV_TO_FORM: list[tuple[str, str]] = list(zip(CSV_COLUMNS, FORM_FIELDS, strict=True))


def sanitize_form_text(value: object) -> str:
    """Return text that can be typed without sending Enter or embedded Tab."""
    text = str(value).strip()
    safe_characters: list[str] = []
    previous_was_space = False

    for character in text:
        if character in {"\r", "\n", "\t"}:
            if not previous_was_space:
                safe_characters.append(" ")
                previous_was_space = True
            continue
        if character.isprintable():
            safe_characters.append(character)
            previous_was_space = character == " "

    return "".join(safe_characters).strip()


@dataclass(slots=True)
class CsvLoadResult:
    path: Path
    dataframe: pd.DataFrame
    missing_columns: list[str]
    extra_columns: list[str]

    @property
    def is_valid(self) -> bool:
        return not self.missing_columns


def load_product_csv(path: str | Path) -> CsvLoadResult:
    csv_path = Path(path).expanduser().resolve()
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file does not exist: {csv_path}")
    if csv_path.suffix.lower() != ".csv":
        raise ValueError("Please select a .csv file.")

    dataframe = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
    dataframe.columns = [column.strip() for column in dataframe.columns]

    missing = [column for column in CSV_COLUMNS if column not in dataframe.columns]
    extra = [column for column in dataframe.columns if column not in CSV_COLUMNS]

    if not missing:
        dataframe = dataframe[CSV_COLUMNS]

    return CsvLoadResult(
        path=csv_path,
        dataframe=dataframe,
        missing_columns=missing,
        extra_columns=extra,
    )


def row_to_form_values(dataframe: pd.DataFrame, row_index: int) -> list[tuple[str, str, str]]:
    if row_index < 0 or row_index >= len(dataframe.index):
        raise IndexError("Row index is outside the CSV data range.")

    row = dataframe.iloc[row_index]
    values: list[tuple[str, str, str]] = []
    for csv_column, form_field in CSV_TO_FORM:
        value = sanitize_form_text(row.get(csv_column, ""))
        values.append((csv_column, form_field, value))
    return values
