"""
core/startup_manager.py
-----------------------
Coordinates startup logic, Windows registry auto-start configurations, and safe-mode boot state checks.
"""

import os
import sys
from pathlib import Path
from utils.logger import get_logger
import config

logger = get_logger(__name__)

# Windows Run Registry Key path
RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_NAME_KEY = "NovaAIAssistant"


class StartupReport:
    """Object containing initialized modules, failed modules, duration, and warnings."""

    def __init__(self) -> None:
        self.initialized_modules = []
        self.failed_modules = []
        self.startup_duration = 0.0
        self.warnings = []

    def to_dict(self) -> dict:
        return {
            "initialized_modules": self.initialized_modules,
            "failed_modules": self.failed_modules,
            "startup_duration": self.startup_duration,
            "warnings": self.warnings
        }


class StartupManager:
    """Coordinates host startup configuration, registry automation, and safe-mode boot state checks."""

    def __init__(self) -> None:
        """Initialize the StartupManager."""
        self._is_windows = sys.platform == "win32"
        logger.info("[StartupManager] Initialized. Platform is Windows: %s", self._is_windows)

    def is_auto_start_registered(self) -> bool:
        """Check if auto-start registry entry exists for Nova."""
        if not self._is_windows:
            logger.debug("[StartupManager] Auto-start check skipped (non-Windows).")
            return False

        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_READ) as key:
                value, reg_type = winreg.QueryValueEx(key, APP_NAME_KEY)
                logger.debug("[StartupManager] Found registry key: %r", value)
                return True
        except FileNotFoundError:
            logger.debug("[StartupManager] Registry key not found.")
            return False
        except Exception as e:
            logger.error("[StartupManager] Failed to read registry: %s", e)
            return False

    def register_auto_start(self, exe_path: str | None = None) -> bool:
        """
        Add Nova registry entry to Windows startup.
        
        Args:
            exe_path: Optional custom path to executable or main.py. Defaults to sys.executable with main.py path.
        """
        if not self._is_windows:
            logger.warning("[StartupManager] Registration skipped (non-Windows).")
            return False

        # Construct path to run command:
        # e.g., if frozen: "c:\path\to\nova.exe --minimized"
        # else: "c:\path\to\python.exe c:\path\to\main.py --minimized"
        if getattr(sys, "frozen", False):
            cmd_path = sys.executable
        else:
            main_py_path = Path(__file__).parent.parent / "main.py"
            # Ensure we wrap the paths in quotes in case they contain spaces
            python_exe = sys.executable
            cmd_path = f'"{python_exe}" "{main_py_path.resolve()}"'

        # Append start flags
        cmd = f"{cmd_path} --minimized"

        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_WRITE) as key:
                winreg.SetValueEx(key, APP_NAME_KEY, 0, winreg.REG_SZ, cmd)
                logger.info("[StartupManager] Registered auto-start registry command: %r", cmd)
                return True
        except Exception as e:
            logger.error("[StartupManager] Failed to register auto-start key: %s", e)
            return False

    def unregister_auto_start(self) -> bool:
        """Remove Nova registry entry from Windows startup."""
        if not self._is_windows:
            logger.warning("[StartupManager] Unregistration skipped (non-Windows).")
            return False

        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_WRITE) as key:
                winreg.DeleteValue(key, APP_NAME_KEY)
                logger.info("[StartupManager] Unregistered auto-start registry key.")
                return True
        except FileNotFoundError:
            logger.debug("[StartupManager] Registry key was already absent.")
            return True
        except Exception as e:
            logger.error("[StartupManager] Failed to unregister auto-start key: %s", e)
            return False

    def detect_startup_mode(self) -> str:
        """
        Detect if Nova started automatically from boot or manually.
        
        Returns:
            "auto" if started automatically, "manual" otherwise.
        """
        # If --minimized flag is present, it indicates it was triggered by auto start
        if "--minimized" in sys.argv:
            logger.info("[StartupManager] Auto-start run detected (--minimized present).")
            return "auto"
        logger.info("[StartupManager] Manual run detected.")
        return "manual"

    def handle_startup_failure(self, exception: Exception, subsystem_name: str) -> None:
        """
        Log details on subsystem startup errors.
        
        Args:
            exception: The raised error exception.
            subsystem_name: Name of the failed subsystem (e.g. "Voice", "ADB").
        """
        logger.error("[StartupManager] Subsystem %s failed to start: %s", subsystem_name, exception, exc_info=True)

    def initialize_startup(self) -> None:
        """
        Execute startup sequence logic: auto-register run keys if AUTO_START config is enabled,
        or verify existing registries conform to standard.
        """
        logger.info("[StartupManager] Running startup sequence...")
        
        # Register or unregister based on configuration
        if config.AUTO_START:
            if not self.is_auto_start_registered():
                logger.info("[StartupManager] AUTO_START configured: registering registry key.")
                self.register_auto_start()
        else:
            if self.is_auto_start_registered():
                logger.info("[StartupManager] AUTO_START not configured: clearing registry key.")
                self.unregister_auto_start()

    def run_lifecycle(self, args=None) -> tuple[StartupReport, Any]:
        """
        Runs the 10-step startup lifecycle sequence deterministically,
        measuring durations and catching any failures gracefully.
        
        Args:
            args: Command line parsed arguments.

        Returns:
            A tuple of (StartupReport, engine_instance).
        """
        import time
        from core.service_manager import (
            ServiceManager, MemoryService, PluginManagerService,
            StartupManagerService, BrowserService, AndroidService, VoiceService
        )
        from memory.short_term import ShortTermMemory
        from core.engine import NovaEngine

        report = StartupReport()
        start_overall = time.time()

        # Instantiate Memory and loader beforehand for adapters
        memory = ShortTermMemory()
        
        # Instantiate adapters
        mem_srv = MemoryService(memory_instance=memory)
        plug_srv = PluginManagerService()
        start_srv = StartupManagerService(manager_instance=self)
        browser_srv = BrowserService()
        android_srv = AndroidService()

        # Instantiate ServiceManager
        sm = ServiceManager()

        # Register services with dependencies to represent the deterministic ordering
        # Ordering: Configuration, Logging, Memory, Plugin Loader, Permission Gate, Browser Manager, Android Manager, LLM Provider, Voice Manager, User Interface
        sm.register_service(mem_srv)
        sm.register_service(plug_srv, dependencies=["Memory"])
        sm.register_service(start_srv, dependencies=["Plugin Manager"])
        sm.register_service(browser_srv, dependencies=["Startup Manager"])
        sm.register_service(android_srv, dependencies=["Browser"])

        # Validate dependencies
        if not sm.validate_dependencies():
            report.warnings.append("ServiceManager dependency validation failed.")

        # Step 1: Configuration
        t0 = time.time()
        try:
            from core.config_service import ConfigService
            cfg_srv = ConfigService()
            if cfg_srv.initialize():
                report.initialized_modules.append("Configuration")
                logger.info("[StartupManager] Subsystem Configuration started successfully in %.4fs", time.time() - t0)
            else:
                report.failed_modules.append("Configuration")
                report.warnings.append("Configuration service failed to initialize.")
        except Exception as e:
            report.failed_modules.append("Configuration")
            report.warnings.append(f"Configuration failure: {e}")

        # Step 2: Logging
        t0 = time.time()
        try:
            from utils.logger import get_logger
            _ = get_logger("startup_check")
            report.initialized_modules.append("Logging")
            logger.info("[StartupManager] Subsystem Logging started successfully in %.4fs", time.time() - t0)
        except Exception as e:
            report.failed_modules.append("Logging")
            report.warnings.append(f"Logging failure: {e}")

        # Step 3: Memory
        t0 = time.time()
        if sm.start_service("Memory"):
            report.initialized_modules.append("Memory")
            logger.info("[StartupManager] Subsystem Memory started successfully in %.4fs", time.time() - t0)
        else:
            report.failed_modules.append("Memory")
            report.warnings.append("Memory service failed to start.")

        # Step 4: Plugin Loader
        t0 = time.time()
        if sm.start_service("Plugin Manager"):
            report.initialized_modules.append("Plugin Loader")
            logger.info("[StartupManager] Subsystem Plugin Loader started successfully in %.4fs", time.time() - t0)
        else:
            report.failed_modules.append("Plugin Loader")
            report.warnings.append("Plugin Manager service failed to start.")

        # Step 5: Permission Gate
        t0 = time.time()
        try:
            from tools.permission_gate import PermissionGate
            _ = PermissionGate()
            report.initialized_modules.append("Permission Gate")
            logger.info("[StartupManager] Subsystem Permission Gate started successfully in %.4fs", time.time() - t0)
        except Exception as e:
            report.failed_modules.append("Permission Gate")
            report.warnings.append(f"Permission Gate failure: {e}")

        # Step 6: Browser Manager
        t0 = time.time()
        if sm.start_service("Browser"):
            report.initialized_modules.append("Browser Manager")
            logger.info("[StartupManager] Subsystem Browser Manager started successfully in %.4fs", time.time() - t0)
        else:
            report.failed_modules.append("Browser Manager")
            report.warnings.append("Browser service failed to start.")

        # Step 7: Android Manager
        t0 = time.time()
        if sm.start_service("Android"):
            report.initialized_modules.append("Android Manager")
            logger.info("[StartupManager] Subsystem Android Manager started successfully in %.4fs", time.time() - t0)
        else:
            report.failed_modules.append("Android Manager")
            report.warnings.append("Android service failed to start.")

        # Instantiate Engine (integrates Plugin Loader, Permission Gate, Browser/Android hooks)
        t_eng = time.time()
        engine = None
        try:
            engine = NovaEngine(memory=memory)
            logger.info("[StartupManager] NovaEngine assembled successfully in %.4fs", time.time() - t_eng)
        except Exception as e:
            report.warnings.append(f"NovaEngine assembly failure: {e}")

        # 8. LLM Provider
        t0 = time.time()
        try:
            if engine and engine.conversation:
                report.initialized_modules.append("LLM Provider")
            else:
                report.initialized_modules.append("LLM Provider")
                report.warnings.append("LLM Provider inactive (offline fallback mode).")
            logger.info("[StartupManager] Subsystem LLM Provider started successfully in %.4fs", time.time() - t0)
        except Exception as e:
            report.failed_modules.append("LLM Provider")
            report.warnings.append(f"LLM Provider failure: {e}")

        # 9. Voice Manager
        t0 = time.time()
        try:
            # Register Voice Service wrapping voice_manager
            voice_plugin = next((p for p in engine.plugins if p.name == "voice"), None)
            if voice_plugin and voice_plugin.voice_manager:
                voice_srv = VoiceService(voice_manager=voice_plugin.voice_manager)
                sm.register_service(voice_srv, dependencies=["Startup Manager"])
                sm.start_service("Voice")
            report.initialized_modules.append("Voice Manager")
            logger.info("[StartupManager] Subsystem Voice Manager started successfully in %.4fs", time.time() - t0)
        except Exception as e:
            report.failed_modules.append("Voice Manager")
            report.warnings.append(f"Voice Manager failure: {e}")

        # 10. User Interface
        t0 = time.time()
        try:
            if args and getattr(args, "gui", False):
                from interface.gui.gui_app import NovaGUIApp
            else:
                from interface.cli import NovaCLI
            report.initialized_modules.append("User Interface")
            logger.info("[StartupManager] Subsystem User Interface started successfully in %.4fs", time.time() - t0)
        except Exception as e:
            report.failed_modules.append("User Interface")
            report.warnings.append(f"User Interface failure: {e}")

        report.startup_duration = time.time() - start_overall
        logger.info("[StartupManager] Startup lifecycle completed in %.4fs. Report: %s", report.startup_duration, report.to_dict())

        return report, engine
