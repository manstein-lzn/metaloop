#!/usr/bin/env python3
"""Parse a trusted TorchScript .pt file into a versioned JSON graph."""

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from datetime import datetime, timezone
from typing import Any


SCHEMA = "torchscript.graph"
VERSION = "1.0"
ERROR_SCHEMA = "torchscript.parser.error"
MAX_TEXT = 4000


class ParserError(Exception):
    def __init__(self, code: str, message: str, action: str, details: Any | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.action = action
        self.details = details


def clean_text(value: Any, limit: int = MAX_TEXT) -> str:
    text = str(value)
    if len(text) > limit:
        return text[:limit] + "...<truncated>"
    return text


def json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, bytes):
        return clean_text(value.decode("utf-8", errors="replace"))
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value[:100]]
    if isinstance(value, dict):
        return {clean_text(k, 200): json_safe(v) for k, v in list(value.items())[:100]}
    return clean_text(value)


def error_payload(code: str, message: str, action: str, details: Any | None = None) -> dict[str, Any]:
    return {
        "ok": False,
        "error": {
            "schema": ERROR_SCHEMA,
            "version": VERSION,
            "code": code,
            "message": message,
            "action": action,
            "details": json_safe(details),
        },
    }


def print_error(code: str, message: str, action: str, details: Any | None = None) -> int:
    print(json.dumps(error_payload(code, message, action, details), ensure_ascii=False))
    return 0


def value_info(value: Any) -> dict[str, str]:
    return {
        "name": clean_text(getattr(value, "debugName", lambda: "<unnamed>")(), 300),
        "type": clean_text(getattr(value, "type", lambda: "<unknown>")(), 600),
    }


def read_attr(node: Any, name: str) -> Any:
    try:
        kind = node.kindOf(name)
    except Exception as exc:
        return f"<unreadable kind: {exc}>"

    method_names = {
        "i": ["i"],
        "f": ["f"],
        "s": ["s"],
        "is": ["is_", "is"],
        "fs": ["fs"],
        "ss": ["ss"],
        "t": ["t"],
        "ts": ["ts"],
        "g": ["g"],
        "gs": ["gs"],
    }.get(kind, [])

    for method_name in method_names:
        method = getattr(node, method_name, None)
        if method is None:
            continue
        try:
            return json_safe(method(name))
        except Exception:
            continue

    try:
        return clean_text(node[name])
    except Exception as exc:
        return f"<unreadable {kind}: {exc}>"


def node_attributes(node: Any) -> dict[str, Any]:
    attrs: dict[str, Any] = {}
    try:
        names = list(node.attributeNames())
    except Exception:
        return attrs
    for name in names:
        attrs[clean_text(name, 200)] = read_attr(node, name)
    return attrs


def graph_from_module(module: Any) -> Any:
    for attr in ("inlined_graph", "graph"):
        try:
            graph = getattr(module, attr)
            if graph is not None:
                return graph
        except Exception:
            pass
    try:
        return module.forward.graph
    except Exception as exc:
        raise ParserError(
            "GRAPH_NOT_FOUND",
            "Could not locate a TorchScript graph on the loaded module.",
            "Open a TorchScript traced or scripted module that exposes a graph.",
            clean_text(exc),
        )


def check_limits(nodes: list[dict[str, Any]], edges: list[dict[str, Any]], max_nodes: int, max_edges: int) -> None:
    if len(nodes) > max_nodes:
        raise ParserError(
            "GRAPH_TOO_LARGE",
            f"Graph has more than {max_nodes} nodes.",
            "Increase torchscriptDagViewer.maxNodes for trusted files, or inspect a smaller model.",
            {"maxNodes": max_nodes, "actualNodes": len(nodes)},
        )
    if len(edges) > max_edges:
        raise ParserError(
            "GRAPH_TOO_LARGE",
            f"Graph has more than {max_edges} edges.",
            "Increase torchscriptDagViewer.maxEdges for trusted files, or inspect a smaller model.",
            {"maxEdges": max_edges, "actualEdges": len(edges)},
        )


