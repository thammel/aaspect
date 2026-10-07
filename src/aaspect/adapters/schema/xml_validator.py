import threading

from lxml import etree

from aaspect.adapters.schema.violations import capped, unchecked, violation
from aaspect.domain.schema_check import SchemaViolation


class XmlSchemaValidator:
    def __init__(self, xsd: bytes, max_violations: int) -> None:
        self._schema = etree.XMLSchema(etree.fromstring(xsd, _safe_parser()))
        self._max_violations = max_violations
        # The error log lives on the shared schema object, so concurrent validations
        # would read each other's errors.
        self._lock = threading.Lock()

    def validate(self, content: bytes) -> list[SchemaViolation]:
        try:
            root = etree.fromstring(content, _safe_parser())
        except etree.XMLSyntaxError as error:
            return [unchecked("well-formedness", f"Not well-formed XML: {error}")]
        with self._lock:
            try:
                if self._schema.validate(root):
                    return []
            except etree.XMLSchemaValidateError as error:
                # Raised e.g. for entity references left unexpanded by the safe parser.
                return [unchecked("unvalidatable", f"Schema validation aborted: {error}")]
            entries = list(self._schema.error_log)
        return capped((_from_entry(root, entry) for entry in entries), self._max_violations)


def _safe_parser() -> etree.XMLParser:
    # Uploaded XML is untrusted: no entity expansion (XXE, billion laughs), no DTD or
    # network fetches, and libxml2's default depth and size limits stay on.
    return etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False, huge_tree=False)


def _from_entry(root: etree._Element, entry: etree._LogEntry) -> SchemaViolation:
    """libxml2 only gives positional paths such as `/*/*[7]`. Grouping needs element names,
    so the path is rebuilt from the element it points at."""
    element = _resolve(root, entry.path)
    if element is None:
        instance_path = generic_path = entry.path or ""
    else:
        instance_path, generic_path = _named_paths(element)
    return violation(
        keyword=entry.type_name,
        schema_path=generic_path,
        instance_path=instance_path,
        message=entry.message,
    )


def _resolve(root: etree._Element, path: str | None) -> etree._Element | None:
    if not path:
        return None
    # libxml2 writes the document's own prefixes into the path (`/aas:environment/...`).
    prefixes = {prefix: uri for prefix, uri in root.nsmap.items() if prefix}
    try:
        found = root.getroottree().xpath(path, namespaces=prefixes)
    except etree.XPathError:
        # E.g. a prefix declared below the root; the raw path is still reported.
        return None
    if isinstance(found, list) and found and isinstance(found[0], etree._Element):
        return found[0]
    return None


def _named_paths(element: etree._Element) -> tuple[str, str]:
    """`/environment/submodels/submodel[2]/id`, and the same without positions."""
    indexed: list[str] = []
    generic: list[str] = []
    for node in [element, *element.iterancestors()]:
        name = etree.QName(node).localname
        generic.append(name)
        parent = node.getparent()
        siblings = [] if parent is None else [child for child in parent if child.tag == node.tag]
        indexed.append(f"{name}[{siblings.index(node) + 1}]" if len(siblings) > 1 else name)
    return "/" + "/".join(reversed(indexed)), "/" + "/".join(reversed(generic))
