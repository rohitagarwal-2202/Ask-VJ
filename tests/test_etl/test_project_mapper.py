"""
Tests for ProjectMapper — validates crosswalk seeding and unmapped detection.
"""

import pytest
from unittest.mock import patch, MagicMock, call

from backend.etl.resolvers.project_mapper import ProjectMapper


@pytest.fixture()
def mapper():
    with patch("backend.etl.resolvers.project_mapper.create_engine", return_value=MagicMock()):
        return ProjectMapper(warehouse_connection_string="postgresql://dummy")


# ──────────────────────────────────────────────────────────────────────
# seed_crosswalk
# ──────────────────────────────────────────────────────────────────────

def test_seed_crosswalk_calls_execute(mapper):
    """Verify that seed_crosswalk executes an INSERT query for each mapping."""
    mock_conn = MagicMock()
    mapper.engine.begin.return_value.__enter__ = MagicMock(return_value=mock_conn)
    mapper.engine.begin.return_value.__exit__ = MagicMock(return_value=False)

    mappings = [
        {
            "canonical_name": "Project Alpha",
            "farvision_bu_id": 101,
            "phase_name": "Phase 1",
            "vjsales_project_name": "Alpha",
            "vjop_project_name": "Alpha RNL",
        },
        {
            "canonical_name": "Project Beta",
            "farvision_bu_id": 102,
            "phase_name": None,
            "vjsales_project_name": "Beta",
            "vjop_project_name": None,
        },
    ]

    mapper.seed_crosswalk(mappings)

    # Should have called conn.execute once per mapping
    assert mock_conn.execute.call_count == 2

    # Verify the second positional arg of each call is the mapping dict
    for i, mapping in enumerate(mappings):
        actual_call = mock_conn.execute.call_args_list[i]
        assert actual_call[0][1] == mapping


# ──────────────────────────────────────────────────────────────────────
# detect_unmapped_projects
# ──────────────────────────────────────────────────────────────────────

def test_detect_unmapped_returns_three_categories(mapper):
    """Verify detect_unmapped_projects returns dict with exactly three keys."""
    mock_conn = MagicMock()
    mapper.engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
    mapper.engine.connect.return_value.__exit__ = MagicMock(return_value=False)

    # Each execute().fetchall()-like iteration returns empty results
    mock_conn.execute.return_value = iter([])

    result = mapper.detect_unmapped_projects()

    assert isinstance(result, dict)
    assert set(result.keys()) == {"vjsales_unmapped", "farvision_unmapped", "vjop_unmapped"}
