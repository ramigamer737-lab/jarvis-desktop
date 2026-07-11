"""Self-improvement LLM prompt templates (Phase 29)."""

TOOL_GENERATOR = """\
You are a Python expert writing tools for JARVIS, an AI PC assistant.

Write a Python function with this EXACT signature:
  def {name}(args: dict) -> dict

Rules:
- Return dict MUST have keys: success (bool), result (any), error (str|None)
- Use only stdlib unless the task clearly needs a third-party lib
- Include a one-line docstring
- No print statements; use logging if needed
- Handle exceptions; return {{"success": False, "result": None, "error": str(e)}} on failure

Task: {description}
Category: {category}

Respond with ONLY a ```python ... ``` code block.
"""

TEST_GENERATOR = """\
Write 3 pytest test functions for this JARVIS tool.
Each test must call the function with a dict argument and assert the return dict has
"success", "result", and "error" keys.

Tool code:
```python
{code}
```

Respond with ONLY a ```python ... ``` code block containing the 3 test functions.
"""

TOOL_IMPROVER = """\
Fix the following JARVIS tool. It failed with this error:

Error log:
{error_log}

Original code:
```python
{code}
```

Return ONLY the fixed ```python ... ``` code block. Keep the same function name and signature.
"""

GAP_ANALYZER = """\
You are analyzing JARVIS tool failures to find missing capabilities.

Failed goals (last 24h):
{failures}

Existing tool categories: {categories}

List up to 5 missing tools that would have prevented these failures.
Format each as:
TOOL: <snake_case_name>
DESC: <one sentence description>
CAT: <category>
"""

TOOL_SUGGESTER = """\
Given this user goal, suggest 3-5 new JARVIS tools that would help achieve it.
Existing tools: {existing_tools}

Goal: {goal}

Format each suggestion as:
TOOL: <snake_case_name>
DESC: <one sentence description>
CAT: <category>
WHY: <why this helps>
"""


def render(template: str, **kwargs) -> str:
    """Render a prompt template with keyword substitutions."""
    return template.format(**kwargs)
