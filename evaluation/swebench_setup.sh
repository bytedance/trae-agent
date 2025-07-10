# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

SWE_BENCH_COMMIT_HASH="2bf15e1be3c995a0758529bd29848a8987546090"

git clone https://github.com/SWE-bench/SWE-bench.git
cd SWE-bench
git checkout $SWE_BENCH_COMMIT_HASH
python3 -m venv swebench_venv
source swebench_venv/bin/activate
pip install -e .
deactivate
