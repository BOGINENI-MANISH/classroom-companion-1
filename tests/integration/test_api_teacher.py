"""Integration tests for teacher API routes.

Tests all four teacher endpoints:
  GET  /api/teacher/{id}/dashboard
  GET  /api/teacher/{id}/assignments
  GET  /api/teacher/{id}/student/{sid}/summary
  POST /api/teacher/{id}/assignment
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest


# ── GET /dashboard ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_dashboard_returns_200(teacher_client, teacher_user):
    r = await teacher_client.get(f"/api/teacher/{teacher_user.id}/dashboard")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_dashboard_teacher_not_found(teacher_client):
    r = await teacher_client.get("/api/teacher/99999/dashboard")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_dashboard_fields(teacher_client, teacher_user, student_user, active_assignment):
    r = await teacher_client.get(f"/api/teacher/{teacher_user.id}/dashboard")
    data = r.json()
    assert data["total_students"] == 1
    assert data["assignments_in_progress"] == 1
    assert data["teacher"]["full_name"] == teacher_user.full_name


# ── GET /assignments ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_assignments_returns_200(teacher_client, teacher_user, active_assignment):
    r = await teacher_client.get(f"/api/teacher/{teacher_user.id}/assignments")
    assert r.status_code == 200
    assert isinstance(r.json(), list)
    assert len(r.json()) >= 1


@pytest.mark.asyncio
async def test_list_assignments_filter_by_status(teacher_client, teacher_user, active_assignment):
    r = await teacher_client.get(
        f"/api/teacher/{teacher_user.id}/assignments",
        params={"status": "in_progress"},
    )
    assert r.status_code == 200
    for item in r.json():
        assert item["status"] == "in_progress"


@pytest.mark.asyncio
async def test_list_assignments_filter_unknown_status(teacher_client, teacher_user, active_assignment):
    r = await teacher_client.get(
        f"/api/teacher/{teacher_user.id}/assignments",
        params={"status": "does_not_exist"},
    )
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_list_assignments_teacher_not_found(teacher_client):
    r = await teacher_client.get("/api/teacher/99999/assignments")
    assert r.status_code == 404


# ── GET /student/{sid}/summary ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_student_summary_returns_200(teacher_client, teacher_user, student_user, active_assignment, mock_llm):
    with patch("api.routes.teacher.get_llm_provider", return_value=mock_llm):
        r = await teacher_client.get(
            f"/api/teacher/{teacher_user.id}/student/{student_user.id}/summary"
        )
    assert r.status_code == 200
    data = r.json()
    assert data["student_id"] == student_user.id
    assert isinstance(data["assignments"], list)


@pytest.mark.asyncio
async def test_student_summary_teacher_not_found(teacher_client, student_user):
    r = await teacher_client.get(f"/api/teacher/99999/student/{student_user.id}/summary")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_student_summary_student_not_found(teacher_client, teacher_user):
    r = await teacher_client.get(f"/api/teacher/{teacher_user.id}/student/99999/summary")
    assert r.status_code == 404


# ── POST /assignment ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_assignment_success(teacher_client, teacher_user, student_user):
    due = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
    payload = {
        "student_telegram_id": student_user.telegram_id,
        "title": "New Essay",
        "description": "Write 300 words.",
        "due_date": due,
    }
    r = await teacher_client.post(
        f"/api/teacher/{teacher_user.id}/assignment", json=payload
    )
    assert r.status_code == 201
    data = r.json()
    assert data["title"] == "New Essay"
    assert data["status"] == "pending"


@pytest.mark.asyncio
async def test_create_assignment_unknown_student(teacher_client, teacher_user):
    due = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
    payload = {
        "student_telegram_id": 999999,
        "title": "Ghost Essay",
        "description": "x",
        "due_date": due,
    }
    r = await teacher_client.post(
        f"/api/teacher/{teacher_user.id}/assignment", json=payload
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_create_assignment_teacher_not_found(teacher_client, student_user):
    due = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
    payload = {
        "student_telegram_id": student_user.telegram_id,
        "title": "x",
        "description": "x",
        "due_date": due,
    }
    r = await teacher_client.post("/api/teacher/99999/assignment", json=payload)
    assert r.status_code == 404
