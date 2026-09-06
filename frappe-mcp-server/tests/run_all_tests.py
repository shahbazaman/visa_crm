"""Runner script to execute all MCP tests in sequence."""
import sys
import os
import subprocess

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
PYTHON_BIN = sys.executable

TEST_FILES = [
    "test_1_server_startup.py",
    "test_2_https_connectivity.py",
    "test_3_4_auth_validation.py",
    "test_5_schema_validation.py",
    "test_6_mcp_tool_execution.py",
    "test_remote_mcp.py",
]

def main():
    print("=" * 60)
    print("STARTING COMPLETE FRAAPPE CRM MCP TEST SUITE")
    print("=" * 60)
    
    for test_file in TEST_FILES:
        path = os.path.join(TESTS_DIR, test_file)
        print(f"\n>>> Running: {test_file}")
        res = subprocess.run([PYTHON_BIN, path])
        if res.returncode != 0:
            print(f"\n[FAILED] {test_file} exited with code {res.returncode}")
            sys.exit(res.returncode)
            
    print("\n" + "=" * 60)
    print("ALL 6 TEST MODULES PASSED (100% SUCCESS)")
    print("=" * 60)

if __name__ == "__main__":
    main()
