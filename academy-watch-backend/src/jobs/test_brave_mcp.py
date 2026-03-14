import os
import sys
import json
import asyncio
import argparse
import logging
from typing import Any, Dict, List

try:
    import dotenv  # type: ignore
    dotenv.load_dotenv(dotenv.find_dotenv())
except Exception:
    pass

try:
    from agents.mcp import MCPServerStdio
except Exception as e:  # pragma: no cover
    print("Error: agents SDK not available (agents.mcp.MCPServerStdio)", file=sys.stderr)
    raise


def _freshness_str(val: str | None, *, fallback: str = "pw") -> str:
    v = (val or fallback).strip()
    # defensively strip non-printables
    return "".join(ch for ch in v if ch.isprintable())


async def _call_tool(server: MCPServerStdio, tool_name: str, args: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Call tool and normalize output; on freshness enum errors, retry with shorthand 'pw'."""
    res = await _call_tool_raw(server, tool_name, args)
    items: List[Dict[str, Any]] = []
    if isinstance(res, dict) and isinstance(res.get("content"), list):
        items = [r for r in res.get("content") if isinstance(r, dict)]
    elif isinstance(res, list):
        items = [r for r in res if isinstance(r, dict)]

    # Decode Brave MCP text payloads that embed JSON in the 'text' field
    decoded: List[Dict[str, Any]] = []
    for it in items:
        if it.get("type") == "text" and isinstance(it.get("text"), str):
            txt = it.get("text")
            try:
                obj = json.loads(txt)
                if isinstance(obj, dict):
                    decoded.append(obj)
                    continue
            except Exception:
                pass
        decoded.append(it)
    return decoded

async def _call_tool_raw(server: MCPServerStdio, tool_name: str, args: Dict[str, Any]):
    try:
        return await server.session.call_tool(tool_name, args)
    except Exception as e:
        msg = str(e)
        if "freshness" in msg and ("invalid_enum_value" in msg or "Invalid enum value" in msg):
            retry = dict(args)
            retry["freshness"] = "pw"
            return await server.session.call_tool(tool_name, retry)
        raise


def _server() -> MCPServerStdio:
    return MCPServerStdio(
        params={
            "command": "npx",
            "args": ["-y", "@brave/brave-search-mcp-server", "--transport", "stdio"],
            "env": {"BRAVE_API_KEY": os.getenv("BRAVE_API_KEY", "")},
        }
    )


def _to_jsonable(obj: Any) -> Any:
    # Best-effort converter for MCP SDK objects
    try:
        if obj is None or isinstance(obj, (str, int, float, bool)):
            return obj
        if isinstance(obj, dict):
            return {str(k): _to_jsonable(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple, set)):
            return [_to_jsonable(x) for x in obj]
        if hasattr(obj, "model_dump"):
            try:
                return _to_jsonable(obj.model_dump())
            except Exception:
                pass
        if hasattr(obj, "dict"):
            try:
                return _to_jsonable(obj.dict())
            except Exception:
                pass
        # Fallback: stringify
        return str(obj)
    except Exception:
        try:
            return str(obj)
        except Exception:
            return repr(obj)


async def main() -> int:
    parser = argparse.ArgumentParser(description="Test the official Brave Search MCP server via stdio")
    parser.add_argument("--query", required=True, help="Search query string")
    parser.add_argument("--freshness", default="pw", help="'pd'|'pw'|'pm'|'py' or 'YYYY-MM-DDtoYYYY-MM-DD'")
    parser.add_argument("--count", type=int, default=8)
    parser.add_argument("--country", default="GB")
    parser.add_argument("--search-lang", dest="search_lang", default="en")
    parser.add_argument("--ui-lang", dest="ui_lang", default="en-GB")
    parser.add_argument("--tool", choices=["web", "news", "both"], default="both")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--show-args", action="store_true", help="Print exact request args sent to MCP")
    parser.add_argument("--full", action="store_true", help="Print all returned items instead of top 3 samples")
    parser.add_argument("--describe", action="store_true", help="List tools and input schema summary before running queries")
    parser.add_argument("--raw", action="store_true", help="Also print a compact preview of raw MCP responses")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO if args.debug else logging.WARNING,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    freshness = _freshness_str(args.freshness)

    if not os.getenv("BRAVE_API_KEY"):
        print("Error: BRAVE_API_KEY is not set in environment", file=sys.stderr)
        return 2

    server = _server()
    async with server:
        # Canary ping with safe freshness shorthand
        try:
            await server.session.call_tool("brave_web_search", {"query": "site:uefa.com match report", "count": 1, "freshness": "pw"})
        except Exception as e:
            print(f"Ping failed: {e}", file=sys.stderr)
            return 3

        if args.describe:
            try:
                tl = await server.session.list_tools()
                names = []
                try:
                    for t in tl:
                        name = getattr(t, "name", None)
                        if name is None and isinstance(t, tuple) and len(t) > 0:
                            name = t[0]
                        names.append(name or str(t))
                except Exception:
                    names = [str(tl)]
                print(json.dumps({"tools": names}, ensure_ascii=False, indent=2))
            except Exception as e:
                print(f"Describe failed: {e}", file=sys.stderr)

        common = {
            "query": args.query,
            "count": max(1, min(args.count, 20)),
            "freshness": freshness,
            "country": args.country,
            "search_lang": args.search_lang,
            "ui_lang": args.ui_lang,
            "extra_snippets": True,
            "safesearch": "moderate",
        }

        out: Dict[str, Any] = {"query": args.query, "freshness": freshness, "country": args.country,
                                "search_lang": args.search_lang, "ui_lang": args.ui_lang}

        if args.tool in ("web", "both"):
            web_req = {**common, "result_filter": ["discussions", "web"]}
            if args.show_args:
                print(json.dumps({"tool": "brave_web_search", "request": web_req}, ensure_ascii=False, indent=2))
            web_items = await _call_tool(server, "brave_web_search", web_req)
            out["web_total"] = len(web_items)
            out["web_samples"] = web_items if args.full else web_items[:3]
            if args.raw:
                raw_web = await _call_tool_raw(server, "brave_web_search", web_req)
                preview = raw_web[:1] if isinstance(raw_web, list) else raw_web
                print(json.dumps({"tool": "brave_web_search", "raw_preview": _to_jsonable(preview)}, ensure_ascii=False, indent=2))

        if args.tool in ("news", "both"):
            news_req = {**common, "result_filter": ["news"]}
            if args.show_args:
                print(json.dumps({"tool": "brave_news_search", "request": news_req}, ensure_ascii=False, indent=2))
            news_items = await _call_tool(server, "brave_news_search", news_req)
            out["news_total"] = len(news_items)
            out["news_samples"] = news_items if args.full else news_items[:3]
            if args.raw:
                raw_news = await _call_tool_raw(server, "brave_news_search", news_req)
                preview = raw_news[:1] if isinstance(raw_news, list) else raw_news
                print(json.dumps({"tool": "brave_news_search", "raw_preview": _to_jsonable(preview)}, ensure_ascii=False, indent=2))

        print(json.dumps(out, ensure_ascii=False, indent=2))
        # non-zero exit if absolutely nothing returned
        totals = int(out.get("web_total", 0)) + int(out.get("news_total", 0))
        return 0 if totals > 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))


