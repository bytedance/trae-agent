# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

# TODO: remove these annotations by defining fine-grained types
# pyright: reportExplicitAny=false
# pyright: reportArgumentType=false
# pyright: reportAny=false

"""Trajectory recording functionality for Trae Agent.

修复历史:
  P0-7  每步 save_trajectory 全量 json.dump + 同步 f.write,阻塞 agent
        event loop → 改为 thread-pool 异步写,合并到 finalize 时单次刷盘
  P1-13 update_lakeview 遍历 list 找 step,O(n) → 用 dict 索引,O(1)
"""

import json
import logging
import os
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any

from trae_agent.tools.base import ToolCall, ToolResult
from trae_agent.utils.llm_clients.llm_basics import LLMMessage, LLMResponse

logger = logging.getLogger(__name__)

# 单实例的轻量 thread pool,做异步写盘。daemon=True 不阻塞进程退出。
_write_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="traj-writer")


class TrajectoryRecorder:
    """Records trajectory data for agent execution and LLM interactions."""

    def __init__(self, trajectory_path: str | None = None, project_name: str | None = None):
        if trajectory_path is None:
            # Save trajectory to Desktop/trae-agent-outputs/<project>/trajectories/
            from trae_agent.utils.output_manager import get_output_dir
            output_dir = get_output_dir(project_name)
            traj_dir = output_dir / "trajectories"
            traj_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            trajectory_path = str(traj_dir / f"trajectory_{timestamp}.json")

        self.trajectory_path: Path = Path(trajectory_path).resolve()
        try:
            self.trajectory_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            logger.warning(
                "Failed to create trajectory directory %s; trajectories may not save.",
                self.trajectory_path.parent,
            )

        self.trajectory_data: dict[str, Any] = {
            "task": "",
            "start_time": "",
            "end_time": "",
            "provider": "",
            "model": "",
            "max_steps": 0,
            "llm_interactions": [],
            "agent_steps": [],
            "success": False,
            "final_result": None,
            "execution_time": 0.0,
        }
        # P1-13: 用 dict 索引替代 list 遍历
        self._agent_steps_by_num: dict[int, dict[str, Any]] = {}
        self._start_time: datetime | None = None
        # P1-7: 跟踪最近一次 _async_save 的 Future,让 _sync_save 可以等它完成
        self._pending_future: Future | None = None

    # -------- public API -----------------------------------------------------

    def start_recording(self, task: str, provider: str, model: str, max_steps: int) -> None:
        self._start_time = datetime.now()
        self.trajectory_data.update(
            {
                "task": task,
                "start_time": self._start_time.isoformat(),
                "provider": provider,
                "model": model,
                "max_steps": max_steps,
                "llm_interactions": [],
                "agent_steps": [],
            }
        )
        self._agent_steps_by_num.clear()
        self._async_save()

    def record_llm_interaction(
        self,
        messages: list[LLMMessage],
        response: LLMResponse,
        provider: str,
        model: str,
        tools: list[Any] | None = None,
    ) -> None:
        interaction = {
            "timestamp": datetime.now().isoformat(),
            "provider": provider,
            "model": model,
            "input_messages": [self._serialize_message(msg) for msg in messages],
            "response": {
                "content": response.content,
                "model": response.model,
                "finish_reason": response.finish_reason,
                "usage": {
                    "input_tokens": response.usage.input_tokens if response.usage else 0,
                    "output_tokens": response.usage.output_tokens if response.usage else 0,
                    "cache_creation_input_tokens": getattr(
                        response.usage, "cache_creation_input_tokens", None
                    )
                    if response.usage
                    else None,
                    "cache_read_input_tokens": getattr(
                        response.usage, "cache_read_input_tokens", None
                    )
                    if response.usage
                    else None,
                    "reasoning_tokens": getattr(response.usage, "reasoning_tokens", None)
                    if response.usage
                    else None,
                },
                "tool_calls": [self._serialize_tool_call(tc) for tc in response.tool_calls]
                if response.tool_calls
                else None,
            },
            "tools_available": [tool.name for tool in tools] if tools else None,
        }
        self.trajectory_data["llm_interactions"].append(interaction)
        self._async_save()

    def record_agent_step(
        self,
        step_number: int,
        state: str,
        llm_messages: list[LLMMessage] | None = None,
        llm_response: LLMResponse | None = None,
        tool_calls: list[ToolCall] | None = None,
        tool_results: list[ToolResult] | None = None,
        reflection: str | None = None,
        error: str | None = None,
    ) -> None:
        step_data = {
            "step_number": step_number,
            "timestamp": datetime.now().isoformat(),
            "state": state,
            "llm_messages": [self._serialize_message(msg) for msg in llm_messages]
            if llm_messages
            else None,
            "llm_response": {
                "content": llm_response.content,
                "model": llm_response.model,
                "finish_reason": llm_response.finish_reason,
                "usage": {
                    "input_tokens": llm_response.usage.input_tokens if llm_response.usage else None,
                    "output_tokens": llm_response.usage.output_tokens
                    if llm_response.usage
                    else None,
                }
                if llm_response.usage
                else None,
                "tool_calls": [self._serialize_tool_call(tc) for tc in llm_response.tool_calls]
                if llm_response.tool_calls
                else None,
            }
            if llm_response
            else None,
            "tool_calls": [self._serialize_tool_call(tc) for tc in tool_calls]
            if tool_calls
            else None,
            "tool_results": [self._serialize_tool_result(tr) for tr in tool_results]
            if tool_results
            else None,
            "reflection": reflection,
            "error": error,
        }
        self.trajectory_data["agent_steps"].append(step_data)
        self._agent_steps_by_num[step_number] = step_data  # P1-13
        self._async_save()

    def update_lakeview(self, step_number: int, lakeview_summary: str) -> None:
        """O(1) lookup (P1-13 修复)."""
        step = self._agent_steps_by_num.get(step_number)
        if step is None:
            logger.warning(
                "update_lakeview called for unknown step_number=%s", step_number
            )
            return
        step["lakeview_summary"] = lakeview_summary
        self._async_save()

    def finalize_recording(self, success: bool, final_result: str | None = None) -> None:
        end_time = datetime.now()
        self.trajectory_data.update(
            {
                "end_time": end_time.isoformat(),
                "success": success,
                "final_result": final_result,
                "execution_time": (end_time - self._start_time).total_seconds()
                if self._start_time
                else 0.0,
            }
        )
        # finalize 用同步写,确保数据落盘
        self._sync_save()

    # -------- save (P0-7 修复) -----------------------------------------------

    def _async_save(self) -> None:
        """异步写盘,不阻塞 agent 主循环。
        P0-7 修复:之前每步同步 json.dump(全量) 阻塞 event loop。
        改为丢进 thread pool,主路径立即返回。
        P1-7 修复:追踪 Future 对象而不是布尔标志 — finalize 同步写时
        必须先等所有 pending async save 完成,否则 async save 写的老快照
        会覆盖 finalize 的新快照。
        """
        if self._pending_future is not None and not self._pending_future.done():
            return  # 已有待写入的快照,跳过本次
        snapshot = self._snapshot()
        path = self.trajectory_path
        self._pending_future = _write_pool.submit(self._do_write, snapshot, path)

    def _sync_save(self) -> None:
        """finalize 时同步写,确保数据落盘再返回。

        P1-7 修复:先 drain 所有 pending async save,再写最终快照。否则
        最后一次 async save 还在写老快照,可能覆盖这里的最终快照。
        """
        if self._pending_future is not None:
            try:
                # 阻塞等异步写盘完成;10s 兜底超时,避免 finalize 卡死。
                self._pending_future.result(timeout=10.0)
            except Exception as e:
                logger.warning("Pending async save did not complete cleanly: %s", e)
            self._pending_future = None
        self._do_write(self._snapshot(), self.trajectory_path)

    def _snapshot(self) -> dict[str, Any]:
        """返回一个深拷贝快照,避免后台写盘与主路径 append 互相覆盖。"""
        return json.loads(json.dumps(self.trajectory_data, ensure_ascii=False))

    @staticmethod
    def _do_write(data: dict[str, Any], path: Path) -> None:
        """实际的磁盘写入。在 thread-pool worker 里跑。"""
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(path.suffix + ".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, path)  # atomic on POSIX
        except Exception as e:
            logger.warning("Failed to save trajectory to %s: %s", path, e)

    # 兼容旧 API
    def save_trajectory(self) -> None:
        self._sync_save()

    # -------- serialization helpers ------------------------------------------

    def _serialize_message(self, message: LLMMessage) -> dict[str, Any]:
        data: dict[str, Any] = {"role": message.role, "content": message.content}
        if message.tool_call:
            data["tool_call"] = self._serialize_tool_call(message.tool_call)
        if message.tool_result:
            data["tool_result"] = self._serialize_tool_result(message.tool_result)
        return data

    def _serialize_tool_call(self, tool_call: ToolCall) -> dict[str, Any]:
        return {
            "call_id": tool_call.call_id,
            "name": tool_call.name,
            "arguments": tool_call.arguments,
            "id": getattr(tool_call, "id", None),
        }

    def _serialize_tool_result(self, tool_result: ToolResult) -> dict[str, Any]:
        return {
            # P2-11 修复:之前用 `tool_result.call_call_id` 永远返回 AttributeError
            # (ToolResult dataclass 没有这个字段)。fallback 到 `call_id` 即可。
            "call_id": getattr(tool_result, "call_id", None),
            "success": tool_result.success,
            "result": tool_result.result,
            "error": tool_result.error,
            "id": getattr(tool_result, "id", None),
        }

    def get_trajectory_path(self) -> str:
        return str(self.trajectory_path)