from pathlib import Path
import json
import hashlib
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def _hashed_envelope(envelope: dict) -> dict:
    payload = dict(envelope)
    payload.pop("envelope_hash", None)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return {**envelope, "envelope_hash": "sha256:" + hashlib.sha256(encoded).hexdigest()}


def test_metaloop_skill_declares_entry_and_enforcement_boundary() -> None:
    skill = (ROOT / "skills" / "metaloop" / "SKILL.md").read_text(encoding="utf-8")
    openai_yaml = (ROOT / "skills" / "metaloop" / "agents" / "openai.yaml").read_text(encoding="utf-8")

    assert "name: metaloop" in skill
    assert "scripts/metaloop_kernel.py" in skill
    assert "do not assume a separate `metaloop` command is installed" in skill
    assert "MetaLoop is skill-first, not prompt-only." in skill
    assert "Prompt handles intelligence. Code handles truth." in skill
    assert "Skill handles entry and alignment." in skill
    assert "Use `scripts/metaloop_kernel.py` for" in skill
    assert "Hooks, sandbox, or wrapper runtime handle stronger non-bypassable constraints" in skill
    assert "Do not weaken locked acceptance after execution" in skill
    assert "Replacing a locked capsule requires a revision reason" in skill
    assert "outcome-first" in skill
    assert "stopping conditions" in skill
    assert "bounded inspection" in skill
    assert "Run relevant tests" in skill
    assert "If validation cannot run, say why" in skill
    assert "The user should be able to say only" in skill
    assert "Do not require the user to ask for Mission Capsules" in skill
    assert "VerificationSpecs" in skill
    assert "single_node" in skill
    assert "multi_thread" in skill
    assert "routable_work_units" in skill
    assert "ask only questions that change the target" in skill
    assert "global_blackboard.json" in skill
    assert "dispatch_map.json" in skill
    assert "job_envelope.json" in skill
    assert "Do not use routable work units just because a task is large" in skill
    assert "read-only summaries" in skill
    assert ".metaloop/control/" in skill
    assert "metaloop_dashboard.py" in skill
    assert "activate" in skill
    assert "context" in skill
    assert "Six-Gate Model" in skill
    assert "Design Gate" in skill
    assert "State Checkpoint" in skill
    assert "Verification Gate" in skill
    assert "Control Point" in skill
    assert "Observation Surface" in skill
    assert "Safe-point discipline" in skill
    assert "do not make a" in skill
    assert "dashboard or observer silently route work" in skill
    assert "must not expose endpoints that write controls" in skill
    assert 'display_name: "MetaLoop"' in openai_yaml
    assert 'default_prompt: "Use $metaloop' in openai_yaml
    assert "Infer the task shape" in openai_yaml
    assert "ask only blocking questions" in openai_yaml


def test_metaloop_skill_reference_captures_lightweight_protocol() -> None:
    reference = (ROOT / "skills" / "metaloop" / "references" / "lightweight_protocol.md").read_text(encoding="utf-8")

    assert "Codex's task design and stable execution protocol layer" in reference
    assert "$metaloop skill" in reference
    assert "Bundled scripts / schemas / validators" in reference
    assert "hooks / sandbox / wrapper runtime" in reference
    assert "must not require the target machine to have the MetaLoop repository installed" in reference
    assert "repair" in reference
    assert "redesign" in reference
    assert "ExtensionSpec" in reference
    assert "Manual or unsupported blocking checks" in reference
    assert "extensions/<domain>/" in reference
    assert "Persistent Agent Threads" in reference
    assert ".metaloop/threads.json" in reference
    assert "Thread context is useful for intelligence" in reference
    assert "Event Log" in reference
    assert ".metaloop/event_log.jsonl" in reference
    assert "Adaptive Goal Loop" in reference
    assert "Goal -> Plan -> Act -> Observe -> Evaluate -> Diagnose -> Decide -> Next Plan" in reference
    assert "Prompt-first for intelligence and code-backed for truth" in reference
    assert "Prompt Surface" in reference
    assert "outcome-first" in reference
    assert "bounded inspection" in reference
    assert "process-heavy prompts" in reference
    assert "context" in reference
    assert "Six Control Gates" in reference


def test_six_gate_model_doc_is_linked_and_runtime_bounded() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    doc = (ROOT / "docs" / "metaloop_six_gate_model.md").read_text(encoding="utf-8")

    assert "docs/metaloop_six_gate_model.md" in readme
    assert "MetaLoop is not an agent runtime" in doc
    assert "Design Gate" in doc
    assert "State Checkpoint" in doc
    assert "Verification Gate" in doc
    assert "Adaptive Loop" in doc
    assert "Control Point" in doc
    assert "Observation Surface" in doc
    assert "Safe-Point Protocol" in doc
    assert "Do not" in doc
    assert "build a hidden scheduler" in doc


