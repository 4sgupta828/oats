"""
Modular prompt components for the UF-Flow planner.
Breaks down the monolithic prompt into focused, reusable components.
"""

from typing import List, Dict, Any
from dataclasses import dataclass
from core.models import Goal, UFDescriptor


@dataclass
class PromptComponent:
    """Base class for prompt components."""
    name: str
    content: str
    priority: int = 1  # Higher priority components appear first


class CorePrinciplesComponent(PromptComponent):
    """Core planning principles."""

    def __init__(self):
        super().__init__(
            name="core_principles",
            content="""
## CORE PRINCIPLES:

1. **EFFICIENCY FIRST**: Choose the most efficient approach for the given goal
   - Single command/shell script when the task is simple and self-contained
   - Multi-step workflow when complexity or data dependencies require it

2. **DATA FLOW AWARENESS**: Understand how data flows between tools
   - Plan the sequence to ensure data dependencies are satisfied
   - Use appropriate data mapping (literal, upstream, context)

3. **TOOL SELECTION**: Choose the right tool for each subtask
   - Match tool capabilities to task requirements
   - Consider input/output formats and data types

4. **COMPLEXITY ASSESSMENT**: Break down only when necessary
   - Simple tasks: Use single tools or shell pipelines
   - Complex tasks: Break into logical steps with clear dependencies
""",
            priority=10
        )


class SecurityGuidelinesComponent(PromptComponent):
    """Security guidelines for command execution."""

    def __init__(self):
        super().__init__(
            name="security_guidelines",
            content="""
## SECURITY GUIDELINES:

1. **COMMAND VALIDATION**: Use only safe, well-tested commands
   - Prefer: cat, grep, find, awk, sed, sort, uniq, wc, head, tail
   - Avoid: rm -rf, chmod 777, sudo, arbitrary script execution

2. **INPUT SANITIZATION**: All literal values must be properly formatted
   - Use string values for all parameters (e.g., "60" not 60)
   - Validate file paths and working directories

3. **RESOURCE LIMITS**: Respect timeout and resource constraints
   - Default timeouts: 60 seconds for shell commands, 120 for complex tasks
   - Working directory must be within safe bounds
""",
            priority=9
        )


class InputResolverComponent(PromptComponent):
    """Input resolver configuration guidelines."""

    def __init__(self):
        super().__init__(
            name="input_resolver",
            content="""
## INPUT RESOLVER CONFIGURATION:

Each node MUST have a complete input_resolver with:

### Data Mapping Sources:
- `"literal"`: Hardcoded values (ALWAYS strings: "60" not 60)
- `"upstream"`: Output from previous nodes (use "output.field" or "output")
- `"context"`: Context variables from goal constraints or workspace
  - Use "working_directory" for current directory
  - Use "workspace.working_directory" for workspace path from constraints
  - Use "timeout" for default timeout values

### Required Structure:
```json
{
  "data_mapping": {
    "parameter_name": {
      "source": "literal|upstream|context",
      "value_selector": "value_or_path",
      "node_id": "required_for_upstream_source"
    }
  },
  "invocation": {
    "type": "python",
    "template": "module.function_name",
    "params": {}
  }
}
```

### Critical Requirements:
- EVERY input_resolver MUST include both "data_mapping" AND "invocation"
- For upstream sources, MUST specify "node_id"
- All literal values MUST be strings
""",
            priority=8
        )


