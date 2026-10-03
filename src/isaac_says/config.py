"""All settings. Values come from environment variables, then the .env file, then the defaults.

Variable names are the upper-cased field names (llm_model is LLM_MODEL).
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# The project root is the folder that holds pyproject.toml.
PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        extra="ignore",  # ignore other variables in .env
    )

    # Secrets. SecretStr keeps them out of logs.
    openai_api_key: SecretStr | None = None
    admin_api_key: SecretStr | None = None

    @field_validator("openai_api_key", "admin_api_key", mode="before")
    @classmethod
    def _clean_secret(cls, value: object) -> object:
        """Remove quotes and spaces around a key, and treat an empty value as not set.

        Docker's --env-file keeps quote characters, so KEY="abc" would arrive with the quotes.
        """
        if isinstance(value, str):
            value = value.strip().strip("\"'").strip()
            return value or None
        return value

    # Models. Reasoning "none" is faster and cheaper.
    llm_model: str = "gpt-5.6-luna"
    reasoning_effort: Literal["none", "low", "medium", "high"] = "none"
    embedding_model: str = "text-embedding-3-small"
    # Seconds to wait for the model before giving up and retrying.
    llm_timeout_seconds: float = Field(default=12.0, gt=0)
    llm_long_timeout_seconds: float = Field(default=40.0, gt=0)

    # Search
    retrieval_top_k: int = Field(default=6, ge=1, le=20)
    review_top_k: int = Field(default=5, ge=1, le=20)  # results per query, for reviews
    # Chunks scoring below this similarity are dropped before the model sees them.
    min_relevance_score: float = Field(default=0.35, ge=0.0, le=1.0)

    # Data
    substack_publication: str = "explainthedata"  # the <name> in <name>.substack.com
    data_dir: Path = PROJECT_ROOT / "data"

    # API
    cors_origins: list[str] = ["http://localhost:8501"]  # Streamlit's default address
    rate_limit_per_minute: int = Field(default=20, ge=1)
    # Most chat messages allowed per day across all visitors, to cap the bill. 0 means no limit.
    daily_question_limit: int = Field(default=300, ge=0)
    # Behind a proxy every request comes from the proxy's address. When true, the rate limit uses
    # the X-Real-IP header instead. Only turn it on if visitors cannot reach the API directly.
    trust_client_ip_header: bool = False
    # `isaac-says purge-threads` deletes conversations idle for longer than this.
    thread_retention_days: int = Field(default=30, ge=1)

    # Prices in USD per million tokens, only used to estimate the cost of each chat.
    llm_input_price_per_m: float = 0.20
    llm_output_price_per_m: float = 1.20

    # Paths worked out from data_dir
    @property
    def snapshot_path(self) -> Path:
        """The saved copy of the newsletter posts, one JSON object per line."""
        return self.data_dir / "raw" / "posts.jsonl"

    @property
    def chroma_dir(self) -> Path:
        return self.data_dir / "chroma"

    @property
    def app_db_url(self) -> str:
        """The database for the question queue, logs and feedback."""
        return f"sqlite+aiosqlite:///{(self.data_dir / 'app.db').as_posix()}"

    @property
    def checkpoint_path(self) -> Path:
        """Where conversations are saved, so they survive a restart."""
        return self.data_dir / "checkpoints.sqlite"

    def require_openai_key(self) -> str:
        """Return the OpenAI key, or stop with a clear message if it is missing."""
        if self.openai_api_key is None or not self.openai_api_key.get_secret_value():
            raise RuntimeError(
                "OPENAI_API_KEY is not set. Copy .env.example to .env and add your key."
            )
        return self.openai_api_key.get_secret_value()


@lru_cache
def get_settings() -> Settings:
    """Return the settings (created once and reused)."""
    return Settings()
