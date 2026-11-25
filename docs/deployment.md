# Triển khai

## Lab/local

1. Cài Docker Engine và Compose v2.
2. Copy `.env.example` thành `.env`, đặt mật khẩu riêng.
3. Cấu hình SNMP auth và targets theo thiết bị lab.
4. Chạy `docker compose config`, sau đó `docker compose up -d`.
5. Kiểm tra `docker compose ps` và Prometheus `/targets`.

Giao diện bind loopback; PostgreSQL không publish cổng host. SQL init chỉ chạy khi PostgreSQL tạo data directory mới. `down` giữ volumes.

## VPS tương lai

Cấu hình này là lab/dev, chưa harden production. Trước VPS cần TLS/reverse proxy, secrets management, ACL/authentication, backup/restore đã diễn tập, retention/capacity monitoring, quy trình cập nhật image và kiểm thử khôi phục. Dùng WireGuard/Tailscale hoặc bastion; không mở cổng quản trị, SNMP hay PostgreSQL ra Internet.