class ReasoningFrameworkComponent(PromptComponent):
    """Framework for systematic problem analysis and plan validation."""

    def __init__(self):
        super().__init__(
            name="reasoning_framework",
            content="""
## SYSTEMATIC REASONING FRAMEWORK:

### STEP 1: PROBLEM ANALYSIS
Before generating ANY plan, systematically analyze the goal:

**Question the Goal:**
- What is the user ACTUALLY trying to achieve?
- What are the implicit requirements not explicitly stated?
- What assumptions am I making about data, files, or context?

**Identify Unknowns:**
- What information do I need that I don't have?
- What files, data sources, or resources does this require?
- Where might these resources be located?

**Break Down Complexity:**
- What are the distinct sub-problems within this goal?
- Which sub-problems depend on others?
- What could go wrong at each step?

### STEP 2: SOLUTION VALIDATION
Before finalizing your plan, validate it will solve the goal:

**Trace Through Execution:**
- Walk through each node step-by-step
- Will each step produce the output the next step needs?
- Are there any gaps or missing transformations?

**Challenge Assumptions:**
- Am I assuming files exist without checking?
- Am I assuming data formats without validation?
- Am I using exact matching when pattern matching is needed?

**Test Edge Cases:**
- What if expected files don't exist?
- What if data is in unexpected formats?
- What if searches return no results or too many results?

### STEP 3: DISCOVERY-FIRST PRINCIPLE
When in doubt, DISCOVER before ASSUMING:

**Always Discovery Pattern:**
```
discover → validate → process → transform → output
```

**Examples:**
- Instead of: `read_file:/path/to/logfile.log`
- Use: `find_files:*.log` → `validate_exists` → `read_file`

- Instead of: `grep "exact_string"`
- Use: `extract_patterns` → `transform_to_searchable` → `search_code`

### STEP 4: CONFIDENCE CHECK
Before presenting the plan, ask yourself:
- Does this plan actually solve the stated goal?
- Have I made any unjustified assumptions?
- Is there a simpler or more robust approach?
- Would this plan work for someone else in a different environment?

**If you cannot confidently answer YES to all questions, revise the plan.**
""",
            priority=9
        )


class ToolSpecificComponent(PromptComponent):
    """Tool-specific usage patterns."""

    def __init__(self):
        super().__init__(
            name="tool_patterns",
            content="""
## TOOL-SPECIFIC PATTERNS:

### execute_shell Usage:
- For commands processing input: use `input_data` + processing `command`
- For standalone commands: use only `command`
- Examples:
  - File processing: `command: "xargs cat"`, `input_data: "file1.py\\nfile2.py"`
  - Text search: `command: "grep 'pattern'"`, `input_data: "text content"`
  - File listing: `command: "find . -name '*.py'"` (no input_data)

### Common Output Patterns:
- `execute_shell` returns: `{"stdout": "text", "stderr": "text", "return_code": 0, "success": true}`
  - Use `"output.stdout"` for text content
- `create_file` returns: `{"filepath": "string", "size": number}`
  - Use `"output.filepath"` for the created file path
- `read_file` returns: string directly
  - Use `"output"` for file content (not `"output.content"`)
# Note: generate_task_script tool has been disabled - use execute_shell for script execution

### Safe Command Examples:
- File concatenation: `"xargs cat"`
- Pattern search: `"grep -E 'pattern'"`
- Field extraction: `"awk -F 'delim' '{print $N}'"`
- Line counting: `"wc -l"`
""",
            priority=7
        )


class OutputFormatComponent(PromptComponent):
    """JSON output format specification."""

    def __init__(self):
        super().__init__(
            name="output_format",
            content="""
## OUTPUT FORMAT:

Return ONLY valid JSON matching this structure:

```json
{
  "id": "plan-unique-id",
  "goal_id": "will-be-set-automatically",
  "status": "running",
  "graph": {
    "node-1": ["node-2", "node-3"],
    "node-2": [],
    "node-3": []
  },
  "nodes": {
    "node-1": {
      "id": "node-1",
      "uf_name": "tool_name:version",
      "status": "pending",
      "input_resolver": { /* complete input resolver */ },
      "result": null
    }
  },
  "confidence_score": 0.85
}
```

### Validation Rules:
- All node IDs referenced in graph must exist in nodes
- Each node must have complete input_resolver
- confidence_score between 0.0 and 1.0
- No additional fields outside this structure
""",
            priority=1
        )


