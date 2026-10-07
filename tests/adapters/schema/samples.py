from functools import cache
from pathlib import Path

from aaspect.adapters.schema.validator import OfficialSchemaValidator
from aaspect.domain.metamodel import MetamodelVersion

SAMPLES = Path(__file__).parent / "samples"


def sample(version: MetamodelVersion, name: str) -> bytes:
    return (SAMPLES / version.value / name).read_bytes()


@cache
def official_validator() -> OfficialSchemaValidator:
    """Shared across tests: compiling all six schemas takes a noticeable fraction of a second."""
    return OfficialSchemaValidator()
