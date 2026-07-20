# MetaLoop v3 Final Protocol

MetaLoop v3 binds one local Git worktree to one SQLite Project. Git supplies
mechanical workspace identity; SQLite supplies protocol history and authority.

```text
Project -> Task -> ContractRevision -> Attempt -> Evidence -> Evaluation
                                     -> Checkpoint
                -> DecisionEvent
RecoveryView is derived from these records plus the live WorkspaceStamp.
```

The lifecycle is `Frame -> Work -> Reconcile -> Adapt -> Prove`. Completion is
valid only when the live workspace equals the latest acknowledged checkpoint,
all stable inputs and evidence retain their hashes, locked validators pass, and
every required authority appears in one linear Evaluation chain.

Workspace alignment is `aligned`, `ahead`, `conflicted`, or `unknown`. Only
`aligned` may pass seal, verification, review, acceptance, or selected Task
integrity. The adapter excludes `.git/` and `.metaloop/` from generic project
change observation, while managed outputs and Evidence are checked directly.

One worktree permits one open mutating Attempt. Separate worktrees produce
separate Project identities. MetaLoop never infers Task ownership or semantic
decisions from paths, prose, or keywords.
