from enum import StrEnum


class MetamodelVersion(StrEnum):
    V3_0 = "3.0"
    V3_1 = "3.1"
    V3_2 = "3.2"


NEWEST_FIRST = (MetamodelVersion.V3_2, MetamodelVersion.V3_1, MetamodelVersion.V3_0)
