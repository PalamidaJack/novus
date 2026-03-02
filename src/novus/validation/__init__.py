"""
Output validation and structured responses for NOVUS.

Ensures agents produce validated, typed outputs using Pydantic models.
Inspired by CrewAI's output validation pattern.
"""

from __future__ import annotations

import json
from typing import Type, TypeVar, Optional, Dict, Any, Union, get_origin, get_args
from dataclasses import dataclass
from pydantic import BaseModel, ValidationError, create_model
import structlog

logger = structlog.get_logger()

T = TypeVar('T', bound=BaseModel)


class OutputValidationError(Exception):
    """Raised when output validation fails."""
    
    def __init__(self, message: str, raw_output: str, validation_errors: list):
        super().__init__(message)
        self.raw_output = raw_output
        self.validation_errors = validation_errors


@dataclass
class ValidationResult:
    """Result of output validation."""
    success: bool
    data: Optional[Any] = None
    raw_output: Optional[str] = None
    error_message: Optional[str] = None
    validation_errors: Optional[list] = None
    
    @property
    def is_valid(self) -> bool:
        return self.success and self.data is not None


class OutputValidator:
    """
    Validates and parses agent outputs.
    
    Supports:
    - Pydantic model validation
    - JSON schema validation
    - Type coercion
    - Retry with correction
    """
    
    def __init__(self, max_retries: int = 3):
        self.max_retries = max_retries
    
    async def validate(
        self,
        raw_output: str,
        output_model: Type[T],
        allow_partial: bool = False
    ) -> ValidationResult:
        """
        Validate raw output against a Pydantic model.
        
        Args:
            raw_output: The raw string output from the agent
            output_model: Pydantic model class to validate against
            allow_partial: Whether to allow partial matches
        
        Returns:
            ValidationResult with parsed data or error info
        """
        # Try direct parsing first
        result = self._try_parse_json(raw_output, output_model)
        if result.is_valid:
            return result
        
        # Try extracting JSON from markdown
        extracted = self._extract_json_from_markdown(raw_output)
        if extracted:
            result = self._try_parse_json(extracted, output_model)
            if result.is_valid:
                return result
        
        # Try fixing common JSON errors
        fixed = self._fix_common_json_errors(raw_output)
        if fixed != raw_output:
            result = self._try_parse_json(fixed, output_model)
            if result.is_valid:
                return result
        
        # If all attempts fail, return error
        return ValidationResult(
            success=False,
            raw_output=raw_output,
            error_message="Failed to validate output",
            validation_errors=result.validation_errors if result else ["Parse error"]
        )
    
    def _try_parse_json(
        self,
        raw_output: str,
        output_model: Type[T]
    ) -> ValidationResult:
        """Try to parse JSON and validate against model."""
        try:
            # Clean the output
            cleaned = raw_output.strip()
            
            # Parse JSON
            data = json.loads(cleaned)
            
            # Validate with Pydantic
            validated = output_model.model_validate(data)
            
            return ValidationResult(
                success=True,
                data=validated,
                raw_output=raw_output
            )
            
        except json.JSONDecodeError as e:
            return ValidationResult(
                success=False,
                raw_output=raw_output,
                error_message=f"JSON decode error: {e}",
                validation_errors=[str(e)]
            )
        except ValidationError as e:
            return ValidationResult(
                success=False,
                raw_output=raw_output,
                error_message="Validation failed",
                validation_errors=e.errors()
            )
    
    def _extract_json_from_markdown(self, text: str) -> Optional[str]:
        """Extract JSON from markdown code blocks."""
        import re
        
        # Look for ```json blocks
        patterns = [
            r'```json\n(.*?)\n```',
            r'```\n(.*?)\n```',
            r'`(.*?)`'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.DOTALL)
            if match:
                return match.group(1).strip()
        
        return None
    
    def _fix_common_json_errors(self, text: str) -> str:
        """Attempt to fix common JSON formatting issues."""
        fixed = text.strip()
        
        # Remove trailing commas
        fixed = fixed.replace(',}', '}').replace(',]', ']')
        
        # Fix single quotes to double quotes
        # This is a naive fix - production would need proper parsing
        in_string = False
        result = []
        for char in fixed:
            if char == '"' and (not result or result[-1] != '\\'):
                in_string = not in_string
            if char == "'" and not in_string:
                result.append('"')
            else:
                result.append(char)
        fixed = ''.join(result)
        
        # Ensure proper wrapping
        if not fixed.startswith('{') and not fixed.startswith('['):
            # Try to wrap in object
            fixed = '{' + fixed + '}'
        
        return fixed
    
    async def validate_with_correction(
        self,
        raw_output: str,
        output_model: Type[T],
        correction_callback: callable
    ) -> ValidationResult:
        """
        Validate with automatic correction attempts.
        
        If validation fails, calls correction_callback with error info
        to get a corrected version.
        """
        for attempt in range(self.max_retries):
            result = await self.validate(raw_output, output_model)
            
            if result.is_valid:
                logger.info("validation_success", attempt=attempt + 1)
                return result
            
            # Try to correct
            if attempt < self.max_retries - 1:
                try:
                    raw_output = await correction_callback(
                        raw_output,
                        result.validation_errors
                    )
                except Exception as e:
                    logger.error("correction_failed", error=str(e))
                    break
        
        return result


