import os
import queue
import subprocess
import sys
import threading
import time
import uuid

import pytest
from pathlib import Path

SCRIPT = Path(__file__).with_name("recovery_across_processes.py")
PYTHON = sys.executable

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        not os.environ.get("AGENTFORGE_DB_PASSWORD"),
        reason="PostgreSQL integration test requires AGENTFORGE_DB_PASSWORD",
    ),
]


def run_recovery_process(mode, thread_id):
    env = os.environ.copy()
    env["AGENTFORGE_TEST_THREAD_ID"] = thread_id
    result = subprocess.run(
        [PYTHON, str(SCRIPT), mode],
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0, (
        f"Recovery process {mode!r} failed with exit code "
        f"{result.returncode}:\n{output}"
    )
    return output


def test_recovery_across_separate_processes():
    thread_id = f"agentforge-recovery-{uuid.uuid4().hex}"
    pause_output = run_recovery_process("pause", thread_id)
    assert "Process 1 paused: True" in pause_output

    resume_output = run_recovery_process("resume", thread_id)
    assert "Process 2 recovered: True" in resume_output
    assert (
        "Final events: ['step_one_completed', "
        "'step_two_resumed:continue']"
    ) in resume_output
    assert resume_output.count("step_one_completed") == 1


def test_recovery_after_forced_process_termination():
    thread_id = f"agentforge-kill-recovery-{uuid.uuid4().hex}"
    env = os.environ.copy()
    env["AGENTFORGE_TEST_THREAD_ID"] = thread_id
    env["AGENTFORGE_HOLD_AFTER_CHECKPOINT"] = "1"

    process = subprocess.Popen(
        [PYTHON, str(SCRIPT), "pause"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=env,
    )

    lines = queue.Queue()
    captured = []

    def read_output():
        try:
            for line in process.stdout:
                lines.put(line)
        finally:
            lines.put(None)

    reader = threading.Thread(target=read_output, daemon=True)
    reader.start()

    deadline = time.monotonic() + 30
    checkpoint_seen = False

    try:
        while time.monotonic() < deadline:
            try:
                line = lines.get(timeout=min(0.2, max(0.01, deadline - time.monotonic())))
            except queue.Empty:
                if process.poll() is not None:
                    break
                continue

            if line is None:
                break

            captured.append(line)
            if "CHECKPOINT_SAVED_AND_WAITING" in line:
                checkpoint_seen = True
                break

        output = "".join(captured)
        assert checkpoint_seen, (
            "Process 1 did not confirm its saved interrupt checkpoint. "
            f"Captured output:\n{output}"
        )
        assert "Process 1 paused: True" in output

        # On Windows, terminate() forcibly terminates the child process.
        process.terminate()
        process.wait(timeout=10)
        assert process.poll() is not None, "Process 1 did not terminate."

    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=10)
        reader.join(timeout=5)
        if process.stdin:
            process.stdin.close()
        if process.stdout:
            process.stdout.close()

    resume_output = run_recovery_process("resume", thread_id)
    assert "Process 2 recovered: True" in resume_output
    assert (
        "Final events: ['step_one_completed', "
        "'step_two_resumed:continue']"
    ) in resume_output
    assert resume_output.count("step_one_completed") == 1
