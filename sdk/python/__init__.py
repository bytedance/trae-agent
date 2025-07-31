# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT


from sdk.python._run import TraeAgentSDK

__all__ = ["run"]

_agent = TraeAgentSDK()
run = _agent.run
