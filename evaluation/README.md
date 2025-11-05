# Evaluation for Trae Agent

This document explains how to evaluate [Trae Agent](https://github.com/bytedance/trae-agent) using [SWE-bench](https://www.swebench.com/), [SWE-bench-Live](https://swe-bench-live.github.io/), and [Multi-SWE-bench](https://multi-swe-bench.github.io/).

## Overview

**SWE-bench** is a benchmark that evaluates language models on real-world software engineering tasks. It contains GitHub issues from popular Python repositories that have been solved by human developers. The benchmark evaluates whether an agent can generate the correct patch to fix the issue.

**SWE-bench-Live** is a live benchmark for issue resolving, designed to evaluate an AI system's ability to complete real-world software engineering tasks. Thanks to our automated dataset curation pipeline, we plan to update SWE-bench-Live on a monthly basis to provide the community with up-to-date task instances and support rigorous and contamination-free evaluation.

**Multi-SWE-bench** is a multilingual benchmark for issue resolving. It spans ​7 languages (i.e., Java, TypeScript, JavaScript, Go, Rust, C, and C++) with ​1,632 high-quality instances, curated from 2,456 candidates by ​68 expert annotators for reliability.

The evaluation process involves:
1. **Setup**: Preparing the evaluation environment with Docker containers
2. **Execution**: Running Trae Agent on instances to generate patches
3. **Evaluation**: Testing the generated patches against the ground truth using harness

## Prerequisites

Before running the evaluation, ensure you have:

- **Docker**: Required for containerized evaluation environments
- **Python 3.12+**: For running the evaluation scripts
- **Git**: For cloning repositories
- **Sufficient disk space**: Docker images can be several GBs per instance
- **API Keys**: OpenAI/Anthropic API keys for Trae Agent

## Setup Instructions

Make sure installing extra dependencies for evaluation and running scripts in the `evaluation` directory.

```bash
uv sync --extra evaluation
cd evaluation
```

### 1. Clone and Setup Benchmark Harness

The `setup.sh` script automates the setup of benchmark harness:

```bash
chmod +x setup.sh
./setup.sh [swe_bench|swe_bench_live|multi_swe_bench]
```

- `swe_bench`: Setup for SWE-Bench
- `swe_bench_live`: Setup for SWE-Bench-Live
- `multi_swe_bench`: Setup for Multi-SWE-Bench

This script:
- Clones the benchmark repository
- Checks out a specific commit for reproducibility (it is the most recent commit hash at the time of writing this document.)
- Creates a Python virtual environment
- Installs the benchmark harness

### 2. Configure Trae Agent

Ensure your `trae_config.yaml` file is properly configured with valid API keys:

```
agents:
  trae_agent:
    enable_lakeview: false
    model: trae_agent_model  # the model configuration name for Trae Agent
    max_steps: 200  # max number of agent steps
    tools:  # tools used with Trae Agent
      - bash
      - str_replace_based_edit_tool
      - sequentialthinking
      - task_done

model_providers:  # model providers configuration
  anthropic:
    api_key: your_anthropic_api_key
    provider: anthropic
  openai:
    api_key: your_openai_api_key
    provider: openai

models:
  trae_agent_model:
    model_provider: anthropic
    model: claude-sonnet-4-20250514
    max_tokens: 4096
    temperature: 0.5
    top_p: 0.9
    top_k: 40
    max_retries: 1
    parallel_tool_calls: 1
```

### 3. Optional: Docker Environment Configuration

Create a `docker_env_config.json` file if you need custom environment variables:

```json
{
  "preparation_env": {
    "HTTP_PROXY": "http://proxy.example.com:8080",
    "HTTPS_PROXY": "https://proxy.example.com:8080"
  },
  "experiment_env": {
    "CUSTOM_VAR": "value"
  }
}
```


## Usage

### Basic Usage
The evaluation script `run_evaluation.py` provides several modes of operation:

```bash
# Run evaluation on all instances of SWE-bench_Verified
python run_evaluation.py --dataset SWE-bench_Verified --working-dir ./trae-workspace

# Run evaluation on specific instances
python run_evaluation.py --instance_ids django__django-12345 scikit-learn__scikit-learn-67890

# Run with custom configuration
python run_evaluation.py --config-file trae_config.yaml --run-id experiment-1
```

### Available Benchmarks and Datasets

**SWE-bench**
- **SWE-bench_Verified**
- **SWE-bench_Lite**
- **SWE-bench**

**SWE-bench-Live**:
- **SWE-bench-Live/lite**
- **SWE-bench-Live/verified**
- **SWE-bench-Live/full**

**Multi-SWE-bench**:
- **Multi-SWE-bench-flash** (Please download `multi_swe_bench_flash.jsonl` from https://huggingface.co/datasets/ByteDance-Seed/Multi-SWE-bench-flash/tree/main and place it in the  `evaluation` directory.)
- **Multi-SWE-bench_mini** (Please download `multi_swe_bench_mini.jsonl` from https://huggingface.co/datasets/ByteDance-Seed/Multi-SWE-bench_mini/tree/main and place it in the  `evaluation` directory.)

### Evaluation Modes

The script supports three modes:

1. **`expr`** (Expression only): Generate patches without evaluation
2. **`eval`** (Evaluation only): Evaluate existing patches
3. **`e2e`** (End-to-end): Both generate and evaluate patches (default)

```bash
# Only generate patches
python run_evaluation.py --mode expr --dataset SWE-bench_Verified

# Only evaluate existing patches
python run_evaluation.py --mode eval --benchmark-harness-path ./SWE-bench

# End-to-end evaluation (default)
python swebench.py --mode e2e --benchmark-harness-path ./SWE-bench
```

### Full Command Reference

```bash
python run_evaluation.py \
  --benchmark SWE-bench \
  --dataset SWE-bench_Verified \
  --config-file ./trae_config.yaml \
  --run-id experiment-1 \
  --benchmark-harness-path ./SWE-bench \
  --docker-env-config ./docker_env_config.json \
  --mode e2e \
  --max_workers 4 \
  --instance_ids astropy__astropy-13453
```

**Parameters:**
- `--benchmark`:  Benchmark to use
- `--dataset`:  Dataset to use
- `--config-file`: Trae Agent configuration file
- `--run-id`: Run ID for benchmark evaluation
- `--benchmark-harness-path`: Path to SWE-bench harness (required for evaluation)
- `--docker-env-config`: Docker environment configuration file
- `--mode`: Evaluation mode (`e2e`, `expr`, `eval`)
- `--max_workers`: Maximum number of worker processes to use for parallel execution.
- `--instance_ids`: Instances to use

## How It Works

### 1. Image Preparation

The script first checks for required Docker images:
- Each instance has a specific Docker image
- Images are pulled automatically if not present locally
- Base Ubuntu image is used for preparing Trae Agent

### 2. Trae Agent Preparation

The script builds Trae Agent in a Docker container:
- Creates artifacts (`trae-agent.tar`, `uv.tar`, `uv_shared.tar`)
- These artifacts are reused across all instances for efficiency

### 3. Instance Execution

For each instance:
1. **Container Setup**: Prepares a Docker container with the instance's environment
2. **Problem Statement**: Writes the GitHub issue description to a file
3. **Trae Agent Execution**: Runs Trae Agent to generate a patch
4. **Patch Collection**: Saves the generated patch for evaluation

### 4. Evaluation

Using benchmark harness:
1. **Patch Collection**: Collects all generated patches into `predictions.json`
2. **Test Execution**: Runs the patches against test suites in Docker containers
3. **Result Generation**: Produces evaluation results with pass/fail status

## Understanding Results

### Output Files

The evaluation creates several files in the working directory:

```
results/{benchmark}_{dataset}_{run_id}/
├── predictions.json              # Generated patches for evaluation
├── results.json                  # Final evaluation results
├── {instance_id}/                # Folder for each instance
│   ├── problem_statement.txt     # GitHub issue description
│   ├── {instance_id}.patch       # Generated patch
│   ├── {instance_id}.json        # Trajectory file
│   └── ...
trae-workspace/
├── trae_config.yaml              # Trae Agent configuration file
├── trae-agent.tar                # Trae Agent build artifacts
├── uv.tar                        # UV binary
└── uv_shared.tar                 # UV shared files
```
