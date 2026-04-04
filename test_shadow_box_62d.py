"""
test_shadow_box_62d.py — 62D Shadow Box Acceptance Tests

Acceptance criteria:
1. Run without errors, dimension validation passes
2. Analyze expert_removal code to detect dimension errors
3. Pre-execute reshape code with zero pollution and auto-fix
4. Validation report outputs completely
5. No modifications to main workspace files (zero pollution)
"""

import json
import os
import sys
import tempfile

# Direct import of shadow_box module to avoid triggering full trae_agent dependency chain
_sb_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trae_agent", "sandbox")
sys.path.insert(0, _sb_dir)
import importlib.util
_spec = importlib.util.spec_from_file_location("shadow_box_62d", os.path.join(_sb_dir, "shadow_box_62d.py"))
_mod = importlib.util.module_from_spec(_spec)
sys.modules["shadow_box_62d"] = _mod
_spec.loader.exec_module(_mod)
ShadowBox62D = _mod.ShadowBox62D
HotNeedleDiagnoser = _mod.HotNeedleDiagnoser
NeuronLayer62D = _mod.NeuronLayer62D


def test_1_sandbox_create_destroy():
    """Test 1: 62-dim zero-trace sandbox create + destroy"""
    print("\n" + "=" * 50)
    print("  TEST 1: 62-dim sandbox create/destroy")
    print("=" * 50)

    box = ShadowBox62D(project_dir=".")

    result = box.create_sandbox()
    assert result["ok"], f"Create failed: {result}"
    assert result["dimensions"] == 62, f"Dimension error: {result['dimensions']}"
    assert result["neurons"] == 52, f"Neuron error: {result['neurons']}"
    assert result["isolation"] == "full_tempdir"
    print(f"  Created: {result['shadow_root']}")
    print(f"  dims={result['dimensions']}, neurons={result['neurons']}")

    status = box.status()
    assert status["active"] is True
    assert status["dimensions"] == 62
    print(f"  Status: active={status['active']}")

    destroy = box.destroy_sandbox()
    assert destroy["ok"], f"Destroy failed: {destroy}"
    assert destroy["zero_pollution"] is True
    print(f"  Destroyed: zero_pollution={destroy['zero_pollution']}")

    print("  PASS")
    return True


def test_2_hot_needle_scan():
    """Test 2: Hot needle precision diagnosis"""
    print("\n" + "=" * 50)
    print("  TEST 2: Hot needle diagnosis")
    print("=" * 50)

    box = ShadowBox62D(project_dir=".")

    test_code_with_errors = '''
import numpy as np

def reshape_expert_tensor(tensor, n_experts=128, dims=[1,2,3]):
    reshaped = tensor.reshape(dims[1], dims[2], n_experts)
    if tensor.shape[0] != reshaped.shape[0]:
        raise ValueError("shape mismatch")
    return reshaped

def quantize_model(weights, quant_type="Q4_K"):
    from ggml_type import dequantize
    result = dequantize(weights, Q2_K)
    return result

def moe_forward(x, gate, experts):
    scores = gate(x)
    top_experts = topk_expert(scores, k=8)
    return sum(experts[i](x) for i in top_experts)

output = "???"
'''

    result = box.hot_needle_scan(code=test_code_with_errors)
    assert result["ok"]
    assert result["total_issues"] > 0, "Should detect issues"
    assert result["critical"] > 0, "Should have critical issues"

    print(f"  Scanned: {result['total_issues']} issues")
    print(f"    Critical: {result['critical']}")
    print(f"    High:     {result['high']}")
    print(f"    Medium:   {result['medium']}")

    for issue in result["issues"]["critical"][:3]:
        print(f"    [{issue['error_type']}] {issue['location']}: {issue['error_detail'][:80]}")

    print("  PASS")
    return True


def test_3_zero_pollution_exec():
    """Test 3: Zero-pollution pre-execution"""
    print("\n" + "=" * 50)
    print("  TEST 3: Zero-pollution execution")
    print("=" * 50)

    box = ShadowBox62D(project_dir=".")

    good_code = "print('Hello from shadow box!')\nprint(2 + 2)"
    result = box.zero_pollution_exec(good_code)
    assert result["ok"], f"Execution failed: {result}"
    assert result["zero_pollution"] is True
    assert "Hello from shadow box!" in result["stdout"]
    print(f"  Normal exec: status={result['status']}")
    print(f"  stdout: {result['stdout'].strip()}")
    print(f"  zero_pollution: {result['zero_pollution']}")

    bad_code = "raise ValueError('test error')"
    result2 = box.zero_pollution_exec(bad_code)
    assert result2["status"] == "failed"
    assert result2["zero_pollution"] is True
    print(f"  Error exec: status={result2['status']}, zero_pollution={result2['zero_pollution']}")

    box.destroy_sandbox()

    print("  PASS")
    return True


