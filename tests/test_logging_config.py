"""Test actual stdout routing with a separate interpreter and clean logging state."""

import subprocess
import sys


def test_database_logs_go_to_stdout_once_across_repeated_configuration(tmp_path):
    path = str(tmp_path / "stdout.sqlite3")
    result = subprocess.run(
        [sys.executable, "-c", """
import sys
from molt_ui.bootstrap import create_service
from molt_ui.config import Settings
settings = Settings(executable="/unavailable/molt", database=sys.argv[1])
create_service(settings).close()
create_service(settings).close()
""", path],
        capture_output=True, text=True, check=True,
    )
    assert result.stdout.count("SQLite database ready") == 2
    assert result.stdout.count("Opening SQLite database") == 2
    assert path in result.stdout
    assert result.stderr == ""
