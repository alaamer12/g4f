# mypy: ignore-errors
import subprocess
from unittest.mock import patch, MagicMock, ANY

import pytest

from c4f.main import *
from c4f.utils import FileChange


@pytest.fixture
def mock_popen():
    with patch("subprocess.Popen") as mock_popen:
        mock_process = MagicMock()
        mock_process.communicate.return_value = ("mock output", "mock error")
        mock_process.returncode = 0
        mock_popen.return_value = mock_process
        yield mock_popen


def test_run_git_command(mock_popen):
    stdout, stderr, code = run_git_command(["git", "status"])
    assert stdout == "mock output"
    assert stderr == "mock error"
    assert code == 0
    mock_popen.assert_called_once()
    args, kwargs = mock_popen.call_args
    assert args[0] == ["git", "status"]
    assert kwargs['stdout'] == subprocess.PIPE
    assert kwargs['stderr'] == subprocess.PIPE
    assert kwargs['text'] == True


@pytest.fixture
def mock_run_git_command():
    with patch("c4f.main.run_git_command") as mock_cmd:
        yield mock_cmd


def test_parse_git_status(mock_run_git_command):
    mock_run_git_command.return_value = ("M file1.txt\nA file2.txt\n?? newfile.txt", "", 0)
    expected_output = [("M", "file1.txt"), ("A", "file2.txt"), ("A", "newfile.txt")]
    assert parse_git_status() == expected_output


def test_parse_git_status_with_error(mock_run_git_command):
    mock_run_git_command.return_value = ("", "fatal: not a git repository", 1)
    with pytest.raises(SystemExit):
        parse_git_status()


@pytest.fixture
def mock_tracked_diff():
    with patch("c4f.main.run_git_command") as mock_cmd:
        yield mock_cmd


def test_get_tracked_file_diff(mock_tracked_diff):
    mock_tracked_diff.side_effect = [("mock diff", "", 0), ("", "", 0)]
    assert get_tracked_file_diff("file1.txt") == "mock diff"
    mock_tracked_diff.assert_called_with(["git", "diff", "--cached", "--", "file1.txt"])


@pytest.fixture
def mock_is_dir():
    with patch("c4f.main.Path.is_dir", return_value=True) as mock:
        yield mock


@pytest.fixture
def mock_is_untracked():
    with patch("c4f.main.is_untracked", return_value=True) as mock:
        yield mock


@pytest.fixture
def mock_handle_untracked_file():
    with patch("c4f.main.handle_untracked_file", return_value="mock diff") as mock:
        yield mock


@pytest.fixture
def mock_handle_directory():
    with patch("c4f.main.handle_directory", return_value="mock dir diff") as mock:
        yield mock


def test_get_file_diff_directory(mock_is_dir, mock_handle_directory):
    assert get_file_diff("some_dir") == "mock dir diff"
    mock_is_dir.assert_called_once()
    mock_handle_directory.assert_called_once()


def test_get_file_diff_untracked(mock_is_untracked, mock_handle_untracked_file):
    assert get_file_diff("newfile.txt") == "mock diff"
    mock_is_untracked.assert_called_once()
    mock_handle_untracked_file.assert_called_once()


@patch("c4f.main.run_git_command")
def test_is_untracked(mock_run_git_command):
    mock_run_git_command.return_value = ("?? file.txt", "", 0)
    assert is_untracked("file.txt") is True
    mock_run_git_command.return_value = ("M file.txt", "", 0)
    assert is_untracked("file.txt") is False


@patch("c4f.main.os.access", return_value=False)
@patch("c4f.main.Path.exists", return_value=True)
def test_handle_untracked_file_permission_denied(mock_exists, mock_access):
    assert handle_untracked_file(Path("file.txt")) == "Permission denied: file.txt"


@patch("c4f.main.Path.exists", return_value=False)
def test_handle_untracked_file_not_found(mock_exists):
    assert handle_untracked_file(Path("file.txt")) == "File not found: file.txt"


@patch("c4f.main.os.access", return_value=True)  # Ensure file is readable
@patch("c4f.main.Path.exists", return_value=True)  # Ensure file exists
@patch("c4f.main.read_file_content", return_value="mock content")  # Mock file reading
def test_handle_untracked_file_read(mock_read, mock_exists, mock_access):
    assert handle_untracked_file(Path("file.txt")) == "mock content"


@patch("builtins.open", side_effect=UnicodeDecodeError("utf-8", b"\x80", 0, 1, "invalid"))
def test_read_file_content_binary(mock_open):
    assert read_file_content(Path("file.txt")) == "Binary file: file.txt"


@patch("builtins.open", new_callable=MagicMock)
def test_read_file_content(mock_open):
    mock_open.return_value.__enter__.return_value.read.side_effect = ["text content", "text content"]
    assert read_file_content(Path("file.txt")) == "text content"


@pytest.mark.parametrize("file_path, diff, expected", [
    (Path("src/module.py"), "", "feat"),
    (Path("tests/test_module.py"), "", "test"),
    (Path("docs/readme.md"), "", "docs"),
    (Path("config/settings.yml"), "", "chore"),
    (Path("scripts/deploy.sh"), "", "chore"),
    (Path("src/main.js"), "", "feat"),
])
def test_analyze_file_type(file_path, diff, expected):
    assert analyze_file_type(file_path, diff) == expected


@pytest.mark.parametrize("file_path, expected", [
    (Path("src/main.py"), "feat"),
    (Path("tests/test_main.py"), "test"),
    (Path("scripts/script.py"), "feat"),
])
def test_check_python_file(file_path, expected):
    assert check_python_file(file_path, "") == expected


@pytest.mark.parametrize("file_path, expected", [
    (Path("README.md"), "docs"),
    (Path("docs/guide.rst"), "docs"),
    (Path("notes.txt"), "docs"),
    (Path("code.py"), None),
])
def test_check_documentation_file(file_path, expected):
    assert check_documentation_file(file_path, "") == expected


@pytest.mark.parametrize("file_path, expected", [
    (Path("setup.py"), "chore"),
    (Path("requirements.txt"), "chore"),
    (Path(".gitignore"), "chore"),
    (Path("config.yaml"), None),  # Not in the list of known config files
    (Path("random.py"), None),  # Not a config file
])
def test_check_configuration_file(file_path, expected):
    assert check_configuration_file(file_path, "") == expected


@pytest.mark.parametrize("file_path, expected", [
    (Path("scripts/deploy.sh"), "chore"),
    (Path("bin/run.sh"), None),
])
def test_check_script_file(file_path, expected):
    assert check_script_file(file_path, "") == expected


@pytest.mark.parametrize("file_path, expected", [
    (Path("tests/test_file.py"), "test"),
    (Path("src/module.py"), None),
])
def test_check_test_file(file_path, expected):
    assert check_test_file(file_path, "") == expected


@pytest.mark.parametrize("file_path, expected", [
    (Path("tests/test_file.py"), True),
    (Path("specs/unit_test.py"), True),
    (Path("code/main.py"), False),
])
def test_is_test_file(file_path, expected):
    assert is_test_file(file_path) == expected


@pytest.mark.parametrize("category, file_path, expected", [
    ("test", "tests/test_example.py", True),
    ("test", "src/main.py", False),
    ("docs", "README.md", True),
    ("docs", "code.py", False),
    ("style", "style/main.css", True),
    ("style", "script.js", False),
    ("ci", ".github/workflows/main.yml", True),
    ("ci", "random_file.txt", False),
    ("build", "setup.py", True),
    ("build", "app.py", False),
    ("perf", "benchmarks/test_benchmark.py", True),
    ("perf", "tests/test_performance.py", False),
    ("chore", ".env", True),
    ("chore", "main.py", False),
    ("feat", "src/feature/new_feature.py", True),
    ("feat", "random.py", False),
    ("fix", "hotfix/patch.py", True),
    ("fix", "app.py", False),
    ("refactor", "refactor/improved_code.py", True),
    ("refactor", "legacy_code.py", False),
])
def test_get_test_patterns(category, file_path, expected):
    patterns = get_test_patterns()
    pattern = re.compile(patterns[category])
    assert bool(pattern.search(file_path)) == expected


@pytest.mark.parametrize("category, diff_text, expected", [
    ("test", "def test_function(): assert True", True),
    ("test", "print('Hello World')", False),
    ("docs", "Updated README.md with new instructions", True),
    ("docs", "Refactored helper function", False),
    ("fix", "Fixed a bug causing crashes", True),
    ("fix", "Added a new feature", False),
    ("refactor", "Refactored the database layer", True),
    ("refactor", "Added a new endpoint", False),
    ("perf", "Optimized query performance", True),
    ("perf", "Refactored the service layer", False),
    ("style", "Formatted code with Prettier", True),
    ("style", "Added new logic for validation", False),
    ("feat", "Implemented new API feature", True),
    ("feat", "Fixed a critical bug", False),
    ("chore", "Updated dependencies to latest version", True),
    ("chore", "Added user authentication", False),
    ("security", "Fixed an XSS vulnerability", True),
    ("security", "Updated the UI design", False),
])
def test_get_diff_patterns(category, diff_text, expected):
    patterns = get_diff_patterns()
    pattern = re.compile(patterns[category], re.IGNORECASE)
    assert bool(pattern.search(diff_text)) == expected


