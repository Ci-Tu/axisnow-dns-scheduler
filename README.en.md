# AxisNow DNS Scheduler

English · [简体中文](README.md)

A self-hosted console for [AxisNow](https://axisnow.io) DNS routing, with a pluggable scheduling engine on top.

- **Day-to-day console replacement**: routing domains, rules, geo/ISP lines, address pools and probe templates in one place. Logins last 180 days and survive container rebuilds.
- **Things the official console can't do**:
  - **Tide scheduling** – switch IP priority order by time of day;
  - **Probe failover** – automatically demote IPs that the edge probes mark as unavailable, and restore them on recovery;
  - **Unified probe wizard** – build a working HTTP probe template for self-hosted servers and clean up duplicate probe tasks;
  - **One-click Cloudflare linking** – create a DNS-only CNAME on your own zone pointing at the routing domain.
- **Every IP shows a flag and its network**, resolved offline from the DB-IP Lite database.

> Not affiliated with AxisNow. Uses their public client API.

## Quick start

```bash
git clone https://github.com/Ci-Tu/axisnow-dns-scheduler.git
cd axisnow-dns-scheduler
cp .env.example .env        # optional
docker compose up -d --build
```

Open `http://<host>:4894`, set an access password, then add your AxisNow API token under **Settings**.
All state lives in `./data` — persist and back it up.

See the Chinese README for the full list of environment variables; they are also documented in [.env.example](.env.example).

## Architecture

- **Backend** (`backend/`): Flask JSON API split by domain (`api/`), business logic in `services/`,
  upstream clients with a shared stale-while-revalidate cache in `clients/`, pluggable `features/`,
  and a scheduler that only writes to AxisNow when the desired state actually changes.
  Configuration is stored in `data/config.json`; probe samples and apply events in SQLite (`data/history.db`).
- **Frontend** (`frontend/`): Vue 3 + TypeScript + Naive UI single-page app, built into the same Docker image.

## Development

```bash
cd backend && pip install -e ".[dev]" && pytest && ruff check .
cd frontend && npm install && npm run dev   # proxies /api to :4894
```

Adding a feature module: see [CONTRIBUTING.md](CONTRIBUTING.md).

## Credits

- IP geolocation: [IP Geolocation by DB-IP](https://db-ip.com) (CC BY 4.0)
- Flags: [flag-icons](https://github.com/lipis/flag-icons) (MIT)

## License

[MIT](LICENSE)
