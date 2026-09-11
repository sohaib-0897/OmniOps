import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User, Workspace, WorkspaceMembership, WorkspaceRole
from app.models.document import SourceDocument, TabularDataset
from app.models.investigation import InvestigationSession, InvestigationStatus
from app.core.security import create_access_token, get_password_hash
from app.tools.python_sandbox import PythonSandboxRunner
from app.tools.duckdb_tool import DuckDBTool
from app.ingestion.web_fetcher import validate_url_security, is_ip_prohibited
from app.ingestion.file_guard import sanitize_filename, validate_magic_bytes

# 1. ADVERSARIAL PYTHON SANDBOX TESTS
def test_sandbox_adversarial_evasions():
    # Attempt 1: Direct forbidden function calls
    res1 = PythonSandboxRunner.execute("x = eval('1 + 1')")
    assert res1.success is False
    assert "restricted function 'eval'" in res1.error_message

    # Attempt 2: Direct open / filesystem access
    res2 = PythonSandboxRunner.execute("f = open('/etc/passwd', 'r')")
    assert res2.success is False
    assert "restricted function 'open'" in res2.error_message

    # Attempt 3: Direct introspection attribute access
    res3 = PythonSandboxRunner.execute("x = ().__class__.__bases__[0].__subclasses__()")
    assert res3.success is False
    assert "Access to introspection attribute '__class__'" in res3.error_message

    # Attempt 4: Unauthorized module import
    res4 = PythonSandboxRunner.execute("import subprocess\nsubprocess.run(['ls'])")
    assert res4.success is False
    assert "Import of unauthorized module 'subprocess'" in res4.error_message

    # Attempt 5: Unauthorized from-import
    res5 = PythonSandboxRunner.execute("from os import system\nsystem('echo hacked')")
    assert res5.success is False
    assert "Import from unauthorized module 'os'" in res5.error_message

    # Attempt 6: Pandas read_csv / read_pickle escape attempt
    res6 = PythonSandboxRunner.execute("import pandas as pd\ndf = pd.read_csv('/etc/passwd')")
    assert res6.success is False
    assert "read_csv" in res6.error_message.lower() or "prohibited" in res6.error_message.lower()

    # Attempt 7: Pandas read_pickle bytecode execution escape
    res7 = PythonSandboxRunner.execute("import pandas as pd\nx = pd.read_pickle('payload.pkl')")
    assert res7.success is False
    assert "read_pickle" in res7.error_message.lower() or "prohibited" in res7.error_message.lower()

    # Attempt 8: Infinite loop timeout enforcement
    res8 = PythonSandboxRunner.execute("while True: pass", timeout_seconds=1)
    assert res8.success is False
    assert "timed out" in res8.error_message

# 2. ADVERSARIAL DUCKDB TESTS
def test_duckdb_adversarial_queries():
    tool = DuckDBTool({})

    # Attempt 1: Mixed-case and whitespace evasion
    res1 = tool.execute_query("   InStALL   httpfs;  ")
    assert res1.success is False
    assert "Security violation" in res1.error_message

    # Attempt 2: Comment injection with LOAD
    res2 = tool.execute_query("SELECT 1; /* comment */ LOAD httpfs;")
    assert res2.success is False
    assert "Security violation" in res2.error_message

    # Attempt 3: Nested CTE with read_parquet
    res3 = tool.execute_query("WITH p AS (SELECT * FROM read_parquet('/tmp/secrets.parquet')) SELECT * FROM p;")
    assert res3.success is False
    assert "Security violation" in res3.error_message

    # Attempt 4: ATTACH command
    res4 = tool.execute_query("ATTACH '/tmp/other.db' AS ext;")
    assert res4.success is False
    assert "Security violation" in res4.error_message

    # Attempt 5: read_csv table function
    res5 = tool.execute_query("SELECT * FROM read_csv('/etc/shadow');")
    assert res5.success is False
    assert "Security violation" in res5.error_message