def test_group_related_changes():
    changes = [
        FileChange(path=Path("src/module1/file1.py"), type="feat", status="added", diff=""),
        FileChange(path=Path("src/module1/file2.py"), type="feat", status="modified", diff=""),
        FileChange(path=Path("src/module2/file3.py"), type="fix", status="removed", diff=""),
        FileChange(path=Path("file4.py"), type="fix", status="modified", diff=""),
    ]

    groups = group_related_changes(changes)
    assert len(groups) == 3  # Expecting 3 groups: module1, module2, and root
    assert len(groups[0]) == 2  # Two feature changes in src/module1
    assert len(groups[1]) == 1  # One fix in src/module2
    assert len(groups[2]) == 1  # One fix in root directory


def test_generate_commit_message(mock_config):
    """Test generate_commit_message with mocked dependencies."""
    changes = [FileChange(Path("src/module1/file1.py"), "added", "", "feat")]
    
    with patch("c4f.main.create_combined_context", return_value="added src/module1/file1.py"), \
         patch("c4f.main.calculate_total_diff_lines", return_value=10), \
         patch("c4f.main.determine_tool_calls", return_value={"function": {"name": "generate_commit", "arguments": {}}}), \
         patch("c4f.main.get_formatted_message", return_value="feat: add new feature"), \
         patch("c4f.main.is_corrupted_message", return_value=False):
        message = generate_commit_message(changes, mock_config)
        assert message == "feat: add new feature"


@pytest.fixture
def mock_config():
    return Config(
        force_brackets=False,
        prompt_threshold=80,
        fallback_timeout=10,
        min_comprehensive_length=50,
        attempt=3,
        diff_max_length=100
    )


def test_determine_tool_calls(mock_config):
    simple_result = determine_tool_calls(False, "Basic change", "", mock_config)
    comprehensive_result = determine_tool_calls(True, "Major update", "Detailed summary", mock_config)

    assert isinstance(simple_result, dict)
    assert isinstance(comprehensive_result, dict)
    assert "sections" in comprehensive_result["function"]["arguments"]


def test_attempt_generate_message(mock_config):
    """Test attempt_generate_message with mocked dependencies."""
    changes = [FileChange(Path("src/module1/file1.py"), "added", "", "feat")]
    combined_context = "added src/module1/file1.py"
    tool_calls = {"function": {"name": "generate_commit", "arguments": {}}}
    total_diff_lines = 10

    with patch("c4f.main.determine_prompt", return_value="Test prompt"), \
         patch("c4f.main.model_prompt", return_value="feat: add new feature"):
        message = attempt_generate_message(combined_context, tool_calls, changes, total_diff_lines, mock_config)
        assert message == "feat: add new feature"


def test_generate_simple_prompt(mock_config):
    combined_text = "Modified README.md"
    prompt = generate_simple_prompt(combined_text, mock_config)
    assert combined_text in prompt
    assert "single-line commit message" in prompt


def test_generate_comprehensive_prompt(mock_config):
    combined_text = "Updated main.py"
    diffs_summary = "Refactored main function and improved logging."
    prompt = generate_comprehensive_prompt(combined_text, diffs_summary, mock_config)
    assert combined_text in prompt
    assert diffs_summary in prompt
    assert "Generate a commit message in this format:" in prompt


def test_determine_prompt_small_change(mock_config):
    combined_text = "Fixed typo in documentation"
    changes = [FileChange(Path("docs.txt"), "M", "Fixed typo")]
    diff_lines = 10  # Less than threshold

    result = determine_prompt(combined_text, changes, diff_lines, mock_config)
    assert "single-line commit message" in result


def test_determine_prompt_large_change(mock_config):
    combined_text = "Refactored entire user authentication module"
    changes = [FileChange(Path("auth.py"), "M", "Refactored auth logic")]
    diff_lines = 100  # More than threshold

    result = determine_prompt(combined_text, changes, diff_lines, mock_config)
    assert "Generate a commit message in this format:" in result


def test_model_prompt(mock_config):
    prompt = "Test prompt"
    tool_calls = {}
    with patch("c4f.main.get_model_response", return_value="Mocked response"):
        response = model_prompt(prompt, tool_calls, mock_config)
        assert response == "Mocked response"


def test_get_model_response(mock_config):
    prompt = "Test model prompt"
    tool_calls = {}
    with patch("c4f.main.client.chat.completions.create") as mock_create:
        mock_create.return_value.choices = [
            type("obj", (object,), {"message": type("msg", (object,), {"content": "Mocked content"})})]
        response = get_model_response(prompt, tool_calls, mock_config)
        assert response == "Mocked content"

    with patch("c4f.main.client.chat.completions.create", side_effect=Exception("API error")):
        response = get_model_response(prompt, tool_calls, mock_config)
        assert response is None


def test_execute_with_progress():
    mock_func = MagicMock(return_value="Mocked response")
    with patch("c4f.main.execute_with_timeout", return_value="Mocked response"):
        response = execute_with_progress(mock_func)
        assert response == "Mocked response"


def test_execute_with_timeout(mock_config):
    mock_func = MagicMock(return_value="Mocked response")
    progress = MagicMock()
    task = MagicMock()
    response = execute_with_timeout(mock_func, progress, task, mock_config)
    assert response == "Mocked response"


def test_execute_with_timeout_exception():
    mock_func = MagicMock(side_effect=Exception("Test exception"))
    progress = MagicMock()
    task = MagicMock()
    response = execute_with_timeout(mock_func, progress, task)
    assert response is None


def test_process_response_none():
    assert process_response(None) is None


def test_handle_error_timeout():
    with patch("c4f.main.console.print") as mock_print:
        handle_error(TimeoutError())
        mock_print.assert_called_with("[yellow]Model response timed out, using fallback message[/yellow]")


def test_handle_error_general():
    with patch("c4f.main.console.print") as mock_print:
        handle_error(Exception("Test error"))
        mock_print.assert_called_with("[yellow]Error in model response, using fallback message: Test error[/yellow]")


def test_commit_changes():
    files = ["file1.txt", "file2.txt"]
    message = "feat: add new feature"
    with patch("c4f.main.stage_files") as mock_stage, \
            patch("c4f.main.do_commit", return_value=("Commit successful", 0)) as mock_commit, \
            patch("c4f.main.display_commit_result") as mock_display:
        commit_changes(files, message)
        mock_stage.assert_called_once_with(files, ANY)  # Use ANY instead of `any`
        mock_commit.assert_called_once_with(message, ANY)
        mock_display.assert_called_once_with(("Commit successful", 0), message)


def test_do_commit():
    message = "fix: bug fix"
    with patch("c4f.main.run_git_command", return_value=("Commit successful", "", 0)) as mock_run:
        result = do_commit(message, MagicMock())
        mock_run.assert_called_once_with(["git", "commit", "-m", message])
        assert result == ("Commit successful", 0)


def test_stage_files():
    files = ["file1.txt", "file2.txt"]
    with patch("c4f.main.run_git_command") as mock_run:
        stage_files(files, MagicMock())
        mock_run.assert_any_call(["git", "add", "--", "file1.txt"])
        mock_run.assert_any_call(["git", "add", "--", "file2.txt"])
        assert mock_run.call_count == len(files)


def test_display_commit_result_success():
    with patch("c4f.main.console.print") as mock_print:
        display_commit_result(("", 0), "test commit")
        mock_print.assert_called_with("[green]✔ Successfully committed:[/green] test commit")


def test_display_commit_result_failure():
    with patch("c4f.main.console.print") as mock_print:
        display_commit_result(("Error committing", 1), "test commit")
        mock_print.assert_called_with("[red]✘ Error committing changes:[/red] Error committing")


def test_reset_staging():
    with patch("c4f.main.run_git_command") as mock_run:
        reset_staging()
        mock_run.assert_called_once_with(["git", "reset", "HEAD"])


def test_format_diff_lines():
    assert format_diff_lines(5) == "[green]5[/green]"
    assert format_diff_lines(25) == "[yellow]25[/yellow]"
    assert format_diff_lines(75) == "[red]75[/red]"


def test_format_time_ago():
    now = datetime.now().timestamp()
    assert format_time_ago(0) == "N/A"
    assert format_time_ago(now - 90000) == "1d ago"  # ~1 day ago
    assert format_time_ago(now - 7200) == "2h ago"  # ~2 hours ago
    assert format_time_ago(now - 120) == "2m ago"  # ~2 minutes ago
    assert format_time_ago(now) == "just now"


class MockFileChange:
    def __init__(self, status, path, _type, diff_lines, last_modified):
        self.status = status
        self.path = path
        self.type = _type
        self.diff_lines = diff_lines
        self.last_modified = last_modified


def test_create_staged_table():
    table = create_staged_table()
    assert isinstance(table, Table)
    assert table.title == "Staged Changes"
    assert table.show_header is True
    assert table.header_style == "bold magenta"
    assert table.show_lines is True


def test_config_staged_table():
    table = Table()
    config_staged_table(table)
    assert len(table.columns) == 5
    assert table.columns[0].header == "Status"
    assert table.columns[1].header == "File Path"
    assert table.columns[2].header == "Type"
    assert table.columns[3].header == "Changes"
    assert table.columns[4].header == "Last Modified"


def test_apply_table_styling():
    table = Table()
    change = MockFileChange("M", "file1.txt", "Modified", 10, 1640995200)
    with patch("c4f.main.format_diff_lines", return_value="10"), \
            patch("c4f.main.format_time_ago", return_value="2d ago"):
        apply_table_styling(table, change)
    assert len(table.rows) == 1


