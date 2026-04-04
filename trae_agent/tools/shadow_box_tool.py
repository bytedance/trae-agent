"""
shadow_box_tool.py — 62D Shadow Box Tool (Trae Agent integration layer)

Registered as a trae-agent Tool, LLM can directly invoke shadow box's 5 core features.
Core algorithms called via local API, implementation details not exposed.
"""

from __future__ import annotations

from trae_agent.tools.base import Tool, ToolCallArguments, ToolExecResult, ToolParameter

import json


class ShadowBoxTool(Tool):
    """62-Dimensional Shadow Box Tool — full-dimension sandbox beyond ShadowWorkspace.

    Supported operations:
    - create_sandbox:   Create 62-dim isolated sandbox
    - destroy_sandbox:  Destroy sandbox (zero residue)
    - hot_needle_scan:  Hot needle precision diagnosis (quantization/dimension/expert errors)
    - analyze_structure: 62-dim code structure analysis
    - zero_pollution_exec: Zero-pollution pre-execution
    - validate:         Real data full validation
    - full_cycle:       Full cycle (create->analyze->diagnose->exec->validate->destroy)
    - status:           View shadow box status
    """

    def __init__(self, model_provider: str | None = None, project_dir: str = "."):
        super().__init__(model_provider)
        self._project_dir = project_dir
        self._box = None

    def _ensure_box(self):
        if self._box is None:
            from trae_agent.sandbox.shadow_box_62d import ShadowBox62D
            self._box = ShadowBox62D(project_dir=self._project_dir)

    def get_name(self) -> str:
        return "shadow_box_62d"

    def get_description(self) -> str:
        return (
            "62-dimensional Shadow Box — isolated sandbox with neural pulse diagnosis. "
            "Provides: 62D code structure analysis, hot needle scanning for reshape/dims/expert errors, "
            "zero-pollution code pre-execution with auto-fix, and real data validation from .memory/. "
            "Operations: create_sandbox, destroy_sandbox, hot_needle_scan, analyze_structure, "
            "zero_pollution_exec, validate, full_cycle, status."
        )

    def get_parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="operation",
                type="string",
                description="Operation to perform",
                enum=[
                    "create_sandbox",
                    "destroy_sandbox",
                    "hot_needle_scan",
                    "analyze_structure",
                    "zero_pollution_exec",
                    "validate",
                    "full_cycle",
                    "status",
                ],
                required=True,
            ),
            ToolParameter(
                name="target",
                type="string",
                description="File or directory path to analyze/scan (for hot_needle_scan, analyze_structure, full_cycle)",
                required=False,
            ),
            ToolParameter(
                name="code",
                type="string",
                description="Code snippet to execute (for zero_pollution_exec) or scan (for hot_needle_scan)",
                required=False,
            ),
            ToolParameter(
                name="copy_files",
                type="string",
                description="Comma-separated list of files to copy into sandbox (for create_sandbox)",
                required=False,
            ),
        ]

    async def execute(self, arguments: ToolCallArguments) -> ToolExecResult:
        """Execute shadow box operation."""
        self._ensure_box()

        op = str(arguments.get("operation", "status"))
        target = arguments.get("target")
        code = arguments.get("code")
        copy_files_str = arguments.get("copy_files")

        try:
            if op == "create_sandbox":
                copy_files = [f.strip() for f in copy_files_str.split(",")] if copy_files_str else None
                result = self._box.create_sandbox(copy_files=copy_files)

            elif op == "destroy_sandbox":
                result = self._box.destroy_sandbox()

            elif op == "hot_needle_scan":
                result = self._box.hot_needle_scan(
                    target=target,
                    code=str(code) if code else None,
                )

            elif op == "analyze_structure":
                if not target:
                    return ToolExecResult(error="analyze_structure requires 'target' parameter")
                result = self._box.analyze_structure(target)

            elif op == "zero_pollution_exec":
                if not code:
                    return ToolExecResult(error="zero_pollution_exec requires 'code' parameter")
                result = self._box.zero_pollution_exec(str(code))

            elif op == "validate":
                result = self._box.validate_real_data()

            elif op == "full_cycle":
                if not target:
                    return ToolExecResult(error="full_cycle requires 'target' parameter")
                result = self._box.full_cycle(
                    target=target,
                    exec_code=str(code) if code else None,
                )

            elif op == "status":
                result = self._box.status()

            else:
                return ToolExecResult(error=f"Unknown operation: {op}")

            output = json.dumps(result, ensure_ascii=False, indent=2, default=str)
            return ToolExecResult(output=output)

        except Exception as e:
            return ToolExecResult(error=f"Shadow box error: {e}")
