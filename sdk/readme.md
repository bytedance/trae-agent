# SDK of Trae-agent

## Python SDK
The Python SDK is located in the sdk/python directory and provides a run function. Here is an example of how to use it:

```py
from sdk.python import run

result = run(
    task="Fix the bug in the authentication module",
    working_dir="/path/to/project",
    provider="openai",
    model="gpt-4o",
    verbose=True
)
```

Currently, we assume the configuration file is named trae_config.json.
