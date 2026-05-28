"""Integration tests for student API routes.

Tests all three student endpoints:
  GET /api/student/{id}/dashboard
  GET /api/student/{id}/assignments
  GET /api/student/{id}/assignments/{aid}
"""
from unittest.mock import patch

import pytest


# ── GET /dashboard ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_student_dashboard_200(student_client, student_user):
    r = await student_client.get(f"/api/student/{student_user.id}/dashboard")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_student_dashboard_not_found(student_client):
    r = await student_client.get("/api/student/99999/dashboard")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_student_dashboard_counts(student_client, student_user, active_assignment):
    r = await student_client.get(f"/api/student/{student_user.id}/dashboard")
    data = r.json()
    assert data["student_id"] == student_user.id
    assert data["student_name"] == student_user.full_name
    assert data["total_assignments"] == 1
    assert data["in_progress"] == 1
    assert data["submitted"] == 0


# ── GET /assignments ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_student_assignments_200(student_client, student_user, active_assignment, mock_llm):
    with patch("api.routes.student.get_llm_provider", return_value=mock_llm):
        r = await student_client.get(f"/api/student/{student_user.id}/assignments")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    assert len(body) == 1
    assert body[0]["id"] == active_assignment.id


@pytest.mark.asyncio
async def test_list_student_assignments_fields(student_client, student_user, active_assignment, mock_llm):
    with patch("api.routes.student.get_llm_provider", return_value=mock_llm):
        r = await student_client.get(f"/api/student/{student_user.id}/assignments")
    item = r.json()[0]
    assert item["title"] == active_assignment.title
    assert item["status"] == "in_progress"
    assert isinstance(item["progress_updates"], list)
    assert item["submission"] is None


@pytest.mark.asyncio
async def test_list_student_assignments_not_found(student_client):
    r = await student_client.get("/api/student/99999/assignments")
    assert r.status_code == 404


# ── GET /assignments/{aid} ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_assignment_detail_200(student_client, student_user, active_assignment, mock_llm):
    with patch("api.routes.student.get_llm_provider", return_value=mock_llm):
        r = await student_client.get(
            f"/api/student/{student_user.id}/assignments/{active_assignment.id}"
        )
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == active_assignment.id
    assert data["title"] == active_assignment.title


@pytest.mark.asyncio
async def test_get_assignment_detail_wrong_student(student_client, teacher_user, active_assignment, mock_llm):
    """A different student cannot see another student's assignment."""
    with patch("api.routes.student.get_llm_provider", return_value=mock_llm):
        r = await student_client.get(
            f"/api/student/{teacher_user.id}/assignments/{active_assignment.id}"
        )
    # teacher_user.id with role='teacher' → 404 from _get_student_or_404
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_get_assignment_detail_not_found(student_client, student_user, mock_llm):
    with patch("api.routes.student.get_llm_provider", return_value=mock_llm):
        r = await student_client.get(
            f"/api/student/{student_user.id}/assignments/99999"
        )
    assert r.status_code == 404
