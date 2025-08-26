import json
import re
import io
import tokenize
from typing import Any

from typing_extensions import override
from unidiff import PatchSet

from trae_agent.agent.agent_basics import AgentError, AgentExecution
from trae_agent.agent.base_agent import BaseAgent
from trae_agent.tools import tools_registry
from trae_agent.tools.base import Tool, ToolExecutor, ToolResult
from trae_agent.utils.llm_clients.llm_basics import LLMMessage, LLMResponse
from trae_agent.prompt.agent_prompt import SELECTOR_AGENT_PROMPT
from trae_agent.utils.config import SelectorAgentConfig


SelectorAgentToolNames = [
    "str_replace_based_edit_tool",
    "bash",
]


class CandidatePatch:
    def __init__(self, id: int, patch: str, cleaned_patch: str, is_success_regression: bool, is_success_patch: bool):
        self.id: int = id
        self.patch: str = patch
        self.cleaned_patch: str = cleaned_patch
        self.is_success_regression: bool = is_success_regression
        self.is_success_patch: bool = is_success_patch
        self.final_patch: str | None = None

def remove_comments_from_line(line: str) -> str:
    try:
        tokens = tokenize.generate_tokens(io.StringIO(line).readline)
        result_parts: list[str] = []
        prev_end = (0, 0)

        for tok_type, tok_str, tok_start, tok_end, _ in tokens:
            if tok_type == tokenize.COMMENT:
                break
            (srow, scol) = tok_start
            if srow == 1 and scol > prev_end[1]:
                result_parts.append(line[prev_end[1]:scol])
            result_parts.append(tok_str)
            prev_end = tok_end

        return ''.join(result_parts).rstrip()
    except tokenize.TokenError:
        if '#' in line:
            return line.split('#', 1)[0].rstrip()
        return line

def clean_patch(ori_patch_text: str):
    # in case ori_patch_text has unexpected trailing newline characters
    # processed_ori_patch_text = ""
    # previous_line = None
    # for line in ori_patch_text.split('\n'):
    #     if previous_line is None:
    #         previous_line = line
    #         continue
    #     elif previous_line.strip() == '' and "diff --git" in line:
    #         previous_line = line
    #         continue
    #     else:
    #         processed_ori_patch_text = processed_ori_patch_text + previous_line + "\n"
    #     previous_line = line
    # if previous_line:
    #     processed_ori_patch_text = processed_ori_patch_text + previous_line

    processed_ori_patch_text = ori_patch_text
    patch = PatchSet(processed_ori_patch_text)
    extracted_lines: list[str] = []
    delete_lines: list[str] = []
    add_lines: list[str] = []
    for patched_file in patch:
        for hunk in patched_file:
            for line in hunk:
                if line.is_added:
                    content = line.value.lstrip('+')
                    if content.strip() and not re.match(r'^\s*#', content):
                        content = remove_comments_from_line(content.rstrip())
                        extracted_lines.append('+' + content)
                        add_lines.append(content)
                elif line.is_removed:
                    content = line.value.lstrip('-')
                    if content.strip() and not re.match(r'^\s*#', content):
                        content = remove_comments_from_line(content.rstrip())
                        extracted_lines.append('-' + content)
                        delete_lines.append(content)
    new_patch_text = '\n'.join(extracted_lines)

    new_patch_text = re.sub(r'\s+', '', new_patch_text)

    return new_patch_text


