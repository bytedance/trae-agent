# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

set -e

case "$1" in
  multi_swe_bench)
    MULTI_SWE_BENCH_COMMIT_HASH="9a9bec0f3725e1e5340299192571f3a4c26ea27d"
    git clone https://github.com/multi-swe-bench/multi-swe-bench.git
    cd multi-swe-bench
    git checkout $MULTI_SWE_BENCH_COMMIT_HASH
    python3 -m venv multi_swebench_venv
    source multi_swebench_venv/bin/activate
    make install
    deactivate
    ;;
  swe_bench)
    SWE_BENCH_COMMIT_HASH="2bf15e1be3c995a0758529bd29848a8987546090"
    git clone https://github.com/SWE-bench/SWE-bench.git
    cd SWE-bench
    git checkout $SWE_BENCH_COMMIT_HASH
    python3 -m venv swebench_venv
    source swebench_venv/bin/activate
    pip install -e .
    deactivate
    ;;
  swe_bench_live)
    SWE_BENCH_LIVE_COMMIT_HASH="cbc2a3ce1d3d0ce588a45ad6730a04623a84a933"
    git clone https://github.com/microsoft/SWE-bench-Live.git
    cd SWE-bench-Live
    git checkout $SWE_BENCH_LIVE_COMMIT_HASH
    python3 -m venv swebench_live_venv
    source swebench_live_venv/bin/activate
    pip install -e .
    deactivate
    ;;
  *)
    echo "Usage: ./setup.sh [multi_swe_bench|swe_bench|swe_bench_live]"
    ;;
esac
