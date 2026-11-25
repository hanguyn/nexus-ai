# Lộ trình

1. **Monitoring foundation (hiện tại):** Compose, Prometheus, exporters, Alertmanager, Grafana, PostgreSQL; chưa xác nhận với thiết bị thật hay notification.
2. **Backend modular monolith:** FastAPI/SQLAlchemy/Alembic/Pydantic; users, sites/devices, dependencies, alerts/incidents, timelines, audit.
3. **Frontend:** React/TypeScript/Vite/Tailwind.
4. **Chẩn đoán:** rule correlation/RCA có evidence trước anomaly detection (Pandas/NumPy/scikit-learn/Isolation Forest) và LLM adapter giới hạn. Không tự tạo metrics/root cause.
5. **Mở rộng:** servers, apps, logs, multi-site, notifications, Nginx/TLS, backups và VPS hardening. Mặc định chỉ đọc, không tự remediation.