class ExampleComponent(PromptComponent):
    """Concrete examples for different scenarios."""

    def __init__(self, scenario: str = "general"):
        examples = {
            "file_processing": self._file_processing_example(),
            "data_analysis": self._data_analysis_example(),
            "script_generation": self._script_generation_example()
        }

        super().__init__(
            name=f"examples_{scenario}",
            content=examples.get(scenario, examples["file_processing"]),
            priority=2
        )

    def _file_processing_example(self) -> str:
        return """
## EXAMPLE: File Creation and Reading Workflow

Goal: "Create a file with content and then read it back"

```json
{
  "id": "plan-create-read-file-001",
  "status": "running",
  "graph": {
    "create-file-node": ["read-file-node"]
  },
  "nodes": {
    "create-file-node": {
      "id": "create-file-node",
      "uf_name": "create_file:1.0.0",
      "status": "pending",
      "input_resolver": {
        "data_mapping": {
          "filename": {"source": "literal", "value_selector": "hello.txt"},
          "content": {"source": "literal", "value_selector": "Hello, world!"}
        },
        "invocation": {"type": "python", "template": "tools.file_system.create_file", "params": {}}
      },
      "result": null
    },
    "read-file-node": {
      "id": "read-file-node",
      "uf_name": "read_file:1.0.0",
      "status": "pending",
      "input_resolver": {
        "data_mapping": {
          "filename": {"source": "upstream", "value_selector": "output.filepath", "node_id": "create-file-node"}
        },
        "invocation": {"type": "python", "template": "tools.file_system.read_file", "params": {}}
      },
      "result": null
    }
  },
  "confidence_score": 0.95
}
```"""

    def _data_analysis_example(self) -> str:
        return """
## EXAMPLE: Data Analysis Workflow

Goal: "Analyze log file for error patterns and generate summary"

```json
{
  "id": "plan-log-analysis-001",
  "status": "running",
  "graph": {
    "read-log-file": ["extract-errors"],
    "extract-errors": ["generate-summary"]
  },
  "nodes": {
    "read-log-file": {
      "id": "read-log-file",
      "uf_name": "read_file:1.0.0",
      "status": "pending",
      "input_resolver": {
        "data_mapping": {
          "filename": {"source": "context", "value_selector": "log_file"}
        },
        "invocation": {"type": "python", "template": "tools.file_system.read_file", "params": {}}
      },
      "result": null
    },
    "extract-errors": {
      "id": "extract-errors",
      "uf_name": "execute_shell:2.1.0",
      "status": "pending",
      "input_resolver": {
        "data_mapping": {
          "command": {"source": "literal", "value_selector": "grep -i 'error\\|exception\\|fail'"},
          "input_data": {"source": "upstream", "value_selector": "output", "node_id": "read-log-file"},
          "timeout": {"source": "literal", "value_selector": "60"}
        },
        "invocation": {"type": "python", "template": "tools.shell_tools.execute_shell", "params": {}}
      },
      "result": null
    }
  },
  "confidence_score": 0.85
}
```"""

    def _script_generation_example(self) -> str:
        return """
## EXAMPLE: Script Generation Workflow

Goal: "Generate a script to process data and execute it"

```json
{
  "id": "plan-script-gen-001",
  "status": "running",
  "graph": {
    "generate-script": ["execute-script"]
  },
  "nodes": {
    "generate-script": {
      "id": "generate-script",
      "uf_name": "generate_task_script:1.0.0",
      "status": "pending",
      "input_resolver": {
        "data_mapping": {
          "task_description": {"source": "literal", "value_selector": "Process CSV data and calculate statistics"},
          "constraints": {"source": "literal", "value_selector": "Use only standard Unix tools"},
          "output_format": {"source": "literal", "value_selector": "json"}
        },
        "invocation": {"type": "python", "template": "tools.llm_integration.generate_task_script", "params": {}}
      },
      "result": null
    },
    "execute-script": {
      "id": "execute-script",
      "uf_name": "execute_task_script:1.0.0",
      "status": "pending",
      "input_resolver": {
        "data_mapping": {
          "script_content": {"source": "upstream", "value_selector": "output.script_content", "node_id": "generate-script"},
          "input_data": {"source": "context", "value_selector": "input_data"},
          "timeout": {"source": "literal", "value_selector": "120"}
        },
        "invocation": {"type": "python", "template": "tools.llm_integration.execute_task_script", "params": {}}
      },
      "result": null
    }
  },
  "confidence_score": 0.8
}
```"""


