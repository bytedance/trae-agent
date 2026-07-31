# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Tests for TrajectoryRecorder batch writing functionality."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from trae_agent.utils.trajectory_recorder import TrajectoryRecorder


class TestTrajectoryRecorderBuffering:
    """Test batch writing and buffering functionality."""

    def test_default_buffer_size(self):
        """Test that default buffer_size is 10."""
        with tempfile.TemporaryDirectory() as tmpdir:
            recorder = TrajectoryRecorder(f"{tmpdir}/test.json")
            assert recorder.buffer_size == 10
            assert recorder._pending_writes == 0

    def test_custom_buffer_size(self):
        """Test custom buffer_size parameter."""
        with tempfile.TemporaryDirectory() as tmpdir:
            recorder = TrajectoryRecorder(f"{tmpdir}/test.json", buffer_size=5)
            assert recorder.buffer_size == 5

    def test_pending_writes_counter(self):
        """Test that _pending_writes increments on each interaction."""
        with tempfile.TemporaryDirectory() as tmpdir:
            recorder = TrajectoryRecorder(f"{tmpdir}/test.json", buffer_size=5)
            recorder.start_recording("test", "test_provider", "test_model", 10)

            # Mock LLM interaction
            messages = [MagicMock()]
            response = MagicMock()
            response.content = "test"
            response.model = "test_model"
            response.finish_reason = "stop"
            response.usage = MagicMock()
            response.usage.input_tokens = 10
            response.usage.output_tokens = 20
            response.tool_calls = None

            initial_pending = recorder._pending_writes
            recorder.record_llm_interaction(messages, response, "test", "model")
            assert recorder._pending_writes == initial_pending + 1

    def test_flush_writes_to_disk(self):
        """Test that flush() writes pending data to disk."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = f"{tmpdir}/test.json"
            recorder = TrajectoryRecorder(path, buffer_size=10)
            recorder.start_recording("test", "test_provider", "test_model", 10)

            # Add some interactions
            for i in range(3):
                messages = [MagicMock()]
                response = MagicMock()
                response.content = f"test {i}"
                response.model = "test_model"
                response.finish_reason = "stop"
                response.usage = MagicMock()
                response.usage.input_tokens = 10
                response.usage.output_tokens = 20
                response.tool_calls = None
                recorder.record_llm_interaction(messages, response, "test", "model")

            # Before flush, file may not have all data
            pending_before = recorder._pending_writes
            assert pending_before > 0

            # Flush should write to disk
            recorder.flush()
            assert recorder._pending_writes == 0

            # Verify file exists and contains data
            assert Path(path).exists()
            with open(path, "r") as f:
                data = json.load(f)
            assert len(data["llm_interactions"]) == 3

    def test_auto_flush_when_buffer_full(self):
        """Test automatic flush when buffer_size is reached."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = f"{tmpdir}/test.json"
            recorder = TrajectoryRecorder(path, buffer_size=3)
            recorder.start_recording("test", "test_provider", "test_model", 10)

            # Add interactions up to buffer size
            for i in range(3):
                messages = [MagicMock()]
                response = MagicMock()
                response.content = f"test {i}"
                response.model = "test_model"
                response.finish_reason = "stop"
                response.usage = MagicMock()
                response.usage.input_tokens = 10
                response.usage.output_tokens = 20
                response.tool_calls = None
                recorder.record_llm_interaction(messages, response, "test", "model")

            # After reaching buffer_size, should auto-flush
            assert recorder._pending_writes == 0

            # Verify file was written
            assert Path(path).exists()
            with open(path, "r") as f:
                data = json.load(f)
            assert len(data["llm_interactions"]) == 3

    def test_close_flushes_pending_writes(self):
        """Test that close() flushes pending writes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = f"{tmpdir}/test.json"
            recorder = TrajectoryRecorder(path, buffer_size=10)
            recorder.start_recording("test", "test_provider", "test_model", 10)

            # Add some interactions (less than buffer size)
            for i in range(2):
                messages = [MagicMock()]
                response = MagicMock()
                response.content = f"test {i}"
                response.model = "test_model"
                response.finish_reason = "stop"
                response.usage = MagicMock()
                response.usage.input_tokens = 10
                response.usage.output_tokens = 20
                response.tool_calls = None
                recorder.record_llm_interaction(messages, response, "test", "model")

            pending_before = recorder._pending_writes
            assert pending_before > 0

            # Close should flush
            recorder.close()
            assert recorder._pending_writes == 0

            # Verify file was written
            assert Path(path).exists()
            with open(path, "r") as f:
                data = json.load(f)
            assert len(data["llm_interactions"]) == 2

    def test_flush_no_pending_writes(self):
        """Test that flush() does nothing when no pending writes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            recorder = TrajectoryRecorder(f"{tmpdir}/test.json", buffer_size=10)
            recorder.start_recording("test", "test_provider", "test_model", 10)

            # No interactions added
            assert recorder._pending_writes == 0

            # Flush should not error
            with patch.object(recorder, "save_trajectory") as mock_save:
                recorder.flush()
                # save_trajectory should not be called when no pending writes
                mock_save.assert_not_called()
