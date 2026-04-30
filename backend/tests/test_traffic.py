from datetime import datetime, timedelta, timezone

from app.models import UserNodeTraffic, VpnUser, VpsNode
from app.services.traffic import apply_xray_stats, enforce_expiration_and_limits, parse_xray_stats, traffic_overview


def test_parse_xray_stats_maps_email_to_username():
    output = """
    stat: <name:"user>>>ivan>>>traffic>>>uplink" value:123 >
    stat: <name:"user>>>ivan>>>traffic>>>downlink" value:456 >
    """
    stats = parse_xray_stats(output)
    assert stats["ivan"]["upload"] == 123
    assert stats["ivan"]["download"] == 456


def test_parse_xray_stats_accepts_spaced_xray_output():
    output = 'stat: < name: "user>>>anna>>>traffic>>>uplink" value: 1024 >'
    stats = parse_xray_stats(output)
    assert stats["anna"]["upload"] == 1024


def test_parse_xray_stats_accepts_actual_json_response():
    output = """
    {
      "stat": [
        {"name": "user>>>admin>>>traffic>>>uplink", "value": 2131193},
        {"name": "user>>>admin>>>traffic>>>downlink", "value": 13488058},
        {"name": "inbound>>>api>>>traffic>>>uplink", "value": 999}
      ]
    }
    """
    stats = parse_xray_stats(output)
    assert stats == {"admin": {"upload": 2131193, "download": 13488058}}


