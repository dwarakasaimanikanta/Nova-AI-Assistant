"""
interface/gui package init.
"""

try:
    from interface.gui.gui_app import NovaGUIApp
except ImportError:
    # Handle environment issues gracefully in test runs
    NovaGUIApp = None

__all__ = ["NovaGUIApp"]
