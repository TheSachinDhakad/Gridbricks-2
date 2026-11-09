"""Controller tests. Unit tests for the statistics and contract mirrors, plus an in-process end-to-end
run with a simulated crash. Run: python -m pytest -q tests

The tests may import `sim` (to drive a world and to cross-check our documented-contract mirrors);
the controller package itself never does.
"""
import copy
import json
import random

import numpy as np
import pytest

from controller import configtools as ct
from controller import settings as S
from controller.aggregates import Ingestor, WFAgg
from controller.features import NCELL, Cohort, Vocab, cohort_index
from controller.governance import Policy, may_submit
from controller.schedule import build_partition
from controller.stats import poisson_sf, ratio_test
from controller.store import Store

OPTS = {"welcome_message": ["W1", "W2", "W3"], "voice": ["V1", "V2", "V3", "V4"],
        "caller_id": ["D1", "D2", "D3"], "prompt_version": ["P1", "P3"]}


# ----------------------------------------------------------------------------- statistics
def test_ratio_test_basic():
    r = ratio_test(600, 1000, 500, 1000)
    assert r.lift == pytest.approx(0.2, abs=0.01) and r.z > 4
    assert ratio_test(500, 1000, 600, 1000).z == pytest.approx(-ratio_test(600, 1000, 500, 1000).z, abs=0.3)
    assert ratio_test(0, 0, 0, 0).se > 0  # no division by zero on empty arms


def test_poisson_sf_matches_known_values():
    assert poisson_sf(0, 3.0) == 1.0
    assert poisson_sf(1, 3.0) == pytest.approx(1 - np.exp(-3), rel=1e-9)
    assert poisson_sf(10, 3.0) == pytest.approx(0.001102, rel=1e-3)
    assert 0 <= poisson_sf(900, 800.0) <= 1


# ----------------------------------------------------------------------------- contract mirrors
def _rand_cfg(rng):
    def d(opts):
        k = rng.randint(1, len(opts))
        return {o: rng.choice([0.1, 0.2, 0.5, 1.0]) for o in rng.sample(opts, k)}
    cohorts = [{"id": "a", "where": {"age_band": ["60+"]}}, {"id": "b", "where": {"lang": ["hi"]}}][: rng.randint(0, 2)]
    alloc = {"default": {dim: d(OPTS[dim]) for dim in ct.AGENT_DIMS}}
    for c in cohorts:
        if rng.random() < 0.5:
            alloc[c["id"]] = {"voice": d(OPTS["voice"])}
    return {"cohorts": cohorts, "allocations": alloc, "prompt_version": rng.choice(OPTS["prompt_version"]),
            "schedule": {"hour_weights": {}, "lead_preferred_hour": {}}}


def test_changed_dims_and_max_shift_mirror_the_simulator():
    from sim.world import changed_dims as sim_changed, max_shift as sim_shift, normalise_config
    wf = {"options": OPTS, "dialling_window": [9, 21]}
    rng = random.Random(1)
    for _ in range(300):
        a = normalise_config(wf, _rand_cfg(rng))
        b = normalise_config(wf, _rand_cfg(rng))
        assert ct.changed_dims(a, b) == sim_changed(a, b)
        assert ct.max_shift(a, b) == pytest.approx(sim_shift(a, b), abs=1e-9)


def test_step_toward_respects_max_shift():
    from sim.world import max_shift as sim_shift, normalise_config
    wf = {"options": OPTS, "dialling_window": [9, 21]}
    cur = normalise_config(wf, {"allocations": {"default": {"welcome_message": {"W1": 1}, "voice": {"V1": 1},
                                                           "caller_id": {"D1": .5, "D2": .5}}}, "prompt_version": "P1"})
    tgt = copy.deepcopy(cur)
    tgt["allocations"]["default"]["welcome_message"] = {"W1": .7, "W2": .15, "W3": .15}
    tgt["allocations"]["default"]["caller_id"] = {"D3": 1}
    steps, c = 0, cur
    while ct.changed_dims(c, tgt):
        nxt = normalise_config(wf, ct.step_toward(c, tgt, 0.2))
        assert sim_shift(c, nxt) <= 0.2 + 1e-9
        c, steps = nxt, steps + 1
        assert steps < 20
    assert steps >= 5  # a 1.0 TV move at 0.2 per step


