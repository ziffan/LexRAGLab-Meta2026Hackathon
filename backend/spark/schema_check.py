"""Pra-validasi skema strict (G-03, O-14) dan validasi keluaran terhadap skema (subset JSON Schema).

`check_strict` menolak sebelum jaringan; `validate_instance` memeriksa keluaran model (tanpa
dependensi `jsonschema`)."""

from __future__ import annotations

import re
from typing import Any

_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_TYPES = {
    "string": lambda v: isinstance(v, str),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "null": lambda v: v is None,
    "array": lambda v: isinstance(v, list),
    "object": lambda v: isinstance(v, dict),
}


def check_schema_name(name: Any) -> str | None:
    if not isinstance(name, str) or not _NAME_RE.match(name):
        return "schema_name must match [A-Za-z0-9_-]{1,64}"
    return None


def _resolve(root: dict, ref: str) -> Any:
    if not isinstance(ref, str) or not ref.startswith("#/"):
        return None
    node: Any = root
    for part in ref[2:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def check_strict(schema: Any) -> str | None:
    """None bila skema memenuhi aturan strict Responses API (G-03); selain itu alasan satu baris."""
    if not isinstance(schema, dict):
        return "schema must be an object"
    if schema.get("type") != "object":
        return "root schema must have type 'object'"
    if "anyOf" in schema:
        return "anyOf is not allowed at the root"
    return _walk(schema, schema, "$", ())


def _walk(node: Any, root: dict, path: str, ref_stack: tuple[str, ...]) -> str | None:
    if not isinstance(node, dict):
        return f"{path}: schema node must be an object"
    if "$ref" in node:
        ref = node["$ref"]
        if ref in ref_stack:
            return f"{path}: recursive schema ($ref {ref}) is not supported"
        target = _resolve(root, ref)
        if target is None:
            return f"{path}: unresolved $ref"
        return _walk(target, root, path, ref_stack + (ref,))
    for banned in ("allOf", "oneOf"):
        if banned in node:
            return f"{path}: {banned} is not supported"
    if "anyOf" in node:
        branches = node["anyOf"]
        if not isinstance(branches, list) or not branches:
            return f"{path}: anyOf must be a non-empty list"
        for i, b in enumerate(branches):
            err = _walk(b, root, f"{path}.anyOf[{i}]", ref_stack)
            if err:
                return err
    props = node.get("properties")
    if node.get("type") == "object" or props is not None:
        if node.get("additionalProperties") is not False:
            return f"{path}: object must set additionalProperties to false"
        props = props or {}
        if not isinstance(props, dict):
            return f"{path}: properties must be an object"
        required = node.get("required", [])
        if not isinstance(required, list):
            return f"{path}: required must be a list"
        missing = sorted(set(props) - set(required))
        if missing:
            return f"{path}: required must list every property (missing: {', '.join(missing)})"
        unknown = sorted(set(required) - set(props))
        if unknown:
            return f"{path}: required lists unknown properties ({', '.join(unknown)})"
        for k, sub in props.items():
            err = _walk(sub, root, f"{path}.{k}", ref_stack)
            if err:
                return err
    if "items" in node:
        err = _walk(node["items"], root, f"{path}[]", ref_stack)
        if err:
            return err
    return None


def validate_instance(value: Any, schema: Any, root: dict | None = None) -> str | None:
    """None bila `value` sesuai `schema`; selain itu alasan satu baris (tanpa isi nilai)."""
    root = root if root is not None else schema
    return _check(value, schema, root, "$")


def _check(value: Any, schema: Any, root: dict, path: str) -> str | None:
    if not isinstance(schema, dict):
        return None
    if "$ref" in schema:
        target = _resolve(root, schema["$ref"])
        return _check(value, target, root, path) if target is not None else f"{path}: unresolved $ref"
    if "anyOf" in schema:
        for b in schema["anyOf"]:
            if _check(value, b, root, path) is None:
                return None
        return f"{path}: does not match any allowed shape"
    t = schema.get("type")
    if t is not None:
        types = t if isinstance(t, list) else [t]
        if not any(_TYPES.get(x, lambda _v: False)(value) for x in types):
            return f"{path}: wrong type"
    ml = schema.get("maxLength")
    if isinstance(value, str) and isinstance(ml, int) and not isinstance(ml, bool) and len(value) > ml:
        return f"{path}: string longer than maxLength {ml}"
    if "enum" in schema and value not in schema["enum"]:
        return f"{path}: value not in enum"
    if "const" in schema and value != schema["const"]:
        return f"{path}: value differs from const"
    if isinstance(value, dict):
        props = schema.get("properties", {})
        for k in schema.get("required", []):
            if k not in value:
                return f"{path}: missing required key '{k}'"
        if schema.get("additionalProperties") is False:
            extra = sorted(set(value) - set(props))
            if extra:
                return f"{path}: unexpected key '{extra[0]}'"
        for k, sub in props.items():
            if k in value:
                err = _check(value[k], sub, root, f"{path}.{k}")
                if err:
                    return err
    if isinstance(value, list) and "items" in schema:
        for i, item in enumerate(value):
            err = _check(item, schema["items"], root, f"{path}[{i}]")
            if err:
                return err
    return None
