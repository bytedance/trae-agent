# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

# pyright: reportExplicitAny=false
# pyright: reportArgumentType=false
# pyright: reportAny=false

"""OpenTelemetry-based tracing for Trae Agent.

This module provides an alternative trajectory recorder that emits
OpenTelemetry spans instead of (or in addition to) writing JSON files.
It is designed to be a drop-in enhancement: when enabled, spans are
created for each LLM interaction and agent step, allowing integration
with any OTLP-compatible backend (Jaeger, Zipkin, Grafana Tempo, etc.).

Enable via environment variables:
  OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
  OTEL_SERVICE_NAME=trae-agent

Or programmatically by calling setup_otel_tracing() before agent execution.
"""

import os
from typing import Any

try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.sdk.resources import Resource, SERVICE_NAME

    _OTEL_AVAILABLE = True
except ImportError:
    _OTEL_AVAILABLE = False


def is_otel_available() -> bool:
    """Check if OpenTelemetry packages are installed."""
    return _OTEL_AVAILABLE


def setup_otel_tracing(
    service_name: str = "trae-agent",
    endpoint: str | None = None,
) -> "trace.Tracer | None":
    """Initialise OpenTelemetry tracing.

    Args:
        service_name: Logical service name shown in the tracing backend.
        endpoint: OTLP gRPC endpoint (e.g. ``http://localhost:4317``).
                  Falls back to the ``OTEL_EXPORTER_OTLP_ENDPOINT``
                  environment variable.

    Returns:
        A ``Tracer`` instance, or ``None`` if OpenTelemetry is not installed.
    """
    if not _OTEL_AVAILABLE:
        return None

    resource = Resource.create({SERVICE_NAME: service_name})
    provider = TracerProvider(resource=resource)

    # Use OTLP gRPC exporter if endpoint is available
    otlp_endpoint = endpoint or os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if otlp_endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

            exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
            provider.add_span_processor(BatchSpanProcessor(exporter))
        except ImportError:
            # Fallback: just record spans in memory (no export)
            pass

    trace.set_tracer_provider(provider)
    return trace.get_tracer("trae-agent")


class OTelTrajectoryRecorder:
    """Records agent trajectory as OpenTelemetry spans.

    Can be used alongside or instead of the JSON-based
    ``TrajectoryRecorder``.  Each agent run produces a root span;
    LLM interactions and tool calls become child spans.
    """

    def __init__(self, tracer: "trace.Tracer | None" = None):
        if not _OTEL_AVAILABLE:
            raise RuntimeError(
                "OpenTelemetry packages are not installed. "
                "Install with: uv add opentelemetry-api opentelemetry-sdk "
                "opentelemetry-exporter-otlp-proto-grpc"
            )
        self._tracer = tracer or trace.get_tracer("trae-agent")
        self._root_span: Any | None = None
        self._step_spans: dict[int, Any] = {}

    def start_recording(self, task: str, provider: str, model: str, max_steps: int) -> None:
        """Start the root span for an agent run."""
        self._root_span = self._tracer.start_span(
            "agent.run",
            attributes={
                "agent.task": task,
                "agent.provider": provider,
                "agent.model": model,
                "agent.max_steps": max_steps,
            },
        )

    def record_llm_interaction(
        self,
        messages: list[Any],
        response: Any,
        provider: str,
        model: str,
        tools: list[Any] | None = None,
    ) -> None:
        """Record an LLM call as a span under the current root span."""
        if not self._root_span:
            return

        ctx = trace.set_span_in_context(self._root_span)
        with self._tracer.start_as_current_span(
            "llm.call",
            context=ctx,
            attributes={
                "llm.provider": provider,
                "llm.model": model,
                "llm.input_message_count": len(messages),
                "llm.output_tokens": response.usage.output_tokens if response.usage else 0,
                "llm.input_tokens": response.usage.input_tokens if response.usage else 0,
                "llm.finish_reason": response.finish_reason or "",
                "llm.tool_call_count": len(response.tool_calls) if response.tool_calls else 0,
            },
        ):
            pass  # span auto-ends

    def record_agent_step(
        self,
        step_number: int,
        state: str,
        tool_calls: list[Any] | None = None,
        tool_results: list[Any] | None = None,
        error: str | None = None,
        **_kwargs: Any,
    ) -> None:
        """Record an agent step as a span."""
        if not self._root_span:
            return

        ctx = trace.set_span_in_context(self._root_span)
        attrs: dict[str, Any] = {
            "step.number": step_number,
            "step.state": state,
        }
        if tool_calls:
            attrs["step.tool_call_count"] = len(tool_calls)
            attrs["step.tool_names"] = [tc.name for tc in tool_calls]
        if error:
            attrs["step.error"] = error

        span = self._tracer.start_as_current_span("agent.step", context=ctx, attributes=attrs)
        self._step_spans[step_number] = span

    def finalize_recording(self, success: bool, final_result: str | None = None) -> None:
        """End the root span."""
        if self._root_span:
            self._root_span.set_attribute("agent.success", success)
            if final_result:
                self._root_span.set_attribute("agent.final_result", final_result[:2048])
            self._root_span.end()
