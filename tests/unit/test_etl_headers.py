import pytest
from src.services.etl import ETLService, CsvMapping
from pathlib import Path


@pytest.mark.asyncio
async def test_mixed_case_headers(tmp_path):
    p = tmp_path / "data.csv"
    p.write_text("User_ID,Name\n1,Ada\n2,Bob\n")
    etl = ETLService(db=None)
    # Ensure function can read and normalize headers without raising
    result = await etl.import_nodes_csv(
        str(p), label="User", mapping=CsvMapping(id_column="User_ID"), lower_case_headers=True
    )
    assert result is not None
