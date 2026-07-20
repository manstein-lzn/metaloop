# Legacy V1 Compatibility

V1 Mission Capsule, ExecutionReport, VerificationResult, ReviewResult,
adaptive-loop, context, event, routing, and thread files are compatibility
artifacts. They are not a second new-work path.

When a workspace contains v1 artifacts and no V2 database, inspect and import
them with:

```bash
python3 "$KERNEL" --workspace . project migrate-legacy
```

Migration validates the Capsule and ExecutionReport, reruns locked validators,
and binds authority only when the fresh result still matches the legacy
VerificationResult. Otherwise the Evaluation is `legacy_unbound`.

Legacy `engineering_governance` is normalized into the V2 ContractRevision
when its refs remain valid. Invalid legacy governance is retained only as
unbound migration metadata.

After `.metaloop/metaloop.db` exists, v1 mutable commands fail closed. Do not
run v1 `design`, `run`, `verify`, context, thread-registry, adaptive, routing,
tick, or relay writes in that workspace. Use Task, Attempt, Evaluation,
DecisionEvent, RecoveryView, and thread assignments instead.