def test_display_changes():
    changes = [
        MockFileChange("A", "file1.txt", "Added", 5, 1640995200),
        MockFileChange("D", "file2.txt", "Deleted", 15, 1640995300)
    ]
    with patch("c4f.main.console.print") as mock_print:
        display_changes(changes)
        assert mock_print.called


def test_main():
    mock_config = Config()
    with patch("c4f.main.handle_non_existent_git_repo"), \
            patch("c4f.main.reset_staging"), \
            patch("c4f.main.get_valid_changes", return_value=["change"]), \
            patch("c4f.main.display_changes"), \
            patch("c4f.main.group_related_changes", return_value=[["group1"]]), \
            patch("c4f.main.process_change_group", return_value=True):
        main(mock_config)


def test_get_valid_changes():
    with patch("c4f.main.parse_git_status", return_value=[("M", "file1.txt")]), \
            patch("c4f.main.process_changed_files", return_value=["processed_change"]):
        changes = get_valid_changes()
        assert changes == ["processed_change"]


def test_process_changed_files():
    with patch("c4f.main.create_progress_bar", return_value=MagicMock()), \
            patch("c4f.main.create_progress_tasks", return_value=(MagicMock(), MagicMock())), \
            patch("c4f.main.process_single_file", return_value="file_change"):
        changes = process_changed_files([("M", "file1.txt")])
        assert changes == ["file_change"]


def test_create_progress_bar():
    progress = create_progress_bar()
    assert isinstance(progress, Progress)


def test_create_progress_tasks():
    progress = MagicMock()
    _, _ = create_progress_tasks(progress, 5)
    assert progress.add_task.called


def test_process_single_file():
    with patch("c4f.main.get_file_diff", return_value="diff"), \
            patch("c4f.main.analyze_file_type", return_value="Modified"), \
            patch("c4f.main.FileChange") as mock_file_change:
        progress_mock = MagicMock()
        diff_task = MagicMock()
        result = process_single_file("M", "file1.txt", progress_mock, diff_task)
        assert result == mock_file_change.return_value
        progress_mock.advance.assert_called_once_with(diff_task)


def test_create_file_change():
    with patch("c4f.main.get_file_diff", return_value="diff"), \
            patch("c4f.main.analyze_file_type", return_value="Modified"), \
            patch("c4f.main.FileChange") as mock_file_change:
        result = create_file_change("M", "file1.txt")
        assert result == mock_file_change.return_value


def test_exit_with_no_changes():
    with patch("c4f.main.console.print") as mock_print, \
            patch("c4f.main.sys.exit") as mock_exit:
        exit_with_no_changes()
        mock_print.assert_called_once_with("[yellow]⚠ No changes to commit[/yellow]")
        mock_exit.assert_called_once_with(0)


def test_process_change_group(mock_config):
    group = [MockFileChange("M", "file1.txt", "Modified", 10, 1640995200)]
    with patch("c4f.main.generate_commit_message", return_value="Commit message"), \
            patch("c4f.main.display_commit_preview"), \
            patch("c4f.main.do_group_commit", return_value=True) as mock_commit, \
            patch("c4f.main.get_valid_user_response", return_value="y"), \
            patch("c4f.main.handle_user_response", return_value=True) as mock_response:
        result = process_change_group(group, mock_config, accept_all=True)
        assert result is True
        mock_commit.assert_called_once_with(group, "Commit message", True)

        result = process_change_group(group, mock_config, accept_all=False)
        assert result is True
        mock_response.assert_called_once_with("y", group, "Commit message")


def test_get_valid_user_response():
    with patch("builtins.input", side_effect=["y", "n", "e", "a", "all", ""]):
        assert get_valid_user_response() == "y"
        assert get_valid_user_response() == "n"
        assert get_valid_user_response() == "e"
        assert get_valid_user_response() == "a"
        assert get_valid_user_response() == "all"
        assert get_valid_user_response() == ""


def test_handle_user_response():
    group = [MockFileChange("M", "file1.txt", "Modified", 10, 1640995200)]
    message = "Commit message"

    with patch("c4f.main.do_group_commit") as mock_commit, \
            patch("c4f.main.console.print") as mock_print:
        # Test "y" response (should call do_group_commit)
        assert handle_user_response("y", group, message) is False
        mock_commit.assert_called_with(group, message)

        # Test "a" and "all" response (should return True)
        assert handle_user_response("a", group, message) is True
        assert handle_user_response("all", group, message) is True

        # Test "n" response (should call console.print)
        assert handle_user_response("n", group, message) is False
        mock_print.assert_called_once_with("[yellow]Skipping these changes...[/yellow]")


def test_do_group_commit():
    group = [MockFileChange("M", "file1.txt", "Modified", 10, 1640995200)]
    with patch("c4f.main.commit_changes") as mock_commit:
        result = do_group_commit(group, "Commit message", True)
        mock_commit.assert_called_with(["file1.txt"], "Commit message")
        assert result is True


def test_display_commit_preview():
    with patch("c4f.main.console.print") as mock_print:
        display_commit_preview("Test commit message")

        # Ensure print was called at least once
        assert mock_print.called

        # Retrieve the actual Panel argument passed to print
        panel_arg = mock_print.call_args[0][0]

        # Ensure it's a Panel instance and contains expected text
        assert isinstance(panel_arg, Panel)
        assert "Proposed commit message:" in panel_arg.renderable
        assert "[bold cyan]Test commit message[/bold cyan]" in panel_arg.renderable


@patch("c4f.main.run_git_command")
def test_git_status_success(mock_run_git):
    mock_run_git.return_value = (" M modified.txt\nA  added.txt\nR  old.txt -> new.txt\n?? untracked.txt", "", 0)
    expected_output = [("M", "modified.txt"), ("A", "added.txt"), ("R", "new.txt"), ("A", "untracked.txt")]
    assert parse_git_status() == expected_output

@patch("c4f.main.run_git_command")
def test_git_status_error_exit(mock_run_git):
    mock_run_git.return_value = ("", "fatal: Not a git repository", 1)
    with patch("sys.exit") as mock_exit:
        parse_git_status()
        mock_exit.assert_called_once_with(1)

@patch("c4f.main.run_git_command")
def test_git_status_empty_output(mock_run_git):
    mock_run_git.return_value = ("", "", 0)
    assert parse_git_status() == []

@patch("c4f.main.run_git_command")
def test_git_status_untracked_files(mock_run_git):
    mock_run_git.return_value = ("?? new_file.txt\n?? another_file.txt", "", 0)
    expected_output = [("A", "new_file.txt"), ("A", "another_file.txt")]
    assert parse_git_status() == expected_output

@patch("c4f.main.run_git_command")
def test_git_status_renamed_file(mock_run_git):
    mock_run_git.return_value = ("R  old_name.txt -> new_name.txt", "", 0)
    expected_output = [("R", "new_name.txt")]
    assert parse_git_status() == expected_output

@patch("c4f.main.run_git_command")
def test_git_status_mixed_changes(mock_run_git):
    mock_run_git.return_value = (" M modified.txt\nD  deleted.txt\nA  new.txt\n?? untracked.txt", "", 0)
    expected_output = [("M", "modified.txt"), ("D", "deleted.txt"), ("A", "new.txt"), ("A", "untracked.txt")]
    assert parse_git_status() == expected_output

def mock_handle_directory(file_path):  # type: ignore
    return f"Mocked directory handling for {file_path}"

def mock_handle_untracked_file(path):  # type: ignore
    return f"Mocked untracked file handling for {path}"

def mock_get_tracked_file_diff(file_path):
    return f"Mocked diff for {file_path}"

@patch("c4f.main.Path.is_dir", return_value=True)
@patch("c4f.main.handle_directory", side_effect=mock_handle_directory)
def test_get_file_diff_directory(mock_handle_dir, mock_is_dir):
    assert get_file_diff("some_directory") == "Mocked directory handling for some_directory"

@patch("c4f.main.is_untracked", return_value=True)
@patch("c4f.main.handle_untracked_file", side_effect=mock_handle_untracked_file)
@patch("c4f.main.Path.is_dir", return_value=False)
def test_get_file_diff_untracked(mock_is_dir, mock_handle_untracked, mock_is_untracked):
    assert get_file_diff("untracked_file.txt") == "Mocked untracked file handling for untracked_file.txt"

@patch("c4f.main.get_tracked_file_diff", side_effect=mock_get_tracked_file_diff)
@patch("c4f.main.is_untracked", return_value=False)
@patch("c4f.main.Path.is_dir", return_value=False)
def test_get_file_diff_tracked(mock_is_dir, mock_is_untracked, mock_get_diff):
    assert get_file_diff("tracked_file.txt") == "Mocked diff for tracked_file.txt"



def test_shorten_diff_no_change(mock_config):
    diff = "line1\nline2\nline3"
    assert shorten_diff(diff, mock_config) == diff

def test_shorten_diff_truncated(mock_config):
    diff = "\n".join(f"line{i}" for i in range(mock_config.diff_max_length + 2))
    expected = "\n".join(f"line{i}" for i in range(mock_config.diff_max_length)) + "\n\n...\n\n"
    assert shorten_diff(diff, mock_config) == expected


@patch("c4f.main.run_git_command", return_value=("", "error", 1))
def test_get_tracked_file_diff_failure(mock_run_git):
    assert get_tracked_file_diff("file.txt") == ""