class SelectorAgent(BaseAgent):
    """Path selection Agent"""

    def __init__(self, selector_agent_config: SelectorAgentConfig):
        """Initialise SelectorAgent"""
        super().__init__(agent_config=selector_agent_config)
        self.project_path: str = ""

    def get_system_prompt(self, num_candidates: int) -> str:
        """Get the system prompt for the Selector Agent"""
        return SELECTOR_AGENT_PROMPT.format(num_candidates=num_candidates)

    @override
    def new_task(
        self,
        task: str,
        extra_args: dict[str, str] | None = None,
        tool_names: list[str] | None = None,
    ):
        """Create a new task."""
        self._task: str = task

        if tool_names is None and len(self.tools) == 0:
            tool_names = SelectorAgentToolNames

            provider = self._model_config.model_provider.provider
            self._tools : list[Tool] = [
                tools_registry[tool_name](model_provider=provider) for tool_name in tool_names
            ]

        self._tool_caller: ToolExecutor = ToolExecutor(self._tools)

        if not extra_args:
            raise AgentError("No extra arguments provided for Selector Agent.")
        if "project_path" not in extra_args:
            raise AgentError("No project path provided for Selector Agent.")
        if "problem_statement" not in extra_args:
            raise AgentError("No problem statement provided for Selector Agent.")
        if "candidate_record" not in extra_args:
            raise AgentError("No candidate patches provided for Selector Agent.")

        self.project_path = extra_args["project_path"]
        self.problem_statement: str = extra_args["problem_statement"]
        candidate_record: dict[str, list[Any]] = json.loads(extra_args["candidate_record"])

        self.patch_candidates: list[CandidatePatch] = []
        for idx in range(len(candidate_record['patches'])):
            if candidate_record['patches'][idx].strip() == '':
                continue
            cleaned_patch = clean_patch(candidate_record['patches'][idx])
            is_success_regression = len(candidate_record['regressions'][idx]) == 0
            self.patch_candidates.append(CandidatePatch(idx, candidate_record['patches'][idx], cleaned_patch, is_success_regression, bool(candidate_record['success_id'][idx])))


        self._initial_messages: list[LLMMessage] = []
        self._initial_messages.append(
            LLMMessage(
                role="system",
                content=self.get_system_prompt(len(self.patch_candidates)),
            )
        )

        user_message = f"\n[Codebase path]:\n{self.project_path}\n\n[Github issue description]:\n```\n{self.problem_statement}\n```\n\n[Candidate Patches]:"
        for idx in range(len(self.patch_candidates)):
            user_message += f"\nPatch-{idx+1}:\n```\n{self.patch_candidates[idx].patch}\n```"
        self._initial_messages.append(
            LLMMessage(
                role="user",
                content=user_message,
            )
        )

        # If trajectory recorder is set, start recording
        if self._trajectory_recorder:
            self._trajectory_recorder.start_recording(
                task=task,
                provider=self._llm_client.provider.value,
                model=self._model_config.model,
                max_steps=self._max_steps,
            )
    
    @override
    async def execute_task(self) -> AgentExecution:
        """Execute the task and finalize trajectory recording."""
        execution = await super().execute_task()

        # Finalize trajectory recording if recorder is available
        if self._trajectory_recorder:
            self._trajectory_recorder.finalize_recording(
                success=execution.success, final_result=execution.final_result
            )

        return execution

    @override
    def reflect_on_result(self, tool_results: list[ToolResult]) -> str | None:
        return None

    @override
    def llm_indicates_task_completed(self, llm_response: LLMResponse) -> bool:
        """Check if the LLM indicates that the task is completed."""
        match = re.search(r'(?:###\s*)?Status:\s*(success|succeed|successfully|successful)\s*\n\s*(?:###\s*)?Result:', llm_response.content)
        if match:
            return True
        return False

    @override
    def _is_task_completed(self, llm_response: LLMResponse) -> bool:
        match = re.search(r'(?:###\s*)?Status:\s*(success|succeed|successfully|successful)\s*\n\s*(?:###\s*)?Result:', llm_response.content)

        if match:
            match = re.search(r'(?:###\s*)?Result:\s*(.+?)\s*(?:###\s*)?Analysis:', llm_response.content)
            if match:
                result = match.group(1).strip().split('Patch-')[-1]
                if result in [str(_+1) for _ in range(len(self.patch_candidates))]:
                    self.final_id: int = self.patch_candidates[int(result)-1].id
                    self.final_patch: str = self.patch_candidates[int(result)-1].patch
                else:
                    self.final_id = self.patch_candidates[0].id
                    self.final_patch = self.patch_candidates[0].patch

                return True
            else:
                return False
        return False

    @override
    def task_incomplete_message(self) -> str:
        return "ERROR! The task is incomplete."

    @override
    async def cleanup_mcp_clients(self) -> None:
        """Clean up all MCP clients to prevent async context leaks."""
        pass

    @override
    async def initialise_mcp(self) -> None:
        """Initialise MCP clients. Override in subclasses that use MCP."""
        pass