class StructuredOutputMixin:
    """
    Mixin for agents that produce structured outputs.
    
    Usage:
        class MyAgent(Agent, StructuredOutputMixin):
            output_model = MyOutputSchema
            
        result = await agent.run("task")  # Returns MyOutputSchema instance
    """
    
    output_model: Optional[Type[BaseModel]] = None
    _validator: OutputValidator = None
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._validator = OutputValidator()
    
    async def parse_output(self, raw_output: str) -> Union[BaseModel, str]:
        """
        Parse and validate agent output.
        
        If output_model is set, validates and returns structured data.
        Otherwise returns raw string.
        """
        if self.output_model is None:
            return raw_output
        
        result = await self._validator.validate(raw_output, self.output_model)
        
        if result.is_valid:
            return result.data
        
        # Log validation failure but return raw output
        logger.warning(
            "output_validation_failed",
            errors=result.validation_errors,
            raw=raw_output[:200]
        )
        return raw_output
    
    def get_output_schema_prompt(self) -> str:
        """
        Generate a prompt snippet describing the expected output schema.
        
        This helps the LLM produce correctly formatted output.
        """
        if self.output_model is None:
            return ""
        
        schema = self.output_model.model_json_schema()
        
        prompt = f"""
You must respond with a valid JSON object matching this schema:

```json
{json.dumps(schema, indent=2)}
```

Requirements:
- Response must be valid JSON
- All required fields must be present
- Follow the specified types exactly
- Do not include markdown formatting outside the JSON

Example response:
```json
{self._generate_example(self.output_model)}
```
"""
        return prompt
    
    def _generate_example(self, model: Type[BaseModel]) -> str:
        """Generate an example instance of the model."""
        example_data = {}
        
        for name, field in model.model_fields.items():
            field_type = field.annotation
            
            # Generate appropriate example based on type
            if field_type == str:
                example_data[name] = f"example_{name}"
            elif field_type == int:
                example_data[name] = 42
            elif field_type == float:
                example_data[name] = 3.14
            elif field_type == bool:
                example_data[name] = True
            elif get_origin(field_type) == list:
                example_data[name] = []
            elif get_origin(field_type) == dict:
                example_data[name] = {}
            else:
                example_data[name] = None
        
        return json.dumps(example_data, indent=2)


# Common output schemas for reuse

class AnalysisOutput(BaseModel):
    """Standard analysis output format."""
    summary: str
    key_findings: list[str]
    confidence_score: float
    sources: list[str] = []
    recommendations: list[str] = []


class CodeOutput(BaseModel):
    """Code generation output format."""
    code: str
    language: str
    explanation: str
    dependencies: list[str] = []
    test_cases: list[str] = []


class ResearchOutput(BaseModel):
    """Research task output format."""
    topic: str
    findings: list[Dict[str, str]]  # [{"point": "...", "evidence": "..."}]
    conclusion: str
    further_research: list[str] = []


class ComparisonOutput(BaseModel):
    """Comparison task output format."""
    items_compared: list[str]
    criteria: list[str]
    comparison_table: Dict[str, Dict[str, str]]  # {item: {criterion: value}}
    winner: Optional[str] = None
    reasoning: str


class CreativeOutput(BaseModel):
    """Creative task output format."""
    title: str
    content: str
    style: str
    target_audience: str
    key_themes: list[str] = []


# Decorator for creating validated agents
def validated_agent(output_model: Type[BaseModel]):
    """
    Decorator to create an agent with output validation.
    
    Usage:
        @validated_agent(AnalysisOutput)
        class ResearchAgent(Agent):
            pass
    """
    def decorator(cls):
        cls.output_model = output_model
        
        # Mix in StructuredOutputMixin
        original_bases = cls.__bases__
        if StructuredOutputMixin not in original_bases:
            cls.__bases__ = (StructuredOutputMixin,) + original_bases
        
        return cls
    return decorator


# Example usage
if __name__ == "__main__":
    from novus.core.agent import Agent
    from novus.core.models import AgentConfig
    
    # Define output schema
    class WeatherReport(BaseModel):
        location: str
        temperature: float
        conditions: str
        forecast: list[Dict[str, str]]
    
    # Create validated agent
    @validated_agent(WeatherReport)
    class WeatherAgent(Agent):
        pass
    
    # Usage
    config = AgentConfig(name="WeatherBot")
    agent = WeatherAgent(config)
    
    # The agent will now expect WeatherReport format output
    print(agent.get_output_schema_prompt())
