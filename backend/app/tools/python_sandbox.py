import ast
import json
import time
import sys
import os
import subprocess
import hashlib
import uuid
import tempfile
from typing import Dict, Any, Optional, Set
from pydantic import BaseModel, Field
from app.core.config import settings

# Modules strictly permitted for analytics and computation
SAFE_MODULES: Set[str] = {
    "math", "statistics", "datetime", "decimal", "json", 
    "pandas", "numpy", "re", "time"
}

# Forbidden attributes and methods (introspection, file I/O, code execution)
FORBIDDEN_ATTRIBUTES: Set[str] = {
    # Dunder introspection & object graph traversal
    "__class__", "__bases__", "__subclasses__", "__globals__", 
    "__code__", "__closure__", "__dict__", "__module__", "__builtins__",
    "__import__", "__reduce__", "__reduce_ex__", "__mro__", "__init_subclass__",
    "__prepare__", "__spec__", "__loader__", "__file__", "__cached__",
    "__init__", "__new__", "__getattribute__",
    "f_locals", "f_globals", "f_builtins", "f_code", "gi_frame", "cr_frame",
    
    # Pandas / Numpy file I/O and dynamic execution methods
    "read_csv", "read_parquet", "read_excel", "read_pickle", "read_sql",
    "read_table", "read_json", "read_html", "read_feather", "read_hdf",
    "read_stata", "read_sas", "read_spss", "read_clipboard", "read_xml",
    "to_pickle", "to_csv", "to_excel", "to_sql", "to_parquet", "to_feather", "to_hdf",
    "to_json", "to_html", "to_stata", "to_clipboard", "to_xml",
    "eval", "query",
    
    # Numpy I/O
    "load", "save", "savez", "savez_compressed", "fromfile", "tofile",
    "memmap", "genfromtxt", "loadtxt", "fromregex", "fromstring"
}

FORBIDDEN_CALLS: Set[str] = {
    "eval", "exec", "compile", "open", "__import__", "globals", "locals", 
    "getattr", "setattr", "delattr", "hasattr", "breakpoint", "input",
    "exit", "quit", "help"
}

class SandboxResult(BaseModel):
    success: bool
    computed_output: Any = None
    stdout: str = ""
    duration_ms: int = 0
    error_message: Optional[str] = None
    reproducibility_hash: Optional[str] = None

class ASTSecurityVisitor(ast.NodeVisitor):
    """Deep AST validator checking imports, attribute access, and function calls."""
    def __init__(self):
        self.errors = []

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            root_mod = alias.name.split(".")[0]
            if root_mod not in SAFE_MODULES:
                self.errors.append(f"Import of unauthorized module '{alias.name}' is prohibited.")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        if node.module:
            root_mod = node.module.split(".")[0]
            if root_mod not in SAFE_MODULES:
                self.errors.append(f"Import from unauthorized module '{node.module}' is prohibited.")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute):
        if node.attr in FORBIDDEN_ATTRIBUTES:
            self.errors.append(f"Access to introspection attribute '{node.attr}' is prohibited.")
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name):
        if node.id in FORBIDDEN_CALLS and isinstance(node.ctx, ast.Load):
            self.errors.append(f"Reference to restricted function '{node.id}' is prohibited.")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        # Additional call checking for nested dynamic lookups
        if isinstance(node.func, ast.Name) and node.func.id in FORBIDDEN_CALLS:
            self.errors.append(f"Call to prohibited function '{node.func.id}()' is blocked.")
        elif isinstance(node.func, ast.Attribute) and node.func.attr in FORBIDDEN_ATTRIBUTES:
            self.errors.append(f"Call to prohibited method '{node.func.attr}()' is blocked.")
        self.generic_visit(node)

def validate_python_code(code: str) -> None:
    """Parse and validate Python source code AST."""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        raise ValueError(f"Syntax error in Python script: {e}")
    
    visitor = ASTSecurityVisitor()
    visitor.visit(tree)
    if visitor.errors:
        raise ValueError(f"Security validation failed: {'; '.join(visitor.errors)}")

