# MetaLoop V2 Governance

V2 governance is an optional immutable block inside a ContractRevision. It is
for architecture-sensitive work where silent drift would invalidate the Task.
It is not a second state system.

```json
{
  "schema": "metaloop.v2.engineering_governance",
  "version": "1.0",
  "change_kind": "repair",
  "stable_inputs": [
    {
      "role": "governing_document",
      "path": "docs/architecture.md",
      "sha256": "sha256:<digest>"
    }
  ],
  "managed_outputs": [
    {
      "role": "implementation",
      "path": "src/feature.py"
    }
  ],
  "allowed_paths": ["src"],
  "migration_plan": null
}
```

## Change Kinds

- `repair`: stable design remains correct; implementation must be repaired.
- `extension`: behavior grows without silently changing existing authority or
  contract meaning.
- `redesign`: goal, ownership, state semantics, public contract, authority, or
  migration model changes. A locked migration plan is required.

The intelligent agent chooses the kind explicitly. Code never infers it from
keywords.

## Reference Roles

Supported roles are `governing_document`, `module_contract`,
`migration_plan`, `implementation`, and `test_contract`.

Stable inputs must exist at contract lock and retain their hash through Attempt
start, seal, verification, review, acceptance, and selected Task integrity.
Managed outputs must be workspace-relative, fall under an `allowed_paths`
prefix, exist before seal, and be attached as exact Attempt evidence.

`allowed_paths` is a locked declaration used for contract clarity. It does not
replace host sandbox, hook, or wrapper enforcement.

## CLI

Pass governance fields while locking the normal V2 contract:

```bash
python3 "$KERNEL" --workspace . task contract \
  --task <task_id> --expected-version <n> --file contract.json \
  --change-kind repair \
  --stable-input governing_document=docs/architecture.md \
  --managed-output implementation=src/feature.py \
  --allowed-path src
```

The kernel resolves safe workspace-relative paths and computes stable-input
hashes. Do not call the v1 `design` command for V2 governance.
