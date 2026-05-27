from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from openpyxl import Workbook

from structai.pipeline.profile import profile_document

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def two_sheet_xlsx(tmp_path: Path) -> Path:
    wb = Workbook()
    customers = wb.active
    assert customers is not None
    customers.title = "customers"
    customers.append(["id", "name"])
    customers.append([1, "Alice"])
    customers.append([2, "Bob"])

    orders = wb.create_sheet("orders")
    orders.append(["id", "customer_id", "total"])
    orders.append([10, 1, 99.5])
    orders.append([11, 2, 12.0])
    orders.append([12, 1, 5.25])

    p = tmp_path / "shop.xlsx"
    wb.save(p)
    return p


def test_profile_xlsx_multi_sheet(two_sheet_xlsx: Path) -> None:
    prof = profile_document(two_sheet_xlsx, "xlsx")
    assert prof.format == "xlsx"
    names = {r.name for r in prof.regions}
    assert names == {"customers", "orders"}
    by_name = {r.name: r for r in prof.regions}
    assert by_name["customers"].row_count == 2
    assert by_name["orders"].row_count == 3