def test_prompt_first_code_backed_reference_is_packaged_and_linked() -> None:
    skill = (ROOT / "skills" / "metaloop" / "SKILL.md").read_text(encoding="utf-8")
    reference = (ROOT / "skills" / "metaloop" / "references" / "prompt_first_code_backed.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    design = (ROOT / "docs" / "metaloop_design_autonomy.md").read_text(encoding="utf-8")

    assert "references/prompt_first_code_backed.md" in skill
    assert "Prompt handles intelligence. Code handles truth." in reference
    assert "Use prompt / skill instructions / examples" in reference
    assert "Use code / kernel / validators" in reference
    assert "Prefer examples before framework code" in reference
    assert "Do not add a new Python module for every useful reasoning pattern." in reference
    assert "Prompt-first / code-backed" in readme
    assert "docs/metaloop_design_autonomy.md" in readme
    assert "Design Autonomy" in design
    assert "single_node" in design
    assert "routable_work_units" in design
    assert "Outcome-First Skill Surface" in (ROOT / "docs" / "metaloop_prompt_first_code_backed.md").read_text(encoding="utf-8")


def test_multi_thread_protocol_doc_is_linked_and_boundary_focused() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    doc = (ROOT / "docs" / "metaloop_multi_thread_agent_protocol.md").read_text(encoding="utf-8")

    assert "docs/metaloop_multi_thread_agent_protocol.md" in readme
    assert ".metaloop/threads.json" in doc
    assert ".metaloop/event_log.jsonl" in doc
    assert "does not schedule background agents by itself" in doc
    assert "Thread context is useful but not authoritative" in doc
    assert "Events do not change locked contracts" in doc
    assert "Do not use one-shot `codex exec` as the default intelligence layer" in doc


def test_observability_control_doc_is_linked_and_read_only() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    doc = (ROOT / "docs" / "metaloop_observability_control.md").read_text(encoding="utf-8")

    assert "docs/metaloop_observability_control.md" in readme
    assert "Dashboard reads truth." in doc
    assert "Control writes intent." in doc
    assert "Observability is read-only." in doc
    assert "metaloop_dashboard.py" in doc
    assert "no mutation routes" in doc
    assert ".metaloop/control/" in doc
    assert "It does not directly kill" in doc
    assert "processes or modify Mission Capsules." in doc
    assert "activation" in doc


def test_bundled_dashboard_is_read_only_and_dependency_free(tmp_path) -> None:
    dashboard = ROOT / "skills" / "metaloop" / "scripts" / "metaloop_dashboard.py"
    source = dashboard.read_text(encoding="utf-8")

    assert "ThreadingHTTPServer" in source
    assert "do_POST" not in source
    assert "activate_once" not in source
    assert "write_control" not in source
    assert "write_text" not in source

    completed = subprocess.run(
        [sys.executable, "-m", "py_compile", str(dashboard)],
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


def test_metaloop_skill_contains_generic_extension_package() -> None:
    profile = json.loads((ROOT / "skills" / "metaloop" / "extensions" / "generic" / "profile.json").read_text(encoding="utf-8"))
    schema = json.loads((ROOT / "skills" / "metaloop" / "extensions" / "generic" / "verification_schema.json").read_text(encoding="utf-8"))
    example = json.loads((ROOT / "skills" / "metaloop" / "extensions" / "generic" / "examples" / "basic.json").read_text(encoding="utf-8"))

    assert profile["domain"] == "generic"
    assert any(item["type"] == "json_metric_gate" for item in profile["validator_types"])
    assert schema["validator_fields"]["resource_gate"]
    assert example["extension_spec"]["schema"] == "metaloop.extension_spec"


def test_bundled_skill_kernel_design_status_and_verify(tmp_path) -> None:
    kernel = ROOT / "skills" / "metaloop" / "scripts" / "metaloop_kernel.py"
    target = tmp_path / "result.txt"

    design = subprocess.run(
        [
            sys.executable,
            str(kernel),
            "--workspace",
            str(tmp_path),
            "design",
            "--intent",
            "Create result.txt",
            "--rationale",
            "File output is the smallest verifiable artifact.",
            "--non-goal",
            "Do not create unrelated files.",
            "--file-exists",
            "result.txt",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert design.returncode == 0
    assert (tmp_path / ".metaloop" / "mission_capsule.json").exists()

    first_verify = subprocess.run(
        [sys.executable, str(kernel), "--workspace", str(tmp_path), "verify"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert first_verify.returncode == 1
    assert "verification: missing_execution_report" in first_verify.stdout

    run = subprocess.run(
        [
            sys.executable,
            str(kernel),
            "--workspace",
            str(tmp_path),
            "run",
            "--command",
            "printf 'done\\n' > result.txt",
            "--evidence",
            "result.txt was created by the run wrapper.",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert run.returncode == 0
    assert "execution: completed" in run.stdout
    assert target.read_text(encoding="utf-8") == "done\n"
    assert (tmp_path / ".metaloop" / "execution_report.json").exists()

    second_verify = subprocess.run(
        [sys.executable, str(kernel), "--workspace", str(tmp_path), "verify"],
        text=True,
        capture_output=True,
        check=False,
    )

    assert second_verify.returncode == 0
    assert "verification: completed_verified" in second_verify.stdout
    assert (tmp_path / ".metaloop" / "verification_result.json").exists()


def test_bundled_skill_kernel_tick_and_relay_routable_work_unit(tmp_path) -> None:
    kernel = ROOT / "skills" / "metaloop" / "scripts" / "metaloop_kernel.py"
    source = tmp_path / "source"
    source.mkdir()
    target = tmp_path / "target"
    (source / ".metaloop").mkdir()
    (source / ".metaloop" / "verification_result.json").write_text(json.dumps({"status": "completed_verified"}), encoding="utf-8")

    envelope = _hashed_envelope(
        {
            "schema": "metaloop.job_envelope",
            "version": "1.0",
            "job_id": "job-source-001",
            "parent_job_id": None,
            "created_at": "2026-05-12T00:00:00Z",
            "assigned_role": "source_role",
            "attempt": 1,
            "retry_count": 0,
            "policy_version": "1.0",
            "intent": {
                "commander_intent": "Produce a generic verified artifact.",
                "global_blackboard_ref": "./global_blackboard.json",
                "blackboard_hash": "sha256:source",
            },
            "payload": {},
            "contract": {
                "expected_outputs": [{"path": "artifact.json", "kind": "artifact", "hash": "sha256:artifact"}],
                "handoff_policy": {
                    "on_success": {"action": "dispatch", "next_role": "target_role"},
                    "on_repair": {"action": "loop_back", "max_retries": 3},
                    "on_redesign": {"action": "route_to", "next_role": "design_role"},
                    "on_blocked": {"action": "escalate", "notify": "human_operator"},
                    "on_human_acceptance": {"action": "suspend", "notify": "human_operator"},
                    "on_contract_defect": {"action": "route_to", "next_role": "design_role"},
                },
            },
        }
    )
    (source / "job_envelope.json").write_text(json.dumps(envelope, indent=2), encoding="utf-8")

    tick = subprocess.run(
        [sys.executable, str(kernel), "--workspace", str(source), "tick", "--json"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert tick.returncode == 0, tick.stderr
    tick_result = json.loads(tick.stdout)
    assert tick_result["route"]["action"] == "dispatch"
    assert (source / ".metaloop" / "outbox" / "target_role.json").exists()

    (source / "global_blackboard.json").write_text("{}", encoding="utf-8")
    template_dir = source / "templates"
    template_dir.mkdir()
    template = {
        "schema": "metaloop.job_envelope",
        "version": "1.0",
        "assigned_role": "target_role",
        "policy_version": "1.0",
        "intent": {
            "commander_intent": "Consume the upstream verified artifact.",
            "global_blackboard_ref": "",
            "blackboard_hash": "",
        },
        "payload": {},
        "contract": {
            "expected_outputs": [{"path": "result.json", "kind": "artifact", "hash": "sha256:result"}],
            "handoff_policy": {
                "on_success": {"action": "dispatch", "next_role": "review_role"},
                "on_repair": {"action": "loop_back", "max_retries": 3},
                "on_redesign": {"action": "route_to", "next_role": "design_role"},
                "on_blocked": {"action": "escalate", "notify": "human_operator"},
                "on_human_acceptance": {"action": "suspend", "notify": "human_operator"},
                "on_contract_defect": {"action": "route_to", "next_role": "design_role"},
            },
        },
    }
    (template_dir / "target_job_envelope.json").write_text(json.dumps(template, indent=2), encoding="utf-8")
    dispatch_map = {
        "schema": "metaloop.dispatch_map",
        "version": "1.0",
        "routes": [
            {
                "target": "target_role",
                "workspace": "../target",
                "role": "target_role",
                "envelope_template": "templates/target_job_envelope.json",
                "blackboard_path": "global_blackboard.json",
            }
        ],
    }
    (source / "dispatch_map.json").write_text(json.dumps(dispatch_map, indent=2), encoding="utf-8")

    relay = subprocess.run(
        [sys.executable, str(kernel), "--workspace", str(source), "relay", "--dispatch-map", "dispatch_map.json", "--json"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert relay.returncode == 0, relay.stderr
    relay_result = json.loads(relay.stdout)
    assert relay_result["status"] == "completed"
    assert (target / "job_envelope.json").exists()
    target_envelope = json.loads((target / "job_envelope.json").read_text(encoding="utf-8"))
    assert target_envelope["parent_job_id"] == "job-source-001"
    assert target_envelope["assigned_role"] == "target_role"
    assert (target / ".metaloop" / "inbox" / "job-source-001.json").exists()


def test_bundled_skill_kernel_observe_control_and_activate(tmp_path) -> None:
    kernel = ROOT / "skills" / "metaloop" / "scripts" / "metaloop_kernel.py"
    node = tmp_path / "node"
    node.mkdir()
    envelope = _hashed_envelope(
        {
            "schema": "metaloop.job_envelope",
            "version": "1.0",
            "job_id": "job-activation-001",
            "parent_job_id": None,
            "created_at": "2026-05-12T00:00:00Z",
            "assigned_role": "worker",
            "attempt": 1,
            "retry_count": 0,
            "policy_version": "1.0",
            "intent": {
                "commander_intent": "Handle the delivered work unit.",
                "global_blackboard_ref": "./global_blackboard.json",
                "blackboard_hash": "sha256:source",
            },
            "payload": {},
            "contract": {
                "expected_outputs": [{"path": "result.json", "kind": "artifact", "hash": "sha256:result"}],
                "handoff_policy": {
                    "on_success": {"action": "dispatch", "next_role": "reviewer"},
                    "on_repair": {"action": "loop_back", "max_retries": 3},
                    "on_redesign": {"action": "route_to", "next_role": "designer"},
                    "on_blocked": {"action": "escalate", "notify": "human_operator"},
                    "on_human_acceptance": {"action": "suspend", "notify": "human_operator"},
                    "on_contract_defect": {"action": "route_to", "next_role": "designer"},
                },
            },
        }
    )
    (node / "job_envelope.json").write_text(json.dumps(envelope, indent=2), encoding="utf-8")

    observe = subprocess.run(
        [sys.executable, str(kernel), "--workspace", str(node), "observe", "--json"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert observe.returncode == 0, observe.stderr
    summary = json.loads(observe.stdout)
    assert summary["schema"] == "metaloop.node_summary"
    assert summary["node_id"] == "job-activation-001"
    assert summary["goal"] == "Handle the delivered work unit."

    observe_brief = subprocess.run(
        [sys.executable, str(kernel), "--workspace", str(node), "observe", "--format", "brief", "--json"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert observe_brief.returncode == 0, observe_brief.stderr
    brief = json.loads(observe_brief.stdout)
    assert brief["schema"] == "metaloop.node_brief"
    assert brief["node_id"] == "job-activation-001"
    assert "next_action" in brief

    activate_dry_run = subprocess.run(
        [sys.executable, str(kernel), "--workspace", str(tmp_path), "activate", "--worker-command", "printf started > marker.txt", "--json"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert activate_dry_run.returncode == 0, activate_dry_run.stderr
    activation = json.loads(activate_dry_run.stdout)
    assert activation["schema"] == "metaloop.activation_result"
    assert activation["dry_run"] is True
    assert activation["counts"]["ready"] == 1
    assert not (node / "marker.txt").exists()

    control = subprocess.run(
        [
            sys.executable,
            str(kernel),
            "--workspace",
            str(node),
            "control",
            "write",
            "--type",
            "halt",
            "--reason",
            "Pause before starting the next attempt.",
            "--json",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert control.returncode == 0, control.stderr
    assert json.loads(control.stdout)["schema"] == "metaloop.control_request"

    blocked = subprocess.run(
        [
            sys.executable,
            str(kernel),
            "--workspace",
            str(tmp_path),
            "activate",
            "--worker-command",
            "printf started > marker.txt",
            "--execute",
            "--json",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert blocked.returncode == 0, blocked.stderr
    blocked_result = json.loads(blocked.stdout)
    assert blocked_result["counts"]["blocked_by_control"] == 1
    assert not (node / "marker.txt").exists()


def test_bundled_skill_kernel_context_checkpoints(tmp_path) -> None:
    kernel = ROOT / "skills" / "metaloop" / "scripts" / "metaloop_kernel.py"

    init = subprocess.run(
        [sys.executable, str(kernel), "--workspace", str(tmp_path), "context", "init", "--json"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert init.returncode == 0, init.stderr
    payload = json.loads(init.stdout)
    assert len(payload["created"]) == 4
    assert payload["summary"]["schema"] == "metaloop.context_summary"

    write = subprocess.run(
        [
            sys.executable,
            str(kernel),
            "--workspace",
            str(tmp_path),
            "context",
            "write",
            "--file",
            "resume_brief.md",
            "--content",
            "# Resume Brief\n\n## Current Goal\n\n- Preserve enough context to resume.",
            "--json",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert write.returncode == 0, write.stderr
    assert json.loads(write.stdout)["name"] == "resume_brief.md"

    read = subprocess.run(
        [sys.executable, str(kernel), "--workspace", str(tmp_path), "context", "read", "--file", "resume_brief.md"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert read.returncode == 0, read.stderr
    assert "Preserve enough context to resume" in read.stdout

    status = subprocess.run(
        [sys.executable, str(kernel), "--workspace", str(tmp_path), "status", "--json"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert status.returncode == 0, status.stderr
    assert json.loads(status.stdout)["context"]["ready_count"] == 4


def test_bundled_skill_kernel_tracks_persistent_agent_threads(tmp_path) -> None:
    kernel = ROOT / "skills" / "metaloop" / "scripts" / "metaloop_kernel.py"

    missing_status = subprocess.run(
        [sys.executable, str(kernel), "--workspace", str(tmp_path), "threads", "status"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert missing_status.returncode == 0
    assert "threads: missing" in missing_status.stdout

    register = subprocess.run(
        [
            sys.executable,
            str(kernel),
            "--workspace",
            str(tmp_path),
            "threads",
            "register",
            "--role",
            "design",
            "--role-type",
            "design",
            "--thread-id",
            "thread-design-123",
            "--agent-name",
            "Design Agent",
            "--responsibility",
            "Draft Mission Capsule and VerificationSpec before execution.",
            "--note",
            "Registered during design handoff.",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert register.returncode == 0
    assert "thread: design" in register.stdout

    registry_path = tmp_path / ".metaloop" / "threads.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    assert registry["schema"] == "metaloop.thread_registry"
    assert registry["agents"]["design"]["thread_id"] == "thread-design-123"
    assert registry["agents"]["design"]["role_type"] == "design"
    assert "shared operational truth is .metaloop artifacts" in registry["coordination_rule"]

    status = subprocess.run(
        [sys.executable, str(kernel), "--workspace", str(tmp_path), "status"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert status.returncode == 0
    assert "threads: ready count=1" in status.stdout

    update = subprocess.run(
        [
            sys.executable,
            str(kernel),
            "--workspace",
            str(tmp_path),
            "threads",
            "update",
            "--role",
            "design",
            "--status",
            "handoff_required",
            "--note",
            "Design thread needs reviewer handoff.",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert update.returncode == 0
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    assert registry["agents"]["design"]["status"] == "handoff_required"
    assert registry["agents"]["design"]["history"][-1]["event"] == "updated"


def test_bundled_skill_kernel_records_long_task_events(tmp_path) -> None:
    kernel = ROOT / "skills" / "metaloop" / "scripts" / "metaloop_kernel.py"

    register = subprocess.run(
        [
            sys.executable,
            str(kernel),
            "--workspace",
            str(tmp_path),
            "threads",
            "register",
            "--role",
            "worker",
            "--role-type",
            "worker",
            "--thread-id",
            "thread-worker-456",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert register.returncode == 0

    append = subprocess.run(
        [
            sys.executable,
            str(kernel),
            "--workspace",
            str(tmp_path),
            "event",
            "append",
            "--type",
            "observation",
            "--agent",
            "worker",
            "--summary",
            "CUDA unavailable; full training cannot start.",
            "--evidence",
            "nvidia-smi failed",
            "--next-action",
            "mark blocked or redesign resource gate",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert append.returncode == 0
    assert "event: event-" in append.stdout

    event_log = tmp_path / ".metaloop" / "event_log.jsonl"
    lines = event_log.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    event = json.loads(lines[0])
    assert event["schema"] == "metaloop.event"
    assert event["type"] == "observation"
    assert event["thread_id"] == "thread-worker-456"
    assert event["evidence"] == ["nvidia-smi failed"]

    listed = subprocess.run(
        [sys.executable, str(kernel), "--workspace", str(tmp_path), "event", "list", "--limit", "1"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert listed.returncode == 0
    assert "events: ready count=1" in listed.stdout
    assert "CUDA unavailable" in listed.stdout

    status = subprocess.run(
        [sys.executable, str(kernel), "--workspace", str(tmp_path), "status", "--json"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert status.returncode == 0
    payload = json.loads(status.stdout)
    assert payload["events"]["state"] == "ready"
    assert payload["events"]["count"] == 1
    assert payload["events"]["latest"]["summary"] == "CUDA unavailable; full training cannot start."


def test_bundled_skill_kernel_records_adaptive_goal_loop(tmp_path) -> None:
    kernel = ROOT / "skills" / "metaloop" / "scripts" / "metaloop_kernel.py"

    init = subprocess.run(
        [
            sys.executable,
            str(kernel),
            "--workspace",
            str(tmp_path),
            "adaptive",
            "init",
            "--goal",
            "Improve a measurable target.",
            "--current-plan",
            "Run a high-signal first attempt.",
            "--success-criterion",
            "Locked VerificationSpec passes.",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert init.returncode == 0, init.stderr
    assert "adaptive_loop: initialized" in init.stdout

    record = subprocess.run(
        [
            sys.executable,
            str(kernel),
            "--workspace",
            str(tmp_path),
            "adaptive",
            "record",
            "--plan",
            "Run a high-signal first attempt.",
            "--observation",
            "The attempt produced evidence but did not satisfy the metric gate.",
            "--evaluation-status",
            "not_satisfied",
            "--diagnosis",
            "The implementation likely contains a bug in the attempted change.",
            "--next-plan",
            "Repair the implementation bug and rerun the same gate.",
            "--evidence",
            ".metaloop/verification_result.json",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert record.returncode == 0, record.stderr
    assert "decision: repair" in record.stdout

    state = json.loads((tmp_path / ".metaloop" / "adaptive_loop.json").read_text(encoding="utf-8"))
    assert state["schema"] == "metaloop.adaptive_goal_loop"
    assert state["iterations"][0]["decision"] == "repair"

    status = subprocess.run(
        [sys.executable, str(kernel), "--workspace", str(tmp_path), "status"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert status.returncode == 0
    assert "adaptive_loop: ready status=active" in status.stdout


def test_bundled_skill_kernel_does_not_hard_verify_manual_only_acceptance(tmp_path) -> None:
    kernel = ROOT / "skills" / "metaloop" / "scripts" / "metaloop_kernel.py"
    target = tmp_path / "review.txt"

    shallow_design = subprocess.run(
        [
            sys.executable,
            str(kernel),
            "--workspace",
            str(tmp_path),
            "design",
            "--intent",
            "Produce a result that needs human review",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert shallow_design.returncode == 1
    assert "at least one --rationale" in shallow_design.stderr

    manual_only_without_override = subprocess.run(
        [
            sys.executable,
            str(kernel),
            "--workspace",
            str(tmp_path),
            "design",
            "--intent",
            "Produce a result that needs human review",
            "--rationale",
            "Human usefulness is the core acceptance boundary.",
            "--non-goal",
            "Do not claim automated completion.",
            "--acceptance",
            "User confirms the result is useful.",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert manual_only_without_override.returncode == 1
    assert "at least one executable validator" in manual_only_without_override.stderr

    design = subprocess.run(
        [
            sys.executable,
            str(kernel),
            "--workspace",
            str(tmp_path),
            "design",
            "--intent",
            "Produce a result that needs human review",
            "--rationale",
            "Human usefulness is the core acceptance boundary.",
            "--non-goal",
            "Do not claim automated completion.",
            "--acceptance",
            "User confirms the result is useful.",
            "--allow-manual-only",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert design.returncode == 0

    verify = subprocess.run(
        [sys.executable, str(kernel), "--workspace", str(tmp_path), "verify"],
        text=True,
        capture_output=True,
        check=False,
    )

    assert verify.returncode == 1
    assert "verification: missing_execution_report" in verify.stdout

    status = subprocess.run(
        [sys.executable, str(kernel), "--workspace", str(tmp_path), "status"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert status.returncode == 0
    assert "next_action: Run execution through the lightweight kernel" in status.stdout

    redesign_without_reason = subprocess.run(
        [
            sys.executable,
            str(kernel),
            "--workspace",
            str(tmp_path),
            "design",
            "--intent",
            "Produce a result that needs human review",
            "--rationale",
            "Human usefulness is the core acceptance boundary.",
            "--non-goal",
            "Do not claim automated completion.",
            "--acceptance",
            "User confirms the result is useful.",
            "--file-exists",
            "review.txt",
            "--force",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert redesign_without_reason.returncode == 1
    assert "revision_reason_required" in redesign_without_reason.stderr

    design_with_hard_validator = subprocess.run(
        [
            sys.executable,
            str(kernel),
            "--workspace",
            str(tmp_path),
            "design",
            "--intent",
            "Produce a result that needs human review",
            "--rationale",
            "Human usefulness is the core acceptance boundary.",
            "--non-goal",
            "Do not claim automated completion.",
            "--acceptance",
            "User confirms the result is useful.",
            "--file-exists",
            "review.txt",
            "--force",
            "--revision-reason",
            "Add executable file validation to the locked contract.",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert design_with_hard_validator.returncode == 0

    run_with_manual_acceptance = subprocess.run(
        [
            sys.executable,
            str(kernel),
            "--workspace",
            str(tmp_path),
            "run",
            "--command",
            "printf 'ready for review\\n' > review.txt",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert run_with_manual_acceptance.returncode == 0
    assert target.read_text(encoding="utf-8") == "ready for review\n"

    verify_with_manual_acceptance = subprocess.run(
        [sys.executable, str(kernel), "--workspace", str(tmp_path), "verify"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert verify_with_manual_acceptance.returncode == 1
    assert "verification: human_acceptance_required" in verify_with_manual_acceptance.stdout


def test_bundled_skill_kernel_supports_locked_json_metric_verification_spec(tmp_path) -> None:
    kernel = ROOT / "skills" / "metaloop" / "scripts" / "metaloop_kernel.py"
    gate = json.dumps({"path": "summary.json", "metric": "held_out.peak1_delta", "operator": ">=", "threshold": 0})

    design = subprocess.run(
        [
            sys.executable,
            str(kernel),
            "--workspace",
            str(tmp_path),
            "design",
            "--intent",
            "Write a summary with a non-regressing held-out metric",
            "--rationale",
            "The metric gate is the locked completion definition.",
            "--non-goal",
            "Do not claim completion from a missing summary.",
            "--json-metric-gate",
            gate,
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert design.returncode == 0

    capsule_path = tmp_path / ".metaloop" / "mission_capsule.json"
    capsule = json.loads(capsule_path.read_text(encoding="utf-8"))
    spec = capsule["verification_spec"]
    assert spec["schema"] == "metaloop.verification_spec"
    assert spec["domain"] == "generic"
    assert spec["extension_hash"].startswith("sha256:")
    assert spec["validators"][0]["type"] == "json_metric_gate"

    run = subprocess.run(
        [
            sys.executable,
            str(kernel),
            "--workspace",
            str(tmp_path),
            "run",
            "--command",
            "printf '{\"held_out\":{\"peak1_delta\":0.1}}' > summary.json",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert run.returncode == 0

    verify = subprocess.run(
        [sys.executable, str(kernel), "--workspace", str(tmp_path), "verify", "--json"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert verify.returncode == 0
    result = json.loads(verify.stdout)
    assert result["status"] == "completed_verified"
    assert result["verification_spec_domain"] == "generic"
    assert result["extension_hash"] == spec["extension_hash"]
    assert result["hard_validator_results"][0]["actual"] == 0.1

    capsule["verification_spec"]["validators"][0]["threshold"] = 1
    capsule_path.write_text(json.dumps(capsule, indent=2), encoding="utf-8")
    tampered_verify = subprocess.run(
        [sys.executable, str(kernel), "--workspace", str(tmp_path), "verify"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert tampered_verify.returncode == 1
    assert "verification: invalid_capsule" in tampered_verify.stdout


def test_bundled_skill_kernel_extension_spec_modes_and_revision(tmp_path) -> None:
    kernel = ROOT / "skills" / "metaloop" / "scripts" / "metaloop_kernel.py"
    extension_path = tmp_path / "extension.json"
    verification_path = tmp_path / "verification.json"
    extension_path.write_text(
        json.dumps(
            {
                "schema": "metaloop.extension_spec",
                "version": "1.0",
                "domain": "experiment_safety",
                "purpose": "Capture experiment-specific safety gates.",
                "validator_types": [{"type": "domain_manual_gate", "mode": "manual"}],
                "risk_checks": ["Check promotion claims and resource use."],
                "review_questions": ["Are subset-only claims blocked?"],
                "known_gaps": ["No automated domain reviewer is installed."],
            }
        ),
        encoding="utf-8",
    )
    verification_path.write_text(
        json.dumps(
            {
                "schema": "metaloop.verification_spec",
                "version": "1.0",
                "domain": "experiment_safety",
                "extension": "experiment_safety",
                "extension_version": "1.0",
                "validators": [
                    {"type": "domain_manual_gate", "mode": "manual", "severity": "blocking", "description": "Manual promotion claim review."}
                ],
                "evidence_requirements": [],
                "resource_gates": [],
            }
        ),
        encoding="utf-8",
    )

    design = subprocess.run(
        [
            sys.executable,
            str(kernel),
            "--workspace",
            str(tmp_path),
            "design",
            "--intent",
            "Review an experiment promotion",
            "--rationale",
            "Domain claims need task-specific review.",
            "--non-goal",
            "Do not hard-verify unavailable domain judgment.",
            "--extension-spec",
            str(extension_path),
            "--verification-spec",
            str(verification_path),
            "--allow-manual-only",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert design.returncode == 0

    capsule_path = tmp_path / ".metaloop" / "mission_capsule.json"
    capsule = json.loads(capsule_path.read_text(encoding="utf-8"))
    assert capsule["extension_spec"]["domain"] == "experiment_safety"
    assert capsule["extension_spec"]["extension_hash"].startswith("sha256:")

    run = subprocess.run(
        [sys.executable, str(kernel), "--workspace", str(tmp_path), "run", "--command", "true"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert run.returncode == 0

    verify = subprocess.run(
        [sys.executable, str(kernel), "--workspace", str(tmp_path), "verify", "--json"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert verify.returncode == 1
    result = json.loads(verify.stdout)
    assert result["status"] == "human_acceptance_required"
    assert result["manual_validator_results"][0]["type"] == "domain_manual_gate"
    assert result["warnings"][0]["type"] == "known_gap"

    capsule["extension_spec"]["purpose"] = "tampered"
    capsule_path.write_text(json.dumps(capsule, indent=2), encoding="utf-8")
    tampered = subprocess.run(
        [sys.executable, str(kernel), "--workspace", str(tmp_path), "verify"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert tampered.returncode == 1
    assert "verification: invalid_capsule" in tampered.stdout

    fixed_design = subprocess.run(
        [
            sys.executable,
            str(kernel),
            "--workspace",
            str(tmp_path),
            "design",
            "--intent",
            "Review an experiment promotion with an executable artifact",
            "--rationale",
            "Add a concrete artifact gate.",
            "--non-goal",
            "Do not overwrite without revision history.",
            "--file-exists",
            "report.txt",
            "--force",
            "--revision-reason",
            "Replace tampered capsule with executable revision.",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert fixed_design.returncode == 0
    assert (tmp_path / ".metaloop" / "revisions").exists()
    revised = json.loads(capsule_path.read_text(encoding="utf-8"))
    assert revised["revision"] == 2
    assert revised["previous_capsule_id"]


def test_bundled_skill_kernel_generic_validator_modes(tmp_path) -> None:
    kernel = ROOT / "skills" / "metaloop" / "scripts" / "metaloop_kernel.py"
    artifact = tmp_path / "artifact.txt"
    artifact.write_text("required text\n", encoding="utf-8")
    digest = "sha256:" + __import__("hashlib").sha256(artifact.read_bytes()).hexdigest()
    advisory = json.dumps({"type": "file_contains", "mode": "executable", "severity": "advisory", "path": "artifact.txt", "contains": "missing advisory text"})
    resource_gate = json.dumps({"type": "resource_gate", "mode": "manual", "severity": "blocking", "resource": "gpu", "requires_user_confirmation": True})

    design = subprocess.run(
        [
            sys.executable,
            str(kernel),
            "--workspace",
            str(tmp_path),
            "design",
            "--intent",
            "Validate generic artifacts and resource gates",
            "--rationale",
            "Generic validators should compose across domains.",
            "--non-goal",
            "Do not treat resource approval as hard verified.",
            "--file-contains",
            json.dumps({"path": "artifact.txt", "contains": "required text"}),
            "--json-field-exists",
            json.dumps({"path": "summary.json", "field": "held_out.peak1_delta"}),
            "--artifact-hash",
            json.dumps({"path": "artifact.txt", "sha256": digest}),
            "--validator",
            advisory,
            "--resource-gate",
            resource_gate,
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert design.returncode == 0

    run = subprocess.run(
        [
            sys.executable,
            str(kernel),
            "--workspace",
            str(tmp_path),
            "run",
            "--command",
            "printf '{\"held_out\":{\"peak1_delta\":0}}' > summary.json",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert run.returncode == 0

    verify = subprocess.run(
        [sys.executable, str(kernel), "--workspace", str(tmp_path), "verify", "--json"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert verify.returncode == 1
    result = json.loads(verify.stdout)
    assert result["status"] == "human_acceptance_required"
    assert result["manual_validator_results"][0]["type"] == "resource_gate"
    assert any(item["type"] == "file_contains" for item in result["warnings"])

    capsule_path = tmp_path / ".metaloop" / "mission_capsule.json"
    capsule = json.loads(capsule_path.read_text(encoding="utf-8"))
    capsule["verification_spec"]["resource_gates"] = []
    capsule["verification_spec"]["spec_hash"] = _test_hash(capsule["verification_spec"], "spec_hash")
    capsule_path.write_text(json.dumps(capsule, indent=2), encoding="utf-8")

    automated_verify = subprocess.run(
        [sys.executable, str(kernel), "--workspace", str(tmp_path), "verify", "--json"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert automated_verify.returncode == 0
    automated_result = json.loads(automated_verify.stdout)
    assert automated_result["status"] == "completed_verified"


def test_bundled_skill_kernel_rejects_malformed_and_out_of_language_specs(tmp_path) -> None:
    kernel = ROOT / "skills" / "metaloop" / "scripts" / "metaloop_kernel.py"
    extension_path = tmp_path / "extension.json"
    verification_path = tmp_path / "verification.json"
    extension_path.write_text(
        json.dumps(
            {
                "schema": "metaloop.extension_spec",
                "version": "1.0",
                "domain": "review_domain",
                "purpose": "Strict review language.",
                "validator_types": [{"type": "domain_gate", "mode": "manual"}],
                "risk_checks": ["Check malformed specs."],
                "review_questions": [],
                "known_gaps": [],
            }
        ),
        encoding="utf-8",
    )

    verification_path.write_text(
        json.dumps(
            {
                "schema": "metaloop.verification_spec",
                "version": "1.0",
                "domain": "review_domain",
                "extension": "review_domain",
                "extension_version": "1.0",
                "validators": [{"type": "domain_gate", "mode": "bogus", "severity": "blocking"}],
                "evidence_requirements": [],
                "resource_gates": [],
            }
        ),
        encoding="utf-8",
    )
    malformed = subprocess.run(
        [
            sys.executable,
            str(kernel),
            "--workspace",
            str(tmp_path),
            "design",
            "--intent",
            "Reject malformed validator mode",
            "--rationale",
            "Locked specs must be explicit.",
            "--non-goal",
            "Do not infer invalid validator metadata.",
            "--extension-spec",
            str(extension_path),
            "--verification-spec",
            str(verification_path),
            "--allow-manual-only",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert malformed.returncode == 1
    assert "mode must be one of" in malformed.stderr

    verification_path.write_text(
        json.dumps(
            {
                "schema": "metaloop.verification_spec",
                "version": "1.0",
                "domain": "review_domain",
                "extension": "review_domain",
                "extension_version": "1.0",
                "validators": [{"type": "file_exists", "mode": "executable", "severity": "blocking", "path": "x"}],
                "evidence_requirements": [],
                "resource_gates": [],
            }
        ),
        encoding="utf-8",
    )
    out_of_language = subprocess.run(
        [
            sys.executable,
            str(kernel),
            "--workspace",
            str(tmp_path),
            "design",
            "--intent",
            "Reject validators outside the extension language",
            "--rationale",
            "ExtensionSpec defines the locked verification language.",
            "--non-goal",
            "Do not bypass domain extension declarations.",
            "--extension-spec",
            str(extension_path),
            "--verification-spec",
            str(verification_path),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert out_of_language.returncode == 1
    assert "type is not declared by extension_spec.validator_types" in out_of_language.stderr


def test_bundled_skill_kernel_reports_declared_but_unimplemented_executable_as_unsupported(tmp_path) -> None:
    kernel = ROOT / "skills" / "metaloop" / "scripts" / "metaloop_kernel.py"
    extension_path = tmp_path / "extension.json"
    verification_path = tmp_path / "verification.json"
    extension_path.write_text(
        json.dumps(
            {
                "schema": "metaloop.extension_spec",
                "version": "1.0",
                "domain": "future_domain",
                "purpose": "Declare a future executable validator.",
                "validator_types": [{"type": "future_gate", "mode": "executable"}],
                "risk_checks": ["Check unsupported executable support before completion."],
                "review_questions": [],
                "known_gaps": [],
            }
        ),
        encoding="utf-8",
    )
    verification_path.write_text(
        json.dumps(
            {
                "schema": "metaloop.verification_spec",
                "version": "1.0",
                "domain": "future_domain",
                "extension": "future_domain",
                "extension_version": "1.0",
                "validators": [
                    {"type": "future_gate", "mode": "executable", "severity": "blocking", "description": "Future executable gate."}
                ],
                "evidence_requirements": [],
                "resource_gates": [],
            }
        ),
        encoding="utf-8",
    )

    design = subprocess.run(
        [
            sys.executable,
            str(kernel),
            "--workspace",
            str(tmp_path),
            "design",
            "--intent",
            "Lock a declared but unavailable validator",
            "--rationale",
            "The verifier must not pretend unsupported executables passed.",
            "--non-goal",
            "Do not mark unsupported validators completed.",
            "--extension-spec",
            str(extension_path),
            "--verification-spec",
            str(verification_path),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert design.returncode == 0
    run = subprocess.run(
        [sys.executable, str(kernel), "--workspace", str(tmp_path), "run", "--command", "true"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert run.returncode == 0
    verify = subprocess.run(
        [sys.executable, str(kernel), "--workspace", str(tmp_path), "verify", "--json"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert verify.returncode == 1
    result = json.loads(verify.stdout)
    assert result["status"] == "unsupported_verification_spec"
    assert result["unsupported_validator_results"][0]["type"] == "future_gate"


def test_bundled_skill_kernel_sanitizes_revision_archive_filename(tmp_path) -> None:
    kernel = ROOT / "skills" / "metaloop" / "scripts" / "metaloop_kernel.py"
    design = subprocess.run(
        [
            sys.executable,
            str(kernel),
            "--workspace",
            str(tmp_path),
            "design",
            "--intent",
            "Create initial capsule",
            "--rationale",
            "Revision archive behavior must be safe.",
            "--non-goal",
            "Do not trust old capsule filenames.",
            "--file-exists",
            "result.txt",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert design.returncode == 0

    capsule_path = tmp_path / ".metaloop" / "mission_capsule.json"
    capsule = json.loads(capsule_path.read_text(encoding="utf-8"))
    capsule["capsule_id"] = "../escape/capsule"
    capsule_path.write_text(json.dumps(capsule, indent=2), encoding="utf-8")
    revised = subprocess.run(
        [
            sys.executable,
            str(kernel),
            "--workspace",
            str(tmp_path),
            "design",
            "--intent",
            "Create revised capsule",
            "--rationale",
            "Archive filenames must be sanitized.",
            "--non-goal",
            "Do not write revision files outside .metaloop/revisions.",
            "--file-exists",
            "result.txt",
            "--force",
            "--revision-reason",
            "Exercise archive sanitization.",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert revised.returncode == 0
    revisions = list((tmp_path / ".metaloop" / "revisions").glob("*.json"))
    assert len(revisions) == 1
    assert revisions[0].parent == tmp_path / ".metaloop" / "revisions"
    assert ".." not in revisions[0].name
    assert "escape_capsule" in revisions[0].name
    assert not (tmp_path / ".metaloop" / "escape").exists()


def _test_hash(payload: dict, hash_key: str) -> str:
    normalized = dict(payload)
    normalized.pop(hash_key, None)
    encoded = json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return "sha256:" + __import__("hashlib").sha256(encoded).hexdigest()
