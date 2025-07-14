from ._run import TraeAgentSDK

__all__ = ["run"]

_agent = TraeAgentSDK()
run = _agent.run
