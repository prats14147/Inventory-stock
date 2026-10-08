# Connect InventoryAI to a Supabase PostgreSQL database

This connects the local InventoryAI backend to Supabase. It does not deploy the FastAPI backend or the React website.

## 1. Create a Supabase project

Create a project in the Supabase dashboard and set a strong database password. Keep that password private. From the project's **Connect** panel, copy the PostgreSQL connection string. For local development on an IPv4 network, choose the **Session pooler** connection. Use the direct connection if your network supports IPv6; the session pooler is the IPv4-compatible option.

The backend uses SQLAlchemy with psycopg2, so use this shape in the project's root `.env` file:

```dotenv
DATABASE_URL=postgresql+psycopg2://<pooler-user>:<URL-encoded-password>@<pooler-host>:5432/postgres?sslmode=require
```

Use the exact pooler host, port, and username shown in Supabase. For shared pooler strings, the username contains the project reference (for example, `postgres.<project-ref>`). If the dashboard gives a URL beginning `postgresql://`, change only its scheme to `postgresql+psycopg2://`. URL-encode reserved characters in the password. Do not paste the URL into source code or commit `.env`.

`backend/app/config.py` reads this root `.env`, and Alembic reads the same setting. `start_inventoryai.ps1` checks the configured database host: it starts local PostgreSQL only for a localhost URL, and otherwise lets the migration step verify the remote connection.

## 2. Create the schema

From a PowerShell terminal at the repository root:

```powershell
Set-Location backend
..\.venv\Scripts\python.exe -m alembic upgrade head
..\.venv\Scripts\python.exe -m alembic current
```

Check that the current migration revision is printed without a connection or migration error. The `alembic upgrade head` step changes the selected Supabase project's schema, so confirm the project and URL before running it.

## 3. Decide whether to seed or restore data

For a brand-new, empty demo database, load the sample dataset once from the repository root:

```powershell
Set-Location ..
.\.venv\Scripts\python.exe scripts\load_database.py
```

This seeds sample products, stores, inventory, and sales. **Do not rerun the loader on a database with data you want to keep:** it truncates and reloads the `daily_sales` and `daily_inventory` tables.

To move an existing local database and preserve its sales/inventory, make a backup and use a PostgreSQL restore workflow instead. The sample loader is not a database migration tool and will replace those two fact tables with the sample CSV data.

## 4. Start and verify InventoryAI

Return to the repository root and run:

```powershell
Set-Location ..
.\start_inventoryai.ps1
```

The script runs Alembic against the URL in `.env`, starts the API and frontend, and reports whether startup succeeds. The frontend still calls the local API at `127.0.0.1:8000`; only PostgreSQL is remote. The `/api/health` endpoint only confirms that the API process responds, so also sign in and load the Inventory or Sales page to verify database access.

## Security and connection notes

- Keep `DATABASE_URL` on the backend. Never put the database password in `frontend/.env` or frontend code.
- InventoryAI connects directly to PostgreSQL through its backend; it does not need Supabase's browser Data API for this setup. Do not expose tables to public client roles unless you configure suitable privileges and Row Level Security.
- The local startup script now skips the local PostgreSQL check when a remote host is configured. Migrations are the actual connection check.
- Supabase connection options and network/IP support can change; choose the string from the project's **Connect** panel rather than composing the hostname yourself.
