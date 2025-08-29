# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Project rules utilities for loading and parsing Project_rules.md files."""

import os
from pathlib import Path
from typing import Optional


class ProjectRulesLoader:
    """Utility class for loading and parsing project rules and user rules files."""

    @staticmethod
    def load_project_rules(project_path: str, rules_file_path: str = "Project_rules.md") -> Optional[str]:
        """Load Project_rules.md file content from project directory.
        Args:
            project_path: Project root directory path
            rules_file_path: Relative path to rules file, defaults to "Project_rules.md"
        Returns:
            Rules file content string, or None if file doesn't exist or read fails
        """
        try:
            if os.path.isabs(rules_file_path):
                full_path = rules_file_path
            else:
                full_path = os.path.join(project_path, rules_file_path)
            
            if not os.path.exists(full_path):
                return None
            
            project_path_resolved = os.path.abspath(project_path)
            full_path_resolved = os.path.abspath(full_path)
            if not full_path_resolved.startswith(project_path_resolved):
                return None
            
            with open(full_path, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                
            return content if content else None
            
        except (OSError, IOError, UnicodeDecodeError):
            return None
    
    @staticmethod
    def load_user_rules(project_path: str, rules_file_path: str = "user_rules.md") -> Optional[str]:
        """Load user_rules.md file content from project directory.
        Args:
            project_path: Project root directory path
            rules_file_path: Relative path to user rules file, defaults to "user_rules.md"
        Returns:
            User rules file content string, or None if file doesn't exist or read fails
        """
        return ProjectRulesLoader.load_project_rules(project_path, rules_file_path)
    
    @staticmethod
    def load_combined_rules(project_path: str, project_rules_path: str = "Project_rules.md", 
                          user_rules_path: str = "user_rules.md", 
                          project_rules_enabled: bool = True,
                          user_rules_enabled: bool = True) -> str:
        """Load and combine project rules and user rules.
        Args:
            project_path: Project root directory path
            project_rules_path: Relative path to project rules file
            user_rules_path: Relative path to user rules file
            project_rules_enabled: Whether to load project rules
            user_rules_enabled: Whether to load user rules
        Returns:
            Combined formatted rules content
        """
        combined_content = ""
        
        # Load project rules
        if project_rules_enabled:
            project_content = ProjectRulesLoader.load_project_rules(project_path, project_rules_path)
            if project_content:
                combined_content += ProjectRulesLoader.format_rules_for_prompt(
                    project_content, "PROJECT-SPECIFIC RULES"
                )
        
        # Load user rules
        if user_rules_enabled:
            user_content = ProjectRulesLoader.load_user_rules(project_path, user_rules_path)
            if user_content:
                combined_content += ProjectRulesLoader.format_rules_for_prompt(
                    user_content, "USER-SPECIFIC RULES"
                )
        
        return combined_content
    
    @staticmethod
    def format_rules_for_prompt(rules_content: str, section_title: str = "PROJECT-SPECIFIC RULES") -> str:
        """Format rules content for adding to system prompt.
        Args:
            rules_content: Original rules file content
            section_title: Title for the rules section
        Returns:
            Formatted rules content
        """
        if not rules_content:
            return ""
        
        formatted_rules = f"""
# {section_title}
The following are {section_title.lower()} and guidelines that you MUST follow:
{rules_content}
# END OF {section_title}
"""
        return formatted_rules
    
    @staticmethod
    def validate_rules_file(file_path: str) -> bool:
        """Validate if rules file is valid.
        Args:
            file_path: Rules file path
        Returns:
            Whether the file is valid
        """
        try:
            if not os.path.exists(file_path):
                return False
            
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            if len(content) > 10000:
                return False

            try:
                content.encode('utf-8')
                for char in content:
                    if ord(char) < 32 and char not in '\n\r\t':
                        return False
                        
            except UnicodeEncodeError:
                return False
            return True
        except (OSError, IOError, UnicodeDecodeError):
            return False