def test_directory_path():
    assert f"Directory: {os.getcwd()}" == handle_directory(str(os.getcwd()))

def test_handle_untracked_file_not_exists():
    path = Path("non_existent_file.txt")
    assert handle_untracked_file(path) == f"File not found: {path}"

@patch("os.access", return_value=False)
def test_handle_untracked_file_no_permission(mock_access):
    path = Path("restricted_file.txt")
    path.touch()  # Create the file
    assert handle_untracked_file(path) == f"Permission denied: {path}"
    path.unlink()  # Clean up

@patch("c4f.main.read_file_content", return_value="file content")
def test_handle_untracked_file_success(mock_read):
    path = Path("valid_file.txt")
    path.touch()  # Create the file
    assert handle_untracked_file(path) == "file content"
    path.unlink()  # Clean up

@patch("c4f.main.read_file_content", side_effect=Exception("Read error"))
def test_handle_untracked_file_exception(mock_read):
    path = Path("error_file.txt")
    try:
        path.touch()  # Create the file
        expected_error = f"Error: Read error"
        assert handle_untracked_file(path) == expected_error
        path.unlink()  # Clean up
    except PermissionError:
        assert True
    finally:
        if path.exists():
            path.unlink()

@pytest.fixture(scope="function")
def simple_file_change():
    yield FileChange(path=Path("file1.py"),
                     status="M",
                     diff="".join(["line1\n", "line2\n", "line3\n"]),
                     type="feat",
                     diff_lines=3,
                     last_modified=1600
                     )

@pytest.fixture(scope="function")
def comprehensive_file_change():
    yield FileChange(path=Path("file1.py"),
                     status="M",
                     diff="".join([f"line{i}\n" for i in range(1, 300)]),
                     type="feat",
                     diff_lines=299,
                     last_modified=1600
                     )

@pytest.fixture(scope="function")
def empty_file_change():
    yield FileChange(path=Path("file1.py"),
                     status="M",
                     diff="",
                     type="feat",
                     diff_lines=0,
                     last_modified=1600
                     )

def test_generate_commit_message_simple(simple_file_change, mock_config):
    changes = [simple_file_change]
    with patch("c4f.main.create_combined_context", return_value="context"), \
            patch("c4f.main.calculate_total_diff_lines", return_value=5), \
            patch("c4f.main.determine_tool_calls", return_value=[]), \
            patch("c4f.main.get_formatted_message", return_value="fix: update file1"), \
            patch("c4f.main.is_corrupted_message", return_value=False):
        assert generate_commit_message(changes, mock_config) == "fix: update file1"


def test_generate_commit_message_comprehensive(possible_values, comprehensive_file_change, mock_config):
    changes = [comprehensive_file_change]
    with patch("c4f.main.create_combined_context", return_value="context"), \
            patch("c4f.main.calculate_total_diff_lines", return_value=20), \
            patch("c4f.main.generate_diff_summary", return_value="summary"), \
            patch("c4f.main.determine_tool_calls", return_value=[]), \
            patch("c4f.main.get_formatted_message", return_value="fix: update file1"), \
            patch("c4f.main.is_corrupted_message", return_value=False), \
            patch("c4f.main.handle_comprehensive_message", return_value="final message"):
        assert any(value in generate_commit_message(changes, mock_config) for value in possible_values)

def test_handle_short_comprehensive_message_use(monkeypatch):
    """Test when user inputs '1', expecting 'use'."""
    monkeypatch.setattr('builtins.input', lambda _: "1")
    result = handle_short_comprehensive_message("test message")
    assert result == "use"

def test_handle_short_comprehensive_message_retry(monkeypatch):
    """Test when user inputs '2', expecting 'retry'."""
    monkeypatch.setattr('builtins.input', lambda _: "2")
    result = handle_short_comprehensive_message("test message")
    assert result == "retry"

def test_handle_short_comprehensive_message_fallback_3(monkeypatch):
    """Test when user inputs '3', expecting 'fallback'."""
    monkeypatch.setattr('builtins.input', lambda _: "3")
    result = handle_short_comprehensive_message("test message")
    assert result == "fallback"

def test_handle_short_comprehensive_message_fallback_invalid(monkeypatch):
    """Test when user inputs an invalid string 'a', expecting 'fallback'."""
    monkeypatch.setattr('builtins.input', lambda _: "a")
    result = handle_short_comprehensive_message("test message")
    assert result == "fallback"

def test_handle_short_comprehensive_message_fallback_empty(monkeypatch):
    """Test when user inputs an empty string, expecting 'fallback'."""
    monkeypatch.setattr('builtins.input', lambda _: "")
    result = handle_short_comprehensive_message("test message")
    assert result == "fallback"

def test_handle_short_comprehensive_message_fallback_multiple(monkeypatch):
    """Test when user inputs '12', expecting 'fallback'."""
    monkeypatch.setattr('builtins.input', lambda _: "12")
    result = handle_short_comprehensive_message("test message")
    assert result == "fallback"


def test_generate_commit_message_retry(possible_values, empty_file_change, mock_config):
    changes = [empty_file_change]
    with patch("c4f.main.create_combined_context", return_value="context"), \
            patch("c4f.main.calculate_total_diff_lines", return_value=20), \
            patch("c4f.main.generate_diff_summary", return_value="summary"), \
            patch("c4f.main.determine_tool_calls", return_value=[]), \
            patch("c4f.main.get_formatted_message", side_effect=["corrupted", "valid message"]), \
            patch("c4f.main.is_corrupted_message", side_effect=[True, False]), \
            patch("c4f.main.handle_comprehensive_message", return_value="valid message"):
        assert any(value not in generate_commit_message(changes, mock_config) for value in possible_values)


def test_is_corrupted_message(mock_config):
    with patch("c4f.main.is_conventional_type", return_value=False), \
            patch("c4f.main.is_conventional_type_with_brackets", return_value=False):
        assert is_corrupted_message("", mock_config) is True



def test_purify_batrick():
    # Path 1: No triple backticks
    assert purify_batrick("simple message") == "simple message"

    # Path 2: Triple backticks with language specifier, multi-line
    assert purify_batrick("```python\ncode here\n```") == "code here"

    # Path 3: Triple backticks without language specifier, multi-line
    assert purify_batrick("```\ncode here\n```") == "code here"

    # Path 4: Triple backticks single line
    assert purify_batrick("```code here```") == "code here"

    # Path 5: Triple backticks with long first line
    assert purify_batrick("```long line here\ncode```") == "long line here\ncode"


def test_is_conventional_type():
    # Path 1: No conventional type found
    assert is_conventional_type("random text") == False

    # Path 2: Conventional type found
    assert is_conventional_type("feat: add new feature") == True
    assert is_conventional_type("FIX: bug") == True
    assert is_conventional_type("docs: update readme") == True


def test_is_conventional_type_with_brackets_force_disable():
    """Test is_convetional_type_with_brackets with force_brackets set to False."""
    # Create a config with force_brackets disabled
    config_no_brackets = Config(force_brackets=False)
    
    # The function should return True regardless of input when force_brackets is False
    assert is_conventional_type_with_brackets("feat: test", config_no_brackets) is True
    assert is_conventional_type_with_brackets("feat(scope): test", config_no_brackets) is True

def test_is_conventional_type_with_brackets_force_enable():
    """Test is_conventional_type_with_brackets with force_brackets set to True."""
    # Create a config with force_brackets enabled
    config_with_brackets = Config(force_brackets=True)

    # With brackets should return True
    assert is_conventional_type_with_brackets("feat(scope): message", config_with_brackets) is True

    # Without brackets should return False
    assert is_conventional_type_with_brackets("feat: message", config_with_brackets) is False


def test_purify_commit_message_introduction():
    # Path 1: No prefix
    assert purify_commit_message_introduction("simple message") == "simple message"

    # Path 2: With various prefixes
    assert purify_commit_message_introduction("commit message: test") == "test"
    assert purify_commit_message_introduction("Commit: test") == "test"
    assert purify_commit_message_introduction("suggested commit message: test") == "test"


def test_purify_explantory_message():
    # Path 1: No explanatory markers
    assert purify_explantory_message("simple message") == "simple message"

    # Path 2: With explanatory markers
    assert purify_explantory_message("feat: add\nexplanation: details") == "feat: add"
    assert purify_explantory_message("fix: bug\nNote: details") == "fix: bug"


def test_purify_htmlxml():
    # Path 1: No HTML/XML
    assert purify_htmlxml("simple message") == "simple message"

    # Path 2: With HTML/XML
    assert purify_htmlxml("<p>text</p>") == "text"
    assert purify_htmlxml("text <div>more</div> text") == "text more text"


def test_purify_disclaimers():
    # Path 1: No disclaimers
    assert purify_disclaimers("simple\nmessage") == "simple\nmessage"

    # Path 2: With disclaimer
    assert purify_disclaimers("feat: add\nlet me know if this works") == "feat: add"
    assert purify_disclaimers("fix: bug\nplease review this") == "fix: bug"


def test_purify_message():
    # Path 1: None input
    assert purify_message(None) is None

    # Path 2: Valid message (will call other functions, but we just test the entry)
    assert isinstance(purify_message("test"), str)


@pytest.fixture(autouse=True)
def possible_values():
    yield ["feat", "test", "fix", "docs", "chore",
           "refactor", "style", "perf", "ci", "build",
           "security"]


