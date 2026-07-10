import sys
from pathlib import Path
import json
import httpx
import httpcore
import requests
import urllib3
from urllib3.response import HTTPResponse
import aiohttp
import asyncio

# 确保上一级目录包含在 sys.path 中
sys.path.append(str(Path(__file__).resolve().parent.parent))

# 终极底层 httpcore/urllib3/aiohttp 绝对物理静默拦截网，支持本地回环放行
try:
    original_httpcore_sync_handle = httpcore.ConnectionPool.handle_request
    original_httpcore_async_handle = httpcore.AsyncConnectionPool.handle_async_request
    original_urllib3_urlopen = urllib3.connectionpool.HTTPConnectionPool.urlopen
    original_requests_send = requests.adapters.HTTPAdapter.send
    original_aiohttp_request = aiohttp.ClientSession._request

    def _should_intercept(url_str: str) -> bool:
        # 放行本地回环流量（Milvus 数据库端口 19530，以及 Langfuse 烟雾测试在本地 127.0.0.1 端口拉起的接收服务器）
        if "127.0.0.1" in url_str or "localhost" in url_str or "19530" in url_str:
            return False
        return True

    def _get_mock_text(body_str: str) -> str:
        if "json" in body_str or "slots" in body_str:
            return '{"intent_type": "medical", "confidence": 0.95, "status": "collected", "followup_question": ""}'
        elif "image" in body_str or "base64" in body_str or "李宏状" in body_str or "mime" in body_str:
            return "您好，看到您发来的李宏状血常规化验单。白细胞总数正常，淋巴细胞百分比偏高，提示可能存在轻微病毒感染。请密切观察，如有发热或精神变差请及时急诊面诊。"
        elif "pass" in body_str or "审查" in body_str or "草稿" in body_str:
            return "PASS"
        else:
            return "<think>【离线推理】患儿症状平稳。</think>您好，我是 AI 助手。建议密切观察病情变化，保持充足水分，如有发烧或反复哭闹请及时面诊。"

    def _get_mock_embeddings_dict() -> dict:
        return {
            "data": [
                {"embedding": [0.1] * 1536, "index": 0, "object": "embedding"},
                {"embedding": [0.1] * 1536, "index": 1, "object": "embedding"}
            ],
            "model": "text-embedding-v3",
            "object": "list",
            "usage": {"prompt_tokens": 4, "total_tokens": 4}
        }

    # === 1. httpcore.ConnectionPool.handle_request 拦截同步请求 ===
    def mock_httpcore_sync_handle(self, request, *args, **kwargs):
        url_str = f"{request.url.scheme.decode('utf-8')}://{request.url.host.decode('utf-8')}:{request.url.port}{request.url.target.decode('utf-8')}".lower()
        if _should_intercept(url_str):
            # 读取物理请求体字节
            body_bytes = b"".join(request.stream) if hasattr(request, "stream") else b""
            body_str = body_bytes.decode("utf-8", errors="ignore").lower()
            
            headers_dict = {k.decode("utf-8").lower(): v.decode("utf-8") for k, v in request.headers}
            accept_header = headers_dict.get("accept", "").lower()
            
            # 严格匹配以规避 "stream": false 误判流式响应的 Bug
            is_stream = "text-event-stream" in accept_header or "event-stream" in accept_header or '"stream":true' in body_str.replace(" ", "").replace("\n", "").replace("\r", "")
            
            if "embeddings" in url_str:
                resp_bytes = json.dumps(_get_mock_embeddings_dict()).encode("utf-8")
                headers = [(b"content-type", b"application/json")]
                return httpcore.Response(200, headers=headers, content=resp_bytes)
            else:
                content = _get_mock_text(body_str)
                if is_stream:
                    # 构造教科书式的 OpenAI SSE 标准分帧，让流式解析器顺利提取 choices.delta.content
                    chunk1 = {
                        "id": "chatcmpl-mock-offline",
                        "object": "chat.completion.chunk",
                        "created": 1719999999,
                        "model": "mock-model",
                        "choices": [{
                            "index": 0,
                            "delta": {
                                "role": "assistant",
                                "content": content
                            },
                            "finish_reason": None
                        }]
                    }
                    chunk2 = {
                        "id": "chatcmpl-mock-offline",
                        "object": "chat.completion.chunk",
                        "created": 1719999999,
                        "model": "mock-model",
                        "choices": [{
                            "index": 0,
                            "delta": {},
                            "finish_reason": "stop"
                        }]
                    }
                    sse_data1 = f"data: {json.dumps(chunk1, ensure_ascii=False)}\r\n\r\n".encode("utf-8")
                    sse_data2 = f"data: {json.dumps(chunk2, ensure_ascii=False)}\r\n\r\ndata: [DONE]\r\n\r\n".encode("utf-8")
                    
                    return httpcore.Response(
                        200, 
                        headers=[(b"content-type", b"text/event-stream")], 
                        content=sse_data1 + sse_data2
                    )
                else:
                    mock_dict = {
                        "id": "chatcmpl-mock-offline",
                        "object": "chat.completion",
                        "created": 1719999999,
                        "model": "mock-model",
                        "choices": [{
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": content
                            },
                            "finish_reason": "stop"
                        }]
                    }
                    resp_bytes = json.dumps(mock_dict, ensure_ascii=False).encode("utf-8")
                    return httpcore.Response(
                        200, 
                        headers=[(b"content-type", b"application/json")], 
                        content=resp_bytes
                    )
        return original_httpcore_sync_handle(self, request, *args, **kwargs)

    # === 2. httpcore.AsyncConnectionPool.handle_async_request 拦截异步请求 ===
    async def mock_httpcore_async_handle(self, request, *args, **kwargs):
        url_str = f"{request.url.scheme.decode('utf-8')}://{request.url.host.decode('utf-8')}:{request.url.port}{request.url.target.decode('utf-8')}".lower()
        if _should_intercept(url_str):
            # 获取请求体内容
            body_bytes = b""
            if hasattr(request, "stream"):
                chunks = []
                async for chunk in request.stream:
                    chunks.append(chunk)
                body_bytes = b"".join(chunks)
            body_str = body_bytes.decode("utf-8", errors="ignore").lower()
            
            headers_dict = {k.decode("utf-8").lower(): v.decode("utf-8") for k, v in request.headers}
            accept_header = headers_dict.get("accept", "").lower()
            
            is_stream = "text-event-stream" in accept_header or "event-stream" in accept_header or '"stream":true' in body_str.replace(" ", "").replace("\n", "").replace("\r", "")
            
            if "embeddings" in url_str:
                resp_bytes = json.dumps(_get_mock_embeddings_dict()).encode("utf-8")
                headers = [(b"content-type", b"application/json")]
                return httpcore.Response(200, headers=headers, content=resp_bytes)
            else:
                content = _get_mock_text(body_str)
                if is_stream:
                    chunk1 = {
                        "id": "chatcmpl-mock-offline",
                        "object": "chat.completion.chunk",
                        "created": 1719999999,
                        "model": "mock-model",
                        "choices": [{
                            "index": 0,
                            "delta": {
                                "role": "assistant",
                                "content": content
                            },
                            "finish_reason": None
                        }]
                    }
                    chunk2 = {
                        "id": "chatcmpl-mock-offline",
                        "object": "chat.completion.chunk",
                        "created": 1719999999,
                        "model": "mock-model",
                        "choices": [{
                            "index": 0,
                            "delta": {},
                            "finish_reason": "stop"
                        }]
                    }
                    sse_data1 = f"data: {json.dumps(chunk1, ensure_ascii=False)}\r\n\r\n".encode("utf-8")
                    sse_data2 = f"data: {json.dumps(chunk2, ensure_ascii=False)}\r\n\r\ndata: [DONE]\r\n\r\n".encode("utf-8")
                    
                    return httpcore.Response(
                        200, 
                        headers=[(b"content-type", b"text/event-stream")], 
                        content=sse_data1 + sse_data2
                    )
                else:
                    mock_dict = {
                        "id": "chatcmpl-mock-offline",
                        "object": "chat.completion",
                        "created": 1719999999,
                        "model": "mock-model",
                        "choices": [{
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": content
                            },
                            "finish_reason": "stop"
                        }]
                    }
                    resp_bytes = json.dumps(mock_dict, ensure_ascii=False).encode("utf-8")
                    return httpcore.Response(
                        200, 
                        headers=[(b"content-type", b"application/json")], 
                        content=resp_bytes
                    )
        return await original_httpcore_async_handle(self, request, *args, **kwargs)

    # 替换 httpcore 方法
    httpcore.ConnectionPool.handle_request = mock_httpcore_sync_handle
    httpcore.AsyncConnectionPool.handle_async_request = mock_httpcore_async_handle

    # === 3. 拦截其他底层网络适配器（urllib3 / requests / aiohttp） ===
    def mock_urllib3_urlopen(self, method, url, body=None, headers=None, *args, **kwargs) -> HTTPResponse:
        full_url = f"{self.scheme}://{self.host}:{self.port}{url}".lower()
        if _should_intercept(full_url):
            body_str = (body or b"").decode("utf-8", errors="ignore").lower()
            if "embeddings" in full_url:
                mock_dict = _get_mock_embeddings_dict()
            else:
                mock_dict = {
                    "id": "chatcmpl-mock-offline",
                    "object": "chat.completion",
                    "created": 1719999999,
                    "model": "mock-model",
                    "choices": [{
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": _get_mock_text(body_str)
                        },
                        "finish_reason": "stop"
                    }]
                }
            return HTTPResponse(
                body=json.dumps(mock_dict).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                status=200,
                request_method=method
            )
        return original_urllib3_urlopen(self, method, url, body, headers, *args, **kwargs)

    def mock_requests_send(self, request, *args, **kwargs) -> requests.Response:
        url = str(request.url).lower()
        if _should_intercept(url):
            res = requests.Response()
            res.status_code = 200
            res.url = request.url
            res.request = request
            body_str = (request.body or b"").decode("utf-8", errors="ignore").lower()
            if "embeddings" in url:
                mock_dict = _get_mock_embeddings_dict()
            else:
                mock_dict = {
                    "id": "chatcmpl-mock-offline",
                    "object": "chat.completion",
                    "created": 1719999999,
                    "model": "mock-model",
                    "choices": [{
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": _get_mock_text(body_str)
                        },
                        "finish_reason": "stop"
                    }]
                }
            res._content = json.dumps(mock_dict).encode("utf-8")
            return res
        return original_requests_send(self, request, *args, **kwargs)

    async def mock_aiohttp_request(self, method, url, **kwargs) -> aiohttp.ClientResponse:
        url_str = str(url).lower()
        if _should_intercept(url_str):
            resp = aiohttp.ClientResponse(method, url, writer=None, continue100=None, timer=None, request_info=None, traces=None, loop=asyncio.get_event_loop(), session=self)
            resp.status = 200
            body_str = ""
            if "json" in kwargs:
                body_str = str(kwargs["json"]).lower()
            elif "data" in kwargs:
                body_str = str(kwargs["data"]).lower()
            
            if "embeddings" in url_str:
                mock_dict = _get_mock_embeddings_dict()
            else:
                mock_dict = {
                    "id": "chatcmpl-mock-offline",
                    "object": "chat.completion",
                    "created": 1719999999,
                    "model": "mock-model",
                    "choices": [{
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": _get_mock_text(body_str)
                        },
                        "finish_reason": "stop"
                    }]
                }
            resp._headers = {"Content-Type": "application/json"}
            resp._body = json.dumps(mock_dict).encode("utf-8")
            return resp
        return await original_aiohttp_request(self, method, url, **kwargs)

    urllib3.connectionpool.HTTPConnectionPool.urlopen = mock_urllib3_urlopen
    requests.adapters.HTTPAdapter.send = mock_requests_send
    aiohttp.ClientSession._request = mock_aiohttp_request
    
    print("[tests] 成功部署全局 httpcore 最底层高精度同步/流式打桩拦截网！")
    
except Exception as e:
    print(f"[tests] 部署全局 httpcore 最底层高精度打桩拦截网失败: {e}")
