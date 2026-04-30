from datetime import datetime, timezone

from app.models import AuditLog, VpsNode
from app.services.server_metrics import (
    apply_node_raw_counters,
    parse_cpu_percent,
    parse_df_output,
    parse_free_output,
    parse_inbound_stats,
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
    xray = '{"stat":[{"name":"inbound>>>vless-reality>>>traffic>>>uplink","value":100},{"name":"inbound>>>vless-reality>>>traffic>>>downlink","value":300},{"name":"inbound>>>api-in>>>traffic>>>uplink","value":999}]}'

    assert parse_cpu_percent(cpu) == 50.0
    assert parse_free_output(free) == {"ram_total_bytes": 1000000000, "ram_used_bytes": 625000000, "ram_percent": 62.5}
    assert parse_df_output(df) == {"disk_total_bytes": 2000000000, "disk_used_bytes": 500000000, "disk_percent": 25.0}
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


def test_background_collect_does_not_create_audit_entry(client, auth_headers, db_session):
    db_session.add(VpsNode(name="Draft", ip_address="203.0.113.91", ssh_username="root", status="draft"))
    db_session.commit()

    response = client.post("/admin/traffic/collect-background", headers=auth_headers)
    assert response.status_code == 200

    audit_actions = [row.action for row in db_session.query(AuditLog).all()]
    assert "collect_stats" not in audit_actions
    assert "debug_collect_stats" not in audit_actions
