# Contributing to Trae Agent

Thank you for your interest in contributing to Trae Agent! We welcome contributions of all kinds from the community.

## Ways to Contribute

There are many ways you can contribute to Trae Agent:

- **Code Contributions**: Add new features, fix bugs, or improve performance
- **Documentation**: Improve README, add code comments, or create examples
- **Bug Reports**: Submit detailed bug reports through issues
- **Feature Requests**: Suggest new features or improvements
- **Code Reviews**: Review pull requests from other contributors
- **Community Support**: Help others in discussions and issues

## Development Setup

You need Python 3.12 or newer, [uv](https://docs.astral.sh/uv/) and `make`. The `make` targets below
shell out to `uv` (`uv venv`, `uv sync --all-extras`, `uv run pytest`), so `make install-dev` fails
with `uv: command not found` if `uv` is not installed.

1. Fork the repository (the **Fork** button at the top of the repository page)

2. Clone **your fork**, then add this repository as a second remote:

   ```bash
   git clone https://github.com/<your-username>/trae-agent.git
   cd trae-agent
   git remote add upstream https://github.com/bytedance/trae-agent.git
   ```

   `origin` now points at the repository you can push to, and `upstream` at the repository you
   will open pull requests against. Cloning `bytedance/trae-agent` instead makes `origin` a
   repository you have no write access to, and step 4 of the Development Process below then fails.

3. Set up your development environment:

   ```bash
   make install-dev
   make pre-commit-install
   ```

4. Before you start work, and again before you open a pull request, bring your branch up to date
   with `upstream`:

   ```bash
   git fetch upstream
   git rebase upstream/main
   ```

## Running Tests

```bash
make test
```

## Development Process

1. Create a new branch:

   ```bash
   git checkout -b feature/amazing-feature
   ```

2. Make your changes following our coding standards:
   - Write clear, documented code
   - Follow PEP 8 style guidelines
   - Add tests for new features
   - Update documentation as needed
   - Maintain type hints and add type checking when possible

3. Commit your changes:

   ```bash
   git commit -m 'Add some amazing feature'
   ```

4. Push to your fork:

   ```bash
   git push origin feature/amazing-feature
   ```

5. Open a Pull Request

## Pull Request Guidelines

- Fill in the pull request template completely
- Include tests for new features
- Update documentation as needed
- Ensure all tests pass and there are no linting errors
- Keep pull requests focused on a single feature or fix
- Reference any related issues

## Code Style

- Follow PEP 8 guidelines
- Use type hints where possible
- Write descriptive docstrings
- Keep functions and methods focused and single-purpose
- Comment complex logic
- Python version requirement: >= 3.12

## Community Guidelines

- Be respectful and inclusive
- Follow our code of conduct
- Help others learn and grow
- Give constructive feedback
- Stay focused on improving the project

## Need Help?

If you need help with anything:

- Check existing issues and discussions
- Join our community channels
- Ask questions in discussions

## License

By contributing to Trae Agent, you agree that your contributions will be licensed under the MIT License.

We appreciate your contributions to making Trae Agent better!