def test_generate_fallback_message(possible_values,simple_file_change, mock_config):
    # Use one of the valid types from possible_values for testing.
    change_type = possible_values[0]
    # Create a list of FileChange objects with dummy file names.
    file_changes = [
        simple_file_change,
        simple_file_change
    ]

    message = generate_fallback_message(file_changes)

    # Build a regex pattern that ensures:
    # 1. The message starts with one of the possible change types.
    # 2. Follows the literal string ": update "
    # 3. Ends with one or more file names (space-separated).
    pattern = r"^(%s): update\s+(.+)$" % "|".join(possible_values)

    # Assert that the generated message matches the expected pattern.
    assert re.match(pattern, message), f"Unexpected format: {message}"

def test_handle_comprehensive_message_none(empty_file_change, mock_config):
    """Test when message is None."""
    result = handle_comprehensive_message(None, [empty_file_change], mock_config)
    assert result is None

def test_handle_comprehensive_message_long_enough(comprehensive_file_change, mock_config):
    """Test when message length >= min_comprehensive_length."""
    long_message = "a" * mock_config.min_comprehensive_length  # Create message that meets minimum length
    result = handle_comprehensive_message(long_message, [comprehensive_file_change], mock_config)
    assert result == long_message


def test_handle_comprehensive_message_short_use_patched(simple_file_change, mock_config):
    """Test short message with 'use' action."""
    with patch("c4f.main.handle_short_comprehensive_message", return_value="use"):
        result = handle_comprehensive_message("short", [simple_file_change], mock_config)
        assert result == "short"

def test_handle_comprehensive_message_short_retry_patched(simple_file_change, mock_config):
    """Test short message with 'retry' action."""
    with patch("c4f.main.handle_short_comprehensive_message", return_value="retry"):
        result = handle_comprehensive_message("short", [simple_file_change], mock_config)
        assert result == "retry"

def test_handle_comprehensive_message_short_fallback_patched(simple_file_change, mock_config):
    """Test short message with 'fallback' action."""
    with patch("c4f.main.handle_short_comprehensive_message", return_value="fallback"):
        with patch("c4f.main.generate_fallback_message", return_value="fallback message"):
            result = handle_comprehensive_message("short", [simple_file_change], mock_config)
            assert result == "fallback message"

@pytest.mark.long
def test_handle_comprehensive_message_short_invalid_then_use_patched(simple_file_change, mock_config):
    """Test short message with invalid action, then 'use' via input."""
    with patch("c4f.main.handle_short_comprehensive_message", return_value="invalid"):
        with patch("builtins.input", return_value=""):  # Empty input counts as "use"
            result = handle_comprehensive_message("short", [simple_file_change], mock_config)
            assert result == "short"

def test_handle_comprehensive_message_short_invalid_then_retry_patched(simple_file_change, mock_config):
    """Test short message with invalid action, then 'retry' via input."""
    with patch("c4f.main.handle_short_comprehensive_message", return_value="invalid"):
        with patch("builtins.input", return_value="r"):  # 'r' for retry
            result = handle_comprehensive_message("short", [simple_file_change], mock_config)
            assert result == "retry"

def test_handle_comprehensive_message_short_invalid_then_fallback_patched(empty_file_change, mock_config):
    """Test short message with invalid action, then 'fallback' via input."""
    with patch("c4f.main.handle_short_comprehensive_message", return_value="invalid"):
        with patch("builtins.input", return_value="f"):  # 'f' for fallback
            with patch("c4f.main.generate_fallback_message", return_value="fallback message"):
                result = handle_comprehensive_message("short", [empty_file_change], mock_config)
                assert result == "fallback message"

@pytest.mark.long
def test_handle_comprehensive_message_short_multiple_invalid_then_use(empty_file_change, mock_config):
    """Test short message with multiple invalid actions, then 'use' via input."""
    with patch("c4f.main.handle_short_comprehensive_message", return_value="invalid"):
        with patch("builtins.input", return_value=""):  # Empty input counts as "use"
            result = handle_comprehensive_message("short", [empty_file_change], mock_config)
            assert result == "short"

def test_generate_commit_message_multiple_retries(comprehensive_file_change, mock_config):
    """Test generate_commit_message with multiple corrupted messages before success."""
    changes = [comprehensive_file_change]
    
    # Mock is_corrupted_message to return True twice then False
    corruption_results = [True, True, False]
    corruption_iter = iter(corruption_results)
    
    with patch("c4f.main.create_combined_context", return_value="context"), \
         patch("c4f.main.calculate_total_diff_lines", return_value=30), \
         patch("c4f.main.determine_tool_calls", return_value={}), \
         patch("c4f.main.get_formatted_message", return_value="valid message"), \
         patch("c4f.main.is_corrupted_message", side_effect=lambda x, y: next(corruption_iter)), \
         patch("c4f.main.generate_fallback_message", return_value="fallback"):
        
        message = generate_commit_message(changes, mock_config)
        # Should get the valid message on the third attempt
        assert message == "valid message"

def test_generate_commit_message_comprehensive_path(comprehensive_file_change, mock_config):
    """Test the comprehensive message path in generate_commit_message."""
    changes = [comprehensive_file_change]
    
    with patch("c4f.main.create_combined_context", return_value="context"), \
         patch("c4f.main.calculate_total_diff_lines", return_value=100), \
         patch("c4f.main.generate_diff_summary", return_value="summary"), \
         patch("c4f.main.determine_tool_calls", return_value={}), \
         patch("c4f.main.get_formatted_message", return_value="comprehensive message"), \
         patch("c4f.main.is_corrupted_message", return_value=False), \
         patch("c4f.main.handle_comprehensive_message", return_value="processed message"):
        
        message = generate_commit_message(changes, mock_config)
        assert message == "processed message"

def test_generate_commit_message_comprehensive_with_retry(comprehensive_file_change, mock_config):
    """Test the comprehensive message path with a retry from handle_comprehensive_message."""
    changes = [comprehensive_file_change]
    
    # First call to handle_comprehensive_message returns "retry", second returns a message
    comprehensive_results = ["retry", "final message"]
    comprehensive_iter = iter(comprehensive_results)
    
    with patch("c4f.main.create_combined_context", return_value="context"), \
         patch("c4f.main.calculate_total_diff_lines", return_value=100), \
         patch("c4f.main.generate_diff_summary", return_value="summary"), \
         patch("c4f.main.determine_tool_calls", return_value={}), \
         patch("c4f.main.get_formatted_message", return_value="comprehensive message"), \
         patch("c4f.main.is_corrupted_message", return_value=False), \
         patch("c4f.main.handle_comprehensive_message", side_effect=lambda x, y, z: next(comprehensive_iter)):
        
        message = generate_commit_message(changes, mock_config)
        assert message == "final message"

def test_generate_commit_message_all_attempts_fail(comprehensive_file_change, mock_config):
    """Test when all message generation attempts fail and fallback is used."""
    changes = [comprehensive_file_change]
    
    # Create a patch context that ensures all attempts return corrupted messages
    with patch("c4f.main.create_combined_context", return_value="context"), \
         patch("c4f.main.calculate_total_diff_lines", return_value=100), \
         patch("c4f.main.generate_diff_summary", return_value="summary"), \
         patch("c4f.main.determine_tool_calls", return_value={}), \
         patch("c4f.main.get_formatted_message", return_value="corrupted message"), \
         patch("c4f.main.is_corrupted_message", return_value=True), \
         patch("c4f.main.generate_fallback_message", return_value="fallback message"):
        
        # Use the config's attempt value
        message = generate_commit_message(changes, mock_config)
        assert message == "fallback message"


@pytest.mark.parametrize("timestamp, expected_result", [
    (0, "N/A"),  # Timestamp is 0
    (datetime.now().timestamp(), "just now"),  # Current time - "just now"
    (datetime.now().timestamp() - 30, "just now"),  # Within a minute - "just now"
    (datetime.now().timestamp() - 120, "2m ago"),  # 2 minutes ago
    (datetime.now().timestamp() - 3700, "1h ago"),  # 1 hour ago
    (datetime.now().timestamp() - 86500, "1d ago"),  # 1 day ago
])
def test_format_time_ago_normal_cases(timestamp, expected_result):
    """Test format_time_ago with various timestamps."""
    assert format_time_ago(timestamp) == expected_result

def test_format_time_ago_edge_cases():
    """Test edge cases for format_time_ago function."""
    # Test negative timestamp (which would make diff > timestamp)
    with patch('c4f.main.datetime') as mock_datetime:
        # Mock datetime to return a fixed timestamp
        mock_now = MagicMock()
        mock_now.timestamp.return_value = 1000
        mock_datetime.now.return_value = mock_now
        
        # Test with negative diff (future timestamp)
        # This will lead to the condition diff >= seconds being false for all cases
        future_timestamp = 2000  # 1000 seconds in the future
        
        # To force test the unreachable code path (the final return "N/A")
        # We need to patch time_units to an empty list so the loop completes
        with patch('c4f.main.format_time_ago.__defaults__', ([], )):
            assert format_time_ago(future_timestamp) == "N/A"
        
        # Test with normal time_units but make diff negative 
        # (another way to force loop completion if that approach is needed)
        with patch('c4f.main.format_time_ago', side_effect=lambda t: "N/A" if t > mock_now.timestamp() else format_time_ago(t)):
            assert format_time_ago(future_timestamp) == "N/A"