def test_cohort_index_matches_simulator_first_match():
    from sim.scenario import FEATURES
    vocab = Vocab()
    for f, vals in FEATURES.items():
        for v in vals:
            vocab.code(f, v)
    cohorts = build_partition("age_band", ["60+", "18-30"], [("lang", [["hi"]])])
    idx = cohort_index(cohorts, vocab)
    rng = random.Random(3)
    for _ in range(500):
        feats = {f: rng.choice(v) for f, v in FEATURES.items()}
        expect = 0
        for i, c in enumerate(cohorts):
            if all(feats[k] in vals for k, vals in c.where.items()):
                expect = i + 1
                break
        assert idx[vocab.cell(feats)] == expect
    assert [c.id for c in cohorts[:2]] == ["age_60__lang_hi", "age_60"]


# ----------------------------------------------------------------------------- ingestion
def _events():
    ev = [{"type": "campaign_created", "ts": "2027-01-04T08:00:00+05:30", "workflow_id": "w", "campaign_id": "w:c1",
           "leads": 2, "config_version_at_creation": 1, "event_id": 1}]
    feats = [{"lang": "hi", "city_tier": "1", "age_band": "60+", "value_band": "low"},
             {"lang": "en", "city_tier": "2", "age_band": "18-30", "value_band": "mid"}]
    for i, f in enumerate(feats):
        ev.append({"type": "lead", "ts": "2027-01-04T08:00:00+05:30", "workflow_id": "w", "campaign_id": "w:c1",
                   "lead_id": f"w:l{i:08d}", "person_id": f"w:p{i:07d}", "features": f, "event_id": 2 + i})
    for k in range(40):
        i = k % 2
        conn = k % 3 == 0
        ev.append({"type": "call", "ts": f"2027-01-04T{9 + k % 3:02d}:05:00+05:30", "workflow_id": "w",
                   "campaign_id": "w:c1", "lead_id": f"w:l{i:08d}", "person_id": f"w:p{i:07d}",
                   "variant": {"welcome_message": "W2", "voice": "V1", "caller_id": "D1", "prompt_version": "P1"},
                   "connected": conn, "engaged": conn and k % 2 == 0,
                   "qa": {"hallucination_flag": k == 0} if conn else None, "event_id": 10 + k})
    return "\n".join(json.dumps(e) for e in ev).encode()


def test_ingest_counts_and_snapshot_roundtrip(tmp_path):
    import datetime as dt
    import pickle
    aggs = {"w": WFAgg(OPTS)}
    vocab = Vocab()
    ing = Ingestor(aggs, vocab, dt.date(2027, 1, 4))
    n, control = ing.ingest(_events())
    assert n == 43 and control[0]["type"] == "campaign_created"
    a = aggs["w"]
    k = a.daily_kpis(0)
    assert k == {"dials": 40, "connected": 14, "engaged": 7}
    assert a.eng[0][:, 1, 0, 0].sum() == 40          # all on W2/V1
    assert a.prm[0][:, 0, 3].sum() == 1              # one flag
    assert a.uploaded[0].sum() == 2 and a.concluded[0].sum() == 7
    # snapshot/restore then replaying nothing gives identical cubes
    s = Store(tmp_path / "x.db")
    s.save_snapshot(5, 600, {"aggs": aggs, "vocab": vocab.to_state()})
    last, minute, st = s.load_snapshot()
    assert last == 5 and np.array_equal(st["aggs"]["w"].eng[0], a.eng[0])
    assert pickle.dumps(st["vocab"]) == pickle.dumps(vocab.to_state())


# ----------------------------------------------------------------------------- governance
def _policy(**kw):
    meta = {"workflow_id": "w", "tenant_id": "t", "mid_flight": "allowed",
            "governance": {"auto_apply": {"enabled": False}, "approver_hours": [10, 19],
                           "approver_latency_minutes": [30, 240], "max_requests_per_24h": 3, **kw}}
    return Policy.from_meta(meta)


