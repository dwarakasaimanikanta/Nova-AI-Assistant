import os
import shutil
import subprocess
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from core.action_result import ActionResult
from core.application_controller import ApplicationController
from core.conversation_context import get_conversation_context
from core.executive_agent import ExecutiveAgent, ExecutionStatus
from core.engine import NovaEngine
from memory.short_term import ShortTermMemory
from tools.browser import BrowserTool
from tools.file_manager import FileManagerTool
from tools.permission_gate import PermissionGate
from tools.terminal import TerminalTool
from tools.base_tool import RiskLevel


@pytest.fixture(autouse=True)
def clean_context():
    ExecutiveAgent._processed_requests.clear()
    ctx = get_conversation_context()
    ctx.reset()
    yield
    ExecutiveAgent._processed_requests.clear()
    ctx.reset()


# 1. Open Chrome success
def test_open_chrome_success():
    controller = ApplicationController()
    with patch("os.path.exists", return_value=True), \
         patch("shutil.which", return_value="C:\\chrome.exe"), \
         patch("subprocess.Popen") as mock_popen:
        
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_popen.return_value = mock_proc
        
        res = controller.launch("chrome")
        assert res.success is True
        assert res.action == "launch_app"
        assert res.target == "chrome"
        
        ctx = get_conversation_context()
        assert ctx.last_application == "chrome"


# 2. Missing executable
def test_missing_executable():
    controller = ApplicationController()
    with patch("os.path.exists", return_value=False), \
         patch("shutil.which", return_value=None):
        
        res = controller.launch("nonexistent_app")
        assert res.success is False
        assert "was not found on this system" in res.error


# 3. Open YouTube
def test_open_youtube():
    mock_manager = MagicMock()
    mock_manager.open_url.return_value = "Success: Opened URL"
    mock_manager.current_url.return_value = "https://www.youtube.com"
    
    tool = BrowserTool(manager=mock_manager)
    res = tool.execute(action="open_youtube")
    
    assert res.success is True
    assert res.target == "youtube"
    
    ctx = get_conversation_context()
    assert ctx.last_browser_page == "https://www.youtube.com"


# 4. Close browser
def test_close_browser():
    mock_manager = MagicMock()
    mock_manager.close_browser.return_value = "Success: Closed Playwright browser."
    
    tool = BrowserTool(manager=mock_manager)
    with patch("psutil.process_iter", return_value=[]):
        res = tool.execute(action="close_browser")
        assert res.success is True
        assert res.target == "browser"


# 5. Create folder
def test_create_folder(tmp_path):
    tool = FileManagerTool()
    target_path = tmp_path / "NovaProject"
    
    res = tool.execute(action="create_folder", path=str(target_path))
    assert res.success is True
    assert target_path.is_dir()
    
    ctx = get_conversation_context()
    assert ctx.last_created_path == str(target_path)
    assert ctx.last_folder == "NovaProject"


# 6. Create file
def test_create_file(tmp_path):
    tool = FileManagerTool()
    target_path = tmp_path / "README.txt"
    
    res = tool.execute(action="create_file", path=str(target_path))
    assert res.success is True
    assert target_path.is_file()
    
    ctx = get_conversation_context()
    assert ctx.last_created_path == str(target_path)
    assert ctx.last_file == "README.txt"


# 7. Open folder
def test_open_folder(tmp_path):
    tool = FileManagerTool()
    target_path = tmp_path / "NovaProject"
    target_path.mkdir()
    
    with patch("os.startfile") as mock_startfile:
        res = tool.execute(action="open_folder", path=str(target_path))
        assert res.success is True
        mock_startfile.assert_called_once_with(target_path)
        
        ctx = get_conversation_context()
        assert ctx.last_opened_path == str(target_path)


# 8. Rename folder
def test_rename_folder(tmp_path):
    tool = FileManagerTool()
    src = tmp_path / "dir1"
    dest = tmp_path / "dir2"
    src.mkdir()
    
    res = tool.execute(action="rename", src=str(src), dest=str(dest))
    assert res.success is True
    assert not src.exists()
    assert dest.is_dir()
    
    ctx = get_conversation_context()
    assert ctx.last_created_path == str(dest)
    assert ctx.last_folder == "dir2"


# 9. Delete with permission gate
def test_delete_with_permission_gate(tmp_path):
    gate = PermissionGate()
    tool = FileManagerTool()
    
    # Delete is Medium Risk, which is approved automatically
    assert gate.check_permission(tool, {"action": "delete", "path": str(tmp_path / "some_file")}) is True


