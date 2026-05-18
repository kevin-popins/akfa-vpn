import asyncio
from datetime import datetime, timedelta, timezone

from app.models import AuditLog, TrafficSnapshot, VpsNode
from app.services.server_metrics import (
    aggregate_node_traffic,
    apply_node_raw_counters,
    base_metric_row,
    collect_nodes_metrics,
    parse_cpu_percent,
    parse_df_output,
    parse_free_output,
    parse_inbound_stats,
    parse_system_network_stats,
)


def test_server_metrics_parsers_parse_free_df_cpu_and_xray_stats():
    cpu = "\n".join(
        [
            "cpu  100 0 100 800 0 0 0 0 0 0",
            "AKFA_CPU_SAMPLE",
            "cpu  150 0 150 900 0 0 0 0 0 0",
        ]
    )
    free = "              total        used        free\nMem:     1000000000   625000000   375000000\n"
    df = "Filesystem     1B-blocks       Used Available Use% Mounted on\n/dev/vda1     2000000000  500000000 1500000000  25% /\n"
    net = """eth0
AKFA_NET_DEV
Inter-|   Receive                                                |  Transmit
 face |bytes    packets errs drop fifo frame compressed multicast|bytes    packets errs drop fifo colls carrier compressed
    lo: 100 1 0 0 0 0 0 0 100 1 0 0 0 0 0 0
  eth0: 2048 2 0 0 0 0 0 0 4096 3 0 0 0 0 0 0
"""
    xray = '{"stat":[{"name":"inbound>>>vless-reality>>>traffic>>>uplink","value":100},{"name":"inbound>>>vless-reality>>>traffic>>>downlink","value":300},{"name":"inbound>>>api-in>>>traffic>>>uplink","value":999}]}'

    assert parse_cpu_percent(cpu) == 50.0
    assert parse_free_output(free) == {"ram_total_bytes": 1000000000, "ram_used_bytes": 625000000, "ram_percent": 62.5}
    assert parse_df_output(df) == {"disk_total_bytes": 2000000000, "disk_used_bytes": 500000000, "disk_percent": 25.0}
    assert parse_system_network_stats(net) == {
        "system_traffic_upload_bytes": 4096,
        "system_traffic_download_bytes": 2048,
        "system_traffic_total_bytes": 6144,
        "system_traffic_source": "host_proc_net_dev",
        "system_traffic_interface": "eth0",
        "system_traffic_available": True,
        "system_traffic_error": None,
    }
    assert parse_inbound_stats(xray) == {"upload": 100, "download": 300}


def test_node_traffic_first_second_and_counter_decrease():
    node = VpsNode(name="Metrics", ip_address="203.0.113.90", ssh_username="root")
    now = datetime.now(timezone.utc)

    first = apply_node_raw_counters(node, 100, 200, now)
    assert first == {"upload_delta": 100, "download_delta": 200, "delta_total": 300}
    assert node.traffic_upload_bytes == 100
    assert node.traffic_download_bytes == 200
    assert node.traffic_total_bytes == 300

    second = apply_node_raw_counters(node, 150, 260, now)
    assert second == {"upload_delta": 50, "download_delta": 60, "delta_total": 110}
    assert node.traffic_total_bytes == 410

    decreased = apply_node_raw_counters(node, 10, 20, now)
    assert decreased == {"upload_delta": 0, "download_delta": 0, "delta_total": 0}
    assert node.traffic_total_bytes == 410
    assert node.last_raw_inbound_upload_bytes == 10
    assert node.last_raw_inbound_download_bytes == 20


def test_node_traffic_snapshots_are_server_level_and_periodic(db_session):
    node = VpsNode(name="Snapshot Node", ip_address="203.0.113.92", ssh_username="root")
    db_session.add(node)
    db_session.flush()
    now = datetime.now(timezone.utc)

    result = apply_node_raw_counters(db_session, node, 100, 250, now)
    assert result == {"upload_delta": 100, "download_delta": 250, "delta_total": 350}
    db_session.add(
        TrafficSnapshot(
            vpn_user_id=None,
            node_id=node.id,
            upload_bytes=10,
            download_bytes=20,
            total_bytes=30,
            collected_at=now - timedelta(days=9),
        )
    )
    db_session.commit()

    assert aggregate_node_traffic(db_session, node.id, "all") == {"upload": 110, "download": 270, "total": 380}
    assert aggregate_node_traffic(db_session, node.id, "7d") == {"upload": 100, "download": 250, "total": 350}
    row = base_metric_row(db_session, node, "all")
    assert row["traffic_type"] == "vpn_xray"
    assert row["traffic_source"] == "node_traffic"
    assert row["vpn_traffic_source"] == "xray_stats"
    assert row["vpn_traffic_total_bytes"] == 380
    assert row["traffic_total_bytes"] == 380
    assert row["system_traffic_source"] == "unavailable"
    assert row["system_traffic_available"] is False


def test_background_collect_does_not_create_audit_entry(client, auth_headers, db_session):
    db_session.add(VpsNode(name="Draft", ip_address="203.0.113.91", ssh_username="root", status="draft"))
    db_session.commit()

    response = client.post("/admin/traffic/collect-background", headers=auth_headers)
    assert response.status_code == 200

    audit_actions = [row.action for row in db_session.query(AuditLog).all()]
    assert "collect_stats" not in audit_actions
    assert "debug_collect_stats" not in audit_actions


async def test_collect_nodes_metrics_returns_partial_rows_when_one_node_times_out(db_session, monkeypatch):
    ok = VpsNode(name="Online", ip_address="203.0.113.100", ssh_username="root", status="online")
    bad = VpsNode(name="Dead host", ip_address="203.0.113.101", ssh_username="root", status="online")
    db_session.add_all([ok, bad])
    db_session.commit()

    async def fake_run_node_metric_commands(node):
        if node.id == bad.id:
            raise asyncio.TimeoutError()
        return {
            "cpu": "cpu  100 0 100 800 0 0 0 0 0 0\nAKFA_CPU_SAMPLE\ncpu  150 0 150 900 0 0 0 0 0 0\n",
            "ram": "              total        used        free\nMem:     1000000000   500000000   500000000\n",
            "disk": "Filesystem 1B-blocks Used Available Use% Mounted on\n/dev/vda1 2000000000 500000000 1500000000 25% /\n",
            "network": "eth0\nAKFA_NET_DEV\neth0: 2048 2 0 0 0 0 0 0 4096 3 0 0 0 0 0 0\n",
            "xray": '{"stat":[]}',
        }

    monkeypatch.setattr("app.services.server_metrics.run_node_metric_commands", fake_run_node_metric_commands)

    rows = await collect_nodes_metrics(db_session, [ok, bad], "all")
    by_id = {row["node_id"]: row for row in rows}

    assert by_id[ok.id]["metrics_status"] == "ok"
    assert by_id[ok.id]["cpu_percent"] == 50.0
    assert by_id[bad.id]["status"] == "timeout"
    assert by_id[bad.id]["metrics_status"] == "timeout"
    assert by_id[bad.id]["system_traffic_available"] is False
    assert "не ответил" in by_id[bad.id]["metrics_error"]
