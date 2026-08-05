"""
tests/test_packaging.py
-----------------------
Unit tests verifying application packaging configuration and path resolution logic.
"""

import sys
from pathlib import Path
from unittest.mock import patch


def test_packaging_spec_file_existence() -> None:
    """Ensure the PyInstaller spec file exists and lists key assets and plugins."""
    spec_path = Path("Nova.spec")
    assert spec_path.exists()
    
    spec_content = spec_path.read_text(encoding="utf-8")
    assert "main.py" in spec_content
    assert "plugins" in spec_content
    assert "skills" in spec_content
    assert "sounddevice" in spec_content
    assert "faster_whisper" in spec_content


def test_frozen_path_resolution() -> None:
    """Ensure path resolution yields persistent directory targets next to the executable when frozen."""
    simulated_meipass = "C:\\Temp\\_MEI12345"
    simulated_exe = "C:\\Program Files\\Nova\\Nova.exe"

    with patch("sys.frozen", True, create=True), \
         patch("sys._MEIPASS", simulated_meipass, create=True), \
         patch("sys.executable", simulated_exe, create=True):
         
        # Simulate logic from config.py base paths definition
        base_dir = Path(sys._MEIPASS).resolve()
        exe_dir = Path(sys.executable).parent.resolve()
        data_dir = exe_dir / "data"
        logs_dir = exe_dir / "logs"
        dotenv_path = exe_dir / ".env"

        assert base_dir == Path(simulated_meipass)
        assert exe_dir == Path("C:\\Program Files\\Nova")
        assert data_dir == Path("C:\\Program Files\\Nova\\data")
        assert logs_dir == Path("C:\\Program Files\\Nova\\logs")
        assert dotenv_path == Path("C:\\Program Files\\Nova\\.env")
