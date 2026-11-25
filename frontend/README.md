# NEXUS AI dashboard

From the repository root, run `docker compose --env-file .env -f deployment/docker-compose.yml up -d --build`. The dashboard listens at `http://127.0.0.1:8080` by default. Override `WEB_BIND_ADDRESS` and `WEB_PORT` in the root environment as needed.

For local frontend development, run `npm install` and `npm run dev` from this directory while the backend listens at `127.0.0.1:8000`. Vite proxies `/api` in development. Run `npm run build` to type-check and bundle the application.

The Demo view uses `GET /api/v1/simulator/scenarios` and the seed, trigger, recovery, and reset endpoints documented in the [project README](../README.md).
