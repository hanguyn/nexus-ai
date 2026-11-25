# Bảo mật

`.env` được ignore bởi Git; không commit secrets. Đổi mật khẩu mẫu Grafana/PostgreSQL. SNMP v2c không mã hóa community; production nên dùng SNMP v3 auth/privacy. Dùng credential chỉ đọc, ACL giới hạn exporter, module phù hợp model. Thiết bị phải cho phép UDP/161 từ exporter.

Cổng quản trị chỉ bind `127.0.0.1`; PostgreSQL không có host port. Không mở SNMP/SSH Internet-facing. Remote access nên qua WireGuard/Tailscale có ACL. Blackbox cần `NET_RAW` cho ICMP; chỉ probe đích được phép. Grafana-PostgreSQL đang dùng SSL disable trên mạng Compose riêng, cần thiết kế lại cho production.

Đây là lab/dev, chưa có TLS, secret manager, RBAC nghiệp vụ hoặc xoay vòng credentials; chưa được harden production.
