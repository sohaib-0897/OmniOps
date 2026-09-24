"""Focused tests for the Concept B read-only endpoints.

* ``GET /workspaces/{id}/files/{file_id}/outline`` — passage map for the source track.
* ``GET /workspaces/{id}/investigations`` — paginated investigation history.
"""
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, get_password_hash
from app.models.document import DocumentChunk, SourceDocument
from app.models.investigation import InvestigationSession
from app.models.user import User, UserSession, Workspace, WorkspaceMembership, WorkspaceRole

SECRET_MARKER = "CONFIDENTIAL-PASSAGE-TEXT-7f3a"


async def _source(db: AsyncSession, workspace_id, *, modality="pdf", name="report.pdf", status="ready") -> SourceDocument:
    doc = SourceDocument(
        workspace_id=workspace_id,
        file_name=name,
        storage_path=f"/storage/{uuid.uuid4().hex}",
        mime_type="application/octet-stream",
        byte_size=1024,
        sha256_hash=uuid.uuid4().hex,
        modality=modality,
        processing_status=status,
    )
    db.add(doc)
    await db.flush()
    return doc


def _chunk(doc: SourceDocument, index: int, content: str, **extra) -> DocumentChunk:
    return DocumentChunk(
        workspace_id=doc.workspace_id,
        source_id=doc.id,
        chunk_index=index,
        content=content,
        modality=doc.modality,
        extraction_method=extra.pop("extraction_method", "NATIVE_TEXT"),
        chunk_metadata=extra.pop("chunk_metadata", {}),
        **extra,
    )


async def _foreign_tenant(db: AsyncSession) -> tuple[User, Workspace, dict]:
    other = User(email=f"other-{uuid.uuid4().hex[:8]}@example.com", hashed_password=get_password_hash("OtherPass123!"), full_name="Other")
    db.add(other)
    await db.flush()
    ws = Workspace(name="Foreign", created_by=other.id)
    db.add(ws)
    await db.flush()
    db.add(WorkspaceMembership(workspace_id=ws.id, user_id=other.id, role=WorkspaceRole.OWNER.value))
    now = datetime.now(timezone.utc)
    session = UserSession(user_id=other.id, expires_at=now + timedelta(days=1), last_used_at=now)
    db.add(session)
    await db.commit()
    token = create_access_token(subject=other.id, session_id=session.id)
    return other, ws, {"Authorization": f"Bearer {token}"}


def _outline_url(workspace_id, file_id) -> str:
    return f"/api/v1/workspaces/{workspace_id}/files/{file_id}/outline"


