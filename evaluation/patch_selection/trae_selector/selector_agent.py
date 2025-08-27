import re
import shlex

from trae_agent.tools import tools_registry
from trae_agent.tools.base import Tool, ToolResult
from trae_agent.utils.config import ModelConfig
from trae_agent.utils.llm_clients.llm_basics import LLMMessage, LLMResponse
from trae_agent.utils.llm_clients.llm_client import LLMClient
from trae_agent.utils.trajectory_recorder import TrajectoryRecorder

from .sandbox import Sandbox


class CandidatePatch:
    def __init__(self, id, patch, cleaned_patch, is_success_regression, is_success_patch):
        self.id = id
        self.patch = patch
        self.cleaned_patch = cleaned_patch
        self.is_success_regression = is_success_regression
        self.is_success_patch = is_success_patch


def build_system_prompt(candidate_length: int) -> str:
    init_prompt = f"""\
# ROLE: Act as an expert code evaluator. Given a codebase, an github issue and **{candidate_length} candidate patches** proposed by your colleagues, your responsibility is to **select the correct one** to solve the issue.

# WORK PROCESS:
You are given a software issue and multiple candidate patches. Your goal is to identify the patch that correctly resolves the issue.

Follow these steps methodically:

**1. Understand the Issue and Codebase**
Carefully read the issue description to comprehend the problem. You may need to examine the codebase for context, including:
    (1) Code referenced in the issue description;
    (2) The original code modified by each patch;
    (3) Unchanged parts of the same file;
    (4) Related files, functions, or modules that interact with the affected code.

**2. Analyze the Candidate Patches**
For each patch, analyze its logic and intended fix. Consider whether the changes align with the issue description and coding conventions.

**3. Validate Functionality (Optional but Recommended)**
If needed, write and run unit tests to evaluate the correctness and potential side effects of each patch.

**4. Select the Best Patch**
Choose the patch that best resolves the issue with minimal risk of introducing new problems.

# FINAL REPORT: If you have successfully selected the correct patch, submit your answer in the following format:
### Status: succeed
### Result: Patch-x
### Analysis: [Explain why Patch-x is correct.]

# IMPORTANT TIPS:
1. Never avoid making a selection.
2. Do not propose new patches.
3. There must be at least one correct patch.
"""
    return init_prompt


def parse_tool_response(answer: LLMResponse, finish_reason: str, sandbox_session):
    result: list[LLMMessage] = []
    print("finish_reason:", finish_reason)
    if answer.tool_calls and len(answer.tool_calls) > 0:
        for tool_call in answer.tool_calls:
            tool_call_id = tool_call.call_id
            tool_name = tool_call.name

            if tool_name == "str_replace_based_edit_tool":
                cmd = "cd /home/swe-bench/tools/ && /home/swe-bench/py312/bin/python3 execute_str_replace_editor.py"
            elif tool_name == "bash":
                cmd = (
                    "cd /home/swe-bench/tools/ && /home/swe-bench/py312/bin/python3 execute_bash.py"
                )
            else:
                tool_message = LLMMessage(
                    role="user",
                    content="The tool name you provided is not in the list. Please choose one from `str_replace_editor` or `bash`!",
                    tool_result=ToolResult(
                        call_id=tool_call_id,
                        name=tool_name,
                        success=False,
                        error="The tool name you provided is not in the list. Please choose one from `str_replace_editor` or `bash`!",
                    ),
                )
                result.append(tool_message)
                continue

            all_arguments_valid = True
            tool_arguments = tool_call.arguments
            for key in tool_arguments:
                if isinstance(tool_arguments[key], list):
                    try:
                        tool_arguments[key] = str([int(factor) for factor in tool_arguments[key]])
                        cmd += f" --{key} {shlex.quote(tool_arguments[key])}"
                    except Exception:
                        pass
                elif isinstance(tool_arguments[key], (int, bool)):
                    cmd += f" --{key} {tool_arguments[key]}"
                elif isinstance(tool_arguments[key], dict):
                    all_arguments_valid = False
                    break
                else:
                    cmd += f" --{key} {shlex.quote(tool_arguments[key])}"

            if not all_arguments_valid:
                print("Tool Call Status: -1")
                tool_message = LLMMessage(
                    role="user",
                    content="Failed call tool. One of the arguments is dict type, you need to check the definition the tool.",
                    tool_result=ToolResult(
                        call_id=tool_call_id,
                        name=tool_name,
                        success=False,
                        error="Failed call tool. One of the arguments is dict type, you need to check the definition the tool.",
                    ),
                )
                result.append(tool_message)
                continue

            cmd += " > /home/swe-bench/tools/log.out 2>&1"
            print(repr(cmd))
            _ = sandbox_session.execute(cmd)
            sandbox_res = sandbox_session.execute("cat /home/swe-bench/tools/log.out")
            status = ""
            status_line_index = -1
            sandbox_res_str_list = sandbox_res.split("\n")
            for index, line in enumerate(sandbox_res_str_list):
                if line.strip().startswith("Tool Call Status:"):
                    status = line
                    status_line_index = index
                    break
            if status_line_index != -1:
                sandbox_res_str_list.pop(status_line_index)
            res_content = "\n".join(sandbox_res_str_list)
            print(status)
            tool_message = LLMMessage(
                role="user",
                content=res_content,
                tool_result=ToolResult(
                    call_id=tool_call_id,
                    name=tool_name,
                    success=status != "Tool Call Status: -1",
                    result=res_content,
                    error=None if status != "Tool Call Status: -1" else res_content,
                ),
            )
            result.append(tool_message)

    return result


