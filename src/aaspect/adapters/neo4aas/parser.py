import json
from xml.etree.ElementTree import ParseError

from neo4aas.core.serialization.xml.xml_to_json import xml_to_aas_json

from aaspect.domain.corpus import AasDocument, DocumentFormat
from aaspect.domain.id_collisions import Environment


class Neo4aasEnvironmentParser:
    """JSON as it is; XML through neo4aas's own conversion, so that both arrive in the
    structure its importer expects."""

    def parse(self, document: AasDocument) -> Environment:
        try:
            # neo4aas reads a str as a file path; only bytes are content.
            if not isinstance(document.content, bytes):
                raise ValueError("not an AAS environment")
            if document.format is DocumentFormat.XML:
                # The standard library parser expands no external entities, and its
                # expat refuses entity amplification attacks.
                environment = xml_to_aas_json(document.content)
            else:
                environment = json.loads(document.content.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError, ParseError) as error:
            raise ValueError(f"not well-formed: {error}") from None
        if not isinstance(environment, dict):
            raise ValueError("not an AAS environment")
        return environment
