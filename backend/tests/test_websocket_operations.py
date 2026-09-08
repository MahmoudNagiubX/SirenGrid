from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.db import init_db
from app.main import app
from app.schemas import IncidentStatus, OperationsEventEnvelope
from app.seed import seed_resources
from app.websocket import reset_operations_stream


@pytest.fixture(autouse=True)
def setup_isolated_db_tables(isolated_engine: Engine) -> None:
    """Initialize all model tables on the isolated test engine."""
    init_db(isolated_engine)


@pytest.fixture(autouse=True)
def reset_operations_stream_sequence() -> None:
    """Reset stream sequence and active connections before and after each test."""
    reset_operations_stream()
    yield
    reset_operations_stream()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _create_sample_incident(client: TestClient) -> dict[str, Any]:
    """Helper to create a valid incident via the manual intake REST endpoint."""
    payload = {
        "incident_type": "traffic_collision",
        "severity": "HIGH",
        "confidence_level": "HIGH",
        "location": {"lat": 30.0561, "lon": 31.3452},
        "location_text": "Corner of Abbas El Akkad and El Nasr Road",
        "casualty_count": 2,
        "required_resources": [
            {"resource_type": "AMBULANCE", "count": 1},
            {"resource_type": "FIRE_RESCUE", "count": 1},
        ],
        "operator_reference": "dispatcher-ws-01",
    }
    resp = client.post("/api/v1/intake/manual", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_connected_websocket_receives_locked_envelope_on_real_operation(client: TestClient) -> None:
    """A connected WebSocket receives the locked envelope shape after a real manual intake operation."""
    with client.websocket_connect("/api/v1/ws/operations") as ws:
        created_incident = _create_sample_incident(client)

        msg = ws.receive_json()

        # Validate against authoritative Pydantic envelope model
        envelope = OperationsEventEnvelope.model_validate(msg)
        assert envelope.event == "incident.created"
        assert envelope.incident_id == created_incident["id"]
        assert envelope.version == 1

        # Check ISO-8601 parseable timestamp
        ts = datetime.fromisoformat(envelope.timestamp)
        assert ts.tzinfo is not None

        # Check payload preserves domain entity fields and version
        assert envelope.payload["id"] == created_incident["id"]
        assert envelope.payload["status"] == IncidentStatus.ACTIVE_UNCONFIRMED.value
        assert envelope.payload["version"] == 1


def test_stream_versions_are_globally_monotonic_across_different_operations(
    client: TestClient,
    db_session: Session,
) -> None:
    """Stream sequence numbers increment globally and monotonically across distinct domain operations in one process."""
    seed_resources(db=db_session)

    with client.websocket_connect("/api/v1/ws/operations") as ws:
        # 1. Incident creation -> version 1
        incident = _create_sample_incident(client)
        inc_id = incident["id"]

        e1 = ws.receive_json()
        assert e1["event"] == "incident.created"
        assert e1["version"] == 1
        assert e1["incident_id"] == inc_id

        # Query an available seeded resource
        res_list = client.get("/api/v1/resources?status=AVAILABLE").json()
        target_res = next(r for r in res_list if r["status"] == "AVAILABLE")
        res_id = target_res["id"]
        res_ver = target_res["version"]

        # 2. Resource assignment -> version 2
        assign_resp = client.post(
            f"/api/v1/resources/{res_id}/assign",
            json={
                "incident_id": inc_id,
                "expected_resource_version": res_ver,
                "operator_reference": "dispatcher-op-assign",
            },
        )
        assert assign_resp.status_code == 200

        e2 = ws.receive_json()
        assert e2["event"] == "resource.updated"
        assert e2["version"] == 2
        assert e2["incident_id"] == inc_id

        # 3. Incident report creation (timeline event) -> version 3
        report_resp = client.post(
            f"/api/v1/incidents/{inc_id}/reports",
            json={
                "source_type": "operator_manual_entry",
                "source_reference": "rep-ws-01",
                "raw_text": "Witness confirms smoke at intersection.",
                "data_reality": "SIMULATED",
                "processing_status": "PROCESSED",
                "evidence_items": [],
            },
        )
        assert report_resp.status_code == 201

        e3 = ws.receive_json()
        assert e3["event"] == "timeline.appended"
        assert e3["version"] == 3
        assert e3["incident_id"] == inc_id

        # 4. Incident facts patch -> version 4
        patch_resp = client.patch(
            f"/api/v1/incidents/{inc_id}/facts",
            json={
                "expected_incident_version": 1,
                "operator_reference": "dispatcher-patch",
                "casualty_count": 5,
            },
        )
        assert patch_resp.status_code == 200

        e4 = ws.receive_json()
        assert e4["event"] == "incident.updated"
        assert e4["version"] == 4
        assert e4["incident_id"] == inc_id
        assert e4["payload"]["version"] == 2  # Domain version

        # 5. Incident lifecycle transition -> version 5
        trans_resp = client.post(
            f"/api/v1/incidents/{inc_id}/transition",
            json={
                "target_status": IncidentStatus.RESPONSE_PROPOSED.value,
                "expected_incident_version": 2,
                "operator_reference": "dispatcher-trans",
            },
        )
        assert trans_resp.status_code == 200

        e5 = ws.receive_json()
        assert e5["event"] == "incident.updated"
        assert e5["version"] == 5
        assert e5["incident_id"] == inc_id
        assert e5["payload"]["version"] == 3  # Domain version

        # Verify strict monotonicity across all five distinct operations
        versions = [e1["version"], e2["version"], e3["version"], e4["version"], e5["version"]]
        assert versions == [1, 2, 3, 4, 5]


def test_incident_associated_resource_events_carry_incident_id(
    client: TestClient,
    db_session: Session,
) -> None:
    """Resource operations associated with an incident (assign, state patch, release) carry the incident_id."""
    seed_resources(db=db_session)
    incident = _create_sample_incident(client)
    inc_id = incident["id"]

    res_list = client.get("/api/v1/resources?status=AVAILABLE").json()
    resource = res_list[0]
    res_id = resource["id"]

    with client.websocket_connect("/api/v1/ws/operations") as ws:
        # 1. Assign resource to incident
        client.post(
            f"/api/v1/resources/{res_id}/assign",
            json={
                "incident_id": inc_id,
                "expected_resource_version": resource["version"],
                "operator_reference": "dispatcher-op-01",
            },
        )
        assign_event = ws.receive_json()
        assert assign_event["event"] == "resource.updated"
        assert assign_event["incident_id"] == inc_id
        assert assign_event["payload"]["status"] == "ASSIGNED"
        assert assign_event["payload"]["assigned_incident_id"] == inc_id

        # 2. Patch state of assigned resource (EN_ROUTE)
        client.patch(
            f"/api/v1/resources/{res_id}/state",
            json={
                "status": "EN_ROUTE",
                "expected_resource_version": assign_event["payload"]["version"],
                "operator_reference": "dispatcher-op-02",
                "incident_id": inc_id,
            },
        )
        state_event = ws.receive_json()
        assert state_event["event"] == "resource.updated"
        assert state_event["incident_id"] == inc_id
        assert state_event["payload"]["status"] == "EN_ROUTE"

        # 3. Release resource back to AVAILABLE
        client.post(
            f"/api/v1/resources/{res_id}/release",
            json={
                "incident_id": inc_id,
                "expected_resource_version": state_event["payload"]["version"],
                "operator_reference": "dispatcher-op-03",
            },
        )
        release_event = ws.receive_json()
        assert release_event["event"] == "resource.updated"
        assert release_event["incident_id"] == inc_id
        assert release_event["payload"]["status"] == "AVAILABLE"
        assert release_event["payload"]["assigned_incident_id"] is None


def test_resource_only_event_carries_incident_id_null(
    client: TestClient,
    db_session: Session,
) -> None:
    """A state patch on an unassigned resource is truly resource-only and carries incident_id null."""
    seed_resources(db=db_session)
    res_list = client.get("/api/v1/resources?status=AVAILABLE").json()
    unassigned_res = next(r for r in res_list if r["assigned_incident_id"] is None)
    res_id = unassigned_res["id"]
    res_ver = unassigned_res["version"]

    with client.websocket_connect("/api/v1/ws/operations") as ws:
        # Patch unassigned resource to OUT_OF_SERVICE
        patch_resp = client.patch(
            f"/api/v1/resources/{res_id}/state",
            json={
                "status": "OUT_OF_SERVICE",
                "expected_resource_version": res_ver,
                "operator_reference": "maintenance-op",
            },
        )
        assert patch_resp.status_code == 200

        event = ws.receive_json()
        assert event["event"] == "resource.updated"
        assert event["incident_id"] is None
        assert event["payload"]["id"] == res_id
        assert event["payload"]["status"] == "OUT_OF_SERVICE"
        assert event["payload"]["assigned_incident_id"] is None


def test_unsuccessful_or_stale_mutation_does_not_publish_false_event(
    client: TestClient,
    db_session: Session,
) -> None:
    """Failed, stale, or semantic no-op requests do not commit or emit false WebSocket events."""
    seed_resources(db=db_session)
    incident = _create_sample_incident(client)
    inc_id = incident["id"]

    res_list = client.get("/api/v1/resources?status=AVAILABLE").json()
    resource = res_list[0]
    res_id = resource["id"]

    with client.websocket_connect("/api/v1/ws/operations") as ws:
        # 1. Stale resource assign (version mismatch -> 409)
        stale_assign = client.post(
            f"/api/v1/resources/{res_id}/assign",
            json={
                "incident_id": inc_id,
                "expected_resource_version": 999,
                "operator_reference": "bad-op",
            },
        )
        assert stale_assign.status_code == 409

        # 2. Illegal lifecycle transition (e.g. ACTIVE_UNCONFIRMED -> CLOSED -> 409)
        illegal_trans = client.post(
            f"/api/v1/incidents/{inc_id}/transition",
            json={
                "target_status": IncidentStatus.CLOSED.value,
                "expected_incident_version": 1,
                "operator_reference": "bad-op",
            },
        )
        assert illegal_trans.status_code == 409

        # 3. Semantic no-op facts patch (same values -> 200, but no mutation or event)
        noop_patch = client.patch(
            f"/api/v1/incidents/{inc_id}/facts",
            json={
                "expected_incident_version": 1,
                "operator_reference": "noop-op",
                "casualty_count": incident["casualty_count"],
            },
        )
        assert noop_patch.status_code == 200
        assert noop_patch.json()["changed_fields"] == []

        # 4. Now execute one valid, successful operation
        valid_assign = client.post(
            f"/api/v1/resources/{res_id}/assign",
            json={
                "incident_id": inc_id,
                "expected_resource_version": resource["version"],
                "operator_reference": "good-op",
            },
        )
        assert valid_assign.status_code == 200

        # The FIRST event received must be the valid assignment event, version 2 (after incident.created version 1)
        event = ws.receive_json()
        assert event["event"] == "resource.updated"
        assert event["incident_id"] == inc_id
        assert event["version"] == 2
        assert event["payload"]["id"] == res_id


def test_no_placeholder_event_types_are_emitted(
    client: TestClient,
    db_session: Session,
) -> None:
    """All events emitted across a full operational workflow belong strictly to the approved existing event subset."""
    seed_resources(db=db_session)
    allowed_events = {
        "incident.created",
        "incident.updated",
        "resource.updated",
        "timeline.appended",
        "plan.approved",
    }

    observed_events: list[str] = []

    with client.websocket_connect("/api/v1/ws/operations") as ws:
        # Create incident
        inc = _create_sample_incident(client)
        inc_id = inc["id"]
        msg = ws.receive_json()
        observed_events.append(msg["event"])

        # Create report
        client.post(
            f"/api/v1/incidents/{inc_id}/reports",
            json={
                "source_type": "operator_manual_entry",
                "source_reference": "rep-audit",
                "raw_text": "Audit report",
                "data_reality": "SIMULATED",
                "processing_status": "PROCESSED",
                "evidence_items": [],
            },
        )
        msg = ws.receive_json()
        observed_events.append(msg["event"])

        # Patch facts
        client.patch(
            f"/api/v1/incidents/{inc_id}/facts",
            json={
                "expected_incident_version": 1,
                "operator_reference": "audit-patch",
                "location_text": "Updated corner audit",
            },
        )
        msg = ws.receive_json()
        observed_events.append(msg["event"])

        # Generate plan
        plan_resp = client.post(f"/api/v1/incidents/{inc_id}/plans/generate")
        assert plan_resp.status_code == 201
        plan = plan_resp.json()
        msg = ws.receive_json()
        observed_events.append(msg["event"])

        # Approve plan
        approve_resp = client.post(
            f"/api/v1/plans/{plan['id']}/approve",
            json={
                "expected_incident_version": plan["incident_version"],
                "expected_plan_version": plan["plan_version"],
                "operator_reference": "audit-approval",
            },
        )
        assert approve_resp.status_code == 200
        msg = ws.receive_json()
        observed_events.append(msg["event"])

    # Ensure all observed events are in the allowed subset and no placeholders (like route.updated) appeared
    for event_type in observed_events:
        assert event_type in allowed_events, f"Unexpected event type emitted: {event_type}"
    assert "route.updated" not in observed_events


def test_rest_state_remains_canonical_and_queryable_for_recovery(
    client: TestClient,
    db_session: Session,
) -> None:
    """REST state remains canonical; clients detect version gaps and recover full state via REST without event replay."""
    seed_resources(db=db_session)

    # 1. Connect client ws1 and receive initial creation event
    with client.websocket_connect("/api/v1/ws/operations") as ws1:
        inc = _create_sample_incident(client)
        inc_id = inc["id"]
        e1 = ws1.receive_json()
        assert e1["version"] == 1

    # ws1 is now disconnected. Perform operations 2 and 3 while client is offline.
    res_list = client.get("/api/v1/resources?status=AVAILABLE").json()
    target_res = res_list[0]
    res_id = target_res["id"]

    # Mutation 2: assign resource
    client.post(
        f"/api/v1/resources/{res_id}/assign",
        json={
            "incident_id": inc_id,
            "expected_resource_version": target_res["version"],
            "operator_reference": "recovery-op-assign",
        },
    )

    # Mutation 3: patch incident facts
    client.patch(
        f"/api/v1/incidents/{inc_id}/facts",
        json={
            "expected_incident_version": 1,
            "operator_reference": "recovery-op-patch",
            "casualty_count": 8,
        },
    )

    # 2. Reconnect with new client ws2. Notice NO replay is delivered upon connection.
    with client.websocket_connect("/api/v1/ws/operations") as ws2:
        # Mutation 4 occurs while ws2 is connected
        client.post(
            f"/api/v1/incidents/{inc_id}/transition",
            json={
                "target_status": IncidentStatus.RESPONSE_PROPOSED.value,
                "expected_incident_version": 2,
                "operator_reference": "recovery-op-trans",
            },
        )

        e4 = ws2.receive_json()
        # The received event has version 4, demonstrating sequence monotonic progress
        assert e4["version"] == 4
        assert e4["event"] == "incident.updated"

        # Client detects gap (version jumped from 1 to 4).
        # Client performs canonical REST recovery queries:
        inc_rest = client.get(f"/api/v1/incidents/{inc_id}").json()
        assert inc_rest["version"] == 3
        assert inc_rest["status"] == IncidentStatus.RESPONSE_PROPOSED.value
        assert inc_rest["casualty_count"] == 8

        res_rest = client.get(f"/api/v1/resources/{res_id}").json()
        assert res_rest["status"] == "ASSIGNED"
        assert res_rest["assigned_incident_id"] == inc_id

        timeline_rest = client.get(f"/api/v1/incidents/{inc_id}/timeline").json()
        event_types = [ev["event_type"] for ev in timeline_rest]
        assert "INCIDENT_CREATED" in event_types
        assert "RESOURCE_ASSIGNED" in event_types
        assert "FACTS_CORRECTED" in event_types
        assert "LIFECYCLE_TRANSITION" in event_types


def test_rest_operations_succeed_with_no_websocket_connected(
    client: TestClient,
    db_session: Session,
) -> None:
    """All REST operations succeed and maintain consistent state when zero WebSocket clients are connected."""
    seed_resources(db=db_session)

    # Manual creation
    inc = _create_sample_incident(client)
    inc_id = inc["id"]
    assert inc["version"] == 1

    # Transition
    trans = client.post(
        f"/api/v1/incidents/{inc_id}/transition",
        json={
            "target_status": IncidentStatus.RESPONSE_PROPOSED.value,
            "expected_incident_version": 1,
            "operator_reference": "no-ws-trans",
        },
    )
    assert trans.status_code == 200
    assert trans.json()["version"] == 2

    # Verification via REST
    read_inc = client.get(f"/api/v1/incidents/{inc_id}").json()
    assert read_inc["status"] == IncidentStatus.RESPONSE_PROPOSED.value
    assert read_inc["version"] == 2


def test_multiple_concurrent_websocket_clients_receive_identical_envelopes(client: TestClient) -> None:
    """Multiple concurrent WebSocket connections receive identical envelopes with the same stream version."""
    with client.websocket_connect("/api/v1/ws/operations") as ws1:
        with client.websocket_connect("/api/v1/ws/operations") as ws2:
            incident = _create_sample_incident(client)

            msg1 = ws1.receive_json()
            msg2 = ws2.receive_json()

            assert msg1 == msg2
            assert msg1["version"] == 1
            assert msg1["event"] == "incident.created"
            assert msg1["incident_id"] == incident["id"]


def test_publish_does_not_block_on_a_stalled_client() -> None:
    """A slow or dead socket must not stall the mutation that triggered it.

    The publishing thread has already committed its database transaction, so
    waiting on a socket write would let one stuck client add seconds to every
    operational mutation.
    """
    import asyncio
    import threading
    import time

    from app.websocket import OperationsConnectionManager

    manager = OperationsConnectionManager()
    delivery_started = threading.Event()
    release_delivery = threading.Event()

    class StalledWebSocket:
        async def send_json(self, _envelope: object) -> None:
            delivery_started.set()
            # Block the stream loop the way a wedged client would.
            await asyncio.get_running_loop().run_in_executor(
                None, release_delivery.wait, 30.0
            )

    loop = asyncio.new_event_loop()
    loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
    loop_thread.start()
    try:
        manager.active_connections.append(StalledWebSocket())
        manager.loop = loop

        started = time.monotonic()
        envelope = manager.publish(
            event="incident.updated", incident_id="inc-stall", payload={}
        )
        elapsed = time.monotonic() - started

        # Publication returns immediately rather than waiting on the socket.
        assert elapsed < 1.0, f"publish blocked for {elapsed:.2f}s"
        assert envelope["event"] == "incident.updated"
        assert envelope["version"] == 1
        assert delivery_started.wait(timeout=5.0), "delivery was never scheduled"
    finally:
        release_delivery.set()
        loop.call_soon_threadsafe(loop.stop)
        loop_thread.join(timeout=5.0)
        loop.close()


def test_publish_prunes_a_socket_that_fails_delivery() -> None:
    """A broken socket is dropped asynchronously without affecting the caller."""
    import asyncio
    import threading

    from app.websocket import OperationsConnectionManager

    manager = OperationsConnectionManager()
    attempted = threading.Event()

    class BrokenWebSocket:
        async def send_json(self, _envelope: object) -> None:
            attempted.set()
            raise RuntimeError("socket is closed")

    loop = asyncio.new_event_loop()
    loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
    loop_thread.start()
    try:
        broken = BrokenWebSocket()
        manager.active_connections.append(broken)
        manager.loop = loop

        # The failure must not propagate to the committing request thread.
        manager.publish(event="incident.updated", incident_id="inc-broken", payload={})

        assert attempted.wait(timeout=5.0)
        deadline = 5.0
        step = 0.05
        waited = 0.0
        while broken in manager.active_connections and waited < deadline:
            threading.Event().wait(step)
            waited += step
        assert broken not in manager.active_connections
    finally:
        loop.call_soon_threadsafe(loop.stop)
        loop_thread.join(timeout=5.0)
        loop.close()