def parse_graph(path: str, max_nodes: int, max_edges: int, max_file_bytes: int) -> dict[str, Any]:
    if not os.path.exists(path):
        raise ParserError("FILE_NOT_FOUND", "The .pt file does not exist.", "Check that the file path is still valid.", path)

    size = os.path.getsize(path)
    if size > max_file_bytes:
        raise ParserError(
            "FILE_TOO_LARGE",
            f"File is {size} bytes, exceeding the configured {max_file_bytes} byte limit.",
            "Increase torchscriptDagViewer.maxFileBytes only for trusted files, or open a smaller model.",
            {"sizeBytes": size, "maxFileBytes": max_file_bytes},
        )

    try:
        import torch  # type: ignore
    except ModuleNotFoundError as exc:
        raise ParserError(
            "PYTORCH_NOT_FOUND",
            "PyTorch is not installed in the selected Python environment.",
            "Install PyTorch in that interpreter or configure torchscriptDagViewer.pythonPath to another interpreter.",
            clean_text(exc),
        )

    try:
        module = torch.jit.load(path, map_location="cpu")
    except Exception as exc:
        raise ParserError(
            "TORCHSCRIPT_LOAD_FAILED",
            "torch.jit.load failed for this trusted .pt file.",
            "Verify that the file is a valid TorchScript traced or scripted artifact and was saved from a trusted source.",
            {"exception": clean_text(exc), "traceback": clean_text(traceback.format_exc())},
        )

    graph = graph_from_module(module)
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    warnings: list[str] = []
    producer_by_value: dict[str, str] = {}

    try:
        graph_inputs = list(graph.inputs())
    except Exception:
        graph_inputs = []
        warnings.append("Could not enumerate graph inputs.")

    try:
        graph_outputs = list(graph.outputs())
    except Exception:
        graph_outputs = []
        warnings.append("Could not enumerate graph outputs.")

    for idx, value in enumerate(graph_inputs):
        info = value_info(value)
        node_id = f"input:{info['name'] or idx}"
        producer_by_value[info["name"]] = node_id
        nodes.append(
            {
                "id": node_id,
                "label": info["name"] or f"input {idx}",
                "kind": "graph::Input",
                "scope": "",
                "attributes": {"type": info["type"]},
                "inputs": [],
                "outputs": [info],
            }
        )
        check_limits(nodes, edges, max_nodes, max_edges)

    try:
        op_nodes = list(graph.nodes())
    except Exception as exc:
        raise ParserError(
            "GRAPH_ENUMERATION_FAILED",
            "Could not enumerate graph nodes.",
            "Verify the file can be loaded by the configured PyTorch version.",
            clean_text(exc),
        )

    for idx, raw_node in enumerate(op_nodes):
        node_id = f"node:{idx}"
        try:
            kind = clean_text(raw_node.kind(), 300)
        except Exception:
            kind = "<unknown>"
        try:
            scope = clean_text(raw_node.scopeName(), 600)
        except Exception:
            scope = ""
        try:
            inputs = [value_info(value) for value in raw_node.inputs()]
        except Exception:
            inputs = []
            warnings.append(f"Could not enumerate inputs for {node_id}.")
        try:
            outputs = [value_info(value) for value in raw_node.outputs()]
        except Exception:
            outputs = []
            warnings.append(f"Could not enumerate outputs for {node_id}.")

        attrs = node_attributes(raw_node)
        try:
            source_range = clean_text(raw_node.sourceRange(), 1200)
            if source_range:
                attrs["sourceRange"] = source_range
        except Exception:
            pass

        display_name = kind.split("::")[-1] if "::" in kind else kind
        nodes.append(
            {
                "id": node_id,
                "label": display_name,
                "kind": kind,
                "scope": scope,
                "attributes": attrs,
                "inputs": inputs,
                "outputs": outputs,
            }
        )

        for input_value in inputs:
            source = producer_by_value.get(input_value["name"])
            if source:
                edges.append(
                    {
                        "id": f"edge:{len(edges)}",
                        "source": source,
                        "target": node_id,
                        "label": input_value["name"],
                        "type": input_value["type"],
                    }
                )

        for output_value in outputs:
            producer_by_value[output_value["name"]] = node_id
        check_limits(nodes, edges, max_nodes, max_edges)

    for idx, value in enumerate(graph_outputs):
        info = value_info(value)
        node_id = f"output:{idx}:{info['name']}"
        nodes.append(
            {
                "id": node_id,
                "label": info["name"] or f"output {idx}",
                "kind": "graph::Output",
                "scope": "",
                "attributes": {"type": info["type"]},
                "inputs": [info],
                "outputs": [],
            }
        )
        source = producer_by_value.get(info["name"])
        if source:
            edges.append(
                {
                    "id": f"edge:{len(edges)}",
                    "source": source,
                    "target": node_id,
                    "label": info["name"],
                    "type": info["type"],
                }
            )
        check_limits(nodes, edges, max_nodes, max_edges)

    return {
        "schema": SCHEMA,
        "version": VERSION,
        "model": {
            "path": os.path.abspath(path),
            "fileName": os.path.basename(path),
            "sizeBytes": size,
            "torchVersion": clean_text(getattr(torch, "__version__", "unknown"), 100),
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "graphInputCount": len(graph_inputs),
            "graphOutputCount": len(graph_outputs),
        },
        "nodes": nodes,
        "edges": edges,
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Parse a trusted TorchScript .pt file.")
    parser.add_argument("model_path")
    parser.add_argument("--max-nodes", type=int, required=True)
    parser.add_argument("--max-edges", type=int, required=True)
    parser.add_argument("--max-file-bytes", type=int, required=True)
    args = parser.parse_args()

    try:
        graph = parse_graph(args.model_path, args.max_nodes, args.max_edges, args.max_file_bytes)
    except ParserError as exc:
        return print_error(exc.code, exc.message, exc.action, exc.details)
    except Exception as exc:
        return print_error(
            "PARSER_FAILED",
            "The parser failed unexpectedly.",
            "Check the selected Python environment and try opening the file again.",
            {"exception": clean_text(exc), "traceback": clean_text(traceback.format_exc())},
        )

    print(json.dumps({"ok": True, "graph": graph}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
