"""Runtime settings read from environment variables."""

from __future__ import annotations

import os

from pydantic import BaseModel, Field

DEFAULT_DATABASE_URL = "sqlite:///./finance_ai.db"


class Settings(BaseModel):
    """Application settings. Values come from FAI_* environment variables."""

    database_url: str = Field(default=DEFAULT_DATABASE_URL)
    echo_sql: bool = False

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            database_url=os.environ.get("FAI_DATABASE_URL", DEFAULT_DATABASE_URL),
            echo_sql=os.environ.get("FAI_ECHO_SQL", "0") == "1",
        )