# 10. Multi-step folder + file
def test_multistep_folder_file(tmp_path):
    from agents.workspace_agent import WorkspaceAgent
    memory = ShortTermMemory()
    engine = NovaEngine(memory=memory)
    workspace = WorkspaceAgent(workspace_root=tmp_path)
    executive = ExecutiveAgent(engine=engine, workspace_agent=workspace)
    
    # Mock get_desktop_path to return our temp sandbox path so it works in test isolation
    with patch("tools.file_manager.get_desktop_path", return_value=tmp_path):
        res = executive.execute("Create NovaProject on my Desktop and create README.txt inside it.")
        
        assert res.status == ExecutionStatus.SUCCESS
        assert (tmp_path / "NovaProject").is_dir()
        assert (tmp_path / "NovaProject" / "README.txt").is_file()


# 11. Multi-step partial failure
def test_multistep_partial_failure(tmp_path):
    from agents.workspace_agent import WorkspaceAgent
    memory = ShortTermMemory()
    engine = NovaEngine(memory=memory)
    workspace = WorkspaceAgent(workspace_root=tmp_path)
    executive = ExecutiveAgent(engine=engine, workspace_agent=workspace)
    
    # Mock the execute to fail on the second step
    original_execute = executive.step_executor.execute
    
    def mock_step_execute(step, cancel_event=None):
        if "readme" in step.input_data.lower():
            step.status = ExecutionStatus.FAILED
            step.output_data = "Failed to create file"
            return "Failed to create file"
        return original_execute(step, cancel_event)
        
    with patch("tools.file_manager.get_desktop_path", return_value=tmp_path), \
         patch.object(executive.step_executor, "execute", side_effect=mock_step_execute):
        
        res = executive.execute("Create NovaProject on my Desktop and create README.txt inside it.")
        assert res.status == ExecutionStatus.FAILED
        assert (tmp_path / "NovaProject").is_dir()
        assert not (tmp_path / "NovaProject" / "README.txt").exists()
        assert "Step 2" in res.final_response
        assert "Failure:" in res.final_response


# 12. Context "open it"
def test_context_open_it(tmp_path):
    ctx = get_conversation_context()
    folder_path = tmp_path / "NovaProject"
    folder_path.mkdir()
    
    ctx.last_created_path = str(folder_path)
    
    resolved = ctx.resolve_follow_up("open it")
    assert resolved == f"open folder {folder_path}"


# 13. Context "create file there"
def test_context_create_file_there(tmp_path):
    ctx = get_conversation_context()
    folder_path = tmp_path / "NovaProject"
    folder_path.mkdir()
    
    ctx.last_opened_path = str(folder_path)
    
    resolved = ctx.resolve_follow_up("create README.txt there")
    assert resolved == f"create file {folder_path / 'README.txt'}"
    
    resolved_inside_it = ctx.resolve_follow_up("create README.txt inside it")
    assert resolved_inside_it == f"create file {folder_path / 'README.txt'}"


# 14. Duplicate prevention
def test_duplicate_prevention():
    mock_engine = MagicMock()
    executive = ExecutiveAgent(engine=mock_engine)
    
    # Mock the planning and step runner to check call count
    mock_res = ActionResult(success=True, action="custom_action", target="custom")
    with patch.object(executive.step_executor, "execute") as mock_exec:
        # Prevent the executor call from raising any errors
        def fake_exec(step, cancel_event=None):
            step.status = ExecutionStatus.SUCCESS
            step.output_data = "Success"
            return "Success"
        mock_exec.side_effect = fake_exec
        
        res1 = executive.execute("do some generic workspace action")
        res2 = executive.execute("do some generic workspace action")
        
        assert mock_exec.call_count == 1
        assert res1.status == res2.status


# 15. False-success prevention
def test_false_success_prevention():
    controller = ApplicationController()
    # Mock Popen to launch but immediately exit with error code 1 (failed verification)
    with patch("os.path.exists", return_value=True), \
         patch("subprocess.Popen") as mock_popen:
        
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 1
        mock_popen.return_value = mock_proc
        
        res = controller.launch("notepad")
        assert res.success is False


# 16. Natural-language aliases
def test_natural_language_aliases():
    controller = ApplicationController()
    assert controller.APP_ALIASES["google chrome"] == "chrome"
    assert controller.APP_ALIASES["vs code"] == "vscode"
    assert controller.APP_ALIASES["calc"] == "calculator"


# 17. Arbitrary shell rejection
def test_arbitrary_shell_rejection():
    gate = PermissionGate()
    tool = TerminalTool()
    
    # Safe whitelisted command
    assert gate.check_permission(tool, {"command": "git status"}) is True
    assert gate.check_permission(tool, {"command": "dir"}) is True
    
    # Arbitrary command should be rejected
    assert gate.check_permission(tool, {"command": "rm -rf /"}) is False
    assert gate.check_permission(tool, {"command": "echo 'hello'"}) is False
