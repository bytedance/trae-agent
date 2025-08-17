"""Tests for metrics endpoints."""

import pytest
from httpx import AsyncClient


class TestMetricsEndpoints:
    """Test metrics and monitoring endpoints."""

    async def test_metrics_endpoint_format(self, client: AsyncClient) -> None:
        """Test that metrics endpoint returns properly formatted Prometheus metrics."""
        # Make some requests to generate metrics
        await client.get("/api/health")
        await client.post("/api/echo/", json={"message": "test"})

        # Get metrics
        response = await client.get("/api/metrics")

        assert response.status_code == 200
        assert response.headers["content-type"] == "text/plain; version=0.0.4; charset=utf-8"

        metrics_text = response.text

        # Verify essential metrics are present
        assert "http_requests_total" in metrics_text
        assert "http_request_duration_seconds" in metrics_text
        assert "system_cpu_usage_percent" in metrics_text
        assert "system_memory_usage_bytes" in metrics_text
        assert "process_memory_bytes" in metrics_text

    async def test_metrics_content_structure(self, client: AsyncClient) -> None:
        """Test that metrics contain proper Prometheus format structure."""
        # Generate some metrics
        await client.get("/api/health")
        response = await client.get("/api/metrics")

        metrics_text = response.text
        lines = metrics_text.split("\n")

        # Check for HELP and TYPE comments
        help_lines = [line for line in lines if line.startswith("# HELP")]
        type_lines = [line for line in lines if line.startswith("# TYPE")]

        assert len(help_lines) > 0, "Should have HELP comments"
        assert len(type_lines) > 0, "Should have TYPE comments"

        # Check for actual metric values
        metric_lines = [line for line in lines if line and not line.startswith("#")]
        assert len(metric_lines) > 0, "Should have actual metric values"

    async def test_http_request_metrics(self, client: AsyncClient) -> None:
        """Test that HTTP request metrics are properly tracked."""
        # Make a request to generate metrics
        await client.get("/api/health")

        # Get metrics
        response = await client.get("/api/metrics")
        metrics_text = response.text

        # Should track the health endpoint request
        assert 'http_requests_total{endpoint="/api/health",method="GET",status_code="200"}' in metrics_text

        # Should have duration metrics
        assert 'http_request_duration_seconds_bucket{endpoint="/api/health"' in metrics_text

    async def test_system_metrics_present(self, client: AsyncClient) -> None:
        """Test that system metrics are collected and exposed."""
        response = await client.get("/api/metrics")
        metrics_text = response.text

        # System CPU metrics
        assert "system_cpu_usage_percent" in metrics_text

        # Memory metrics with labels
        assert 'system_memory_usage_bytes{type="used"}' in metrics_text
        assert 'system_memory_usage_bytes{type="available"}' in metrics_text
        assert 'system_memory_usage_bytes{type="total"}' in metrics_text

        # Disk metrics with labels
        assert 'system_disk_usage_bytes{device="root",type="used"}' in metrics_text
        assert 'system_disk_usage_bytes{device="root",type="free"}' in metrics_text
        assert 'system_disk_usage_bytes{device="root",type="total"}' in metrics_text

        # Process memory metrics
        assert 'process_memory_bytes{type="rss"}' in metrics_text
        assert 'process_memory_bytes{type="vms"}' in metrics_text

    async def test_metrics_endpoint_not_tracked(self, client: AsyncClient) -> None:
        """Test that the metrics endpoint itself is not tracked in metrics."""
        # Make multiple requests to metrics endpoint
        for _ in range(3):
            await client.get("/api/metrics")

        response = await client.get("/api/metrics")
        metrics_text = response.text

        # The metrics endpoint itself should not appear in HTTP request metrics
        assert 'endpoint="/api/metrics"' not in metrics_text

    async def test_health_endpoint_basic(self, client: AsyncClient) -> None:
        """Test the basic health endpoint."""
        response = await client.get("/api/health")

        assert response.status_code == 200
        data = response.json()

        # Check basic structure (updated for desktop deployment)
        assert "status" in data
        assert data["status"] == "healthy"
        assert "timestamp" in data
        assert "system" in data
        assert "storage" in data

    async def test_monitoring_health_endpoint_detailed(
        self,
        client: AsyncClient,
    ) -> None:
        """Test the enhanced monitoring health endpoint with system information."""
        response = await client.get("/api/health")

        assert response.status_code == 200
        data = response.json()

        # Updated for desktop deployment with enhanced health info
        assert data["status"] == "healthy"
        assert "timestamp" in data
        assert "system" in data
        assert "storage" in data

        # Check storage monitoring for desktop deployment
        storage = data["storage"]
        assert "data_dir" in storage
        assert "sqlite_db" in storage

    async def test_readiness_and_liveness_endpoints(self, client: AsyncClient) -> None:
        """Test Kubernetes readiness and liveness probes."""
        # Test readiness
        readiness_response = await client.get("/api/readiness")
        assert readiness_response.status_code == 200
        assert readiness_response.json() == {"status": "ready"}

        # Test liveness
        liveness_response = await client.get("/api/liveness")
        assert liveness_response.status_code == 200
        assert liveness_response.json() == {"status": "alive"}

    async def test_multiple_requests_increment_counters(
        self,
        client: AsyncClient,
    ) -> None:
        """Test that multiple requests properly increment counter metrics."""
        # Get initial count
        initial_response = await client.get("/api/metrics")
        initial_metrics = initial_response.text

        initial_count = 0
        for line in initial_metrics.split("\n"):
            if 'http_requests_total{endpoint="/api/health"' in line and 'status_code="200"' in line:
                initial_count = float(line.split()[-1])
                break

        # Make multiple requests
        for _i in range(3):
            await client.get("/api/health")

        # Get final count
        response = await client.get("/api/metrics")
        metrics_text = response.text

        # Find the counter line for health endpoint
        for line in metrics_text.split("\n"):
            if 'http_requests_total{endpoint="/api/health"' in line and 'status_code="200"' in line:
                # Extract the count value (should be initial + 3)
                final_count = float(line.split()[-1])
                expected_count = initial_count + 3.0
                assert final_count == expected_count, f"Expected {expected_count} requests, got {final_count}"
                break
        else:
            pytest.fail("Could not find http_requests_total metric for /api/health")
