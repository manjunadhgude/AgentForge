"""Environment-based configuration for AgentForge."""
from dataclasses import dataclass
import os
from sqlalchemy.engine import URL


@dataclass(frozen=True)
class Settings:
    app_name: str = "AgentForge"
    environment: str = "development"
    log_level: str = "INFO"
    database_host: str = "127.0.0.1"
    database_port: int = 5432
    database_name: str = "agentforge"
    database_user: str = "agentforge"
    llm_provider: str = "fake"
    llm_model: str = "fake-agentforge-model"

    @classmethod
    def from_env(cls) -> "Settings":
        port_text = os.getenv("AGENTFORGE_DB_PORT", "5432")
        try:
            port = int(port_text)
        except ValueError as exc:
            raise ValueError("AGENTFORGE_DB_PORT must be an integer") from exc

        if not 1 <= port <= 65535:
            raise ValueError("AGENTFORGE_DB_PORT must be between 1 and 65535")

        level = os.getenv("AGENTFORGE_LOG_LEVEL", "INFO").upper()
        if level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("AGENTFORGE_LOG_LEVEL is invalid")

        provider = os.getenv("AGENTFORGE_LLM_PROVIDER", "fake").lower()
        if provider not in {"fake", "openai"}:
            raise ValueError("AGENTFORGE_LLM_PROVIDER must be fake or openai")

        return cls(
            app_name=os.getenv("AGENTFORGE_APP_NAME", "AgentForge"),
            environment=os.getenv("AGENTFORGE_ENV", "development"),
            log_level=level,
            database_host=os.getenv("AGENTFORGE_DB_HOST", "127.0.0.1"),
            database_port=port,
            database_name=os.getenv("AGENTFORGE_DB_NAME", "agentforge"),
            database_user=os.getenv("AGENTFORGE_DB_USER", "agentforge"),
            llm_provider=provider,
            llm_model=os.getenv(
                "AGENTFORGE_LLM_MODEL", "fake-agentforge-model"
            ),
        )

    def database_url(self) -> URL:
        """Build a safely escaped SQLAlchemy URL without exposing the password."""
        password = os.getenv("AGENTFORGE_DB_PASSWORD")
        if not password:
            raise ValueError(
                "Set AGENTFORGE_DB_PASSWORD in the current shell first."
            )

        return URL.create(
            drivername="postgresql+psycopg",
            username=self.database_user,
            password=password,
            host=self.database_host,
            port=self.database_port,
            database=self.database_name,
        )


settings = Settings.from_env()
