# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Rules Manager for managing project_rules.md and user_rules.md files."""

import os
import re
from pathlib import Path
from typing import List, Optional, Dict, Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


class RulesManager:
    """Manager for project and user rules files."""
    
    def __init__(self, working_dir: Optional[str] = None):
        """Initialize the rules manager.
        
        Args:
            working_dir: Working directory path. If None, uses current directory.
        """
        self.working_dir = Path(working_dir) if working_dir else Path.cwd()
        self.project_rules_file = self.working_dir / "project_rules.md"
        self.user_rules_file = self.working_dir / "user_rules.md"
    
    def _ensure_file_exists(self, file_path: Path, file_type: str) -> None:
        """Ensure the rules file exists, create if not.
        
        Args:
            file_path: Path to the rules file
            file_type: Type of rules file (project or user)
        """
        if not file_path.exists():
            template_content = self._get_template_content(file_type)
            file_path.write_text(template_content, encoding='utf-8')
            console.print(f"[green]Created {file_type} rules file: {file_path}[/green]")
    
    def _get_template_content(self, file_type: str) -> str:
        """Get template content for rules file.
        
        Args:
            file_type: Type of rules file (project or user)
            
        Returns:
            Template content string
        """
        if file_type == "project":
            return """# Project Rules

## Code Style
- Follow PEP 8 for Python code
- Use meaningful variable and function names
- Add docstrings for all public functions and classes

## Architecture
- Follow the existing project structure
- Use dependency injection where appropriate
- Implement proper error handling

## Testing
- Write unit tests for new functionality
- Ensure all tests pass before committing
- Maintain test coverage above 80%

## Documentation
- Update README.md when adding new features
- Document API changes in appropriate files
- Use clear and concise comments
"""
        else:  # user rules
            return """# User Rules

## Personal Preferences
- Prefer explicit over implicit code
- Use type hints for better code clarity
- Favor composition over inheritance

## Workflow
- Create feature branches for new work
- Use descriptive commit messages
- Review code before merging

## Tools and Libraries
- Use pytest for testing
- Use black for code formatting
- Use mypy for type checking
"""
    
    def _parse_rules(self, content: str) -> Dict[str, List[str]]:
        """Parse rules content into sections.
        
        Args:
            content: Raw markdown content
            
        Returns:
            Dictionary mapping section names to lists of rules
        """
        sections = {}
        current_section = None
        current_rules = []
        
        for line in content.split('\n'):
            line = line.strip()
            if line.startswith('## '):
                if current_section:
                    sections[current_section] = current_rules
                current_section = line[3:].strip()
                current_rules = []
            elif line.startswith('- '):
                current_rules.append(line[2:].strip())
        
        if current_section:
            sections[current_section] = current_rules
        
        return sections
    
    def _format_rules(self, sections: Dict[str, List[str]], title: str) -> str:
        """Format rules sections back to markdown.
        
        Args:
            sections: Dictionary mapping section names to lists of rules
            title: Title for the rules file
            
        Returns:
            Formatted markdown content
        """
        content = f"# {title}\n\n"
        for section, rules in sections.items():
            content += f"## {section}\n"
            for rule in rules:
                content += f"- {rule}\n"
            content += "\n"
        return content.rstrip() + "\n"
    
    def list_rules(self, file_type: str) -> None:
        """List all rules in the specified file.
        
        Args:
            file_type: Type of rules file ('project' or 'user')
        """
        file_path = self.project_rules_file if file_type == "project" else self.user_rules_file
        
        if not file_path.exists():
            console.print(f"[yellow]{file_type.title()} rules file does not exist: {file_path}[/yellow]")
            return
        
        content = file_path.read_text(encoding='utf-8')
        sections = self._parse_rules(content)
        
        if not sections:
            console.print(f"[yellow]No rules found in {file_type} rules file[/yellow]")
            return
        
        table = Table(title=f"{file_type.title()} Rules")
        table.add_column("Section", style="cyan")
        table.add_column("Rules", style="green")
        
        for section, rules in sections.items():
            rules_text = "\n".join([f"• {rule}" for rule in rules])
            table.add_row(section, rules_text)
        
        console.print(table)
    
    def add_rule(self, file_type: str, section: str, rule: str) -> None:
        """Add a new rule to the specified section.
        
        Args:
            file_type: Type of rules file ('project' or 'user')
            section: Section name to add the rule to
            rule: Rule text to add
        """
        file_path = self.project_rules_file if file_type == "project" else self.user_rules_file
        title = "Project Rules" if file_type == "project" else "User Rules"
        
        self._ensure_file_exists(file_path, file_type)
        
        content = file_path.read_text(encoding='utf-8')
        sections = self._parse_rules(content)
        
        if section not in sections:
            sections[section] = []
        
        if rule not in sections[section]:
            sections[section].append(rule)
            new_content = self._format_rules(sections, title)
            file_path.write_text(new_content, encoding='utf-8')
            console.print(f"[green]Added rule to {section} in {file_type} rules[/green]")
        else:
            console.print(f"[yellow]Rule already exists in {section}[/yellow]")
    
    def remove_rule(self, file_type: str, section: str, rule_pattern: str) -> None:
        """Remove a rule from the specified section.
        
        Args:
            file_type: Type of rules file ('project' or 'user')
            section: Section name to remove the rule from
            rule_pattern: Pattern to match the rule to remove
        """
        file_path = self.project_rules_file if file_type == "project" else self.user_rules_file
        title = "Project Rules" if file_type == "project" else "User Rules"
        
        if not file_path.exists():
            console.print(f"[red]{file_type.title()} rules file does not exist[/red]")
            return
        
        content = file_path.read_text(encoding='utf-8')
        sections = self._parse_rules(content)
        
        if section not in sections:
            console.print(f"[red]Section '{section}' not found in {file_type} rules[/red]")
            return
        
        original_count = len(sections[section])
        sections[section] = [rule for rule in sections[section] 
                           if not re.search(rule_pattern, rule, re.IGNORECASE)]
        
        removed_count = original_count - len(sections[section])
        
        if removed_count > 0:
            new_content = self._format_rules(sections, title)
            file_path.write_text(new_content, encoding='utf-8')
            console.print(f"[green]Removed {removed_count} rule(s) from {section} in {file_type} rules[/green]")
        else:
            console.print(f"[yellow]No rules matching '{rule_pattern}' found in {section}[/yellow]")
    
    def update_rule(self, file_type: str, section: str, old_pattern: str, new_rule: str) -> None:
        """Update an existing rule in the specified section.
        
        Args:
            file_type: Type of rules file ('project' or 'user')
            section: Section name containing the rule
            old_pattern: Pattern to match the rule to update
            new_rule: New rule text
        """
        file_path = self.project_rules_file if file_type == "project" else self.user_rules_file
        title = "Project Rules" if file_type == "project" else "User Rules"
        
        if not file_path.exists():
            console.print(f"[red]{file_type.title()} rules file does not exist[/red]")
            return
        
        content = file_path.read_text(encoding='utf-8')
        sections = self._parse_rules(content)
        
        if section not in sections:
            console.print(f"[red]Section '{section}' not found in {file_type} rules[/red]")
            return
        
        updated = False
        for i, rule in enumerate(sections[section]):
            if re.search(old_pattern, rule, re.IGNORECASE):
                sections[section][i] = new_rule
                updated = True
                break
        
        if updated:
            new_content = self._format_rules(sections, title)
            file_path.write_text(new_content, encoding='utf-8')
            console.print(f"[green]Updated rule in {section} in {file_type} rules[/green]")
        else:
            console.print(f"[yellow]No rule matching '{old_pattern}' found in {section}[/yellow]")
    
    def add_section(self, file_type: str, section: str) -> None:
        """Add a new section to the rules file.
        
        Args:
            file_type: Type of rules file ('project' or 'user')
            section: Section name to add
        """
        file_path = self.project_rules_file if file_type == "project" else self.user_rules_file
        title = "Project Rules" if file_type == "project" else "User Rules"
        
        self._ensure_file_exists(file_path, file_type)
        
        content = file_path.read_text(encoding='utf-8')
        sections = self._parse_rules(content)
        
        if section in sections:
            console.print(f"[yellow]Section '{section}' already exists in {file_type} rules[/yellow]")
            return
        
        sections[section] = []
        new_content = self._format_rules(sections, title)
        file_path.write_text(new_content, encoding='utf-8')
        console.print(f"[green]Added section '{section}' to {file_type} rules[/green]")
    
    def remove_section(self, file_type: str, section: str) -> None:
        """Remove a section from the rules file.
        
        Args:
            file_type: Type of rules file ('project' or 'user')
            section: Section name to remove
        """
        file_path = self.project_rules_file if file_type == "project" else self.user_rules_file
        title = "Project Rules" if file_type == "project" else "User Rules"
        
        if not file_path.exists():
            console.print(f"[red]{file_type.title()} rules file does not exist[/red]")
            return
        
        content = file_path.read_text(encoding='utf-8')
        sections = self._parse_rules(content)
        
        if section not in sections:
            console.print(f"[red]Section '{section}' not found in {file_type} rules[/red]")
            return
        
        del sections[section]
        new_content = self._format_rules(sections, title)
        file_path.write_text(new_content, encoding='utf-8')
        console.print(f"[green]Removed section '{section}' from {file_type} rules[/green]")
    
    def validate_permissions(self, file_type: str) -> bool:
        """Validate write permissions for the rules file.
        
        Args:
            file_type: Type of rules file ('project' or 'user')
            
        Returns:
            True if permissions are valid, False otherwise
        """
        file_path = self.project_rules_file if file_type == "project" else self.user_rules_file
        
        try:
            # Check if directory is writable
            if not os.access(file_path.parent, os.W_OK):
                console.print(f"[red]No write permission for directory: {file_path.parent}[/red]")
                return False
            
            # Check if file is writable (if it exists)
            if file_path.exists() and not os.access(file_path, os.W_OK):
                console.print(f"[red]No write permission for file: {file_path}[/red]")
                return False
            
            return True
        except Exception as e:
            console.print(f"[red]Permission check failed: {e}[/red]")
            return False