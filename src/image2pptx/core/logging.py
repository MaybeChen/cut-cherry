import structlog


def configure_logging() -> None:
    structlog.configure(processors=[structlog.processors.JSONRenderer()])