class PromptBuilder:
    """Builds context-aware prompts from components."""

    def __init__(self):
        self.components: Dict[str, PromptComponent] = {}
        self._register_default_components()

    def _register_default_components(self):
        """Register default prompt components."""
        self.components["core_principles"] = CorePrinciplesComponent()
        self.components["reasoning_framework"] = ReasoningFrameworkComponent()
        self.components["security_guidelines"] = SecurityGuidelinesComponent()
        self.components["input_resolver"] = InputResolverComponent()
        self.components["tool_patterns"] = ToolSpecificComponent()
        self.components["output_format"] = OutputFormatComponent()

    def add_component(self, component: PromptComponent):
        """Add a custom component."""
        self.components[component.name] = component

    def build_prompt(self, goal: Goal, tools: List[UFDescriptor], context: Dict[str, Any] = None) -> str:
        """Build a context-aware prompt."""

        # Determine scenario based on goal
        scenario = self._detect_scenario(goal)

        # Add appropriate example component
        example_component = ExampleComponent(scenario)
        self.components[example_component.name] = example_component

        # Sort components by priority (highest first)
        sorted_components = sorted(
            self.components.values(),
            key=lambda x: x.priority,
            reverse=True
        )

        # Build the prompt
        prompt_parts = [
            "You are an expert autonomous agent planner. Your task is to decompose a user's GOAL into an optimal execution plan using the available TOOLS.",
            ""
        ]

        # Add components
        for component in sorted_components:
            prompt_parts.append(component.content)
            prompt_parts.append("")

        # Add dynamic content
        prompt_parts.extend([
            "## AVAILABLE TOOLS:",
            self._format_tools(tools),
            "",
            "## USER GOAL:",
            f'"{goal.description}"',
            ""
        ])

        if goal.constraints:
            prompt_parts.extend([
                "## GOAL CONSTRAINTS:",
                self._format_constraints(goal.constraints),
                ""
            ])

        if context:
            prompt_parts.extend([
                "## SYSTEM CONTEXT:",
                self._format_context(context),
                ""
            ])

        prompt_parts.extend([
            "Generate an optimal execution plan that achieves the goal efficiently and safely.",
            "Return ONLY the JSON plan - no explanations or markdown formatting."
        ])

        return "\n".join(prompt_parts)

    def _detect_scenario(self, goal: Goal) -> str:
        """Detect the scenario type based on goal description."""
        description = goal.description.lower()

        if any(word in description for word in ["log", "error", "analyze", "pattern"]):
            return "data_analysis"
        elif any(word in description for word in ["generate", "script", "create"]):
            return "script_generation"
        else:
            return "file_processing"

    def _format_tools(self, tools: List[UFDescriptor]) -> str:
        """Format tools for the prompt."""
        lines = []
        for tool in tools:
            input_props = tool.input_schema.get('properties', {})
            input_str = ", ".join([
                f"{name}: {props.get('type', 'string')}"
                for name, props in input_props.items()
            ])
            lines.append(f"- {tool.name}:{tool.version}: {tool.description}")
            if input_str:
                lines.append(f"  Inputs: {input_str}")
        return "\n".join(lines)

    def _format_constraints(self, constraints: Dict[str, Any]) -> str:
        """Format goal constraints."""
        import json
        return json.dumps(constraints, indent=2)

    def _format_context(self, context: Dict[str, Any]) -> str:
        """Format system context."""
        import json
        return json.dumps(context, indent=2)