def test_request_budget_keeps_a_slot_for_incidents(tmp_path):
    s = Store(tmp_path / "g.db")
    pol = _policy()
    now = 600  # D0 10:00
    assert may_submit(pol, s, now, "routine")[0]
    s.add_proposal({"proposal_id": "p1", "workflow_id": "w", "path": "approval", "purpose": "routine",
                    "status": "pending", "base_version": 1, "created_minute": now, "body": {}})
    s.update_proposal("p1", submitted_minute=now)
    assert not may_submit(pol, s, now + 15, "routine")[0]      # routine budget (1/day) used
    assert may_submit(pol, s, now + 15, "protective")[0]       # 2 of 3, one still free
    s.add_proposal({"proposal_id": "p2", "workflow_id": "w", "path": "approval", "purpose": "protective",
                    "status": "pending", "base_version": 1, "created_minute": now, "body": {}})
    s.update_proposal("p2", submitted_minute=now + 15)
    assert not may_submit(pol, s, now + 30, "protective")[0]   # last slot reserved...
    assert may_submit(pol, s, now + 30, "incident")[0]         # ...for incidents
    assert may_submit(pol, s, now + 1440 + 15, "routine")[0]   # rolling window frees up


def test_routine_window_respects_latency_and_tenant_prefs():
    pol = _policy()
    assert pol.routine_window(10 * 60) and pol.routine_window(14 * 60 + 45) and not pol.routine_window(15 * 60)
    slow = _policy(approver_hours=[10, 18], approver_latency_minutes=[60, 480])
    assert slow.routine_window(10 * 60) and not slow.routine_window(11 * 60)
    S.TENANT_PREFS["t"] = {"earliest_submit_hour": 11}
    try:
        assert not _policy().routine_window(10 * 60 + 30) and _policy().routine_window(11 * 60)
    finally:
        S.TENANT_PREFS.pop("t")


# ----------------------------------------------------------------------------- learning rules
def _agg_with(rates_by_option, conn_per_option, dim="welcome_message", days=(0, 1)):
    agg = WFAgg(OPTS)
    vocab = Vocab()
    cell = vocab.cell({"lang": "hi", "city_tier": "1", "age_band": "31-45", "value_band": "low"})
    for d in days:
        cube = agg.eng_day(d)
        for o, p in rates_by_option.items():
            i = OPTS[dim].index(o)
            n = conn_per_option[o] // len(days)
            idx = (cell, i, 0) if dim == "welcome_message" else (cell, 0, i)
            cube[idx][0] += n
            cube[idx][1] += n
            cube[idx][2] += int(round(p * n))
        agg.did_day(d)[10, 0] += [100, 30, 15]
    return agg, vocab


def test_experiment_promotes_clear_winner_and_drops_clear_loser(tmp_path):
    from controller.experiments import ExperimentEngine
    s = Store(tmp_path / "e.db")
    agg, vocab = _agg_with({"W1": 0.50, "W2": 0.62, "W3": 0.40}, {"W1": 4000, "W2": 1200, "W3": 1200})
    e = ExperimentEngine(s, "w", agg, vocab, {"welcome_message": "W1", "voice": "V1"}, 0.02)
    tr = e.evaluate(1, set(), {}, lambda d, f: True)
    states = {(t["option"], t["state"]) for t in tr}
    assert ("W2", "winner") in states and ("W3", "dropped") in states
    alloc = e.allocation("welcome_message", e.statuses("welcome_message", None, None))
    assert alloc == {"W2": 1 - S.HOLDOUT, "W1": S.HOLDOUT}


def test_experiment_does_not_promote_noise(tmp_path):
    from controller.experiments import ExperimentEngine
    s = Store(tmp_path / "n.db")
    agg, vocab = _agg_with({"W1": 0.50, "W2": 0.52, "W3": 0.49}, {"W1": 3000, "W2": 600, "W3": 600})
    e = ExperimentEngine(s, "w", agg, vocab, {"welcome_message": "W1", "voice": "V1"}, 0.02)
    assert e.evaluate(1, set(), {}, lambda d, f: True) == []
    a = e.allocation("welcome_message", e.statuses("welcome_message", None, None))
    assert a["W1"] == pytest.approx(0.7) and a["W2"] == a["W3"] == pytest.approx(0.15)