class PythonSandboxRunner:
    """Executes validated Python analytics code in an isolated OS subprocess with secure file I/O."""

    @classmethod
    def execute(
        cls, 
        code: str, 
        input_data: Optional[Dict[str, Any]] = None,
        timeout_seconds: int = settings.SANDBOX_TIMEOUT_SECONDS
    ) -> SandboxResult:
        start_time = time.time()
        
        # 1. AST Static Analysis
        try:
            validate_python_code(code)
        except ValueError as e:
            return SandboxResult(
                success=False,
                duration_ms=int((time.time() - start_time) * 1000),
                error_message=str(e)
            )

        # 2. Prepare Unique Execution Files in Temp Directory
        exec_id = uuid.uuid4().hex
        output_file_path = os.path.join(tempfile.gettempdir(), f"omniops_sandbox_out_{exec_id}.json")
        
        inputs_json = json.dumps(input_data or {})
        escaped_out_path = output_file_path.replace("\\", "\\\\")

        runner_script = f"""
import sys
import json

# Input bindings
INPUT_DATA = json.loads({repr(inputs_json)})

def run_calculation():
{chr(10).join('    ' + line for line in code.splitlines())}

try:
    result = run_calculation()
    output_payload = {{
        "success": True,
        "result": result,
        "error": None
    }}
except Exception as e:
    output_payload = {{
        "success": False,
        "result": None,
        "error": str(e)
    }}

try:
    with open("{escaped_out_path}", "w", encoding="utf-8") as f:
        json.dump(output_payload, f, default=str)
except Exception as write_err:
    print(f"FAILED_TO_WRITE_OUTPUT: {{write_err}}", file=sys.stderr)
"""
        # 3. Spawn Subprocess with Stripped Environment (No API keys or DB credentials)
        safe_env = {
            "PATH": sys.exec_prefix + ";" + sys.exec_prefix + "\\Scripts" if sys.platform == "win32" else "/usr/bin:/bin",
            "PYTHONUNBUFFERED": "1"
        }
        
        process = None
        try:
            process = subprocess.Popen(
                [sys.executable, "-c", runner_script],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=safe_env
            )
            
            try:
                stdout, stderr = process.communicate(timeout=timeout_seconds)
            except subprocess.TimeoutExpired:
                if process:
                    process.kill()
                    stdout, stderr = process.communicate()
                return SandboxResult(
                    success=False,
                    duration_ms=int((time.time() - start_time) * 1000),
                    error_message=f"Execution timed out after {timeout_seconds} seconds."
                )

            duration_ms = int((time.time() - start_time) * 1000)
            
            # Read structured output from secure temporary file
            if os.path.exists(output_file_path):
                try:
                    with open(output_file_path, "r", encoding="utf-8") as f:
                        output_json = json.load(f)
                finally:
                    try:
                        os.unlink(output_file_path)
                    except OSError:
                        pass
                
                if output_json.get("success"):
                    result_val = output_json.get("result")
                    
                    # Compute reproducibility hash
                    hash_input = json.dumps(
                        {"code": code.strip(), "input": input_data, "output": result_val},
                        sort_keys=True,
                        default=str
                    )
                    repro_hash = hashlib.sha256(hash_input.encode("utf-8")).hexdigest()
                    
                    return SandboxResult(
                        success=True,
                        computed_output=result_val,
                        stdout=stdout.strip(),
                        duration_ms=duration_ms,
                        reproducibility_hash=repro_hash
                    )
                else:
                    return SandboxResult(
                        success=False,
                        stdout=stdout.strip(),
                        duration_ms=duration_ms,
                        error_message=output_json.get("error") or "Unknown execution failure."
                    )
            else:
                return SandboxResult(
                    success=False,
                    stdout=stdout.strip(),
                    duration_ms=duration_ms,
                    error_message=f"Execution error: {stderr.strip() if stderr else 'No output generated.'}"
                )

        except Exception as e:
            return SandboxResult(
                success=False,
                duration_ms=int((time.time() - start_time) * 1000),
                error_message=f"Sandbox runtime error: {str(e)}"
            )
        finally:
            if os.path.exists(output_file_path):
                try:
                    os.unlink(output_file_path)
                except OSError:
                    pass
