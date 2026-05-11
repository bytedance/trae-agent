# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Long-term memory extraction and visualization for trae-agent."""

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from trae_agent.agent.agent_basics import AgentStep
from trae_agent.utils.config import LongTermMemoryConfig
from trae_agent.utils.llm_clients.llm_basics import LLMMessage
from trae_agent.utils.llm_clients.llm_client import LLMClient

MEMORY_EXTRACTOR_PROMPT = """
Given the following execution steps of an AI agent solving a task, extract the key "problem" and "conclusion" for each logical group of steps.

A "problem" describes what the agent was trying to solve or figure out.
A "conclusion" describes what the agent discovered, decided, or accomplished.

Group consecutive steps that address the same sub-problem into a single section.
Number the sections sequentially using the step range (e.g., steps="1-3", steps="4-5").

Output format — repeat this block for each group:
<group steps="N-M">
<problem>...</problem>
<conclusion>...</conclusion>
</group>

Be concise. Each problem and conclusion should be at most 2 sentences.
Focus on facts: file paths, function names, root causes, specific changes made.
Do not include any other commentary.
"""

group_re = re.compile(r'<group steps="([^"]+)">\s*<problem>(.*?)</problem>\s*<conclusion>(.*?)</conclusion>\s*</group>', re.DOTALL)


@dataclass
class MemorySection:
    """A single section of extracted memory."""

    step_range: str  # e.g. "1-3"
    problem: str
    conclusion: str

    def heading(self) -> str:
        return f"Step {self.step_range}"


@dataclass
class MemoryDocument:
    """A complete memory document extracted from agent execution."""

    task_name: str
    session_id: str = ""
    sections: list[MemorySection] = field(default_factory=list)
    created_at: str = ""
    step_count: int = 0

    def to_markdown(self) -> str:
        """Render the full document as Markdown."""
        lines = [f"# Long-term Memory — Task: {self.task_name}", ""]
        if self.session_id:
            lines.append(f"Session: {self.session_id}")
            lines.append("")
        if self.created_at:
            lines.append(f"Generated: {self.created_at} | Steps: {self.step_count}")
            lines.append("")
        for section in self.sections:
            lines.append(f"## {section.heading()}")
            lines.append(f"**Problem**: {section.problem}")
            lines.append(f"**Conclusion**: {section.conclusion}")
            lines.append("")
        return "\n".join(lines)

    @classmethod
    def from_markdown(cls, markdown_text: str) -> "MemoryDocument":
        """Parse a Markdown file back into a MemoryDocument."""
        task_match = re.search(r"# Long-term Memory — Task: (.+)", markdown_text)
        task_name = task_match.group(1).strip() if task_match else "Unknown"

        session_match = re.search(r"^Session: (.+)$", markdown_text, re.MULTILINE)
        session_id = session_match.group(1).strip() if session_match else ""

        sections: list[MemorySection] = []
        # Match ## Step N-M blocks
        section_pattern = re.compile(
            r"## Step ([^\n]+)\n\*\*Problem\*\*: ([^\n]+)\n\*\*Conclusion\*\*: ([^\n]+)", re.DOTALL
        )
        for match in section_pattern.finditer(markdown_text):
            sections.append(
                MemorySection(
                    step_range=match.group(1).strip(),
                    problem=match.group(2).strip(),
                    conclusion=match.group(3).strip(),
                )
            )

        return cls(task_name=task_name, session_id=session_id, sections=sections)