# ---------------------------------------------------------------------------
# Passage map
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_outline_requires_authentication(client: AsyncClient, db_session, test_workspace):
    doc = await _source(db_session, test_workspace.id)
    await db_session.commit()
    resp = await client.get(_outline_url(test_workspace.id, doc.id))
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_outline_pdf_ordering_lengths_and_pages(client, db_session, test_workspace, auth_headers):
    doc = await _source(db_session, test_workspace.id)
    # Inserted out of order to prove ordering is by chunk_index, not insertion.
    texts = {2: "c" * 30, 0: "a" * 120, 1: "b" * 45}
    pages = {0: 1, 1: 1, 2: 2}
    for index in (2, 0, 1):
        db_session.add(_chunk(doc, index, texts[index], page_number=pages[index], chunk_metadata={"page": pages[index], "char_count": len(texts[index])}))
    await db_session.commit()

    resp = await client.get(_outline_url(test_workspace.id, doc.id), headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["source_id"] == str(doc.id)
    assert data["modality"] == "pdf"
    assert data["processing_status"] == "ready"
    assert data["passage_count"] == 3
    assert data["chunk_index"] == [0, 1, 2]
    assert data["char_length"] == [120, 45, 30]
    assert data["page_number"] == [1, 1, 2]
    assert data["heading"] == [None, None, None]
    assert data["audio_start_ms"] == [None, None, None]
    assert len(data["chunk_id"]) == 3 and len(set(data["chunk_id"])) == 3


@pytest.mark.asyncio
async def test_outline_docx_reports_headings_without_pages(client, db_session, test_workspace, auth_headers):
    doc = await _source(db_session, test_workspace.id, modality="docx", name="memo.docx")
    db_session.add(_chunk(doc, 0, "## Summary\nRevenue grew.", extraction_method="DOCX_TEXT", chunk_metadata={"heading": "Summary"}))
    db_session.add(_chunk(doc, 1, "## Risks\nChurn rose.", extraction_method="DOCX_TEXT", chunk_metadata={"heading": "Risks"}))
    await db_session.commit()

    data = (await client.get(_outline_url(test_workspace.id, doc.id), headers=auth_headers)).json()["data"]
    assert data["heading"] == ["Summary", "Risks"]
    assert data["page_number"] == [None, None]
    assert data["char_length"] == [len("## Summary\nRevenue grew."), len("## Risks\nChurn rose.")]


@pytest.mark.asyncio
async def test_outline_audio_reports_timestamps(client, db_session, test_workspace, auth_headers):
    doc = await _source(db_session, test_workspace.id, modality="audio", name="call.mp3")
    db_session.add(_chunk(doc, 0, "hello there", audio_start_ms=0, audio_end_ms=4200, extraction_method="TRANSCRIPTION"))
    db_session.add(_chunk(doc, 1, "general kenobi", audio_start_ms=4200, audio_end_ms=9100, extraction_method="TRANSCRIPTION"))
    await db_session.commit()

    data = (await client.get(_outline_url(test_workspace.id, doc.id), headers=auth_headers)).json()["data"]
    assert data["audio_start_ms"] == [0, 4200]
    assert data["audio_end_ms"] == [4200, 9100]
    assert data["page_number"] == [None, None]


@pytest.mark.asyncio
async def test_outline_empty_source_returns_empty_columns(client, db_session, test_workspace, auth_headers):
    doc = await _source(db_session, test_workspace.id, modality="spreadsheet", name="sales.xlsx")
    await db_session.commit()

    resp = await client.get(_outline_url(test_workspace.id, doc.id), headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["passage_count"] == 0
    for column in ("chunk_id", "chunk_index", "char_length", "page_number", "audio_start_ms", "audio_end_ms", "heading"):
        assert data[column] == []


@pytest.mark.asyncio
async def test_outline_unknown_and_deleted_source_is_404(client, db_session, test_workspace, auth_headers):
    resp = await client.get(_outline_url(test_workspace.id, uuid.uuid4()), headers=auth_headers)
    assert resp.status_code == 404

    doc = await _source(db_session, test_workspace.id)
    db_session.add(_chunk(doc, 0, "soon gone"))
    await db_session.commit()
    doc_id = doc.id
    await db_session.delete(doc)
    await db_session.commit()
    resp = await client.get(_outline_url(test_workspace.id, doc_id), headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_outline_denies_foreign_workspace(client, db_session, test_workspace, auth_headers):
    _, foreign_ws, _ = await _foreign_tenant(db_session)
    foreign_doc = await _source(db_session, foreign_ws.id)
    db_session.add(_chunk(foreign_doc, 0, SECRET_MARKER))
    await db_session.commit()

    resp = await client.get(_outline_url(foreign_ws.id, foreign_doc.id), headers=auth_headers)
    assert resp.status_code == 403
    assert SECRET_MARKER not in resp.text


@pytest.mark.asyncio
async def test_outline_enforces_source_ownership_across_workspaces(client, db_session, test_workspace, auth_headers):
    """A foreign source id addressed through the caller's own workspace is not found."""
    _, foreign_ws, _ = await _foreign_tenant(db_session)
    foreign_doc = await _source(db_session, foreign_ws.id)
    db_session.add(_chunk(foreign_doc, 0, SECRET_MARKER))
    await db_session.commit()

    resp = await client.get(_outline_url(test_workspace.id, foreign_doc.id), headers=auth_headers)
    assert resp.status_code == 404
    assert SECRET_MARKER not in resp.text


@pytest.mark.asyncio
async def test_outline_never_leaks_passage_content(client, db_session, test_workspace, auth_headers):
    doc = await _source(db_session, test_workspace.id, modality="docx", name="secret.docx")
    db_session.add(_chunk(
        doc, 0, f"## Heading\n{SECRET_MARKER} with more words",
        extraction_method="DOCX_TEXT",
        chunk_metadata={"heading": "Heading", "extraction_id": "x", "note": SECRET_MARKER},
    ))
    await db_session.commit()

    resp = await client.get(_outline_url(test_workspace.id, doc.id), headers=auth_headers)
    assert resp.status_code == 200
    assert SECRET_MARKER not in resp.text
    data = resp.json()["data"]
    assert "content" not in data
    assert set(data) == {
        "source_id", "modality", "processing_status", "passage_count", "chunk_id",
        "chunk_index", "char_length", "page_number", "audio_start_ms", "audio_end_ms", "heading",
    }
    assert json.dumps(data).count("Heading") == 1


# ---------------------------------------------------------------------------
# Investigation history
# ---------------------------------------------------------------------------

def _history_url(workspace_id, **params) -> str:
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return f"/api/v1/workspaces/{workspace_id}/investigations" + (f"?{query}" if query else "")


async def _investigation(db, workspace_id, user_id, objective, created_at, status="completed", completed_at=None):
    session = InvestigationSession(
        workspace_id=workspace_id,
        user_id=user_id,
        objective=objective,
        status=status,
        created_at=created_at,
        completed_at=completed_at,
        final_response={"executive_summary": SECRET_MARKER},
        failure_message=None,
    )
    db.add(session)
    await db.flush()
    return session


@pytest.mark.asyncio
async def test_history_requires_authentication(client, test_workspace):
    resp = await client.get(_history_url(test_workspace.id))
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_history_is_newest_first_minimal_and_paginated(client, db_session, test_user, test_workspace, auth_headers):
    base = datetime(2026, 9, 1, tzinfo=timezone.utc)
    for day in range(5):
        await _investigation(
            db_session, test_workspace.id, test_user.id, f"Question {day}",
            created_at=base + timedelta(days=day),
            completed_at=base + timedelta(days=day, minutes=2),
        )
    await _investigation(db_session, test_workspace.id, test_user.id, "Still running", created_at=base + timedelta(days=9), status="running")
    await db_session.commit()

    resp = await client.get(_history_url(test_workspace.id, limit=2), headers=auth_headers)
    assert resp.status_code == 200
    page = resp.json()["data"]
    assert page["total"] == 6 and page["limit"] == 2 and page["offset"] == 0
    assert [item["objective"] for item in page["items"]] == ["Still running", "Question 4"]
    assert page["items"][0]["status"] == "running" and page["items"][0]["completed_at"] is None
    assert set(page["items"][0]) == {"id", "objective", "status", "created_at", "completed_at"}
    assert SECRET_MARKER not in resp.text

    second = (await client.get(_history_url(test_workspace.id, limit=2, offset=2), headers=auth_headers)).json()["data"]
    assert [item["objective"] for item in second["items"]] == ["Question 3", "Question 2"]

    tail = (await client.get(_history_url(test_workspace.id, limit=100, offset=6), headers=auth_headers)).json()["data"]
    assert tail["items"] == [] and tail["total"] == 6


@pytest.mark.asyncio
async def test_history_rejects_out_of_range_pagination(client, test_workspace, auth_headers):
    for params in ({"limit": 0}, {"limit": 101}, {"offset": -1}):
        resp = await client.get(_history_url(test_workspace.id, **params), headers=auth_headers)
        assert resp.status_code == 422


@pytest.mark.asyncio
async def test_history_is_tenant_filtered(client, db_session, test_user, test_workspace, auth_headers):
    other, foreign_ws, foreign_headers = await _foreign_tenant(db_session)
    now = datetime.now(timezone.utc)
    await _investigation(db_session, test_workspace.id, test_user.id, "Mine", created_at=now)
    await _investigation(db_session, foreign_ws.id, other.id, "Theirs", created_at=now)
    await db_session.commit()

    mine = (await client.get(_history_url(test_workspace.id), headers=auth_headers)).json()["data"]
    assert [item["objective"] for item in mine["items"]] == ["Mine"]

    denied = await client.get(_history_url(foreign_ws.id), headers=auth_headers)
    assert denied.status_code == 403
    assert "Theirs" not in denied.text

    theirs = (await client.get(_history_url(foreign_ws.id), headers=foreign_headers)).json()["data"]
    assert [item["objective"] for item in theirs["items"]] == ["Theirs"]
