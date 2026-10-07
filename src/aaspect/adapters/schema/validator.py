import json
from collections.abc import Sequence
from importlib.resources import files

from aaspect.adapters.schema.json_validator import JsonSchemaValidator
from aaspect.adapters.schema.xml_validator import XmlSchemaValidator
from aaspect.domain.corpus import AasDocument, DocumentFormat
from aaspect.domain.metamodel import MetamodelVersion
from aaspect.domain.schema_check import SchemaViolation


class OfficialSchemaValidator:
    """Validates against the official schemas copied into `schemas/`.

    All schemas are compiled up front, so a broken schema fails at startup, not on the
    first upload.
    """

    def __init__(self) -> None:
        self._json = {
            version: JsonSchemaValidator(json.loads(_schema_file(version, "aas.json")))
            for version in MetamodelVersion
        }
        self._xml = {
            version: XmlSchemaValidator(_schema_file(version, "AAS.xsd"))
            for version in MetamodelVersion
        }

    def validate(
        self, document: AasDocument, version: MetamodelVersion
    ) -> Sequence[SchemaViolation]:
        if document.format is DocumentFormat.JSON:
            return self._json[version].validate(document.content)
        return self._xml[version].validate(document.content)


def _schema_file(version: MetamodelVersion, name: str) -> bytes:
    return files("aaspect.adapters.schema").joinpath("schemas", version.value, name).read_bytes()
