"""TaskIQ broker configuration with environment-based selection.

Following best practices:
- InMemoryBroker for tests (zero configuration, deterministic execution)
- ZeroMQBroker for everyday local/single-host production runs
- Clean upgrade path to distributed brokers (NATS/RabbitMQ) via environment flags

ZeroMQ benefits:
- Zero infrastructure dependencies (only needs pyzmq wheel)
- Out-of-process task execution when running TaskIQ workers
- Limitation: single worker process (use -w 1 when running workers)

Upgrade path:
- For serious multi-node deployments, TaskIQ officially recommends NATS or RabbitMQ
- Switch brokers via TRAE_API_TASKIQ_BROKER environment variable
- To ScheduledTask with cron="* * * * *" need to impliment taskiq.abc.schedule_source.ScheduleSource

Usage:
    # 1️⃣ Start the API
    uvicorn trae_api.core.application:get_app --reload

    # 2️⃣ Start a single TaskIQ worker in another shell
    taskiq worker trae_api.tasks.broker:broker --fs-discover -w 1

    # 3️⃣ Switch to distributed broker (when available)
    export TRAE_API_TASKIQ_BROKER=nats
    taskiq worker trae_api.tasks.broker:broker -w 4
"""

import taskiq_fastapi
from taskiq import AsyncBroker, InMemoryBroker, ZeroMQBroker

# Future distributed broker imports (uncomment when needed):
# from taskiq_nats import JetStreamBroker
# from taskiq_aio_pika import AioPikaBroker
# Redis result backend would be imported like this when available:
# from taskiq_redis import RedisAsyncResultBackend
from trae_api.core.config import settings
from trae_api.tasks.result_backends import SQLiteResultBackend


def create_broker() -> AsyncBroker:
    """
    Create broker based on environment and configuration.

    Broker selection logic:
    1. Unit-tests & CI: InMemoryBroker (zero config, deterministic)
    2. Local/single-host production: ZeroMQBroker (out-of-process, zero infrastructure)
    3. Multi-node production: Distributed brokers via environment override

    Returns:
        AsyncBroker: Configured broker instance

    Raises:
        ValueError: If unknown broker type is specified
    """
    # Detect if we're running in test environment:
    # 1. Explicit environment variable: TRAE_API_ENVIRONMENT=pytest
    # 2. Auto-detection: pytest in sys.modules (fallback when env var not set)
    import sys
    is_pytest_env = settings.environment.lower() == "pytest"
    is_pytest_detected = "pytest" in sys.modules and settings.taskiq_broker is None
    
    # 1. Unit-tests & CI - use InMemoryBroker with SQLite backend for testing
    if is_pytest_env or is_pytest_detected:
        broker = InMemoryBroker(await_inplace=True)  # Execute tasks synchronously for test assertions
        # Add SQLite result backend for integration testing
        return broker.with_result_backend(
            SQLiteResultBackend(str(settings.taskiq_db_path)),
        )

    # 2. Override via environment if explicitly specified
    # Default to 'default' for desktop deployment (InMemory + SQLite)
    chosen = (settings.taskiq_broker or "default").lower()

    if chosen in {"inmemory", "memory"}:
        return InMemoryBroker()

    if chosen in {"zmq", "zeromq"}:
        # ZeroMQBroker for everyday local/single-host production
        # Remember: use -w 1 when running workers to avoid duplicate executions
        # Uses SQLite result backend for local task status tracking
        return ZeroMQBroker(
            zmq_pub_host=settings.taskiq_zmq_pub_host,
            zmq_sub_host=settings.taskiq_zmq_sub_host,
        ).with_result_backend(
            SQLiteResultBackend(str(settings.taskiq_db_path)),
        )

    # 3. Future distributed broker support
    # TODO: TaskIQ officially recommends NATS or RabbitMQ for serious multi-node deployments
    # Uncomment and install appropriate packages when scaling beyond single host:

    # if chosen == "nats":
    #     import os
    #     nats_url = os.getenv("NATS_URL", "nats://127.0.0.1:4222")
    #     return JetStreamBroker(nats_url, queue="taskiq")

    # if chosen in {"pika", "rabbitmq"}:
    #     import os
    #     amqp_url = os.getenv("RABBITMQ_URL", "amqp://guest:guest@127.0.0.1/")
    #     return AioPikaBroker(amqp_url)

    # Default for desktop: InMemoryBroker with SQLite result backend
    # This provides the best of both worlds for local deployment:
    # - No external processes needed (InMemory execution)
    # - Persistent task result tracking (SQLite backend)
    return InMemoryBroker().with_result_backend(
        SQLiteResultBackend(str(settings.taskiq_db_path)),
    )


# Create broker instance using factory pattern
broker: AsyncBroker = create_broker()

# TODO: Add metrics middleware when TaskIQ context compatibility is resolved
# broker.add_middlewares(MetricsMiddleware())

# Initialize taskiq-fastapi integration
# Using string path to avoid circular imports (recommended by TaskIQ docs)
taskiq_fastapi.init(
    broker,
    "trae_api.core.application:get_app",
)