def test_4_code_structure_analysis():
    """Test 4: 62-dim code structure analysis"""
    print("\n" + "=" * 50)
    print("  TEST 4: 62-dim structure analysis")
    print("=" * 50)

    repo_root = os.path.dirname(os.path.abspath(__file__))
    target = os.path.join(repo_root, "trae_agent")
    box = ShadowBox62D(project_dir=repo_root)

    result = box.analyze_structure(target)
    assert result["ok"], f"Analysis failed: {result}"
    assert result["dimensions"] == 62
    assert result["neurons"] == 52

    summary = result["summary"]
    print(f"  Files: {summary['files']}")
    print(f"  Lines: {summary['total_lines']}")
    print(f"  Functions: {summary['total_functions']}")
    print(f"  Classes:   {summary['total_classes']}")
    print(f"  Complexity: {summary['complexity_score']}")
    print(f"  Dimensions: {result['dimensions']}")
    print(f"  Neurons:    {result['neurons']}")

    telem = result.get("telemetry_62d", {})
    if telem:
        print(f"  Telemetry: {json.dumps(telem, ensure_ascii=False)}")

    hn = result.get("hot_needle", {})
    print(f"  Hot needle: {hn.get('total_issues', 0)} issues")

    print("  PASS")
    return True


def test_5_real_data_validate():
    """Test 5: Real data validation"""
    print("\n" + "=" * 50)
    print("  TEST 5: Real data validation")
    print("=" * 50)

    box = ShadowBox62D(project_dir=".")

    result = box.validate_real_data()
    assert result["ok"], f"Validation failed: {result}"

    print(f"  62-dim status: {result['62d_dim_status']}")
    print(f"  52-neuron:     {result['52_neuron_status']}")
    print(f"  Hot needle:    {result['hot_needle_detect_count']}")
    print(f"  Zero pollution:{result['zero_pollution_verified']}")
    print(f"  Memory path:   {result['memory_path']}")

    dim_detail = result.get("dim_detail", {})
    dim_values = dim_detail.get("dim_values", {})
    if dim_values:
        print(f"  Active dims: {json.dumps(dim_values, ensure_ascii=False)}")

    print("  PASS")
    return True


def test_6_full_cycle():
    """Test 6: Full cycle"""
    print("\n" + "=" * 50)
    print("  TEST 6: Full cycle")
    print("=" * 50)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write('''
import numpy as np

def process_experts(tensor, n_experts=128):
    reshaped = tensor.reshape(dims[1], n_experts)
    output = dequantize(reshaped, Q4_K)
    return output
''')
        test_file = f.name

    try:
        box = ShadowBox62D(project_dir=os.path.dirname(test_file))
        result = box.full_cycle(
            target=test_file,
            exec_code="print('shadow exec OK')",
        )

        score = result.get("score", {})
        print(f"  Dim check:    {score.get('dim_check')}")
        print(f"  Neuron check: {score.get('neuron_check')}")
        print(f"  Hot needle:   {score.get('hot_needle_issues')} issues")
        print(f"    Critical:   {score.get('critical_issues')}")
        print(f"  Execution:    {score.get('execution')}")
        print(f"  Zero pollut.: {score.get('zero_pollution')}")
        print(f"  Overall:      {score.get('overall')}")

        assert score.get("hot_needle_issues", 0) > 0, "Should detect hot needle issues"

    finally:
        os.unlink(test_file)

    print("  PASS")
    return True


def test_7_neuron_layer():
    """Test 7: 62-dim neuron layer"""
    print("\n" + "=" * 50)
    print("  TEST 7: 62-dim neuron layer")
    print("=" * 50)

    layer = NeuronLayer62D()

    assert len(layer.DIM_NAMES) == 62, f"Dim names count error: {len(layer.DIM_NAMES)}"
    print(f"  Dim names: {len(layer.DIM_NAMES)}")
    print(f"  Last 10: {layer.DIM_NAMES[52:]}")

    dim_result = layer.validate_dimensions()
    assert dim_result["total_dims"] == 62
    print(f"  Validation: total={dim_result['total_dims']}, pass={dim_result['pass']}")

    diagnoser = HotNeedleDiagnoser()
    diags = diagnoser.scan_code("x = tensor.reshape(dims[1], dims[2], n_experts)")
    assert len(diags) > 0, "Should detect diagnosis"
    print(f"  Scan rules: {len(diagnoser._SCAN_RULES)}")
    print(f"  Test diags: {len(diags)} issues")

    print("  PASS")
    return True


if __name__ == "__main__":
    print("\n" + "#" * 60)
    print("  62D Shadow Box — Full Acceptance Test")
    print("#" * 60)

    tests = [
        test_1_sandbox_create_destroy,
        test_2_hot_needle_scan,
        test_3_zero_pollution_exec,
        test_4_code_structure_analysis,
        test_5_real_data_validate,
        test_6_full_cycle,
        test_7_neuron_layer,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            failed += 1
            print(f"  FAIL: {e}")
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 60)
    print(f"  Result: {passed}/{len(tests)} passed, {failed} failed")
    if failed == 0:
        print("  62D Shadow Box: ALL TESTS PASSED!")
    print("=" * 60)