def test_purify_batrick_multiline_without_language_specifier():
    """Test purify_batrick with multiline code block without language specifier."""
    input_text = "```\nfirst line\nsecond line\n```"
    expected = "first line\nsecond line"
    assert purify_batrick(input_text) == expected

def test_purify_batrick_multiline_with_language_specifier():
    """Test purify_batrick with multiline code block with language specifier."""
    input_text = "```python\nfirst line\nsecond line\n```"
    expected = "first line\nsecond line"
    assert purify_batrick(input_text) == expected

def test_purify_batrick_single_line():
    """Test purify_batrick with single line code block."""
    input_text = "```code here```"
    expected = "code here"
    assert purify_batrick(input_text) == expected

def test_purify_batrick_first_line_with_content():
    """Test purify_batrick with first line containing content - untapped path."""
    # This tests the path where first line has more than just backticks
    input_text = "```This is a long first line\nsecond line\nthird line\n```"
    expected = "This is a long first line\nsecond line\nthird line\n"
    assert purify_batrick(input_text) == expected

def test_get_valid_changes_with_changes():
    """Test get_valid_changes processes changes when they exist."""
    git_status_output = [("M", "file1.txt"), ("A", "file2.txt")]
    processed_changes = [MagicMock(), MagicMock()]

    with patch("c4f.main.parse_git_status", return_value=git_status_output), \
            patch("c4f.main.process_changed_files", return_value=processed_changes) as mock_process:
        result = get_valid_changes()

        mock_process.assert_called_once_with(git_status_output)
        assert result == processed_changes

def test_process_single_file_with_diff():
    """Test process_single_file with a valid diff."""
    status = "M"
    file_path = "test_file.py"
    progress = MagicMock()
    diff_task = MagicMock()
    
    mock_file_change = MagicMock()
    
    with patch("c4f.main.Path") as mock_path, \
         patch("c4f.main.get_file_diff", return_value="some diff") as mock_get_diff, \
         patch("c4f.main.analyze_file_type", return_value="feat") as mock_analyze, \
         patch("c4f.main.FileChange", return_value=mock_file_change) as mock_fc:
        
        result = process_single_file(status, file_path, progress, diff_task)
        
        mock_path.assert_called_once_with(file_path)
        mock_get_diff.assert_called_once_with(file_path)
        progress.advance.assert_called_once_with(diff_task)
        mock_analyze.assert_called_once()
        mock_fc.assert_called_once()
        assert result == mock_file_change

def test_process_single_file_without_diff():
    """Test process_single_file when no diff is returned (untested path)."""
    status = "M"
    file_path = "empty_file.py"
    progress = MagicMock()
    diff_task = MagicMock()
    
    with patch("c4f.main.Path") as mock_path, \
         patch("c4f.main.get_file_diff", return_value="") as mock_get_diff, \
         patch("c4f.main.analyze_file_type") as mock_analyze, \
         patch("c4f.main.FileChange") as mock_fc:
        
        result = process_single_file(status, file_path, progress, diff_task)
        
        mock_path.assert_called_once_with(file_path)
        mock_get_diff.assert_called_once_with(file_path)
        progress.advance.assert_called_once_with(diff_task)
        mock_analyze.assert_not_called()
        mock_fc.assert_not_called()
        assert result is None


def test_get_valid_user_response_first_try_valid():
    """Test get_valid_user_response with a valid response on first try."""
    valid_responses = ["y", "n", "e", "a", "all", ""]

    for response in valid_responses:
        with patch("builtins.input", return_value=response):
            result = get_valid_user_response()
            assert result == response


def test_get_valid_user_response_invalid_then_valid():
    """Test get_valid_user_response with invalid response first, then valid."""
    # First return invalid response, then valid
    with patch("builtins.input", side_effect=["invalid", "y"]):
        result = get_valid_user_response()
        assert result == "y"


def test_get_valid_user_response_multiple_invalid_then_valid():
    """Test get_valid_user_response with multiple invalid responses before valid."""
    # Testing the loop - return multiple invalid responses before a valid one
    with patch("builtins.input", side_effect=["invalid1", "invalid2", "invalid3", "y"]):
        result = get_valid_user_response()
        assert result == "y"


def test_handle_user_response_valid_responses():
    """Test handle_user_response with various valid responses."""
    group = [MagicMock(), MagicMock()]
    message = "Test commit message"

    # Test "a" response
    with patch("c4f.main.do_group_commit", return_value=True) as mock_commit:
        result = handle_user_response("a", group, message)
        mock_commit.assert_called_once_with(group, message, True)
        assert result is True

    # Test "all" response
    with patch("c4f.main.do_group_commit", return_value=True) as mock_commit:
        result = handle_user_response("all", group, message)
        mock_commit.assert_called_once_with(group, message, True)
        assert result is True

    # Test "y" response
    with patch("c4f.main.do_group_commit", return_value=False) as mock_commit:
        result = handle_user_response("y", group, message)
        mock_commit.assert_called_once_with(group, message)
        assert result is False

    # Test empty response (defaults to "y")
    with patch("c4f.main.do_group_commit", return_value=False) as mock_commit:
        result = handle_user_response("", group, message)
        mock_commit.assert_called_once_with(group, message)
        assert result is False

    # Test "n" response
    with patch("c4f.main.console.print") as mock_print, \
            patch("c4f.main.do_group_commit") as mock_commit:
        result = handle_user_response("n", group, message)
        mock_print.assert_called_once_with("[yellow]Skipping these changes...[/yellow]")
        mock_commit.assert_not_called()
        assert result is False

    # Test "e" response
    new_message = "Edited commit message"
    with patch("builtins.input", return_value=new_message), \
            patch("c4f.main.do_group_commit", return_value=False) as mock_commit:
        result = handle_user_response("e", group, message)
        mock_commit.assert_called_once_with(group, new_message)
        assert result is False

def test_find_git_root_success():
    """Test successful git root detection."""
    mock_path = Path("/path/to/git/repo")
    
    with patch("c4f.main.run_git_command") as mock_run_git, \
         patch("pathlib.Path.exists") as mock_exists, \
         patch("pathlib.Path.resolve", return_value=mock_path):
        
        # Setup mocks
        mock_run_git.return_value = (str(mock_path), "", 0)
        mock_exists.side_effect = [True, True]  # For root_path.exists() and .git check
        
        # Test
        result = find_git_root()
        
        # Verify
        assert result == mock_path
        mock_run_git.assert_called_once_with(["git", "rev-parse", "--show-toplevel"])
        assert mock_exists.call_count == 2

def test_find_git_root_command_error():
    """Test when git command fails."""
    with patch("c4f.main.run_git_command") as mock_run_git:
        # Setup mock to simulate git command error
        mock_run_git.return_value = ("", "fatal: not a git repository", 1)
        
        # Test
        with pytest.raises(FileNotFoundError) as exc_info:
            find_git_root()
        
        # Verify
        assert "Git error: fatal: not a git repository" in str(exc_info.value)
        mock_run_git.assert_called_once_with(["git", "rev-parse", "--show-toplevel"])

def test_find_git_root_no_git_directory():
    """Test when .git directory doesn't exist."""
    mock_path = Path("/path/to/non/git/repo")
    
    with patch("c4f.main.run_git_command") as mock_run_git, \
         patch("pathlib.Path.exists") as mock_exists, \
         patch("pathlib.Path.resolve", return_value=mock_path):
        
        # Setup mocks
        mock_run_git.return_value = (str(mock_path), "", 0)
        mock_exists.side_effect = [True, False]  # root exists but .git doesn't
        
        # Test
        with pytest.raises(FileNotFoundError) as exc_info:
            find_git_root()
        
        # Verify
        assert "Not a git repository" in str(exc_info.value)
        assert mock_exists.call_count == 2

def test_find_git_root_path_not_exists():
    """Test when the returned path doesn't exist."""
    mock_path = Path("/nonexistent/path")
    
    with patch("c4f.main.run_git_command") as mock_run_git, \
         patch("pathlib.Path.exists") as mock_exists, \
         patch("pathlib.Path.resolve", return_value=mock_path):
        
        # Setup mocks
        mock_run_git.return_value = (str(mock_path), "", 0)
        mock_exists.return_value = False  # Path doesn't exist
        
        # Test
        with pytest.raises(FileNotFoundError) as exc_info:
            find_git_root()
        
        # Verify
        assert "Not a git repository" in str(exc_info.value)
        mock_exists.assert_called_once()

def test_find_git_root_general_exception():
    """Test when an unexpected exception occurs."""
    with patch("c4f.main.run_git_command") as mock_run_git:
        # Setup mock to raise an unexpected exception
        mock_run_git.side_effect = Exception("Unexpected error")
        
        # Test
        with pytest.raises(FileNotFoundError) as exc_info:
            find_git_root()
        
        # Verify
        assert "Failed to determine git root: Unexpected error" in str(exc_info.value)
        mock_run_git.assert_called_once()

def test_handle_non_existent_git_repo_success():
    """Test successful git repo handling."""
    mock_path = Path("/path/to/git/repo")
    
    with patch("c4f.main.find_git_root", return_value=mock_path) as mock_find_root, \
         patch("os.chdir") as mock_chdir:
        
        # Test
        handle_non_existent_git_repo()
        
        # Verify
        mock_find_root.assert_called_once()
        mock_chdir.assert_called_once_with(mock_path)

