"""Public entrypoints for the NaraninYeo assistant runtime."""

from dotenv import load_dotenv
load_dotenv()

from naraninyeo.api import create_app


__all__ = ["create_app"]
