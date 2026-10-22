"""Everything that differs between versions of the AAS metamodel, in one place.

A new version is added here: its name and its XML namespace.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum


class MetamodelVersion(StrEnum):
    V3_0 = "3.0"
    V3_1 = "3.1"
    V3_2 = "3.2"


@dataclass(frozen=True, slots=True)
class VersionDetails:
    xml_namespace: str


DETAILS: Mapping[MetamodelVersion, VersionDetails] = {
    MetamodelVersion.V3_0: VersionDetails(xml_namespace="https://admin-shell.io/aas/3/0"),
    MetamodelVersion.V3_1: VersionDetails(xml_namespace="https://admin-shell.io/aas/3/1"),
    MetamodelVersion.V3_2: VersionDetails(xml_namespace="https://admin-shell.io/aas/3/2"),
}

NEWEST_FIRST = (MetamodelVersion.V3_2, MetamodelVersion.V3_1, MetamodelVersion.V3_0)
OLDEST_FIRST = tuple(reversed(NEWEST_FIRST))