def test_overloaded_number_is_not_mistaken_for_a_flagged_one(tmp_path):
    from controller import callerid
    s = Store(tmp_path / "d.db")
    s.clock = lambda: (2 * 1440 + 14 * 60, "")
    agg = WFAgg(OPTS)
    for did in ("D1", "D2"):
        s.set_did("w", did, "healthy")
    for d in (0, 1, 2):
        for h in range(9, 15):
            # D1 steadily worse (load), D2 fine: same ratio every day → not a sudden flag
            agg.did_day(d)[h, 0] += [300, 50, 25]
            agg.did_day(d)[h, 1] += [300, 85, 42]
    assert callerid.evaluate(s, "w", agg, 2, 14, 0.02) == []
    # now D2 collapses today: flagged
    for h in range(9, 15):
        agg.did[2][h, 1] = [300, 25, 12]
    tr = callerid.evaluate(s, "w", agg, 2, 14, 0.02)
    assert [(t["did"], t["state"]) for t in tr] == [("D2", "bad")]
    assert callerid.target(s, "w", agg, gated=False) == {"D1": 1.0, "D3": S.DID_EXPLORE_AUTO} or \
        callerid.target(s, "w", agg, gated=False)["D1"] > 0.9


# ----------------------------------------------------------------------------- end to end with a crash
@pytest.fixture()
def sim_client(tmp_path):
    from fastapi.testclient import TestClient
    from sim import server
    from sim.scenario import load_scenario
    from sim.world import World
    sc = load_scenario("scenarios/public_02_incidents.yaml")
    sc["days"], sc["history_days"] = 4, 3
    for t in sc["tenants"]:
        for w in t["workflows"]:
            w["daily_batch"]["size"] = 400
            w["dials_per_hour"] = 120
    server._world = World(sc, tmp_path / "run")
    yield TestClient(server.app, base_url="http://sim"), server._world
    server._world = None


def test_end_to_end_with_crash_and_restart(sim_client, tmp_path):
    from controller.controller import Controller
    from controller.simclient import Sim
    client, world = sim_client
    db = tmp_path / "state.db"

    ctl = Controller(Sim("http://sim", client=client), Store(db))
    ctl.bootstrap()
    # run ~2.5 simulated days then "crash" (drop the object without finishing)
    while ctl.now < 2 * 1440 + 12 * 60:
        st = ctl.sim.state()
        ctl._set_clock(st)
        ctl.decide(st)
        ctl.snapshot()
        ctl._set_clock(ctl.sim.advance_to(ctl._next_minute(st)))
        ctl.ingest_new()
    before = world.event_seq
    del ctl

    ctl2 = Controller(Sim("http://sim", client=client), Store(db))
    ctl2.bootstrap()                       # restores snapshot, replays newer chunks, reconciles
    ctl2.run()
    assert world.state()["finished"] and world.event_seq > before
    store = Store(db)
    # every applied proposal appears exactly once in the simulator's version history
    applied = [p for p in store.proposals() if p["status"] == "applied"]
    sim_pids = [v["proposal_id"] for w in world.wfs.values() for v in w.versions if v["proposal_id"]]
    assert len(sim_pids) == len(set(sim_pids))
    assert {p["proposal_id"] for p in applied} == set(sim_pids)
    # nothing left dangling, aggregates equal a from-scratch replay
    assert not store.proposals(statuses=("planned", "submitting"))
    fresh = Controller(Sim("http://sim", client=client), Store(tmp_path / "fresh.db"))
    fresh.bootstrap()
    for wid in world.wfs:
        for d, cube in fresh.aggs[wid].eng.items():
            assert np.array_equal(cube, ctl2.aggs[wid].eng[d]), (wid, d)
    assert store.one("SELECT COUNT(*) FROM decisions WHERE kind='restart'")[0] == 1