class LongTermMemory:
    """Long-term memory extraction and management system."""

    def __init__(self, config: LongTermMemoryConfig, fallback_model):
        from trae_agent.utils.config import ModelConfig

        model = config.model if config.model else fallback_model
        self._llm_client = LLMClient(model)
        self._model_config: ModelConfig = model
        self._config = config
        self._sections: list[MemorySection] = []
        self._preloaded_sections: list[MemorySection] = []
        self._session_id: str = ""
        self._output_dir = Path(config.output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._task_name: str = ""

    def set_task(self, task_name: str):
        """Called at task start."""
        self._task_name = task_name
        self._sections = []

    def set_session_id(self, session_id: str) -> None:
        """Set the session ID for this memory instance."""
        self._session_id = session_id

    def load_memory(self, path: str) -> None:
        """Load memory sections from a previously saved .md file.

        The loaded sections are stored in _preloaded_sections and persist
        across set_task() calls, providing cross-session context.
        """
        filepath = Path(path)
        if not filepath.exists():
            raise FileNotFoundError(f"Memory file not found: {path}")
        markdown_text = filepath.read_text(encoding="utf-8")
        doc = MemoryDocument.from_markdown(markdown_text)
        if doc.sections:
            self._preloaded_sections = doc.sections

    def _agent_step_str(self, agent_step: AgentStep) -> str | None:
        """Convert an AgentStep to a string for the LLM."""
        if agent_step.llm_response is None:
            return None

        content = agent_step.llm_response.content.strip()

        tool_calls_content = ""
        if agent_step.llm_response.tool_calls is not None:
            tool_calls_content = "\n".join(
                f"[`{tool_call.name}`] `{tool_call.arguments}`"
                for tool_call in agent_step.llm_response.tool_calls
            )
            tool_calls_content = tool_calls_content.strip()
            content = f"{content}\n\nTool calls:\n{tool_calls_content}"

        if agent_step.tool_results:
            results_content = "\n".join(
                f"[{r.name}] success={r.success}: {r.result or r.error or ''}"
                for r in agent_step.tool_results
                if r
            )
            if results_content:
                content = f"{content}\n\nTool results:\n{results_content}"

        return content

    async def extract_memory(self, steps: list[AgentStep]) -> MemoryDocument | None:
        """Extract memory from agent steps using LLM."""
        # Build step text
        step_texts: list[str] = []
        for step in steps:
            step_str = self._agent_step_str(step)
            if step_str:
                step_texts.append(f"<step id=\"{step.step_number}\">\n{step_str}\n</step>")

        if not step_texts:
            return None

        steps_formatted = "\n\n".join(step_texts)

        # Truncate if too long
        if len(steps_formatted) > 300_000:
            steps_formatted = steps_formatted[-300_000:]

        llm_messages = [
            LLMMessage(
                role="user",
                content=f"Below are the execution steps of an AI agent:\n\n{steps_formatted}",
            ),
            LLMMessage(role="assistant", content="I understand."),
            LLMMessage(role="user", content=MEMORY_EXTRACTOR_PROMPT),
        ]

        self._model_config.temperature = 0.1
        llm_response = self._llm_client.chat(
            model_config=self._model_config,
            messages=llm_messages,
            reuse_history=False,
        )

        content = llm_response.content.strip()

        # Retry if parsing fails
        retry = 0
        while retry < 10 and not group_re.search(content):
            retry += 1
            llm_response = self._llm_client.chat(
                model_config=self._model_config,
                messages=llm_messages,
                reuse_history=False,
            )
            content = llm_response.content.strip()

        # Parse response
        sections: list[MemorySection] = []
        for match in group_re.finditer(content):
            sections.append(
                MemorySection(
                    step_range=match.group(1).strip(),
                    problem=match.group(2).strip(),
                    conclusion=match.group(3).strip(),
                )
            )

        if not sections:
            return None

        self._sections = sections

        return MemoryDocument(
            task_name=self._task_name,
            sections=sections,
            created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            step_count=len(steps),
        )

    async def extract_and_save(self, steps: list[AgentStep]) -> str | None:
        """Extract memory and save to Markdown file. Returns the file path."""
        doc = await self.extract_memory(steps)
        if doc is None:
            return None
        self._sections = doc.sections
        doc.session_id = self._session_id
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"memory_{timestamp}.md"
        filepath = self._output_dir / filename
        filepath.write_text(doc.to_markdown(), encoding="utf-8")
        self._update_index(str(filepath))
        return str(filepath)

    def build_memory_message(self) -> LLMMessage | None:
        """Build an LLMMessage containing the compressed memory summary."""
        all_sections = self._preloaded_sections + self._sections
        if not all_sections:
            return None
        content = "# Long-term Memory Summary\n\n"
        content += "The following is a compressed summary of the agent's previous execution. "
        content += "Use this as context instead of the full conversation history.\n\n"
        if self._preloaded_sections:
            content += "## Context from Previous Sessions\n\n"
            for section in self._preloaded_sections:
                content += f"### {section.heading()}\n"
                content += f"**Problem**: {section.problem}\n"
                content += f"**Conclusion**: {section.conclusion}\n\n"
        if self._sections:
            content += "## Context from Current Session\n\n"
            for section in self._sections:
                content += f"### {section.heading()}\n"
                content += f"**Problem**: {section.problem}\n"
                content += f"**Conclusion**: {section.conclusion}\n\n"
        return LLMMessage(role="user", content=content)

    # --- Memory index management ---

    def _index_path(self) -> Path:
        """Return the path to the memory index file."""
        return self._output_dir / "index.json"

    def _load_index(self) -> dict:
        """Load the memory index from disk, or return empty structure."""
        path = self._index_path()
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return {"version": 1, "sessions": {}}

    def _save_index(self, index: dict) -> None:
        """Save the memory index to disk."""
        path = self._index_path()
        path.write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")

    def _update_index(self, memory_file_path: str) -> None:
        """Update the index with the current session's memory file."""
        if not self._session_id:
            return
        index = self._load_index()
        sessions = index["sessions"]
        if self._session_id not in sessions:
            sessions[self._session_id] = {
                "task_name": self._task_name,
                "memory_files": [memory_file_path],
                "trajectory_file": "",
                "created_at": datetime.now().isoformat(),
            }
        else:
            entry = sessions[self._session_id]
            if memory_file_path not in entry["memory_files"]:
                entry["memory_files"].append(memory_file_path)
        self._save_index(index)

    def set_trajectory_file(self, trajectory_file: str) -> None:
        """Record the trajectory file path for this session in the index."""
        if not self._session_id:
            return
        index = self._load_index()
        sessions = index["sessions"]
        if self._session_id in sessions:
            sessions[self._session_id]["trajectory_file"] = trajectory_file
        self._save_index(index)

    @classmethod
    def query_index(cls, index_path: str) -> dict:
        """Read and return the memory index. Used by CLI commands."""
        path = Path(index_path)
        if not path.exists():
            return {"version": 1, "sessions": {}}
        return json.loads(path.read_text(encoding="utf-8"))
