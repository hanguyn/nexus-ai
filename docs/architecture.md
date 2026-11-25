# Kiến trúc

Prometheus lưu time-series và scrape chính nó cùng exporters. SNMP Exporter chuyển `/snmp` thành metrics; Blackbox thực hiện ICMP/HTTP/HTTPS/TCP qua `/probe`. File service discovery cho phép thêm mục tiêu mà không sửa scrape jobs. Alertmanager nhận cảnh báo nhưng chưa gửi thông báo.

Grafana provision Prometheus và PostgreSQL. Network `monitoring` nối Prometheus/exporters/Alertmanager/Grafana. Network `application` là internal, nối Grafana với PostgreSQL; Grafana tham gia cả hai. PostgreSQL chỉ có schema nền; metrics không lưu tại đây.

Trong tương lai backend modular monolith có thể đọc metrics/sự kiện qua API, quản lý users/sites/devices/incidents và ghi RCA evidence/audit vào PostgreSQL. RCA phải nêu bằng chứng có cấu trúc. Chưa có backend hay AI. Có thể mở rộng sang Linux/Windows servers, apps, logs và nhiều site.
