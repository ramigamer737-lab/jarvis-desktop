"""Phase 29 — ToolTester: sandbox-test generated tools via pytest subprocess."""
from __future__ import annotations

import ast
import logging
import re
import subprocess
import tempfile
import textwrap
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .prompts import render, TEST_GENERATOR

log = logging.getLogger(__name__)

# Imports that are blocked in generated tool code (safety)
_BLOCKED = {"os.system", "subprocess.Popen", "subprocess.call", "shutil.rmtree",
            "eval(", "exec(", "__import__"}


@dataclass
class TestResult:
    passed: int = 0
    failed: int = 0
    errors: int = 0
    output: str = ""
    duration_ms: float = 0.0
    syntax_ok: bool = True
    syntax_error: str = ""
    blocked_imports: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.syntax_ok and not self.blocked_imports and self.passed >= 2 and self.failed == 0


class ToolTester:
    """Tests generated tools in an isolated subprocess sandbox."""

    def __init__(self, provider: Any = None, timeout: int = 30) -> None:
        self.provider = provider
        self.timeout = timeout

    # ── public API ────────────────────────────────────────────────────────────

    def validate_syntax(self, code: str) -> TestResult:
        """AST-parse the code and check for blocked patterns."""
        result = TestResult()
        try:
            ast.parse(code)
        except SyntaxError as e:
            result.syntax_ok = False
            result.syntax_error = str(e)
            return result
        result.blocked_imports = [b for b in _BLOCKED if b in code]
        return result

    async def test_tool(self, tool) -> TestResult:
        """Generate tests via LLM (or use defaults) and run pytest in a temp dir."""
        result = self.validate_syntax(tool.code)
        if not result.syntax_ok or result.blocked_imports:
            return result
        test_code = await self._generate_tests(tool)
        return self._run_pytest(tool.code, test_code)

    # ── private ───────────────────────────────────────────────────────────────

    async def _generate_tests(self, tool) -> str:
        """Ask LLM for tests, fall back to a generic smoke test."""
        if self.provider:
            try:
                from autonomous_agent.llm_providers import Message
                prompt = render(TEST_GENERATOR, code=tool.code)
                resp = await self.provider.complete([Message(role="user", content=prompt)])
                m = re.search(r"```python\s*(.*?)```", resp.content, re.DOTALL)
                if m:
                    return m.group(1).strip()
            except Exception as e:
                log.warning("Test generation failed (%s), using fallback", e)
        return self._fallback_tests(tool.name)

    @staticmethod
    def _fallback_tests(func_name: str) -> str:
        return textwrap.dedent(f"""\
            import pytest
            from tool import {func_name}

            def test_returns_dict():
                result = {func_name}({{}})
                assert isinstance(result, dict)

            def test_has_success_key():
                result = {func_name}({{}})
                assert "success" in result

            def test_has_result_key():
                result = {func_name}({{}})
                assert "result" in result or "error" in result
        """)

    def _run_pytest(self, tool_code: str, test_code: str) -> TestResult:
        tmp = Path(tempfile.mkdtemp(prefix=f"jarvis_test_{uuid.uuid4().hex[:8]}_"))
        try:
            (tmp / "tool.py").write_text(tool_code)
            (tmp / "test_tool.py").write_text(test_code)
            t0 = time.monotonic()
            proc = subprocess.run(
                ["python", "-m", "pytest", "test_tool.py", "-v", "--tb=short",
                 "--timeout=10", "-q"],
                cwd=tmp, capture_output=True, text=True, timeout=self.timeout,
            )
            duration = (time.monotonic() - t0) * 1000
            output = proc.stdout + proc.stderr
            return TestResult(
                passed=output.count(" PASSED"),
                failed=output.count(" FAILED"),
                errors=output.count(" ERROR"),
                output=output[:2000],
                duration_ms=round(duration, 1),
            )
        except subprocess.TimeoutExpired:
            return TestResult(errors=1, output="Timeout exceeded", duration_ms=self.timeout * 1000)
        except Exception as e:
            return TestResult(errors=1, output=str(e))
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)
