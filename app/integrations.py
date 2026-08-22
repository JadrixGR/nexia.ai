"""Traduce Responses/Anthropic a Chat Completions y de vuelta."""
from __future__ import annotations

import json
import secrets
import time
from typing import Any


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return str(content or "")
    parts: list[str] = []
    for part in content:
        if isinstance(part, str):
            parts.append(part)
        elif isinstance(part, dict):
            text = part.get("text") or part.get("content")
            if text is not None:
                parts.append(str(text))
    return "\n".join(parts)


def responses_to_chat(body: dict) -> tuple[list[dict], list[dict]]:
    messages: list[dict] = []
    instructions = body.get("instructions")
    if instructions:
        messages.append({"role": "system", "content": _content_text(instructions)})
    source = body.get("input", "")
    if isinstance(source, str):
        messages.append({"role": "user", "content": source})
    elif isinstance(source, list):
        for item in source:
            if not isinstance(item, dict):
                continue
            item_type = item.get("type", "message")
            if item_type == "message":
                role = item.get("role", "user")
                if role == "developer":
                    role = "system"
                messages.append({"role": role, "content": _content_text(item.get("content", ""))})
            elif item_type == "function_call_output":
                messages.append({
                    "role": "tool",
                    "tool_call_id": item.get("call_id") or item.get("id"),
                    "content": _content_text(item.get("output", "")),
                })
            elif item_type == "function_call":
                messages.append({
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{
                        "id": item.get("call_id") or item.get("id"),
                        "type": "function",
                        "function": {"name": item.get("name"), "arguments": item.get("arguments", "{}")},
                    }],
                })
    tools: list[dict] = []
    for tool in body.get("tools") or []:
        if not isinstance(tool, dict) or tool.get("type") != "function":
            continue
        tools.append({
            "type": "function",
            "function": {
                "name": tool.get("name"),
                "description": tool.get("description", ""),
                "parameters": tool.get("parameters") or {},
            },
        })
    return messages, tools


def _response_output(message: dict) -> list[dict]:
    output: list[dict] = []
    content = _content_text(message.get("content"))
    if content:
        output.append({
            "id": "msg_" + secrets.token_hex(12),
            "type": "message",
            "status": "completed",
            "role": "assistant",
            "content": [{"type": "output_text", "text": content, "annotations": []}],
        })
    for call in message.get("tool_calls") or []:
        function = call.get("function") or {}
        output.append({
            "id": "fc_" + secrets.token_hex(12),
            "type": "function_call",
            "status": "completed",
            "call_id": call.get("id") or "call_" + secrets.token_hex(12),
            "name": function.get("name", "tool"),
            "arguments": function.get("arguments", "{}"),
        })
    return output


