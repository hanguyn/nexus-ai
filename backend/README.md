# Backend (planned)

Backend chưa được triển khai. Định hướng là Python modular monolith dùng FastAPI, SQLAlchemy, Alembic và Pydantic. PostgreSQL sẽ lưu users/authentication, sites/devices, dependencies, alerts/incidents, timelines, anomaly results, RCA evidence, recommendations và audit logs. Prometheus vẫn lưu metrics. Bắt đầu bằng tích hợp chỉ đọc, tương quan quy tắc; chưa tự động remediation.
