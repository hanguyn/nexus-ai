# NEXUS AI

**Nghiên cứu và phát triển nền tảng giám sát hạ tầng CNTT tích hợp trí tuệ nhân tạo hỗ trợ phát hiện bất thường và chẩn đoán sự cố.**

NEXUS AI hướng tới nền tảng tự lưu trữ giám sát mạng và hỗ trợ chẩn đoán. Bản hiện tại chỉ dựng monitoring foundation; backend, frontend, AI/RCA và tự động khắc phục đều chưa được triển khai.

## Kiến trúc và công nghệ

Prometheus thu thập metrics từ chính nó, SNMP Exporter và Blackbox Exporter. Alertmanager nhận cảnh báo nhưng chưa gửi thông báo ra ngoài. Grafana được provision Prometheus và PostgreSQL datasource. PostgreSQL chỉ khởi tạo `pgcrypto` và schema `nexus`; metrics time-series thuộc Prometheus.

Monitoring: Prometheus 3.5.0, Alertmanager 0.28.1, SNMP Exporter 0.26.0, Blackbox Exporter 0.27.0, Grafana 11.6.0. Database: PostgreSQL 17 Alpine. Stack tương lai: FastAPI, SQLAlchemy, Alembic, Pydantic; React, TypeScript, Vite, Tailwind; Pandas, NumPy, scikit-learn và adapter LLM. Deployment: Docker Compose; Nginx là dự kiến.

```text
Thiết bị --SNMP--> SNMP Exporter --scrape--> Prometheus --> Alertmanager
Endpoint --probe--> Blackbox Exporter --scrape--> Prometheus
Grafana --> Prometheus + PostgreSQL
```

## Cấu trúc

`monitoring/` cấu hình Prometheus/exporters/Grafana/Alertmanager; `database/init/` SQL tối thiểu; `backend/`, `frontend/` ghi chú định hướng; `docs/` kiến trúc, triển khai, vận hành, bảo mật, lộ trình.

## Cài đặt

Cần Docker Engine và Compose v2. Linux cần `NET_RAW` cho ICMP (đã khai báo); một số môi trường Desktop/WSL không hỗ trợ ICMP.

```bash
cp .env.example .env
```

Đổi mật khẩu mẫu trong `.env` trước khi chạy.

```bash
docker compose config
docker compose up -d
docker compose ps
```

| Dịch vụ | URL |
|---|---|
| Prometheus | http://127.0.0.1:9090 |
| Alertmanager | http://127.0.0.1:9093 |
| Blackbox Exporter | http://127.0.0.1:9115 |
| SNMP Exporter | http://127.0.0.1:9116 |
| Grafana | http://127.0.0.1:3000 |

PostgreSQL không publish cổng ra host. `docker compose down` giữ volumes; `docker compose down -v` xóa dữ liệu bền vững.

## Thêm mục tiêu

Thêm thiết bị vào `monitoring/prometheus/targets/snmp_targets.yml`, thay địa chỉ tài liệu `192.0.2.10` bằng địa chỉ lab. Thêm endpoint vào `blackbox_targets.yml` với module `http_2xx`, `https_2xx`, `tcp_connect` hoặc `icmp`. Không cần sửa scrape job. Các địa chỉ ví dụ chỉ thuộc dải tài liệu, không phải thiết bị lab thật.

SNMP mẫu dùng v2c và community minh họa `CHANGE_ME_READ_ONLY`; phải thay trước khi thử thiết bị thật. v2c không mã hóa community; ưu tiên SNMP v3 auth/privacy trong production. Dùng credential chỉ đọc, giới hạn ACL để exporter được truy vấn UDP/161. Module/MIB phụ thuộc model; `if_mib` không hỗ trợ mọi thiết bị.

## Vận hành, bảo mật và giới hạn

Kiểm tra bằng `docker compose ps`, `docker compose logs --tail=100 prometheus grafana postgres`, và Prometheus UI > Status > Targets. SNMP lỗi: kiểm tra ACL, community, version và module. ICMP lỗi: kiểm tra `NET_RAW` và runtime.

`.env` không được commit. Cổng quản trị chỉ bind loopback; không mở PostgreSQL, SNMP hay giao diện quản trị ra Internet. Truy cập từ xa qua WireGuard/Tailscale với ACL; không mở SSH/SNMP trực tiếp Internet. Đây là cấu hình lab/dev, chưa harden production. Chưa có user nghiệp vụ, dashboard giả lập, webhook, backend/frontend, AI, RCA, remediation tự động hay backup policy.

## Lộ trình

1. Xác nhận monitoring với thiết bị thật.
2. Backend modular monolith quản lý users, sites/devices, dependencies, alerts/incidents, timelines, RCA evidence, recommendations, audit logs.
3. Frontend React/TypeScript.
4. Tương quan quy tắc/RCA evidence trước anomaly detection và LLM adapter có giới hạn.
5. Thêm servers, apps, logs, multi-site và VPS có reverse proxy/bảo mật.

Xem [architecture](docs/architecture.md), [deployment](docs/deployment.md), [operations](docs/operations.md), [security](docs/security.md), [roadmap](docs/roadmap.md).
