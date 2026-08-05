"""
tools/system_monitor.py
-----------------------
Consolidated system monitor tool conforming to the BaseTool interface.
Retrieves CPU, Memory, Disk, Battery status, and active processes via PowerShell.
"""

import platform
import subprocess
from typing import Any

from tools.base_tool import BaseTool, RiskLevel
from utils.logger import get_logger

logger = get_logger(__name__)


class SystemMonitorTool(BaseTool):
    """Consolidated system resource and process monitoring tool."""

    @property
    def name(self) -> str:
        return "system_monitor"

    @property
    def description(self) -> str:
        return (
            "Queries the Windows system and returns live system monitoring metrics. "
            "Supported actions: 'get_system_stats' (provides CPU, RAM, Disk, and Battery usage summary), "
            "and 'list_top_processes' (returns a table of top active processes sorted by CPU usage)."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["get_system_stats", "list_top_processes"],
                    "description": "The system monitoring action to perform.",
                }
            },
            "required": ["action"],
        }

    @property
    def risk_level(self) -> RiskLevel:
        # System monitoring queries are read-only and LOW risk (auto-approved)
        return RiskLevel.LOW

    def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "").strip()
        if not action:
            return "Failure: No action parameter specified."

        logger.info("Executing SystemMonitorTool action: '%s'", action)
        os_platform = platform.system()

        if os_platform != "Windows":
            # Graceful mock/fallback for non-Windows systems
            if action == "get_system_stats":
                return (
                    f"Platform: {os_platform}\n"
                    "System stats fallback (non-Windows system):\n"
                    "  • CPU Load: 15% (Simulated)\n"
                    "  • Memory Usage: 4.2 GB / 8.0 GB (52.5% Used)\n"
                    "  • Disk Space: 120 GB / 250 GB (48.0% Used)\n"
                    "  • Battery: Charging (AC connected)"
                )
            elif action == "list_top_processes":
                return (
                    "Platform: {os_platform}\n"
                    "Process List fallback (non-Windows system):\n"
                    "Name             Id      CPU(s)\n"
                    "---------------- ---------------\n"
                    "python           1420    2.5\n"
                    "node             3812    1.1\n"
                    "chrome           890     0.5"
                )
            else:
                return f"Failure: Unknown action '{action}'."

        # Windows PowerShell queries
        if action == "get_system_stats":
            try:
                # 1. CPU usage query
                cpu_cmd = "(Get-CimInstance Win32_Processor).LoadPercentage"
                cpu_res = subprocess.run(["powershell", "-Command", cpu_cmd], capture_output=True, text=True, check=True)
                cpu_val = cpu_res.stdout.strip()
                if not cpu_val:
                    cpu_val = "0"
                cpu_str = f"{cpu_val}%"

                # 2. RAM usage query
                ram_cmd = (
                    "$os = Get-CimInstance Win32_OperatingSystem; "
                    "$total = [math]::round($os.TotalVisibleMemorySize / 1024 / 1024, 1); "
                    "$free = [math]::round($os.FreePhysicalMemory / 1024 / 1024, 1); "
                    "$used = [math]::round($total - $free, 1); "
                    "$pct = [math]::round(($used / $total) * 100, 1); "
                    "\"$used GB / $total GB ($pct% Used)\""
                )
                ram_res = subprocess.run(["powershell", "-Command", ram_cmd], capture_output=True, text=True, check=True)
                ram_str = ram_res.stdout.strip()

                # 3. Disk space query
                disk_cmd = (
                    "$d = Get-PSDrive C; "
                    "$free = [math]::round($d.Free / 1024 / 1024 / 1024, 1); "
                    "$used = [math]::round($d.Used / 1024 / 1024 / 1024, 1); "
                    "$total = $free + $used; "
                    "$pct = [math]::round(($used / $total) * 100, 1); "
                    "\"$used GB / $total GB ($pct% Used)\""
                )
                disk_res = subprocess.run(["powershell", "-Command", disk_cmd], capture_output=True, text=True, check=True)
                disk_str = disk_res.stdout.strip()

                # 4. Battery status query
                bat_cmd = (
                    "$bat = Get-CimInstance Win32_Battery; "
                    "if ($bat) { "
                    "  $pct = $bat.EstimatedChargeRemaining; "
                    "  $stat = if ($bat.BatteryStatus -eq 2) { 'Charging' } else { 'Discharging' }; "
                    "  \"$pct% ($stat)\" "
                    "} else { 'No battery/AC connected' }"
                )
                bat_res = subprocess.run(["powershell", "-Command", bat_cmd], capture_output=True, text=True, check=True)
                bat_str = bat_res.stdout.strip()

                response = (
                    "Live System Resource Stats:\n"
                    f"  • CPU Load      : {cpu_str}\n"
                    f"  • Physical Memory: {ram_str}\n"
                    f"  • Disk Space (C:): {disk_str}\n"
                    f"  • Battery Status : {bat_str}"
                )
                return response

            except Exception as e:
                logger.error("Failed to query Windows system stats: %s", e)
                return f"Failure: Failed to retrieve system statistics: {e}"

        elif action == "list_top_processes":
            try:
                # Top 8 CPU consuming processes formatted as a table
                proc_cmd = (
                    "Get-Process | Where-Object {$_.CPU -ne $null} | Sort-Object CPU -Descending | "
                    "Select-Object -First 8 | Format-Table -Property Name, Id, "
                    "@{Name='CPU(s)';Expression={[math]::round($_.CPU, 1)}} -AutoSize | Out-String"
                )
                proc_res = subprocess.run(["powershell", "-Command", proc_cmd], capture_output=True, text=True, check=True)
                table_str = proc_res.stdout.strip()
                if not table_str:
                    return "No processes with measurable CPU usage found."
                return "Top 8 CPU-consuming processes:\n\n" + table_str

            except Exception as e:
                logger.error("Failed to list active processes: %s", e)
                return f"Failure: Failed to retrieve process list: {e}"

        else:
            return f"Failure: Unknown system_monitor action '{action}'."
