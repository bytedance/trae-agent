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


# Issue 8 修复: trajectory 文件此前没有任何大小保护 —— 长任务会把每步的完整
# LLM 历史 + 大段工具输出原样塞进 JSON,单文件可达数 GB,加载/导出极慢,甚至
# 撑爆磁盘。这里加两层保护(均可通过环境变量覆盖):
#   TRAJECTORY_MAX_FIELD_BYTES  单个字符串字段(text/result/error)的截断阈值,
#                               超过就保留首尾各一半并加 [truncated] 标记。
#   TRAJECTORY_MAX_INTERACTIONS llm_interactions 数组的硬上限,超过则丢弃最旧
#                               的(它们是冗余的累积历史,信息密度最低)。
_MAX_FIELD_BYTES = max(1024, int(os.environ.get("TRAJECTORY_MAX_FIELD_BYTES", str(50 * 1024))))
_MAX_INTERACTIONS = max(10, int(os.environ.get("TRAJECTORY_MAX_INTERACTIONS", "200")))


def _truncate_field(value: str | None) -> str | None:
    """Truncate a long string field in place to keep the trajectory file bounded.

    Keeps the head and tail so callers can still see the start/end of long
    tool outputs or model responses. Returns ``None`` unchanged.
    """
    if value is None:
        return None
    if not isinstance(value, str):
        return value
    if len(value.encode("utf-8", errors="replace")) <= _MAX_FIELD_BYTES:
        return value
    # 按字符数估算(UTF-8 下字节数 >= 字符数),取头尾各一半。
    half_chars = _MAX_FIELD_BYTES // 4
    original_len = len(value)
    head = value[:half_chars]
    tail = value[-half_chars:] if half_chars > 0 else ""
    marker = (
        f"\n[...truncated {original_len - len(head) - len(tail)} chars "
        f"/ set TRAJECTORY_MAX_FIELD_BYTES to enlarge...]\n"
    )
    return head + marker + tail


class TrajectoryRecorder:
    """Records trajectory data for agent execution and LLM interactions."""

    def __init__(self, trajectory_path: str | None = None):
        if trajectory_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            trajectory_path = f"trajectories/trajectory_{timestamp}.json"

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
                # Issue 8: 模型输出可能极长(尤其带长 tool_call 参数),截断保护。
                "content": _truncate_field(response.content),
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
        # Issue 8: 硬上限,超过则丢弃最旧的(信息密度最低的累积历史)。
        interactions = self.trajectory_data["llm_interactions"]
        if len(interactions) > _MAX_INTERACTIONS:
            self.trajectory_data["llm_interactions"] = interactions[-_MAX_INTERACTIONS:]
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
                "content": _truncate_field(llm_response.content),
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
        data: dict[str, Any] = {
            "role": message.role,
            "content": self._serialize_content(message.content),
        }
        if message.tool_call:
            data["tool_call"] = self._serialize_tool_call(message.tool_call)
        if message.tool_result:
            data["tool_result"] = self._serialize_tool_result(message.tool_result)
        return data

    @staticmethod
    def _serialize_content(content: Any) -> Any:
        """Serialize message content for the trajectory file.

        Multimodal content lists may carry base64 image data that would bloat
        the trajectory JSON to many MB. Keep the text parts, but replace each
        image part with a small redaction placeholder.
        """
        if not isinstance(content, list):
            return content
        parts: list[Any] = []
        for part in content:
            part_type = getattr(part, "type", None)
            if part_type is None and isinstance(part, dict):
                part_type = part.get("type")
            if part_type in ("image", "image_url"):
                media_type = getattr(part, "media_type", None)
                if media_type is None and isinstance(part, dict):
                    media_type = part.get("media_type")
                parts.append(
                    {
                        "type": "image",
                        "media_type": media_type,
                        "data": "[image data redacted from trajectory]",
                    }
                )
            elif part_type == "text" or hasattr(part, "text"):
                text = getattr(part, "text", None)
                if text is None and isinstance(part, dict):
                    text = part.get("text")
                parts.append({"type": "text", "text": _truncate_field(text)})
            else:
                parts.append(str(part))
        return parts

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
            # Issue 8: 截断超长结果,避免几 GB 的 trajectory 文件。
            "result": _truncate_field(tool_result.result),
            "error": _truncate_field(tool_result.error),
            "id": getattr(tool_result, "id", None),
        }

    def get_trajectory_path(self) -> str:
        return str(self.trajectory_path)