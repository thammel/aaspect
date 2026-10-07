# Official AAS schemas

Copied unchanged from [admin-shell-io/aas-specs-metamodel](https://github.com/admin-shell-io/aas-specs-metamodel),
directory `schemas/json/aas.json` and `schemas/xml/AAS.xsd`.

| Version | Tag | Commit |
|---|---|---|
| 3.0 | `IDTA-01001-3-0-1_schemasV3.0.9` | `b11bbab79d9c2b47761ce878bee0ba592ee87513` |
| 3.1 | `v3.1.2` | `a93e41c07c4018e864cba6016b760b9c7e0d849f` |
| 3.2 | `v3.2.0` | `ecd191273a28dd9c4e7bb75e923f0f0fe5da444e` |

License: Creative Commons Attribution 4.0 International, see `LICENSE.txt` (identical in
all three tags). Published by the Industrial Digital Twin Association (IDTA).

The files are not modified. When loading the JSON schemas, AASpect rewrites two things
in memory (`../schema_rewrite.py`):

- Characters outside the Basic Multilingual Plane are matched as UTF-16 surrogate pairs
  (`\ud800[\udc00-\udfff]|...`); this is replaced by the equivalent code-point range.
- Each `oneOf` over element types is replaced by a choice on the element's `modelType`,
  because listing all errors of the original `oneOf` grows exponentially with nesting.

Loading fails if a surrogate pattern or a `oneOf` of another form appears, so check both
rewrites whenever the schemas are updated.
