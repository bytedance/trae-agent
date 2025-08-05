# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Console factory for creating different types of CLI consoles."""

from trae_agent.utils.config import LakeviewConfig

from .cli_console import CLIConsole, ConsoleMode, ConsoleType
from .rich_console import RichCLIConsole
from .simple_console import SimpleCLIConsole


class ConsoleFactory:
    """Factory class for creating CLI console instances."""

    @staticmethod
    def create_console(
        console_type: ConsoleType,
        mode: ConsoleMode = ConsoleMode.RUN,
        lakeview_config: LakeviewConfig | None = None,
    ) -> CLIConsole:
        """Create a console instance based on type and mode.

        Args:
            console_type: Type of console to create (SIMPLE or RICH)
            mode: Console operation mode (RUN or INTERACTIVE)
            config: Configuration object

        Returns:
            CLIConsole instance

        Raises:
            ValueError: If console_type is not supported
        """

        if console_type == ConsoleType.SIMPLE:
            return SimpleCLIConsole(mode=mode, lakeview_config=lakeview_config)
        elif console_type == ConsoleType.RICH:
            return RichCLIConsole(mode=mode, lakeview_config=lakeview_config)

    @staticmethod
    def get_recommended_console_type(mode: ConsoleMode) -> ConsoleType:
        """Get the recommended console type for a given mode.

        Args:
            mode: Console operation mode

        Returns:
            Recommended console type
        """
        # Rich console is ideal for interactive mode
        if mode == ConsoleMode.INTERACTIVE:
            return ConsoleType.RICH
        # Simple console works well for run mode
        else:
            return ConsoleType.SIMPLE
