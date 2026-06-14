"""
Tests for DataImporter in crawlers/base.py.

Focuses on import_problems, import_records, and import_all with mocked Prisma client.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from crawlers.base import DataImporter


# ──────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────

@pytest.fixture
def prisma_mock() -> MagicMock:
    """Return a mock Prisma client with problem.upsert and record.upsert as AsyncMock."""
    mock = MagicMock()
    mock.problem = MagicMock()
    mock.problem.upsert = AsyncMock(return_value=None)
    mock.record = MagicMock()
    mock.record.upsert = AsyncMock(return_value=None)
    return mock


def _make_importer(prisma_mock: MagicMock, data_dir: str) -> DataImporter:
    importer = DataImporter(prisma_mock)
    importer.data_dir = Path(data_dir)
    return importer


# ──────────────────────────────────────────────
# import_problems
# ──────────────────────────────────────────────

class TestImportProblems:
    """Tests for DataImporter.import_problems."""

    @pytest.mark.asyncio
    async def test_upserts_single_problem(self, prisma_mock: MagicMock) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            importer = _make_importer(prisma_mock, td)
            pdir = importer._platform_dir("leetcode") / "problems"
            pdir.mkdir(parents=True)
            (pdir / "2025-06-13_two-sum.json").write_text(
                '{"source_id":"two-sum","title":"Two Sum","difficulty":"Easy","tags":["array","hash-table"],"content":"Find two numbers..."}',
                encoding="utf-8",
            )

            count = await importer.import_problems("leetcode")

            assert count == 1
            prisma_mock.problem.upsert.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_upsert_uses_platform_and_source_id_in_where(self, prisma_mock: MagicMock) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            importer = _make_importer(prisma_mock, td)
            pdir = importer._platform_dir("codeforces") / "problems"
            pdir.mkdir(parents=True)
            (pdir / "cf_problem.json").write_text(
                '{"source_id":"1742E","title":"Binary Search","difficulty":"Medium","tags":["binary-search"]}',
                encoding="utf-8",
            )

            await importer.import_problems("codeforces")

            upsert_call = prisma_mock.problem.upsert.call_args
            where_clause = upsert_call[1]["where"]
            assert where_clause == {
                "platform_source_id": {
                    "platform": "codeforces",
                    "source_id": "1742E",
                }
            }

    @pytest.mark.asyncio
    async def test_upsert_includes_all_fields_in_create(self, prisma_mock: MagicMock) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            importer = _make_importer(prisma_mock, td)
            pdir = importer._platform_dir("leetcode") / "problems"
            pdir.mkdir(parents=True)
            (pdir / "p1.json").write_text(
                '{"source_id":"p1","title":"T","difficulty":"Hard","tags":["a","b"],"content":"body"}',
                encoding="utf-8",
            )

            await importer.import_problems("leetcode")

            create_data = prisma_mock.problem.upsert.call_args[1]["data"]["create"]
            assert create_data["platform"] == "leetcode"
            assert create_data["source_id"] == "p1"
            assert create_data["title"] == "T"
            assert create_data["difficulty"] == "Hard"
            assert create_data["tags"] == ["a", "b"]
            assert create_data["content"] == "body"
            assert create_data["raw_data"] == {
                "source_id": "p1", "title": "T", "difficulty": "Hard",
                "tags": ["a", "b"], "content": "body",
            }

    @pytest.mark.asyncio
    async def test_upsert_includes_all_fields_in_update(self, prisma_mock: MagicMock) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            importer = _make_importer(prisma_mock, td)
            pdir = importer._platform_dir("leetcode") / "problems"
            pdir.mkdir(parents=True)
            (pdir / "p1.json").write_text(
                '{"source_id":"p1","title":"Updated Title","difficulty":"Easy","tags":["c"],"content":"new body"}',
                encoding="utf-8",
            )

            await importer.import_problems("leetcode")

            update_data = prisma_mock.problem.upsert.call_args[1]["data"]["update"]
            assert update_data["title"] == "Updated Title"
            assert update_data["difficulty"] == "Easy"
            assert update_data["tags"] == ["c"]
            assert update_data["content"] == "new body"
            assert update_data["raw_data"] is not None

    @pytest.mark.asyncio
    async def test_import_from_list_file(self, prisma_mock: MagicMock) -> None:
        """File contains a list of problem records."""
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            importer = _make_importer(prisma_mock, td)
            pdir = importer._platform_dir("leetcode") / "problems"
            pdir.mkdir(parents=True)
            (pdir / "batch.json").write_text(
                '[{"source_id":"a1","title":"A"}, {"source_id":"a2","title":"B"}]',
                encoding="utf-8",
            )

            count = await importer.import_problems("leetcode")
            assert count == 2
            assert prisma_mock.problem.upsert.await_count == 2

    @pytest.mark.asyncio
    async def test_uses_id_field_when_source_id_missing(self, prisma_mock: MagicMock) -> None:
        """When source_id is missing, falls back to id field."""
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            importer = _make_importer(prisma_mock, td)
            pdir = importer._platform_dir("leetcode") / "problems"
            pdir.mkdir(parents=True)
            (pdir / "p1.json").write_text(
                '{"id":"my-id","title":"Test"}', encoding="utf-8"
            )

            count = await importer.import_problems("leetcode")
            assert count == 1
            where_clause = prisma_mock.problem.upsert.call_args[1]["where"]
            assert where_clause["platform_source_id"]["source_id"] == "my-id"

    @pytest.mark.asyncio
    async def test_skips_missing_source_id_and_id(self, prisma_mock: MagicMock) -> None:
        """When neither source_id nor id is present, skip the record."""
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            importer = _make_importer(prisma_mock, td)
            pdir = importer._platform_dir("cf") / "problems"
            pdir.mkdir(parents=True)
            (pdir / "bad.json").write_text(
                '{"title":"No ID","content":"test"}', encoding="utf-8"
            )

            count = await importer.import_problems("cf")
            assert count == 0
            prisma_mock.problem.upsert.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_skips_source_id_none(self, prisma_mock: MagicMock) -> None:
        """When source_id and id are both None, skip."""
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            importer = _make_importer(prisma_mock, td)
            pdir = importer._platform_dir("cf") / "problems"
            pdir.mkdir(parents=True)
            (pdir / "none_id.json").write_text(
                '{"source_id":null,"id":null,"title":"No ID"}', encoding="utf-8"
            )

            count = await importer.import_problems("cf")
            assert count == 0
            prisma_mock.problem.upsert.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_handles_upsert_exception(self, prisma_mock: MagicMock) -> None:
        """When upsert raises, the error is caught and count not incremented."""
        prisma_mock.problem.upsert.side_effect = RuntimeError("DB connection lost")
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            importer = _make_importer(prisma_mock, td)
            pdir = importer._platform_dir("leetcode") / "problems"
            pdir.mkdir(parents=True)
            (pdir / "p1.json").write_text(
                '{"source_id":"p1","title":"Test"}', encoding="utf-8"
            )

            count = await importer.import_problems("leetcode")
            assert count == 0

    @pytest.mark.asyncio
    async def test_empty_directory_returns_zero(self, prisma_mock: MagicMock) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            importer = _make_importer(prisma_mock, td)
            count = await importer.import_problems("leetcode")
            assert count == 0

    @pytest.mark.asyncio
    async def test_date_filter_only_matching_files(self, prisma_mock: MagicMock) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            importer = _make_importer(prisma_mock, td)
            pdir = importer._platform_dir("leetcode") / "problems"
            pdir.mkdir(parents=True)
            (pdir / "2025-06-13_abc.json").write_text(
                '{"source_id":"abc","title":"ABC"}', encoding="utf-8"
            )
            (pdir / "2025-06-14_def.json").write_text(
                '{"source_id":"def","title":"DEF"}', encoding="utf-8"
            )

            count = await importer.import_problems("leetcode", date="2025-06-13")
            assert count == 1
            prisma_mock.problem.upsert.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_multiple_records_different_files(self, prisma_mock: MagicMock) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            importer = _make_importer(prisma_mock, td)
            pdir = importer._platform_dir("leetcode") / "problems"
            pdir.mkdir(parents=True)
            (pdir / "a.json").write_text('{"source_id":"id1","title":"A"}', encoding="utf-8")
            (pdir / "b.json").write_text('{"source_id":"id2","title":"B"}', encoding="utf-8")
            (pdir / "c.json").write_text('{"source_id":"id3","title":"C"}', encoding="utf-8")

            count = await importer.import_problems("leetcode")
            assert count == 3
            assert prisma_mock.problem.upsert.await_count == 3

    @pytest.mark.asyncio
    async def test_default_missing_fields(self, prisma_mock: MagicMock) -> None:
        """Missing optional fields should default to empty strings/lists."""
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            importer = _make_importer(prisma_mock, td)
            pdir = importer._platform_dir("leetcode") / "problems"
            pdir.mkdir(parents=True)
            (pdir / "minimal.json").write_text(
                '{"source_id":"min"}', encoding="utf-8"
            )

            count = await importer.import_problems("leetcode")
            assert count == 1
            create_data = prisma_mock.problem.upsert.call_args[1]["data"]["create"]
            assert create_data["title"] == ""
            assert create_data["tags"] == []
            assert create_data["content"] == ""
            assert create_data["difficulty"] is None


# ──────────────────────────────────────────────
# import_records
# ──────────────────────────────────────────────

class TestImportRecords:
    """Tests for DataImporter.import_records."""

    @pytest.mark.asyncio
    async def test_upserts_single_record(self, prisma_mock: MagicMock) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            importer = _make_importer(prisma_mock, td)
            rdir = importer._platform_dir("leetcode") / "records"
            rdir.mkdir(parents=True)
            (rdir / "2025-06-13_rec.json").write_text(
                '{"id":"rec1","uid":"user1","problem_id":"two-sum","verdict":"AC","language":"python","timestamp":1700000000}',
                encoding="utf-8",
            )

            count = await importer.import_records("leetcode")
            assert count == 1
            prisma_mock.record.upsert.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_upsert_uses_platform_and_record_id_in_where(self, prisma_mock: MagicMock) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            importer = _make_importer(prisma_mock, td)
            rdir = importer._platform_dir("codeforces") / "records"
            rdir.mkdir(parents=True)
            (rdir / "rec.json").write_text(
                '{"id":"sub123","uid":"tourist","problem_id":"1742E","verdict":"OK","language":"cpp","timestamp":1700000000}',
                encoding="utf-8",
            )

            await importer.import_records("codeforces")

            where_clause = prisma_mock.record.upsert.call_args[1]["where"]
            assert where_clause == {
                "platform_record_id": {
                    "platform": "codeforces",
                    "record_id": "sub123",
                }
            }

    @pytest.mark.asyncio
    async def test_upsert_falls_back_to_record_id_field(self, prisma_mock: MagicMock) -> None:
        """When id is missing, falls back to record_id field."""
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            importer = _make_importer(prisma_mock, td)
            rdir = importer._platform_dir("leetcode") / "records"
            rdir.mkdir(parents=True)
            (rdir / "rec.json").write_text(
                '{"record_id":"r99","uid":"u","problem_id":"p"}', encoding="utf-8"
            )

            count = await importer.import_records("leetcode")
            assert count == 1
            where_clause = prisma_mock.record.upsert.call_args[1]["where"]
            assert where_clause["platform_record_id"]["record_id"] == "r99"

    @pytest.mark.asyncio
    async def test_upsert_falls_back_to_composite_key(self, prisma_mock: MagicMock) -> None:
        """When neither id nor record_id, uses uid_timestamp composite."""
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            importer = _make_importer(prisma_mock, td)
            rdir = importer._platform_dir("leetcode") / "records"
            rdir.mkdir(parents=True)
            (rdir / "rec.json").write_text(
                '{"uid":"user1","timestamp":1234567890,"verdict":"AC"}', encoding="utf-8"
            )

            count = await importer.import_records("leetcode")
            assert count == 1
            where_clause = prisma_mock.record.upsert.call_args[1]["where"]
            assert where_clause["platform_record_id"]["record_id"] == "user1_1234567890"

    @pytest.mark.asyncio
    async def test_import_from_list_file(self, prisma_mock: MagicMock) -> None:
        """File contains a list of record dicts."""
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            importer = _make_importer(prisma_mock, td)
            rdir = importer._platform_dir("leetcode") / "records"
            rdir.mkdir(parents=True)
            (rdir / "batch.json").write_text(
                '[{"id":"r1","uid":"u1","problem_id":"p1"}, {"id":"r2","uid":"u2","problem_id":"p2"}]',
                encoding="utf-8",
            )

            count = await importer.import_records("leetcode")
            assert count == 2
            assert prisma_mock.record.upsert.await_count == 2

    @pytest.mark.asyncio
    async def test_handles_upsert_exception(self, prisma_mock: MagicMock) -> None:
        """When record upsert raises, error is caught and count not incremented."""
        prisma_mock.record.upsert.side_effect = RuntimeError("DB offline")
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            importer = _make_importer(prisma_mock, td)
            rdir = importer._platform_dir("cf") / "records"
            rdir.mkdir(parents=True)
            (rdir / "rec.json").write_text(
                '{"id":"r1","uid":"u","problem_id":"p"}', encoding="utf-8"
            )

            count = await importer.import_records("cf")
            assert count == 0

    @pytest.mark.asyncio
    async def test_empty_directory_returns_zero(self, prisma_mock: MagicMock) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            importer = _make_importer(prisma_mock, td)
            count = await importer.import_records("leetcode")
            assert count == 0

    @pytest.mark.asyncio
    async def test_date_filter(self, prisma_mock: MagicMock) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            importer = _make_importer(prisma_mock, td)
            rdir = importer._platform_dir("leetcode") / "records"
            rdir.mkdir(parents=True)
            (rdir / "2025-06-13_rec.json").write_text(
                '{"id":"r1","uid":"u1","problem_id":"p1"}', encoding="utf-8"
            )
            (rdir / "2025-06-14_rec.json").write_text(
                '{"id":"r2","uid":"u2","problem_id":"p2"}', encoding="utf-8"
            )

            count = await importer.import_records("leetcode", date="2025-06-13")
            assert count == 1
            prisma_mock.record.upsert.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_all_fields_in_create(self, prisma_mock: MagicMock) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            importer = _make_importer(prisma_mock, td)
            rdir = importer._platform_dir("leetcode") / "records"
            rdir.mkdir(parents=True)
            (rdir / "rec.json").write_text(
                '{"id":"r1","uid":"user1","problem_id":"p1","verdict":"AC","language":"python3","timestamp":"2025-06-13T10:00:00Z","extra":"ignored"}',
                encoding="utf-8",
            )

            await importer.import_records("leetcode")

            create_data = prisma_mock.record.upsert.call_args[1]["data"]["create"]
            assert create_data["platform"] == "leetcode"
            assert create_data["record_id"] == "r1"
            assert create_data["uid"] == "user1"
            assert create_data["problem_id"] == "p1"
            assert create_data["verdict"] == "AC"
            assert create_data["language"] == "python3"
            assert create_data["timestamp"] == "2025-06-13T10:00:00Z"
            assert create_data["raw_data"] is not None

    @pytest.mark.asyncio
    async def test_default_missing_fields_in_create(self, prisma_mock: MagicMock) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            importer = _make_importer(prisma_mock, td)
            rdir = importer._platform_dir("leetcode") / "records"
            rdir.mkdir(parents=True)
            (rdir / "minimal.json").write_text(
                '{"id":"min1"}', encoding="utf-8"
            )

            await importer.import_records("leetcode")

            create_data = prisma_mock.record.upsert.call_args[1]["data"]["create"]
            assert create_data["uid"] == ""
            assert create_data["problem_id"] is None
            assert create_data["verdict"] is None
            assert create_data["language"] is None
            assert create_data["timestamp"] is None

    @pytest.mark.asyncio
    async def test_duplicate_skips_in_prisma_layer(self, prisma_mock: MagicMock) -> None:
        """Duplicate entries are handled by the upsert (update) semantics."""
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            importer = _make_importer(prisma_mock, td)
            pdir = importer._platform_dir("leetcode") / "problems"
            pdir.mkdir(parents=True)
            # Two files with the same source_id.
            (pdir / "first.json").write_text(
                '{"source_id":"dup","title":"First"}', encoding="utf-8"
            )
            (pdir / "second.json").write_text(
                '{"source_id":"dup","title":"Second"}', encoding="utf-8"
            )

            count = await importer.import_problems("leetcode")
            # Both are upserted (second overwrites first).
            assert count == 2
            assert prisma_mock.problem.upsert.await_count == 2


# ──────────────────────────────────────────────
# import_all
# ──────────────────────────────────────────────

class TestImportAll:
    """Tests for DataImporter.import_all."""

    @pytest.mark.asyncio
    async def test_import_all_no_dir(self, prisma_mock: MagicMock) -> None:
        importer = DataImporter(prisma_mock)
        importer.data_dir = Path("/nonexistent/path/xyz")
        results = await importer.import_all()
        assert results == {}

    @pytest.mark.asyncio
    async def test_import_all_with_multiple_platforms(self, prisma_mock: MagicMock) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            importer = _make_importer(prisma_mock, td)
            for plat in ("leetcode", "codeforces", "atcoder"):
                pdir = importer._platform_dir(plat) / "problems"
                pdir.mkdir(parents=True)
                (pdir / f"{plat}_p1.json").write_text(
                    f'{{"source_id":"{plat}-1","title":"P1"}}', encoding="utf-8"
                )

            results = await importer.import_all()
            assert len(results) == 3
            assert results["leetcode"]["problems"] == 1
            assert results["codeforces"]["problems"] == 1
            assert results["atcoder"]["problems"] == 1
            assert prisma_mock.problem.upsert.await_count == 3

    @pytest.mark.asyncio
    async def test_import_all_includes_records(self, prisma_mock: MagicMock) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            importer = _make_importer(prisma_mock, td)
            pdir = importer._platform_dir("leetcode") / "problems"
            rdir = importer._platform_dir("leetcode") / "records"
            pdir.mkdir(parents=True)
            rdir.mkdir(parents=True)
            (pdir / "p1.json").write_text('{"source_id":"lc-1","title":"A"}', encoding="utf-8")
            (rdir / "r1.json").write_text(
                '{"id":"rec1","uid":"u","problem_id":"lc-1","verdict":"AC"}', encoding="utf-8"
            )

            results = await importer.import_all()
            assert results["leetcode"]["problems"] == 1
            assert results["leetcode"]["records"] == 1
            prisma_mock.problem.upsert.assert_awaited_once()
            prisma_mock.record.upsert.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_import_all_with_date_filter(self, prisma_mock: MagicMock) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            importer = _make_importer(prisma_mock, td)
            pdir = importer._platform_dir("leetcode") / "problems"
            pdir.mkdir(parents=True)
            (pdir / "2025-06-13_a.json").write_text('{"source_id":"a","title":"A"}', encoding="utf-8")
            (pdir / "2025-06-14_b.json").write_text('{"source_id":"b","title":"B"}', encoding="utf-8")

            results = await importer.import_all(date="2025-06-13")
            assert results["leetcode"]["problems"] == 1
            prisma_mock.problem.upsert.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_import_all_skips_non_dirs(self, prisma_mock: MagicMock) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            importer = _make_importer(prisma_mock, td)
            # Put a file (not dir) at top level.
            (Path(td) / "README.txt").write_text("hello", encoding="utf-8")
            # Put a real platform dir with problems.
            pdir = importer._platform_dir("leetcode") / "problems"
            pdir.mkdir(parents=True)
            (pdir / "p1.json").write_text('{"source_id":"lc-1","title":"T"}', encoding="utf-8")

            results = await importer.import_all()
            assert "leetcode" in results
            assert "README.txt" not in results
            assert results["leetcode"]["problems"] == 1

    @pytest.mark.asyncio
    async def test_import_all_skips_platform_with_no_data(self, prisma_mock: MagicMock) -> None:
        """Platform dir exists but has no JSON files -> excluded from results."""
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            importer = _make_importer(prisma_mock, td)
            # Create directory but no files.
            pdir = importer._platform_dir("empty_platform") / "problems"
            pdir.mkdir(parents=True)

            results = await importer.import_all()
            assert "empty_platform" not in results


# ──────────────────────────────────────────────
# _read_json_files edge cases
# ──────────────────────────────────────────────

class TestReadJsonFiles:
    """Tests for DataImporter._read_json_files static method."""

    def test_missing_directory_returns_empty_list(self) -> None:
        records = DataImporter._read_json_files(Path("/nonexistent/dir/abc"))
        assert records == []

    def test_single_dict_file(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            (d / "file.json").write_text('{"key":"value"}', encoding="utf-8")
            records = DataImporter._read_json_files(d)
            assert records == [{"key": "value"}]

    def test_list_file(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            (d / "list.json").write_text('[{"a":1},{"b":2}]', encoding="utf-8")
            records = DataImporter._read_json_files(d)
            assert records == [{"a": 1}, {"b": 2}]

    def test_mixed_single_and_list_files(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            (d / "single.json").write_text('{"x":1}', encoding="utf-8")
            (d / "list.json").write_text('[{"y":2},{"z":3}]', encoding="utf-8")
            records = DataImporter._read_json_files(d)
            assert len(records) == 3
            assert {"x": 1} in records
            assert {"y": 2} in records
            assert {"z": 3} in records

    def test_skips_broken_json(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            (d / "bad.json").write_text("not valid { json", encoding="utf-8")
            (d / "good.json").write_text('{"ok":true}', encoding="utf-8")
            records = DataImporter._read_json_files(d)
            assert records == [{"ok": True}]

    def test_date_filter(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            (d / "2025-06-13_a.json").write_text('{"id":"a"}', encoding="utf-8")
            (d / "2025-06-13_b.json").write_text('{"id":"b"}', encoding="utf-8")
            (d / "2025-06-14_c.json").write_text('{"id":"c"}', encoding="utf-8")
            records = DataImporter._read_json_files(d, date="2025-06-13")
            assert records == [{"id": "a"}, {"id": "b"}]

    def test_date_filter_no_date_no_prefix(self) -> None:
        """When no date is set, all *.json files are matched."""
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            (d / "abc.json").write_text('{"id":"a"}', encoding="utf-8")
            (d / "def.json").write_text('{"id":"b"}', encoding="utf-8")
            records = DataImporter._read_json_files(d)
            assert len(records) == 2

    def test_handles_oserror(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            (d / "bad.json").write_text('{"a":1}', encoding="utf-8")
            with patch("pathlib.Path.read_text", side_effect=OSError("permission denied")):
                records = DataImporter._read_json_files(d)
            assert records == []

    def test_empty_directory(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            records = DataImporter._read_json_files(d)
            assert records == []

    def test_sorted_glob_order(self) -> None:
        """Files are read in sorted order."""
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            (d / "c.json").write_text('{"id":"c"}', encoding="utf-8")
            (d / "a.json").write_text('{"id":"a"}', encoding="utf-8")
            (d / "b.json").write_text('{"id":"b"}', encoding="utf-8")
            records = DataImporter._read_json_files(d)
            assert [r["id"] for r in records] == ["a", "b", "c"]


# ──────────────────────────────────────────────
# DataImporter initialization
# ──────────────────────────────────────────────

class TestDataImporterInit:
    """Tests for DataImporter.__init__."""

    def test_stores_prisma_client(self) -> None:
        mock = MagicMock()
        di = DataImporter(mock)
        assert di.prisma is mock

    def test_default_data_dir(self) -> None:
        di = DataImporter(MagicMock())
        assert di.data_dir == Path("data/raw")

    def test_platform_dir(self) -> None:
        di = DataImporter(MagicMock())
        assert di._platform_dir("leetcode") == Path("data/raw/leetcode")
        assert di._platform_dir("codeforces") == Path("data/raw/codeforces")