class SelectorAgent:
    def __init__(
        self,
        *,
        llm_config: ModelConfig,
        sandbox: Sandbox,
        project_path: str,
        issue_description: str,
        trajectory_file_name: str,
        candidate_list: list[CandidatePatch],
        max_turn: int = 50,
    ):
        self.llm_config = llm_config
        self.max_turn = max_turn
        self.sandbox = sandbox
        self.sandbox_session = self.sandbox.get_session()
        self.sandbox_session.execute("git reset --hard HEAD")
        self.initial_messages: list[LLMMessage] = []
        self.candidate_list: list[CandidatePatch] = candidate_list
        self.project_path: str = project_path
        self.issue_description: str = issue_description
        self.tools: list[Tool] = [
            tools_registry[tool_name](model_provider=llm_config.model_provider.provider)
            for tool_name in ["bash", "str_replace_based_edit_tool"]
        ]
        self.llm_client = LLMClient(llm_config)
        self.trajectory_recorder: TrajectoryRecorder = TrajectoryRecorder(trajectory_file_name)

        self.initial_messages.append(
            LLMMessage(role="system", content=build_system_prompt(len(candidate_list)))
        )
        user_prompt = f"\n[Codebase path]:\n{project_path}\n\n[Github issue description]:\n```\n{issue_description}\n```\n\n[Candidate Patches]:"
        for idx in range(0, len(candidate_list)):
            user_prompt += f"\nPatch-{idx + 1}:\n```\n{candidate_list[idx].patch}\n```"
        user_message = LLMMessage(role="user", content=user_prompt)
        self.initial_messages.append(user_message)

    def run(self):
        print(f"max_turn: {self.max_turn}")
        print(f"### User Prompt:\n{self.initial_messages[1].content}\n")

        turn = 0
        final_id, final_patch = self.candidate_list[0].id, self.candidate_list[0].patch
        messages = self.initial_messages
        while turn < self.max_turn:
            turn += 1
            llm_response = self.llm_client.chat(messages, self.llm_config, self.tools)
            self.trajectory_recorder.record_llm_interaction(
                messages,
                llm_response,
                self.llm_config.model_provider.provider,
                self.llm_config.model,
                self.tools,
            )
            answer_content = llm_response.content
            print(f"\n### Selector's Answer({turn})\n", answer_content)
            messages: list[LLMMessage] = []
            match = re.search(
                r"(?:###\s*)?Status:\s*(success|succeed|successfully|successful)\s*\n\s*(?:###\s*)?Result:",
                answer_content,
            )

            if match:
                print("Match-1:", match.group(1).strip())
                match = re.search(
                    r"(?:###\s*)?Result:\s*(.+?)\s*(?:###\s*)?Analysis:", answer_content
                )
                if match:
                    result = match.group(1).strip().split("Patch-")[-1]
                    print("Match-2:", result)
                    if result in [str(_ + 1) for _ in range(len(self.candidate_list))]:
                        final_id = self.candidate_list[int(result) - 1].id
                        final_patch = self.candidate_list[int(result) - 1].patch
                    else:
                        final_id = self.candidate_list[0].id
                        final_patch = self.candidate_list[0].patch
                    break
            else:
                messages += parse_tool_response(
                    llm_response, llm_response.finish_reason or "", self.sandbox_session
                )
                if messages[-1].content and " seconds. Partial output:" in messages[-1].content:
                    self.sandbox_session = self.sandbox.get_session()

            print(f"\n### System Response({turn})\n", messages)
        self.trajectory_recorder.finalize_recording(True, final_patch)
        self.sandbox_session.execute("git reset --hard HEAD")
        self.sandbox_session.close()

        return final_id, final_patch
