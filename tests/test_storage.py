from metaloop.kernel import MetaLoopKernel
from metaloop.schemas import AcceptanceCriteria, MissionSpec
from metaloop.storage import SQLiteRunStore


def test_sqlite_store_persists_events_and_final_state(tmp_path) -> None:
    store = SQLiteRunStore(tmp_path / "runs.sqlite")
    mission = MissionSpec(
        intent="Create a dummy artifact",
        acceptance_criteria=[AcceptanceCriteria(description="Dummy acceptance")],
    )

    state = MetaLoopKernel(store=store).run(mission)

    final_state = store.final_state(state.mission.run_id)
    events = store.events_for_run(state.mission.run_id)
    latest_checkpoint = store.latest_checkpoint(state.mission.run_id)

    assert final_state is not None
    assert final_state.status == state.status
    assert len(events) == len(state.events)
    assert latest_checkpoint is not None
    assert latest_checkpoint.mission.run_id == state.mission.run_id


def test_sqlite_store_lists_runs(tmp_path) -> None:
    store = SQLiteRunStore(tmp_path / "runs.sqlite")
    mission = MissionSpec(
        intent="Create a dummy artifact",
        acceptance_criteria=[AcceptanceCriteria(description="Dummy acceptance")],
    )

    state = MetaLoopKernel(store=store).run(mission)
    runs = store.list_runs()

    assert runs[0]["run_id"] == state.mission.run_id
    assert runs[0]["status"] == state.status.value


def test_sqlite_store_finds_latest_resumable_run(tmp_path) -> None:
    store = SQLiteRunStore(tmp_path / "runs.sqlite")
    mission = MissionSpec(
        intent="Create a dummy artifact",
        acceptance_criteria=[AcceptanceCriteria(description="Dummy acceptance")],
    )
    from metaloop.schemas import KernelState, RunStatus

    state = KernelState(mission=mission, status=RunStatus.RUNNING)
    store.start_run(state)
    store.save_checkpoint(state)

    assert store.latest_resumable_run_id() == mission.run_id