# 3. ADVERSARIAL SSRF TESTS
def test_ssrf_adversarial_vectors():
    # Attempt 1: Loopback IPv4
    with pytest.raises(ValueError, match="restricted"):
        validate_url_security("http://127.0.0.1:8000/api")

    # Attempt 2: Localhost keyword
    with pytest.raises(ValueError, match="restricted"):
        validate_url_security("http://localhost:3000")

    # Attempt 3: 0.0.0.0 current network
    with pytest.raises(ValueError, match="restricted"):
        validate_url_security("http://0.0.0.0:80")

    # Attempt 4: Cloud metadata IP
    assert is_ip_prohibited("169.254.169.254") is True
    assert is_ip_prohibited("10.0.1.50") is True
    assert is_ip_prohibited("192.168.1.1") is True
    assert is_ip_prohibited("172.16.0.1") is True
    assert is_ip_prohibited("::1") is True

    # Attempt 5: Unsupported scheme (file://, gopher://, ftp://)
    with pytest.raises(ValueError, match="Invalid URL scheme"):
        validate_url_security("file:///etc/passwd")

    with pytest.raises(ValueError, match="Invalid URL scheme"):
        validate_url_security("gopher://127.0.0.1:70")

# 4. ADVERSARIAL FILE SECURITY TESTS
def test_file_security_adversarial_inputs():
    # Attempt 1: Linux Directory Traversal
    clean1 = sanitize_filename("../../../../etc/passwd")
    assert ".." not in clean1
    assert "/" not in clean1
    assert clean1 == "passwd"

    # Attempt 2: Windows Directory Traversal
    clean2 = sanitize_filename("..\\..\\Windows\\System32\\cmd.exe")
    assert ".." not in clean2
    assert "\\" not in clean2
    assert "cmd.exe" in clean2

    # Attempt 3: Null byte injection
    clean3 = sanitize_filename("report.pdf\x00.exe")
    assert "\x00" not in clean3

    # Attempt 4: Magic byte mismatch (executable disguised as PDF)
    assert validate_magic_bytes(b"MZ\x90\x00\x03\x00\x00\x00", ".pdf") is False
    assert validate_magic_bytes(b"%PDF-1.4", ".pdf") is True

# 5. ADVERSARIAL MULTI-TENANT IDOR & RBAC INTEGRATION TESTS
@pytest.mark.asyncio
async def test_adversarial_cross_tenant_idor(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user: User,
    test_workspace: Workspace,
    auth_headers: dict
):
    # Create Victim Workspace and Victim Document
    victim_user = User(
        email="victim_corp@company.com",
        hashed_password=get_password_hash("VictimPass123!"),
        full_name="Victim CEO"
    )
    db_session.add(victim_user)
    await db_session.flush()

    victim_ws = Workspace(
        name="Victim Secret Workspace",
        created_by=victim_user.id
    )
    db_session.add(victim_ws)
    await db_session.flush()

    victim_mem = WorkspaceMembership(
        workspace_id=victim_ws.id,
        user_id=victim_user.id,
        role=WorkspaceRole.OWNER.value
    )
    db_session.add(victim_mem)

    victim_doc = SourceDocument(
        workspace_id=victim_ws.id,
        file_name="q3_merger_confidential.pdf",
        storage_path="/tmp/fake_path.pdf",
        mime_type="application/pdf",
        byte_size=1024,
        sha256_hash="deadbeef12345678",
        modality="pdf",
        processing_status="ready"
    )
    db_session.add(victim_doc)

    victim_session = InvestigationSession(
        workspace_id=victim_ws.id,
        user_id=victim_user.id,
        objective="Analyze merger acquisition targets",
        status=InvestigationStatus.COMPLETED.value
    )
    db_session.add(victim_session)
    await db_session.commit()

    # Adversarial Attempt 1: Test User queries victim document chunks preview
    preview_resp = await client.get(
        f"/api/v1/workspaces/{victim_ws.id}/files/{victim_doc.id}/preview",
        headers=auth_headers
    )
    assert preview_resp.status_code == 403

    # Adversarial Attempt 2: Test User attempts to delete victim document
    del_resp = await client.delete(
        f"/api/v1/workspaces/{victim_ws.id}/files/{victim_doc.id}",
        headers=auth_headers
    )
    assert del_resp.status_code == 403

    # Adversarial Attempt 3: Test User attempts to read victim investigation details
    inv_resp = await client.get(
        f"/api/v1/investigations/{victim_session.id}",
        headers=auth_headers
    )
    assert inv_resp.status_code == 403

    # Adversarial Attempt 4: Test User attempts to stream victim investigation SSE
    stream_resp = await client.get(
        f"/api/v1/investigations/{victim_session.id}/stream", headers=auth_headers
    )
    assert stream_resp.status_code == 403

    # Adversarial Attempt 5: Test User attempts to get victim evidence lineage
    ev_resp = await client.get(
        f"/api/v1/investigations/{victim_session.id}/evidence",
        headers=auth_headers
    )
    assert ev_resp.status_code == 403
