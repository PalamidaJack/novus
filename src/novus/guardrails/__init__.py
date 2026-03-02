"""
Guardrails system for NOVUS.

Provides input/output validation, content filtering, and safety controls.
Inspired by OpenAI Agents SDK guardrails.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import structlog

logger = structlog.get_logger()


class GuardrailType(str, Enum):
    """Types of guardrails."""
    INPUT_VALIDATION = "input_validation"
    OUTPUT_FILTERING = "output_filtering"
    CONTENT_MODERATION = "content_moderation"
    PII_DETECTION = "pii_detection"
    TOPIC_CONTROL = "topic_control"
    RATE_LIMITING = "rate_limiting"
    COST_CONTROL = "cost_control"
    CUSTOM = "custom"


@dataclass
class GuardrailResult:
    """Result of a guardrail check."""
    passed: bool
    guardrail_name: str
    message: Optional[str] = None
    action: Optional[str] = None  # "block", "warn", "truncate", "redact"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class GuardrailRule:
    """A single guardrail rule."""
    name: str
    guardrail_type: GuardrailType
    enabled: bool = True
    
    # For pattern matching
    patterns: List[str] = field(default_factory=list)
    
    # For custom functions
    validate_fn: Optional[Callable] = None
    
    # Configuration
    action: str = "block"  # block, warn, truncate, redact
    severity: str = "high"  # low, medium, high, critical


class Guardrails:
    """
    Guardrails system for input/output validation and content filtering.
    
    Features:
    - Input validation
    - Output filtering
    - Content moderation
    - PII detection
    - Topic control
    - Rate limiting
    - Cost controls
    """
    
    def __init__(self):
        self.rules: Dict[str, GuardrailRule] = {}
        self._setup_default_rules()
        
    def _setup_default_rules(self) -> None:
        """Set up default guardrail rules."""
        
        # Input: Block empty prompts
        self.add_rule(GuardrailRule(
            name="no_empty_input",
            guardrail_type=GuardrailType.INPUT_VALIDATION,
            patterns=[],
            validate_fn=lambda x: len(x.strip()) > 0,
            action="block",
            severity="high"
        ))
        
        # Input: Max length
        self.add_rule(GuardrailRule(
            name="max_input_length",
            guardrail_type=GuardrailType.INPUT_VALIDATION,
            patterns=[],
            validate_fn=lambda x: len(x) <= 100000,
            action="block",
            severity="medium"
        ))
        
        # Output: Profanity filter
        profanity_patterns = [
            r"\b(fuck|shit|damn|ass|bitch|crap)\b",
            r"\b(hell|damned|bloody)\b"
        ]
        self.add_rule(GuardrailRule(
            name="profanity_filter",
            guardrail_type=GuardrailType.CONTENT_MODERATION,
            patterns=profanity_patterns,
            action="redact",
            severity="medium"
        ))
        
        # Output: PII detection (basic)
        pii_patterns = [
            (r"\b\d{3}-\d{2}-\d{4}\b", "SSN"),
            (r"\b\d{16}\b", "Credit Card"),
            (r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", "Email"),
        ]
        self.add_rule(GuardrailRule(
            name="pii_detection",
            guardrail_type=GuardrailType.PII_DETECTION,
            patterns=[p[0] for p in pii_patterns],
            action="redact",
            severity="critical"
        ))
        
        # Output: Block code execution results containing dangerous patterns
        self.add_rule(GuardrailRule(
            name="no_dangerous_code",
            guardrail_type=GuardrailType.CONTENT_MODERATION,
            patterns=[
                r"rm -rf",
                r"del /[fqs]",
                r"format c:",
                r" DROP TABLE",
                r"sudo\s+rm",
            ],
            action="block",
            severity="critical"
        ))

        # Prompt injection resistance
        self.add_rule(GuardrailRule(
            name="prompt_injection_markers",
            guardrail_type=GuardrailType.INPUT_VALIDATION,
            patterns=[
                r"ignore\s+previous\s+instructions",
                r"reveal\s+(system|developer)\s+prompt",
                r"override\s+safety",
            ],
            action="block",
            severity="critical",
        ))

        # Insecure output handling / secret exposure
        self.add_rule(GuardrailRule(
            name="secret_exposure_filter",
            guardrail_type=GuardrailType.OUTPUT_FILTERING,
            patterns=[
                r"sk-[A-Za-z0-9]{10,}",
                r"-----BEGIN\s+PRIVATE\s+KEY-----",
                r"api[_-]?key\s*[:=]\s*[A-Za-z0-9_\-]{8,}",
            ],
            action="redact",
            severity="critical",
        ))

        # Excessive agency indicators
        self.add_rule(GuardrailRule(
            name="excessive_agency_actions",
            guardrail_type=GuardrailType.CONTENT_MODERATION,
            patterns=[
                r"rm\s+-rf",
                r"curl\s+.*\|\s*sh",
                r"DROP\s+TABLE",
                r"chmod\s+777",
            ],
            action="block",
            severity="critical",
        ))
    
    def add_rule(self, rule: GuardrailRule) -> None:
        """Add a guardrail rule."""
        self.rules[rule.name] = rule
        logger.info("guardrail_rule_added", name=rule.name, type=rule.guardrail_type.value)
    
    def remove_rule(self, name: str) -> None:
        """Remove a guardrail rule."""
        if name in self.rules:
            del self.rules[name]
            logger.info("guardrail_rule_removed", name=name)
    
    def enable_rule(self, name: str) -> None:
        """Enable a guardrail rule."""
        if name in self.rules:
            self.rules[name].enabled = True
    
    def disable_rule(self, name: str) -> None:
        """Disable a guardrail rule."""
        if name in self.rules:
            self.rules[name].enabled = False
    
    async def check_input(self, text: str) -> GuardrailResult:
        """Check input against all input validation rules."""
        for rule in self.rules.values():
            if not rule.enabled:
                continue
            if rule.guardrail_type != GuardrailType.INPUT_VALIDATION:
                continue
            
            result = await self._check_rule(rule, text)
            if not result.passed:
                return result
        
        return GuardrailResult(
            passed=True,
            guardrail_name="all"
        )
    
    async def check_output(self, text: str) -> GuardrailResult:
        """Check output against all output filtering rules."""
        for rule in self.rules.values():
            if not rule.enabled:
                continue
            if rule.guardrail_type not in [
                GuardrailType.OUTPUT_FILTERING,
                GuardrailType.CONTENT_MODERATION,
                GuardrailType.PII_DETECTION
            ]:
                continue
            
            result = await self._check_rule(rule, text)
            if not result.passed:
                return result
        
        return GuardrailResult(
            passed=True,
            guardrail_name="all"
        )
    
    async def _check_rule(self, rule: GuardrailRule, text: str) -> GuardrailResult:
        """Check a specific rule against text."""
        
        # Custom function validation
        if rule.validate_fn:
            try:
                passed = rule.validate_fn(text)
                if not passed:
                    return GuardrailResult(
                        passed=False,
                        guardrail_name=rule.name,
                        message=f"Failed custom validation: {rule.name}",
                        action=rule.action,
                        metadata={"rule_type": "custom"}
                    )
            except Exception as e:
                logger.warning("guardrail_validation_error", rule=rule.name, error=str(e))
        
        # Pattern matching
        for pattern in rule.patterns:
            try:
                matches = re.findall(pattern, text, re.IGNORECASE)
                if matches:
                    return GuardrailResult(
                        passed=False,
                        guardrail_name=rule.name,
                        message=f"Found prohibited content: {matches[:3]}",
                        action=rule.action,
                        metadata={
                            "pattern": pattern,
                            "matches": len(matches),
                            "examples": matches[:3]
                        }
                    )
            except re.error as e:
                logger.warning("invalid_pattern", pattern=pattern, error=str(e))
        
        return GuardrailResult(passed=True, guardrail_name=rule.name)
    
    async def filter_output(self, text: str) -> tuple[str, List[GuardrailResult]]:
        """Filter output and return modified text with results."""
        results = []
        filtered_text = text
        
        for rule in self.rules.values():
            if not rule.enabled:
                continue
            
            if rule.guardrail_type not in [
                GuardrailType.OUTPUT_FILTERING,
                GuardrailType.CONTENT_MODERATION,
                GuardrailType.PII_DETECTION
            ]:
                continue
            
            # Check rule
            result = await self._check_rule(rule, filtered_text)
            results.append(result)
            
            # Apply action
            if not result.passed:
                if rule.action == "redact":
                    for pattern in rule.patterns:
                        filtered_text = re.sub(
                            pattern,
                            "[REDACTED]",
                            filtered_text,
                            flags=re.IGNORECASE
                        )
                elif rule.action == "truncate":
                    filtered_text = filtered_text[:1000] + "... [truncated]"
                # "block" returns the result, text unchanged
        
        return filtered_text, results
    
    def get_stats(self) -> Dict[str, Any]:
        """Get guardrail statistics."""
        enabled = sum(1 for r in self.rules.values() if r.enabled)
        return {
            "total_rules": len(self.rules),
            "enabled_rules": enabled,
            "rules_by_type": {
                t.value: sum(1 for r in self.rules.values() if r.guardrail_type == t)
                for t in GuardrailType
            }
        }


class InputGuardrails:
    """
    Decorator for adding input guardrails to functions.
    
    Usage:
        @InputGuardrails(max_length=10000, allowed_topics=["tech", "science"])
        async def my_agent_function(input_text):
            ...
    """
    
    def __init__(
        self,
        max_length: Optional[int] = None,
        min_length: Optional[int] = None,
        allowed_topics: Optional[List[str]] = None,
        blocked_patterns: Optional[List[str]] = None
    ):
        self.max_length = max_length
        self.min_length = min_length
        self.allowed_topics = allowed_topics
        self.blocked_patterns = blocked_patterns or []
    
    def __call__(self, func):
        async def wrapper(*args, **kwargs):
            input_text = args[0] if args else kwargs.get("input", "")
            
            # Length checks
            if self.max_length and len(input_text) > self.max_length:
                raise ValueError(f"Input too long: {len(input_text)} > {self.max_length}")
            
            if self.min_length and len(input_text) < self.min_length:
                raise ValueError(f"Input too short: {len(input_text)} < {self.min_length}")
            
            # Pattern checks
            for pattern in self.blocked_patterns:
                if re.search(pattern, input_text, re.IGNORECASE):
                    raise ValueError(f"Input contains prohibited pattern: {pattern}")
            
            return await func(*args, **kwargs)
        
        return wrapper


class OutputGuardrails:
    """
    Decorator for adding output guardrails.
    """
    
    def __init__(
        self,
        max_length: Optional[int] = None,
        filter_profanity: bool = True,
        redact_pii: bool = True
    ):
        self.max_length = max_length
        self.filter_profanity = filter_profanity
        self.redact_pii = redact_pii
        self._guardrails = Guardrails()
    
    def __call__(self, func):
        async def wrapper(*args, **kwargs):
            result = await func(*args, **kwargs)
            
            if isinstance(result, str):
                # Apply filters
                filtered, _ = await self._guardrails.filter_output(result)
                
                if self.max_length:
                    filtered = filtered[:self.max_length]
                
                return filtered
            
            return result
        
        return wrapper


# FastAPI middleware for guardrails
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware

class GuardrailsMiddleware(BaseHTTPMiddleware):
    """Middleware for applying guardrails to API requests."""
    
    def __init__(self, app, guardrails: Optional[Guardrails] = None):
        super().__init__(app)
        self.guardrails = guardrails or Guardrails()
    
    async def dispatch(self, request: Request, call_next):
        # Check input for POST requests with body
        if request.method == "POST":
            # Get request body
            body = await request.body()
            
            if body:
                text = body.decode()
                result = await self.guardrails.check_input(text)
                
                if not result.passed:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Input blocked by guardrail: {result.message}"
                    )
        
        response = await call_next(request)
        
        return response


# Example usage
if __name__ == "__main__":
    async def example():
        guardrails = Guardrails()
        
        # Add custom rule
        guardrails.add_rule(GuardrailRule(
            name="no_competitor_mentions",
            guardrail_type=GuardrailType.CONTENT_MODERATION,
            patterns=[r"\b(OpenAI|Google|Microsoft)\b"],
            action="redact",
            severity="medium"
        ))
        
        # Check input
        result = await guardrails.check_input("Hello world")
        print(f"Input check: {'PASSED' if result.passed else 'FAILED'}")
        
        # Check and filter output
        text = "OpenAI is great! Check out openai.com"
        filtered, results = await guardrails.filter_output(text)
        print(f"Original: {text}")
        print(f"Filtered: {filtered}")
        print(f"Results: {len(results)} guardrails triggered")
        
        print(f"\nStats: {guardrails.get_stats()}")
    
    asyncio.run(example())
