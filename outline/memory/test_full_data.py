#!/usr/bin/env python3
"""Full data loading test for all benchmarks.

Tests that real data (not just samples) can be loaded and parsed.
"""

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

DATASETS_DIR = Path(__file__).parent / "datasets"

def test_locomo_full() -> Dict[str, Any]:
    """Test loading full LoCoMo dataset (10 conversations)."""
    data_file = DATASETS_DIR / "locomo_repo" / "data" / "locomo10.json"
    if not data_file.exists():
        return {"status": "FAIL", "error": f"File not found: {data_file}"}

    try:
        with open(data_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        if not isinstance(data, list):
            return {"status": "FAIL", "error": f"Expected list, got {type(data)}"}

        # Validate all items
        total_qa = 0
        for i, item in enumerate(data):
            required_keys = ['qa', 'conversation', 'sample_id']
            missing = [k for k in required_keys if k not in item]
            if missing:
                return {"status": "FAIL", "error": f"Item {i} missing keys: {missing}"}

            if not isinstance(item['qa'], list):
                return {"status": "FAIL", "error": f"Item {i} qa must be list"}

            total_qa += len(item['qa'])

            # Validate first QA in each conversation
            if item['qa']:
                qa = item['qa'][0]
                if 'question' not in qa or 'answer' not in qa:
                    return {"status": "FAIL", "error": f"Item {i} QA missing question/answer"}

        return {
            "status": "PASS",
            "conversations": len(data),
            "total_qa_pairs": total_qa,
            "avg_qa_per_conv": round(total_qa / len(data), 1),
        }
    except Exception as e:
        return {"status": "FAIL", "error": str(e)}

def test_membench_full() -> Dict[str, Any]:
    """Test loading full MemBench dataset (all task types)."""
    base_dir = DATASETS_DIR / "membench_repo" / "MemData" / "FirstAgent"
    if not base_dir.exists():
        return {"status": "FAIL", "error": f"Directory not found: {base_dir}"}

    try:
        task_files = list(base_dir.glob("*.json"))
        if not task_files:
            return {"status": "FAIL", "error": "No JSON files found"}

        total_roles = 0
        total_events = 0
        total_qa = 0
        task_counts = {}

        for task_file in task_files:
            with open(task_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            if not isinstance(data, dict) or 'roles' not in data:
                return {"status": "FAIL", "error": f"{task_file.name} invalid format"}

            roles = data['roles']
            events = data.get('events', [])

            total_roles += len(roles)
            total_events += len(events)

            # Count QA pairs
            for role in roles:
                if 'QA' in role:
                    total_qa += len(role['QA'])

            task_counts[task_file.stem] = {
                'roles': len(roles),
                'events': len(events),
            }

        return {
            "status": "PASS",
            "task_types": len(task_files),
            "total_roles": total_roles,
            "total_events": total_events,
            "total_qa_pairs": total_qa,
            "tasks": task_counts,
        }
    except Exception as e:
        return {"status": "FAIL", "error": str(e)}

def test_memoryagentbench_full() -> Dict[str, Any]:
    """Test loading MemoryAgentBench dataset from HuggingFace download."""
    data_dir = DATASETS_DIR / "memoryagentbench" / "raw"
    if not data_dir.exists():
        return {
            "status": "SKIP",
            "reason": "Data not downloaded yet",
            "action": "Run: python3 -c 'from huggingface_hub import snapshot_download; snapshot_download(repo_id=\"ai-hyz/MemoryAgentBench\", repo_type=\"dataset\", local_dir=\"datasets/memoryagentbench/raw\")'",
        }

    try:
        # Look for JSONL files
        jsonl_files = list(data_dir.glob("*.jsonl"))
        if not jsonl_files:
            # Maybe it's in a subdirectory
            jsonl_files = list(data_dir.rglob("*.jsonl"))

        if not jsonl_files:
            return {
                "status": "FAIL",
                "error": f"No .jsonl files found in {data_dir}",
                "hint": "Check if download completed successfully",
            }

        file_stats = {}
        total_lines = 0

        for jsonl_file in jsonl_files:
            line_count = 0
            with open(jsonl_file, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        # Validate it's valid JSON
                        try:
                            json.loads(line)
                            line_count += 1
                        except json.JSONDecodeError as e:
                            return {
                                "status": "FAIL",
                                "error": f"{jsonl_file.name} line {line_count+1}: {e}",
                            }

            file_stats[jsonl_file.name] = line_count
            total_lines += line_count

        return {
            "status": "PASS",
            "files": len(jsonl_files),
            "total_samples": total_lines,
            "breakdown": file_stats,
        }
    except Exception as e:
        return {"status": "FAIL", "error": str(e)}

def main():
    tests = [
        ("LoCoMo (full)", test_locomo_full),
        ("MemBench (full)", test_membench_full),
        ("MemoryAgentBench (full)", test_memoryagentbench_full),
    ]

    results = {}
    for name, test_fn in tests:
        print(f"Testing {name}...", end=" ")
        result = test_fn()
        results[name] = result
        status = result["status"]
        if status == "PASS":
            print("✓ PASS")
        elif status == "SKIP":
            print(f"⊘ SKIP")
        else:
            print(f"✗ FAIL")

    # Summary
    print("\n" + "="*70)
    print("FULL DATA LOADING TEST SUMMARY")
    print("="*70)
    for name, result in results.items():
        status = result["status"]
        print(f"\n{name}")
        print(f"  Status: {status}")
        if status == "PASS":
            for k, v in result.items():
                if k != "status":
                    if isinstance(v, dict):
                        print(f"  {k}:")
                        for sk, sv in list(v.items())[:5]:  # Show first 5 items
                            print(f"    {sk}: {sv}")
                        if len(v) > 5:
                            print(f"    ... and {len(v)-5} more")
                    else:
                        print(f"  {k}: {v}")
        elif status == "SKIP":
            print(f"  Reason: {result.get('reason', 'N/A')}")
            if 'action' in result:
                print(f"  Action: {result['action'][:100]}...")
        else:
            print(f"  Error: {result.get('error', 'Unknown')}")

    # Exit code
    passed = sum(1 for r in results.values() if r["status"] == "PASS")
    skipped = sum(1 for r in results.values() if r["status"] == "SKIP")
    failed = sum(1 for r in results.values() if r["status"] == "FAIL")

    print(f"\nPassed: {passed}, Skipped: {skipped}, Failed: {failed}")

    if failed > 0:
        print("\n✗ Some tests failed. Fix errors before proceeding.")
        sys.exit(1)
    elif passed >= 2:  # At least 2 benchmarks must work
        print("\n✓ Data loading tests complete. Ready for evaluation.")
        sys.exit(0)
    else:
        print("\n⚠ Not enough benchmarks ready. Need at least 2 passing.")
        sys.exit(1)

if __name__ == "__main__":
    main()
