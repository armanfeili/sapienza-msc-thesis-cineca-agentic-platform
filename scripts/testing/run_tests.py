#!/usr/bin/env python3
"""Quick test runner to show progress"""
import subprocess
import sys

def run_test(test_file, description):
    """Run a test file and show result"""
    print(f"\n{'='*60}")
    print(f"Running: {description}")
    print(f"File: {test_file}")
    print('='*60)
    
    result = subprocess.run(
        ["python", "-m", "pytest", test_file, "-v", "--tb=line", "-q"],
        capture_output=True,
        text=True,
        timeout=300
    )
    
    # Extract summary line
    lines = result.stdout.split('\n')
    for line in lines[-10:]:
        if 'passed' in line or 'failed' in line or 'error' in line:
            print(line)
    
    return result.returncode == 0

if __name__ == "__main__":
    print("\n🧪 INTEGRATION TEST PROGRESS TRACKER\n")
    
    results = {}
    
    # Test batch operations
    try:
        results['batch_ops'] = run_test(
            "tests/integration/test_batch_operations.py",
            "Batch Operations Tests"
        )
    except Exception as e:
        print(f"❌ Batch operations failed: {e}")
        results['batch_ops'] = False
    
    # Test export/import
    try:
        results['export_import'] = run_test(
            "tests/integration/test_export_import.py",
            "Export/Import Tests"
        )
    except Exception as e:
        print(f"❌ Export/import failed: {e}")
        results['export_import'] = False
    
    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print('='*60)
    for test, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{test}: {status}")
    
    print(f"\nTotal: {sum(results.values())}/{len(results)} test files passed")
