# Selector Agent

This document explains how to further enhance [Trae Agent](https://github.com/bytedance/trae-agent) using the selector agent.
Selector agent is the first agent-based ensemble reasoning approach for repository-level issue resolution.
It formulates our goal as an optimal solution search problem and addresses two key challenges, i.e., large ensemble spaces and repository-level understanding, through modular agents for generation, pruning, and selection.

## 📖 Demo

### Regression Testing
For regression testing, please refer to [Agentless](https://github.com/OpenAutoCoder/Agentless/blob/main/README_swebench.md).

Each result entry contains a `regression` field that indicates test outcomes:
   - An empty array [] signifies the patch successfully passed all regression tests;
   - Any non-empty value indicates the patch caused test failures (with details specifying which tests failed).

### Preparation

**Important:** You need to download a Python 3.12 package from [Google Drive](https://drive.google.com/file/d/1dF7kbcmdLRJu7TEh8G7Oe8_6NY3aieKa/view?usp=sharing) and unzip it into `evaluation/patch_selection/trae_selector/tools/py312`. This is used to execute agent tools in Docker containers.

### Input Format

Patch candidates are stored in a JSON line file. For each instance, the structure is as follows:

```json
{
    "instance_id": "django__django-14017",
    "issue": "Issue description....",
    "patches": [
        "patch diff 1",
        "patch diff 2",
        ...,
        "patch diff N",
    ],
    "success_id": [
        1,
        0,
        ...,
        1
    ],
    "regressions": [
      [regression_test_names for patch diff 1..],
      [regression_test_names for patch diff 2..],
      ...,
      [regression_test_names for patch diff N..],
    ]
}
```

Note: success_id is either 1 (the corresponding patch diff is a correct patch) or 0 (the corresponding patch diff is a wrong patch). Once a patch is selected by the Selector Agent, we can quickly report if the selected patch is correct or not.

The regressions field is optional. If you have done regression test selection using Agentless, you can fill in selected regression tests here.

### Patch Selection

```bash
python3 evaluation/patch_selection/selector.py \
    --instances_path "path/to/swebench-verified.json" \
    --candidate_path "path/to/patch_candidates.jsonl" \
    --result_path "path/to/save/results" \
    --num_candidate NUMBER_OF_PATCH_CANDIDATES_PER_INSTANCE \
    --max_workers 10 \
    --group_size GROUP_SIZE \
    --max_retry 20 \
    --max_turn 200 \
    --config_file trae_config.yaml \
    --model_name MODEL_NAME_IN_CONFIG_FILE \
    --majority_voting
```

Note: if you have a lot of patch candidates, for example 50, you can set group_size to 10. The patch selection is done by 5 (50/10) groups. A patch is selected for each group. You can then select from these 5.

`--majority_voting` is optional. If enabled, for each candidate group, multiple patch selection is conducted and the patch with most selected frequency is the final answer. This mode consumes more token consumption.

### Example

After running with [example.jsonl](example/example.jsonl), in the result_path, we get the following files:

```text
├── log
│   └── group_0
│       └── astropy__astropy-14369_voting_0_trail_1.json
├── output
│   └── group_0
│       └── astropy__astropy-14369.log
├── patch
│   └── group_0
│       └── astropy__astropy-14369_1.patch
└── statistics
    └── group_0
        └── astropy__astropy-14369.json
```

* The file in the log directory stores LLM interaction history.
* The file in the output directory stores raw standard output and standard error.
* Patch directory stores selected patches.
* Statistics directory stores whether the selected patch is correct or not.

You can use the `analysis.py` script to visualise the selection results (even during the selection is running to see intermediate results)

```bash
python3 analysis.py --output_path "path/to/save/results"
```