def chat_to_response(payload: dict, model: str) -> dict:
    choice = (payload.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    usage = payload.get("usage") or {}
    return {
        "id": "resp_" + secrets.token_hex(16),
        "object": "response",
        "created_at": int(time.time()),
        "status": "completed",
        "error": None,
        "model": model,
        "output": _response_output(message),
        "usage": {
            "input_tokens": int(usage.get("prompt_tokens") or 0),
            "output_tokens": int(usage.get("completion_tokens") or 0),
            "total_tokens": int(usage.get("total_tokens") or 0),
        },
    }


def responses_sse(response: dict):
    created = dict(response)
    created["status"] = "in_progress"
    created["output"] = []
    yield _event("response.created", {"type": "response.created", "response": created, "sequence_number": 0})
    sequence = 1
    for index, item in enumerate(response["output"]):
        added = dict(item)
        added["status"] = "in_progress"
        if item["type"] == "message":
            added["content"] = []
        elif item["type"] == "function_call":
            added["arguments"] = ""
        yield _event("response.output_item.added", {"type": "response.output_item.added", "output_index": index, "item": added, "sequence_number": sequence})
        sequence += 1
        if item["type"] == "message":
            text = item["content"][0]["text"]
            part = {"type": "output_text", "text": "", "annotations": []}
            yield _event("response.content_part.added", {"type": "response.content_part.added", "item_id": item["id"], "output_index": index, "content_index": 0, "part": part, "sequence_number": sequence})
            sequence += 1
            yield _event("response.output_text.delta", {"type": "response.output_text.delta", "item_id": item["id"], "output_index": index, "content_index": 0, "delta": text, "sequence_number": sequence})
            sequence += 1
            yield _event("response.output_text.done", {"type": "response.output_text.done", "item_id": item["id"], "output_index": index, "content_index": 0, "text": text, "sequence_number": sequence})
            sequence += 1
            yield _event("response.content_part.done", {"type": "response.content_part.done", "item_id": item["id"], "output_index": index, "content_index": 0, "part": item["content"][0], "sequence_number": sequence})
            sequence += 1
        else:
            arguments = item.get("arguments", "{}")
            yield _event("response.function_call_arguments.delta", {"type": "response.function_call_arguments.delta", "item_id": item["id"], "output_index": index, "delta": arguments, "sequence_number": sequence})
            sequence += 1
            yield _event("response.function_call_arguments.done", {"type": "response.function_call_arguments.done", "item_id": item["id"], "output_index": index, "arguments": arguments, "sequence_number": sequence})
            sequence += 1
        yield _event("response.output_item.done", {"type": "response.output_item.done", "output_index": index, "item": item, "sequence_number": sequence})
        sequence += 1
    yield _event("response.completed", {"type": "response.completed", "response": response, "sequence_number": sequence})


def anthropic_to_chat(body: dict) -> tuple[list[dict], list[dict]]:
    messages: list[dict] = []
    if body.get("system"):
        messages.append({"role": "system", "content": _content_text(body["system"])})
    for item in body.get("messages") or []:
        if not isinstance(item, dict):
            continue
        role = item.get("role", "user")
        content = item.get("content", "")
        if isinstance(content, str):
            messages.append({"role": role, "content": content})
            continue
        text_parts: list[str] = []
        tool_calls: list[dict] = []
        for part in content if isinstance(content, list) else []:
            if not isinstance(part, dict):
                continue
            if part.get("type") == "text":
                text_parts.append(str(part.get("text") or ""))
            elif part.get("type") == "tool_use":
                tool_calls.append({
                    "id": part.get("id"),
                    "type": "function",
                    "function": {"name": part.get("name"), "arguments": json.dumps(part.get("input") or {})},
                })
            elif part.get("type") == "tool_result":
                messages.append({
                    "role": "tool",
                    "tool_call_id": part.get("tool_use_id"),
                    "content": _content_text(part.get("content", "")),
                })
        if text_parts or tool_calls:
            message = {"role": role, "content": "\n".join(text_parts)}
            if tool_calls:
                message["tool_calls"] = tool_calls
            messages.append(message)
    tools = [{
        "type": "function",
        "function": {
            "name": tool.get("name"),
            "description": tool.get("description", ""),
            "parameters": tool.get("input_schema") or {},
        },
    } for tool in body.get("tools") or [] if isinstance(tool, dict)]
    return messages, tools


def chat_to_anthropic(payload: dict, model: str) -> dict:
    choice = (payload.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    content: list[dict] = []
    text = _content_text(message.get("content"))
    if text:
        content.append({"type": "text", "text": text})
    for call in message.get("tool_calls") or []:
        function = call.get("function") or {}
        try:
            tool_input = json.loads(function.get("arguments") or "{}")
        except json.JSONDecodeError:
            tool_input = {"raw": function.get("arguments") or ""}
        content.append({
            "type": "tool_use",
            "id": call.get("id") or "toolu_" + secrets.token_hex(12),
            "name": function.get("name", "tool"),
            "input": tool_input,
        })
    usage = payload.get("usage") or {}
    return {
        "id": "msg_" + secrets.token_hex(16),
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": content,
        "stop_reason": "tool_use" if any(part["type"] == "tool_use" for part in content) else "end_turn",
        "stop_sequence": None,
        "usage": {
            "input_tokens": int(usage.get("prompt_tokens") or 0),
            "output_tokens": int(usage.get("completion_tokens") or 0),
        },
    }


def anthropic_sse(message: dict):
    start = dict(message)
    start["content"] = []
    start["stop_reason"] = None
    yield _event("message_start", {"type": "message_start", "message": start})
    for index, part in enumerate(message["content"]):
        if part["type"] == "text":
            yield _event("content_block_start", {"type": "content_block_start", "index": index, "content_block": {"type": "text", "text": ""}})
            yield _event("content_block_delta", {"type": "content_block_delta", "index": index, "delta": {"type": "text_delta", "text": part["text"]}})
        else:
            yield _event("content_block_start", {"type": "content_block_start", "index": index, "content_block": {"type": "tool_use", "id": part["id"], "name": part["name"], "input": {}}})
            yield _event("content_block_delta", {"type": "content_block_delta", "index": index, "delta": {"type": "input_json_delta", "partial_json": json.dumps(part["input"])}})
        yield _event("content_block_stop", {"type": "content_block_stop", "index": index})
    yield _event("message_delta", {"type": "message_delta", "delta": {"stop_reason": message["stop_reason"], "stop_sequence": None}, "usage": {"output_tokens": message["usage"]["output_tokens"]}})
    yield _event("message_stop", {"type": "message_stop"})


def _event(name: str, payload: dict) -> str:
    return f"event: {name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