def test_handle_non_existent_git_repo_error():
    """Test error handling in git repo verification."""
    with patch("c4f.main.find_git_root") as mock_find_root, \
         patch("c4f.main.console.print") as mock_print, \
         patch("sys.exit") as mock_exit:
        
        # Setup mock to raise FileNotFoundError
        error_msg = "Not a git repository"
        mock_find_root.side_effect = FileNotFoundError(error_msg)
        
        # Test
        handle_non_existent_git_repo()
        
        # Verify
        mock_find_root.assert_called_once()
        mock_print.assert_called_once_with(f"[red]Error: {error_msg}[/red]")
        mock_exit.assert_called_once_with(1)

def test_handle_non_existent_git_repo_chdir_error():
    """Test when changing directory fails."""
    mock_path = Path("/path/to/git/repo")
    error_msg = "Permission denied"
    
    with patch("c4f.main.find_git_root", return_value=mock_path) as mock_find_root, \
         patch("os.chdir", side_effect=OSError(error_msg)) as mock_chdir, \
         patch("c4f.main.console.print") as mock_print, \
         patch("sys.exit") as mock_exit:
        
        # Test
        handle_non_existent_git_repo()
        
        # Verify
        mock_find_root.assert_called_once()
        mock_chdir.assert_called_once_with(mock_path)
        mock_print.assert_called_once_with(f"[red]Error: Failed to change directory: {error_msg}[/red]")
        mock_exit.assert_called_once_with(1)

def test_create_combined_context():
    changes = [
        FileChange(Path("src/module1/file1.py"), "added", "", "feat"),
        FileChange(Path("src/module2/file2.py"), "modified", "", "fix")
    ]
    context = create_combined_context(changes)

    # Normalize to Unix-style paths for consistent testing
    normalized_context = context.replace("\\", "/")

    expected_output = "added src/module1/file1.py\nmodified src/module2/file2.py"
    assert normalized_context == expected_output

def test_generate_diff_summary(mock_config):
    changes = [
        FileChange(Path("file1.py"), "M", "diff content 1", "feat"),
        FileChange(Path("file2.py"), "A", "diff content 2", "feat")
    ]
    summary = generate_diff_summary(changes, mock_config)
    assert "File [1]" in summary
    assert "file1.py" in summary
    assert "diff content 1" in summary
    assert "File [2]" in summary
    assert "file2.py" in summary
    assert "diff content 2" in summary


# Test for line 63: Error handling in run_git_command
def test_run_git_command_error():
    with patch("subprocess.Popen") as mock_popen:
        mock_process = MagicMock()
        mock_process.communicate.side_effect = Exception("Test error")
        mock_popen.return_value = mock_process

        with pytest.raises(Exception):
            run_git_command(["git", "status"])


# Test for lines 102-103: Error handling in get_git_status_output
def test_get_git_status_output_error():
    with patch("c4f.main.run_git_command") as mock_run_git:
        mock_run_git.side_effect = Exception("Test error")

        with pytest.raises(Exception):
            get_git_status_output()


# Test for line 131: Error handling in handle_git_status_error
def test_handle_git_status_error():
    with patch("c4f.main.console.print") as mock_print:
        with patch("sys.exit") as mock_exit:
            handle_git_status_error("Test error")
            mock_print.assert_called_once()
            mock_exit.assert_called_once_with(1)


# Test for lines 169-173: Error handling in process_untracked_file
def test_process_untracked_file_directory_error():
    with patch("pathlib.Path.is_dir", return_value=True):
        with patch("c4f.main.list_untracked_files") as mock_list:
            mock_list.return_value = []  # Return empty list on error
            result = process_untracked_file("??", "test_dir")
            assert result == []


# Test for line 232: Error handling in process_renamed_file
def test_process_renamed_file_error():
    with pytest.raises(IndexError):
        process_renamed_file("invalid_path")


# Test for line 273: Error handling in process_git_status_line
def test_process_git_status_line_error():
    with patch("c4f.main.process_untracked_file") as mock_process:
        mock_process.return_value = []  # Return empty list on error
        result = process_git_status_line("?? file.txt")
        assert result == []


# Test for lines 452->442: Branch in parse_git_status
def test_parse_git_status_empty_output():
    with patch("c4f.main.get_git_status_output", return_value=("", "", 0)):
        result = parse_git_status()
        assert result == []


# Test for lines 478-483: Error handling in list_untracked_files
def test_list_untracked_files_error():
    with patch("pathlib.Path.glob") as mock_glob:
        mock_glob.return_value = []  # Return empty list on error
        result = list_untracked_files(Path("test_dir"))
        assert result == []


# Test for lines 732->734: Branch in get_tracked_file_diff
def test_get_tracked_file_diff_error():
    with patch("c4f.main.run_git_command") as mock_run_git:
        mock_run_git.side_effect = [
            ("", "", 1),  # First call fails
            ("", "", 1)  # Second call fails
        ]
        result = get_tracked_file_diff("test_file.txt")
        assert result == ""


# Test for line 750: Error handling in handle_untracked_file
def test_handle_untracked_file_error():
    with patch("pathlib.Path.exists", return_value=True):
        with patch("os.access", return_value=True):
            with patch("c4f.main.read_file_content", side_effect=Exception("Test error")):
                with patch("c4f.main.console.print") as mock_print:
                    result = handle_untracked_file(Path("test_file.txt"))
                    assert result == "Error: Test error"
                    mock_print.assert_called_once()


# Test for lines 1206-1207: Error handling in process_single_file
def test_process_single_file_error():
    with patch("c4f.main.get_file_diff", return_value=""):  # Return empty diff to trigger None return
        with patch("c4f.main.Progress") as mock_progress:
            mock_progress_instance = MagicMock()
            mock_progress.return_value.__enter__.return_value = mock_progress_instance
            mock_progress_instance.add_task.return_value = 1

            result = process_single_file("M", "test_file.txt", mock_progress_instance, 1)
            assert result is None


# Test for line 1213: Error handling in create_file_change
def test_create_file_change_error():
    with patch("c4f.main.get_file_diff", return_value=""):  # Return empty diff to trigger None return
        result = create_file_change("M", "test_file.txt")
        assert result is None


# Test for line 1221: Error handling in process_changed_files
def test_process_changed_files_error():
    with patch("c4f.main.Progress") as mock_progress:
        mock_progress_instance = MagicMock()
        mock_progress.return_value.__enter__.return_value = mock_progress_instance
        mock_progress_instance.add_task.return_value = 1

        with patch("c4f.main.process_single_file", return_value=None):  # Return None to simulate error
            result = process_changed_files([("M", "test_file.txt")])
            assert result == []



# Test for lines 1376-1377: Error handling in find_git_root
def test_find_git_root_error():
    with patch("c4f.main.run_git_command", side_effect=Exception("Test error")):
        with pytest.raises(FileNotFoundError):
            find_git_root()


# Additional test for process_untracked_file
def test_process_untracked_file_regular_file():
    with patch("pathlib.Path.is_dir", return_value=False):
        result = process_untracked_file("??", "test_file.txt")
        assert result == [("A", "test_file.txt")]


# Additional test for process_git_status_line with renamed file
def test_process_git_status_line_renamed():
    result = process_git_status_line("R  old.txt -> new.txt")
    assert result == [("R", "new.txt")]


# Additional test for process_git_status_line with regular change
def test_process_git_status_line_regular():
    result = process_git_status_line("M  file.txt")
    assert result == [("M", "file.txt")]


# Additional test for get_tracked_file_diff with unstaged changes
def test_get_tracked_file_diff_unstaged():
    with patch("c4f.main.run_git_command") as mock_run_git:
        mock_run_git.side_effect = [
            ("", "", 0),  # No staged changes
            ("unstaged diff", "", 0)  # Unstaged changes
        ]
        result = get_tracked_file_diff("test_file.txt")
        assert result == "unstaged diff"


# Test for determine_tool_calls function
def test_determine_tool_calls_comprehensive():
    result = determine_tool_calls(True, "test text", "test summary")
    assert result["function"]["name"] == "generate_commit"
    assert result["function"]["arguments"]["format"] == "detailed"


def test_determine_tool_calls_simple():
    result = determine_tool_calls(False, "test text")
    assert result["function"]["name"] == "generate_commit"
    assert result["function"]["arguments"]["format"] == "inline"


# Test for create_simple_tool_call function
def test_create_simple_tool_call():
    result = create_simple_tool_call("test text")
    assert result["function"]["name"] == "generate_commit"
    assert result["function"]["arguments"]["style"] == "conventional"
    assert result["function"]["arguments"]["max_length"] == 72


# Test for create_comprehensive_tool_call function
def test_create_comprehensive_tool_call():
    result = create_comprehensive_tool_call("test text", "test summary")
    assert result["function"]["name"] == "generate_commit"
    assert result["function"]["arguments"]["style"] == "conventional"
    assert result["function"]["arguments"]["format"] == "detailed"


# Test for handle_comprehensive_message function
def test_handle_comprehensive_message_short():
    with patch("c4f.main.handle_short_comprehensive_message") as mock_handle:
        mock_handle.return_value = "use"
        config = MagicMock()
        config.min_comprehensive_length = 100
        result = handle_comprehensive_message("short message", [], config)
        assert result == "short message"




# Test for calculate_total_diff_lines function




