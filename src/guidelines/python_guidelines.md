# Python Coding Guidelines

## Naming Conventions
- Use `snake_case` for functions and variables
- Use `PascalCase` for classes
- Use `UPPER_SNAKE_CASE` for constants
- Function names must be descriptive verbs: `get_orders()` not `orders()`
- Variable names must describe what they hold: `active_orders` not `data`

## Function Design
- Functions must have a single responsibility
- Functions longer than 20 lines should be broken into smaller functions
- Maximum 4 parameters per function; use a dataclass or dict for more
- All public functions must have a docstring with Args and Returns sections
- Avoid nested functions more than 2 levels deep

## Code Quality
- No hardcoded strings for config values; use environment variables or config files
- No bare `except:` clauses; always catch specific exceptions
- Never use `eval()` or `exec()` on untrusted input
- Import order: stdlib → third-party → local (use isort or ruff to enforce)
- Maximum line length: 88 characters (Black/Ruff default)

## Error Handling
- Always log exceptions with context before re-raising
- Use custom exception classes for domain-specific errors
- Never silently swallow exceptions with `pass` in except blocks

## Type Hints
- All function signatures must have type hints for parameters and return value
- Use `Optional[X]` instead of `X | None` for Python < 3.10
- Use `List`, `Dict`, `Tuple` from `typing` for Python < 3.9

## Security
- Never commit secrets, API keys, or passwords in source code
- Use `os.environ` or `pydantic-settings` to read configuration
- Validate all inputs before processing
- Use parameterized queries; never concatenate user input into SQL strings
- Avoid `pickle` for untrusted data deserialization

## Testing
- Every function must have at least one unit test
- Test file names: `test_<module_name>.py`
- Use `pytest` as the test framework
- Mock external API calls in unit tests; never make real HTTP calls