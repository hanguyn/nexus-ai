# Vận hành

```bash
docker compose config
docker compose up -d
docker compose ps
docker compose logs -f prometheus
docker compose logs --tail=100 grafana postgres
docker compose restart prometheus
docker compose down
```

`docker compose down -v` xóa dữ liệu trong volumes. Kiểm tra Prometheus UI > Status > Targets. Với SNMP, kiểm tra ACL, community, phiên bản, module và MIB phù hợp model. Địa chỉ TEST-NET chỉ minh họa. Với ICMP, kiểm tra `NET_RAW` và runtime. Alertmanager chưa có kênh notification.

Khi có công cụ phù hợp, xác thực bằng `promtool check config monitoring/prometheus/prometheus.yml`, `amtool check-config monitoring/alertmanager/alertmanager.yml` và validator exporter đúng image version.