def test_enforce_expiration_and_traffic_limits(db_session):
    expired = VpnUser(
        first_name="A",
        last_name="B",
        username="expired",
        uuid="00000000-0000-0000-0000-000000000001",
        subscription_token="expired-token",
        expires_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    limited = VpnUser(
        first_name="C",
        last_name="D",
        username="limited",
        uuid="00000000-0000-0000-0000-000000000002",
        subscription_token="limited-token",
        traffic_limit_bytes=10,
        used_total_bytes=10,
    )
    db_session.add_all([expired, limited])
    db_session.commit()
    assert enforce_expiration_and_limits(db_session) == 2
    assert expired.status == "expired"
    assert limited.status == "traffic_limited"


def test_traffic_overview_includes_active_user_with_zero_bytes(db_session):
    user = VpnUser(
        first_name="Zero",
        last_name="Traffic",
        username="zero",
        uuid="00000000-0000-0000-0000-000000000003",
        subscription_token="zero-token",
    )
    db_session.add(user)
    db_session.commit()
    rows = traffic_overview(db_session)
    assert rows[0]["username"] == "zero"
    assert rows[0]["total_bytes"] == 0
    assert rows[0]["online_status"] == "offline"
    assert rows[0]["collected"] is False


def test_traffic_overview_excludes_deleted_and_disabled_users(db_session):
    active = VpnUser(
        first_name="Active",
        last_name="Traffic",
        username="active-traffic",
        uuid="00000000-0000-0000-0000-000000000004",
        subscription_token="active-traffic-token",
        used_total_bytes=2048,
    )
    deleted = VpnUser(
        first_name="Deleted",
        last_name="Traffic",
        username="deleted-traffic",
        uuid="00000000-0000-0000-0000-000000000005",
        subscription_token="deleted-traffic-token",
        status="deleted",
        used_total_bytes=4096,
    )
    disabled = VpnUser(
        first_name="Disabled",
        last_name="Traffic",
        username="disabled-traffic",
        uuid="00000000-0000-0000-0000-000000000006",
        subscription_token="disabled-traffic-token",
        status="disabled",
        used_total_bytes=8192,
    )
    db_session.add_all([active, deleted, disabled])
    db_session.commit()

    rows = traffic_overview(db_session)
    assert [row["username"] for row in rows] == ["active-traffic"]
    assert rows[0]["total_bytes"] == 2048


def test_traffic_deltas_are_added_and_last_online_updates(db_session):
    node = VpsNode(name="Stats", ip_address="203.0.113.40", ssh_username="root")
    user = VpnUser(
        first_name="Delta",
        last_name="User",
        username="delta-user",
        uuid="00000000-0000-0000-0000-000000000007",
        subscription_token="delta-token",
    )
    db_session.add_all([node, user])
    db_session.commit()

    first_seen = datetime.now(timezone.utc) - timedelta(minutes=1)
    result = apply_xray_stats(db_session, node, {"delta-user": {"upload": 100, "download": 250}}, first_seen)
    assert result["updated_users"] == 1
    assert user.used_upload_bytes == 100
    assert user.used_download_bytes == 250
    assert user.used_total_bytes == 350
    assert user.last_seen_delta_bytes == 350
    assert user.last_online_at == first_seen
    assert user.online_status == "online"

    second_seen = datetime.now(timezone.utc)
    apply_xray_stats(db_session, node, {"delta-user": {"upload": 130, "download": 300}}, second_seen)
    assert user.used_upload_bytes == 130
    assert user.used_download_bytes == 300
    assert user.used_total_bytes == 430
    assert user.last_seen_delta_bytes == 80
    assert user.last_online_at == second_seen


def test_same_user_traffic_is_tracked_per_node_and_summed(db_session):
    node_a = VpsNode(name="Node A", ip_address="203.0.113.70", ssh_username="root")
    node_b = VpsNode(name="Node B", ip_address="203.0.113.71", ssh_username="root")
    user = VpnUser(
        first_name="Multi",
        last_name="Traffic",
        username="multi-traffic",
        uuid="00000000-0000-0000-0000-000000000070",
        subscription_token="multi-traffic-token",
    )
    db_session.add_all([node_a, node_b, user])
    db_session.commit()

    first_seen = datetime.now(timezone.utc) - timedelta(seconds=30)
    apply_xray_stats(db_session, node_a, {"multi-traffic": {"upload": 100, "download": 200}}, first_seen)
    apply_xray_stats(db_session, node_b, {"multi-traffic": {"upload": 10, "download": 20}}, first_seen)
    assert user.used_upload_bytes == 110
    assert user.used_download_bytes == 220
    assert user.used_total_bytes == 330

    second_seen = datetime.now(timezone.utc)
    apply_xray_stats(db_session, node_a, {"multi-traffic": {"upload": 150, "download": 250}}, second_seen)
    apply_xray_stats(db_session, node_b, {"multi-traffic": {"upload": 15, "download": 25}}, second_seen)
    assert user.used_upload_bytes == 165
    assert user.used_download_bytes == 275
    assert user.used_total_bytes == 440
    assert user.online_status == "online"

    rows = db_session.query(UserNodeTraffic).filter_by(vpn_user_id=user.id).order_by(UserNodeTraffic.node_id).all()
    assert [(row.node_id, row.total_bytes) for row in rows] == [(node_a.id, 400), (node_b.id, 40)]


def test_raw_counter_decrease_resets_baseline_without_subtracting(db_session):
    node = VpsNode(name="Restarted", ip_address="203.0.113.41", ssh_username="root")
    user = VpnUser(
        first_name="Restart",
        last_name="Counter",
        username="restart-counter",
        uuid="00000000-0000-0000-0000-000000000009",
        subscription_token="restart-counter-token",
        used_upload_bytes=1000,
        used_download_bytes=2000,
        used_total_bytes=3000,
        last_raw_upload_bytes=900,
        last_raw_download_bytes=1900,
    )
    db_session.add_all([node, user])
    db_session.commit()

    result = apply_xray_stats(db_session, node, {"restart-counter": {"upload": 50, "download": 80}})
    assert result["updated_users"] == 0
    assert user.used_upload_bytes == 1000
    assert user.used_download_bytes == 2000
    assert user.used_total_bytes == 3000
    assert user.last_raw_upload_bytes == 50
    assert user.last_raw_download_bytes == 80


def test_online_status_becomes_offline_after_timeout(db_session):
    user = VpnUser(
        first_name="Old",
        last_name="Online",
        username="old-online",
        uuid="00000000-0000-0000-0000-000000000008",
        subscription_token="old-online-token",
        last_online_at=datetime.now(timezone.utc) - timedelta(minutes=4),
    )
    db_session.add(user)
    db_session.commit()
    assert user.online_status == "offline"
