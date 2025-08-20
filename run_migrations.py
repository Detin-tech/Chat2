import os
import sys
from pathlib import Path
from alembic import command
from alembic.config import Config


def main() -> None:
    """Bootstrap database tables using Alembic migrations."""
    project_root = Path(__file__).resolve().parent
    backend_dir = project_root / "backend"
    sys.path.insert(0, str(backend_dir))

    db_path = backend_dir / "open_webui" / "data" / "database.sqlite3"
    os.makedirs(db_path.parent, exist_ok=True)
    os.environ.setdefault("DATABASE_URL", f"sqlite:///{db_path}")

    config = Config(str(backend_dir / "open_webui" / "alembic.ini"))
    config.set_main_option("script_location", str(backend_dir / "open_webui" / "migrations"))

    command.upgrade(config, "head")


if __name__ == "__main__":
    main()
