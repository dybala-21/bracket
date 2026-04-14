from bracket import Harness, ExecutionContract


def main():
    contract = ExecutionContract.code_change(
        goal="Fix failing test and verify it passes",
        requires_verification=True,
    )

    harness = Harness(app_name="acme-agent", artifact_dir=".bracket")
    run = harness.start_run(contract)

    run.record_file_read("app.py", byte_count=1842)
    run.record_tool_call("file.read", {"path": "app.py"})
    run.record_file_changed("app.py")
    run.record_tool_success("file.write")
    run.record_command("pytest tests/test_app.py", exit_code=0, kind="verification")

    result = harness.finish_run_sync(run, final_output="Updated app.py and pytest passed.")

    print(f"Verdict: {result.verdict.outcome.value}")
    print(f"Missing: {result.verdict.missing_requirement_ids}")
    print(f"Explanation: {result.verdict.explanation}")
    print(f"Artifact saved: .bracket/runs/{run.run_id}/")


if __name__ == "__main__":
    main()
