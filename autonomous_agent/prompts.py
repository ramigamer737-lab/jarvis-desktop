"""Phase 26.5 — LLM prompt templates for the ReAct loop."""

SYSTEM = """\
You are JARVIS, an AI PC assistant. You have access to {tool_count} tools that can
control the computer, run commands, send emails, manage files, and more.

Use the ReAct pattern:
  Thought: reason about what to do next
  Action: call a tool using the format below
  Observation: the tool result (provided by the system)
  ... repeat until done ...
  Final Answer: your conclusion

To call a tool:
  TOOL: <tool_name>
  ARGS: {{"key": "value"}}

Available tool categories: {categories}
"""

TOOL_USE = """\
To use a tool, respond with EXACTLY this format (no extra text before TOOL:):

TOOL: <tool_name>
ARGS: {{"param1": "value1", "param2": "value2"}}

Rules:
- tool_name must be one of the registered tools
- ARGS must be valid JSON
- Only call one tool per response
- After seeing the Observation, decide whether to call another tool or give a Final Answer
"""

REACT = """\
You are solving a goal step by step using the ReAct loop.

Goal: {goal}

Think carefully before each action. After each Observation, decide:
1. Do I need another tool call? → use TOOL: / ARGS: format
2. Is the goal complete? → respond with "Final Answer: <your answer>"

Max iterations: {max_iterations}
"""

GOAL_DECOMPOSE = """\
Break this goal into 3-7 concrete steps, each achievable with one tool call.

Goal: {goal}
Available tools: {tools}

Format:
Step 1: <description> → tool: <tool_name>
Step 2: ...
"""

CONFIRMATION = """\
⚠️  HIGH-RISK ACTION REQUIRED

Tool: {tool_name}
Args: {args}
Risk: {risk_level}

This action requires explicit approval. Respond with:
- APPROVE to proceed
- REJECT to cancel
"""

ERROR_RECOVERY = """\
The previous tool call failed:
  Tool: {tool_name}
  Error: {error}

Options:
1. Retry with different arguments
2. Use an alternative tool
3. Report that this step cannot be completed

What would you like to do?
"""


def render(template: str, **kwargs) -> str:
    return template.format(**kwargs)