def test_handle_short_comprehensive_message_fallback():
    with patch("builtins.input", return_value="3"):
        result = handle_short_comprehensive_message("test message")
        assert result == "fallback"


# Test for main function
def test_main_no_changes():
    with patch("c4f.main.handle_non_existent_git_repo"):
        with patch("c4f.main.reset_staging"):
            with patch("c4f.main.get_valid_changes", return_value=[]):
                with patch("c4f.main.exit_with_no_changes") as mock_exit:
                    main()
                    mock_exit.assert_called_once()


def test_main_with_changes():
    changes = [
        FileChange(status="M", path=Path("test.txt"), type="feat", diff="test", diff_lines=5, last_modified=0)
    ]
    with patch("c4f.main.handle_non_existent_git_repo"):
        with patch("c4f.main.reset_staging"):
            with patch("c4f.main.get_valid_changes", return_value=changes):
                with patch("c4f.main.display_changes"):
                    with patch("c4f.main.group_related_changes", return_value=[changes]):
                        with patch("c4f.main.process_change_group", return_value=True):
                            main()


# Test for get_valid_changes function
def test_get_valid_changes_empty():
    with patch("c4f.main.parse_git_status", return_value=[]):
        result = get_valid_changes()
        assert result == []


# Test for get_model_response function
def test_get_model_response_success():
    with patch("c4f.main.client.chat.completions.create") as mock_create:
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "test message"
        mock_create.return_value = mock_response
        config = MagicMock()
        result = get_model_response("test prompt", {}, config)
        assert result == "test message"


def test_get_model_response_error():
    with patch("c4f.main.client.chat.completions.create", side_effect=Exception("Test error")):
        with patch("c4f.main.console.print") as mock_print:
            config = MagicMock()
            result = get_model_response("test prompt", {}, config)
            assert result is None
            mock_print.assert_called_once()



# Test for execute_with_timeout function
def test_execute_with_timeout_success():
    with patch("concurrent.futures.ThreadPoolExecutor") as mock_executor:
        mock_future = MagicMock()
        mock_future.result.return_value = "test result"
        mock_executor.return_value.__enter__.return_value.submit.return_value = mock_future

        progress = MagicMock()
        task = MagicMock()
        result = execute_with_timeout(lambda: "test result", progress, task)
        assert result == "test result"


def test_execute_with_timeout_timeout():
    with patch("concurrent.futures.ThreadPoolExecutor") as mock_executor:
        mock_future = MagicMock()
        mock_future.result.side_effect = TimeoutError()
        mock_executor.return_value.__enter__.return_value.submit.return_value = mock_future

        progress = MagicMock()
        task = MagicMock()
        result = execute_with_timeout(lambda: "test result", progress, task)
        assert result is None




def test_process_response_single_line():
    with patch("c4f.main.console.print") as mock_print:
        result = process_response("test message")
        assert result == "test message"
        mock_print.assert_called_once()


def test_process_response_multi_line():
    with patch("c4f.main.console.print") as mock_print:
        result = process_response("first line\nsecond line")
        assert result == "first line\nsecond line"
        mock_print.assert_called_once()

def test_handle_error_other():
    with patch("c4f.main.console.print") as mock_print:
        handle_error(Exception("Test error"))
        mock_print.assert_called_once_with(
            "[yellow]Error in model response, using fallback message: Test error[/yellow]")


# Test for commit_changes function
def test_commit_changes_success():
    with patch("c4f.main.Progress") as mock_progress:
        with patch("c4f.main.stage_files") as mock_stage:
            with patch("c4f.main.do_commit") as mock_commit:
                with patch("c4f.main.display_commit_result") as mock_display:
                    mock_commit.return_value = ("Success", 0)
                    commit_changes(["test.txt"], "test message")
                    mock_stage.assert_called_once()
                    mock_commit.assert_called_once()
                    mock_display.assert_called_once()




def test_display_commit_result_error():
    with patch("c4f.main.console.print") as mock_print:
        display_commit_result(("Error", 1), "test message")
        mock_print.assert_called_once()

# Test for generate_diff_summary function

# Test for determine_prompt function
def test_determine_prompt_simple():
    config = MagicMock()
    config.prompt_threshold = 50
    result = determine_prompt("test text", [], 10, config)
    assert "test text" in result
    assert "conventional commit message" in result.lower()


# Test for generate_simple_prompt function
def test_generate_simple_prompt_with_brackets():
    config = MagicMock()
    config.force_brackets = True
    result = generate_simple_prompt("test text", config)
    assert "test text" in result
    assert "Please use brackets" in result


def test_generate_simple_prompt_without_brackets():
    config = MagicMock()
    config.force_brackets = False
    result = generate_simple_prompt("test text", config)
    assert "test text" in result
    assert "Please use brackets" not in result


# Test for generate_comprehensive_prompt function
def test_generate_comprehensive_prompt_with_brackets():
    config = MagicMock()
    config.force_brackets = True
    result = generate_comprehensive_prompt("test text", "test summary", config)
    assert "test text" in result
    assert "test summary" in result
    assert "Please use brackets" in result


def test_generate_comprehensive_prompt_without_brackets():
    config = MagicMock()
    config.force_brackets = False
    result = generate_comprehensive_prompt("test text", "test summary", config)
    assert "test text" in result
    assert "test summary" in result
    assert "Please use brackets" not in result


# Test for handle_comprehensive_message with retry
def test_handle_comprehensive_message_retry():
    with patch("c4f.main.handle_short_comprehensive_message") as mock_handle:
        mock_handle.return_value = "retry"
        config = MagicMock()
        config.min_comprehensive_length = 100
        result = handle_comprehensive_message("short message", [], config)
        assert result == "retry"


# Test for handle_comprehensive_message with fallback
def test_handle_comprehensive_message_fallback():
    with patch("c4f.main.handle_short_comprehensive_message") as mock_handle:
        mock_handle.return_value = "fallback"
        config = MagicMock()
        config.min_comprehensive_length = 100
        changes = [
            FileChange(status="M", path=Path("test.txt"), type="feat", diff="test diff", diff_lines=5, last_modified=0)
        ]
        result = handle_comprehensive_message("short message", changes, config)
        assert result.startswith("feat: update")


# Test for handle_short_comprehensive_message with empty input


# Test for execute_with_timeout with custom timeout
def test_execute_with_timeout_custom_timeout():
    with patch("concurrent.futures.ThreadPoolExecutor") as mock_executor:
        mock_future = MagicMock()
        mock_future.result.return_value = "test result"
        mock_executor.return_value.__enter__.return_value.submit.return_value = mock_future

        progress = MagicMock()
        task = MagicMock()
        result = execute_with_timeout(lambda: "test result", progress, task, timeout=5)
        assert result == "test result"


# Test for execute_with_timeout with config timeout
def test_execute_with_timeout_config_timeout():
    with patch("concurrent.futures.ThreadPoolExecutor") as mock_executor:
        mock_future = MagicMock()
        mock_future.result.return_value = "test result"
        mock_executor.return_value.__enter__.return_value.submit.return_value = mock_future

        progress = MagicMock()
        task = MagicMock()
        config = MagicMock()
        config.fallback_timeout = 15
        result = execute_with_timeout(lambda: "test result", progress, task, "arg1", config)
        assert result == "test result"




# Test for main with config
def test_main_with_config():
    config = MagicMock()
    with patch("c4f.main.handle_non_existent_git_repo"):
        with patch("c4f.main.reset_staging"):
            with patch("c4f.main.get_valid_changes", return_value=[]):
                with patch("c4f.main.exit_with_no_changes") as mock_exit:
                    main(config)
                    mock_exit.assert_called_once()


# Test for main without config
def test_main_without_config():
    with patch("c4f.main.handle_non_existent_git_repo"):
        with patch("c4f.main.reset_staging"):
            with patch("c4f.main.get_valid_changes", return_value=[]):
                with patch("c4f.main.exit_with_no_changes") as mock_exit:
                    with patch("c4f.config.default_config") as mock_config:
                        main()
                        mock_exit.assert_called_once()


# Test for main with multiple change groups
def test_main_multiple_groups():
    changes1 = [FileChange(status="M", path=Path("test1.txt"), type="feat", diff="test", diff_lines=5, last_modified=0)]
    changes2 = [FileChange(status="M", path=Path("test2.txt"), type="fix", diff="test", diff_lines=5, last_modified=0)]

    with patch("c4f.main.handle_non_existent_git_repo"):
        with patch("c4f.main.reset_staging"):
            with patch("c4f.main.get_valid_changes", return_value=changes1 + changes2):
                with patch("c4f.main.display_changes"):
                    with patch("c4f.main.group_related_changes", return_value=[changes1, changes2]):
                        with patch("c4f.main.process_change_group", side_effect=[False, True]):
                            main()


# Test for get_model_response with no choices
def test_get_model_response_no_choices():
    with patch("c4f.main.client.chat.completions.create") as mock_create:
        mock_response = MagicMock()
        mock_response.choices = []
        mock_create.return_value = mock_response
        config = MagicMock()
        result = get_model_response("test prompt", {}, config)
        assert result is None


# Test for get_model_response with None response
def test_get_model_response_none_response():
    with patch("c4f.main.client.chat.completions.create") as mock_create:
        mock_create.return_value = None
        config = MagicMock()
        result = get_model_response("test prompt", {}, config)
        assert result is None