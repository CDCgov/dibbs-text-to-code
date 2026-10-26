import os
from dataclasses import dataclass
from pathlib import Path

SUPPORTED_DTYPES = ("float32", "float16", "bfloat16")


@dataclass(frozen=True)
class Settings:
    """Runtime configuration for the inference service, read from the environment.

    Attributes:
        retriever_model_uri: Where to load the retriever from: an ``s3://`` prefix, a local
            directory, or a Hugging Face repo id.
        reranker_model_uri: Where to load the reranker from, in the same forms.
        model_dtype: Torch dtype to load both models in.
        model_device: Torch device to run on (``cuda`` in AWS, ``cpu`` or ``mps`` locally).
        model_cache_dir: Local directory that remote models are downloaded into.
    """

    retriever_model_uri: str
    reranker_model_uri: str
    model_dtype: str = "float32"
    model_device: str = "cuda"
    model_cache_dir: Path = Path("/models")

    def __post_init__(self) -> None:
        """Validates the settings.

        Raises:
            ValueError: If the dtype is not supported.
        """
        if self.model_dtype not in SUPPORTED_DTYPES:
            raise ValueError(
                f"MODEL_DTYPE must be one of {', '.join(SUPPORTED_DTYPES)}, got '{self.model_dtype}'"
            )

    @classmethod
    def from_env(cls) -> Settings:
        """Builds settings from environment variables.

        Returns:
            The service settings.

        Raises:
            ValueError: If a required variable is missing or a value is invalid.
        """
        retriever = os.getenv("RETRIEVER_MODEL_URI")
        reranker = os.getenv("RERANKER_MODEL_URI")
        if not retriever or not reranker:
            raise ValueError("RETRIEVER_MODEL_URI and RERANKER_MODEL_URI must both be set")

        return cls(
            retriever_model_uri=retriever,
            reranker_model_uri=reranker,
            model_dtype=os.getenv("MODEL_DTYPE") or "float32",
            model_device=os.getenv("MODEL_DEVICE") or "cuda",
            model_cache_dir=Path(os.getenv("MODEL_CACHE_DIR") or "/models"),
        )
