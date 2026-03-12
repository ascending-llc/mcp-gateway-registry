import asyncio
import json
import os
from collections.abc import Callable
from typing import Any

import httpx
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.credentials import RefreshableCredentials

from registry.constants import REGISTRY_CONSTANTS
from registry.core.mcp_client import MCPServerData, get_tools_and_capabilities_from_server


class _SigV4HttpxAuth(httpx.Auth):
    """HTTPX auth provider that signs each request using AWS SigV4."""

    requires_request_body = True

    def __init__(self, service: str, region: str, credentials_provider: Callable[[], Any]):
        self.service = service
        self.region = region
        self.credentials_provider = credentials_provider

    def auth_flow(self, request: httpx.Request):
        credentials = self.credentials_provider()
        if isinstance(credentials, RefreshableCredentials):
            credentials = credentials.get_frozen_credentials()
        else:
            credentials = credentials.get_frozen_credentials()

        aws_request = AWSRequest(
            method=request.method,
            url=str(request.url),
            data=request.content,
            headers=dict(request.headers),
        )
        SigV4Auth(credentials, self.service, self.region).add_auth(aws_request)

        for key, value in aws_request.headers.items():
            request.headers[key] = value
        yield request


class AgentCoreRuntimeInvoker:
    """
    Runtime data-plane invoker.

    Keeps IAM and JWT execution paths separate so federation client can stay focused
    on discovery + model transformation.
    """

    def __init__(
        self,
        *,
        default_region: str,
        get_runtime_client: Callable[[str], Any],
        get_runtime_credentials_provider: Callable[[str], Any],
        extract_region_from_arn: Callable[[str, str], str],
    ):
        self.default_region = default_region
        self.get_runtime_client = get_runtime_client
        self.get_runtime_credentials_provider = get_runtime_credentials_provider
        self.extract_region_from_arn = extract_region_from_arn
        self._runtime_init_retry_attempts = max(
            1, int(getattr(REGISTRY_CONSTANTS, "AGENTCORE_RUNTIME_INIT_RETRY_ATTEMPTS", 4) or 4)
        )
        self._runtime_init_retry_delay_seconds = float(
            getattr(REGISTRY_CONSTANTS, "AGENTCORE_RUNTIME_INIT_RETRY_DELAY_SECONDS", 5.0) or 5.0
        )
        self._a2a_card_retry_attempts = max(
            1, int(getattr(REGISTRY_CONSTANTS, "AGENTCORE_A2A_CARD_RETRY_ATTEMPTS", 3) or 3)
        )
        self._a2a_card_retry_delay_seconds = float(
            getattr(REGISTRY_CONSTANTS, "AGENTCORE_A2A_CARD_RETRY_DELAY_SECONDS", 3.0) or 3.0
        )

    @staticmethod
    def detect_runtime_auth_mode(
        metadata: dict[str, Any],
        runtime_detail: dict[str, Any] | None = None,
    ) -> str:
        """
        Detect runtime data-plane auth mode from authorizer configuration.
        Defaults to IAM when not explicitly JWT.
        """
        config = (runtime_detail or {}).get("authorizerConfiguration") or metadata.get("authorizerConfiguration") or {}
        text = json.dumps(config, default=str).upper()
        if "JWT" in text:
            return "JWT"
        return "IAM"

    async def fetch_mcp_payloads(
        self,
        *,
        runtime_url: str,
        transport_type: str | None,
        metadata: dict[str, Any],
        runtime_detail: dict[str, Any] | None = None,
    ) -> MCPServerData:
        mode = self.detect_runtime_auth_mode(metadata=metadata, runtime_detail=runtime_detail)
        if mode == "IAM":
            sdk_result = await self._fetch_mcp_payloads_via_sdk(metadata=metadata, runtime_detail=runtime_detail)
            if not sdk_result.error_message:
                return sdk_result

            # Fallback path for IAM: use SigV4-authenticated MCP transport over HTTP.
            http_fallback = await self._fetch_mcp_payloads_via_http_with_retry(
                runtime_url=runtime_url,
                transport_type=transport_type,
                metadata=metadata,
                runtime_detail=runtime_detail,
            )
            if not http_fallback.error_message:
                return http_fallback
            return sdk_result

        return await self._fetch_mcp_payloads_via_http_with_retry(
            runtime_url=runtime_url,
            transport_type=transport_type,
            metadata=metadata,
            runtime_detail=runtime_detail,
        )

    async def invoke_runtime_prompt(
        self,
        *,
        runtime_arn: str,
        prompt: str = "ping",
        qualifier: str = "DEFAULT",
    ) -> dict[str, Any]:
        """
        Directly invoke runtime with a simple prompt payload for smoke testing.
        """
        if not runtime_arn:
            raise ValueError("runtime_arn is required")

        region = self.extract_region_from_arn(runtime_arn, self.default_region)
        client = await self._get_runtime_client(region)

        payload = json.dumps({"prompt": prompt}, ensure_ascii=False).encode("utf-8")
        response = await self._call_with_runtime_init_retry(
            lambda: client.invoke_agent_runtime(
                agentRuntimeArn=runtime_arn,
                qualifier=qualifier,
                payload=payload,
            )
        )

        response_bytes = self._read_response_blob(response.get("response"))
        response_text = response_bytes.decode("utf-8", errors="replace") if response_bytes else ""
        response_json = self._extract_json_payload(response_text)

        return {
            "runtimeArn": runtime_arn,
            "qualifier": qualifier,
            "statusCode": response.get("statusCode"),
            "contentType": response.get("contentType"),
            "runtimeSessionId": response.get("runtimeSessionId"),
            "mcpSessionId": response.get("mcpSessionId"),
            "mcpProtocolVersion": response.get("mcpProtocolVersion"),
            "responseJson": response_json or None,
            "responseText": response_text if not response_json else None,
        }

    async def fetch_a2a_card(
        self,
        *,
        card_url: str,
        metadata: dict[str, Any],
        runtime_detail: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        mode = self.detect_runtime_auth_mode(metadata=metadata, runtime_detail=runtime_detail)
        if mode == "IAM":
            return await self._fetch_a2a_card_via_sdk(metadata=metadata, runtime_detail=runtime_detail)

        headers, httpx_auth = await self._build_runtime_http_auth(
            metadata=metadata,
            runtime_detail=runtime_detail,
        )
        async with httpx.AsyncClient(timeout=20.0, headers=headers, auth=httpx_auth) as client:
            response = await client.get(card_url)
            response.raise_for_status()
            return response.json()

    async def _fetch_mcp_payloads_via_http(
        self,
        *,
        runtime_url: str,
        transport_type: str | None,
        metadata: dict[str, Any],
        runtime_detail: dict[str, Any] | None = None,
    ) -> MCPServerData:
        headers, httpx_auth = await self._build_runtime_http_auth(
            metadata=metadata,
            runtime_detail=runtime_detail,
        )
        return await get_tools_and_capabilities_from_server(
            runtime_url,
            headers=headers,
            transport_type=transport_type,
            include_resources=True,
            include_prompts=True,
            httpx_auth=httpx_auth,
        )

    async def _fetch_mcp_payloads_via_http_with_retry(
        self,
        *,
        runtime_url: str,
        transport_type: str | None,
        metadata: dict[str, Any],
        runtime_detail: dict[str, Any] | None = None,
    ) -> MCPServerData:
        last_result: MCPServerData | None = None
        for attempt in range(1, self._runtime_init_retry_attempts + 1):
            result = await self._fetch_mcp_payloads_via_http(
                runtime_url=runtime_url,
                transport_type=transport_type,
                metadata=metadata,
                runtime_detail=runtime_detail,
            )
            last_result = result
            if not result.error_message or not self._is_runtime_init_timeout_text(result.error_message):
                return result
            if attempt < self._runtime_init_retry_attempts:
                await asyncio.sleep(self._runtime_init_retry_delay_seconds * attempt)
        return last_result or MCPServerData(None, None, None, None, "MCP HTTP retry failed")

    async def _fetch_a2a_card_via_sdk(
        self,
        *,
        metadata: dict[str, Any],
        runtime_detail: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        runtime_arn = (
            (runtime_detail or {}).get("agentRuntimeArn")
            or metadata.get("runtimeArn")
            or metadata.get("agentRuntimeArn")
        )
        if not runtime_arn:
            raise ValueError("Missing runtime ARN for GetAgentCard")

        region = self.extract_region_from_arn(runtime_arn, self.default_region)
        client = await self._get_runtime_client(region)
        response = await self._call_with_a2a_card_retry(
            lambda: client.get_agent_card(agentRuntimeArn=runtime_arn, qualifier="DEFAULT")
        )
        card = response.get("agentCard")
        if isinstance(card, dict):
            return card
        if isinstance(card, str):
            return json.loads(card)
        raise ValueError("GetAgentCard returned unexpected payload")

    async def _fetch_mcp_payloads_via_sdk(
        self,
        *,
        metadata: dict[str, Any],
        runtime_detail: dict[str, Any] | None = None,
    ) -> MCPServerData:
        runtime_arn = (
            (runtime_detail or {}).get("agentRuntimeArn")
            or metadata.get("runtimeArn")
            or metadata.get("agentRuntimeArn")
        )
        if not runtime_arn:
            return MCPServerData(None, None, None, None, "Missing runtime ARN for InvokeAgentRuntime")

        region = self.extract_region_from_arn(runtime_arn, self.default_region)
        client = await self._get_runtime_client(region)

        try:
            # Follow AWS official IAM sample: call tools/list directly via InvokeAgentRuntime.
            (
                tools_result,
                runtime_session_id,
                mcp_session_id,
                protocol_version,
            ) = await self._call_with_runtime_init_retry_async(
                lambda: self._invoke_mcp_jsonrpc(
                    client=client,
                    runtime_arn=runtime_arn,
                    method="tools/list",
                    params={},
                    request_id=1,
                    runtime_session_id=None,
                    mcp_session_id=None,
                    protocol_version=None,
                )
            )
            resources_result, _, _, _ = await self._invoke_mcp_jsonrpc(
                client=client,
                runtime_arn=runtime_arn,
                method="resources/list",
                params={},
                request_id=2,
                runtime_session_id=runtime_session_id,
                mcp_session_id=mcp_session_id,
                protocol_version=protocol_version,
            )
            prompts_result, _, _, _ = await self._invoke_mcp_jsonrpc(
                client=client,
                runtime_arn=runtime_arn,
                method="prompts/list",
                params={},
                request_id=3,
                runtime_session_id=runtime_session_id,
                mcp_session_id=mcp_session_id,
                protocol_version=protocol_version,
            )
        except Exception as exc:
            return MCPServerData(None, None, None, None, f"SDK MCP invocation failed: {exc}")

        tools = self._normalize_mcp_tools(tools_result.get("tools", []))
        resources = self._normalize_mcp_resources(resources_result.get("resources", []))
        prompts = self._normalize_mcp_prompts(prompts_result.get("prompts", []))
        capabilities = {"sdkInvokeMode": "invoke_agent_runtime"}
        return MCPServerData(
            tools=tools,
            resources=resources,
            prompts=prompts,
            capabilities=capabilities,
            requires_init=bool(runtime_session_id or mcp_session_id),
            error_message=None,
        )

    async def _get_runtime_client(self, region: str) -> Any:
        client = await self.get_runtime_client(region)
        if not client:
            raise ValueError(f"Failed to initialize AgentCore runtime client for region {region}")
        return client

    async def _invoke_mcp_jsonrpc(
        self,
        *,
        client: Any,
        runtime_arn: str,
        method: str,
        params: dict[str, Any],
        request_id: int,
        runtime_session_id: str | None,
        mcp_session_id: str | None,
        protocol_version: str | None,
    ) -> tuple[dict[str, Any], str | None, str | None, str | None]:
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        }
        kwargs: dict[str, Any] = {
            "agentRuntimeArn": runtime_arn,
            "qualifier": "DEFAULT",
            "contentType": "application/json",
            "accept": "application/json, text/event-stream",
            "payload": json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        }
        if runtime_session_id:
            kwargs["runtimeSessionId"] = runtime_session_id
        if mcp_session_id:
            kwargs["mcpSessionId"] = mcp_session_id
        if protocol_version:
            kwargs["mcpProtocolVersion"] = protocol_version

        try:
            response = await asyncio.to_thread(client.invoke_agent_runtime, **kwargs)
        except Exception as exc:
            raise ValueError(
                "invoke_agent_runtime failed "
                f"(method={method}, runtime_arn={runtime_arn}, qualifier=DEFAULT, accept={kwargs['accept']}, "
                f"contentType={kwargs['contentType']}): {exc}"
            ) from exc

        response_bytes = self._read_response_blob(response.get("response"))
        response_text = response_bytes.decode("utf-8", errors="replace") if response_bytes else ""
        response_payload = self._extract_json_payload(response_text)
        if response_text and not response_payload:
            raise ValueError(
                "invoke_agent_runtime returned non-JSON response "
                f"(method={method}, statusCode={response.get('statusCode')}, "
                f"contentType={response.get('contentType')}, body={response_text[:1000]})"
            )

        if response_payload.get("error"):
            raise ValueError(
                "MCP method failed "
                f"(method={method}, statusCode={response.get('statusCode')}, contentType={response.get('contentType')}, "
                f"error={response_payload['error']}, body={response_text[:1000]})"
            )

        return (
            response_payload.get("result", {}),
            response.get("runtimeSessionId") or runtime_session_id,
            response.get("mcpSessionId") or mcp_session_id,
            response.get("mcpProtocolVersion") or protocol_version,
        )

    @staticmethod
    def _extract_json_payload(response_text: str) -> dict[str, Any]:
        """
        Parse JSON payload from direct JSON or SSE-like "data: {...}" envelope.
        """
        if not response_text:
            return {}

        # Direct JSON response.
        try:
            parsed = json.loads(response_text)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        # Handle text/event-stream style chunks.
        for line in response_text.splitlines():
            data_line = line.strip()
            if data_line.startswith("data:"):
                candidate = data_line[5:].strip()
                try:
                    parsed = json.loads(candidate)
                    if isinstance(parsed, dict):
                        return parsed
                except json.JSONDecodeError:
                    continue

        # Fallback: find first JSON object in mixed text.
        start = response_text.find("{")
        if start >= 0:
            candidate = response_text[start:]
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                return {}

        return {}

    async def _call_with_runtime_init_retry(self, operation: Callable[[], Any]) -> Any:
        """
        Retry transient runtime initialization timeout errors from AgentCore runtime.
        """
        last_exc: Exception | None = None
        for attempt in range(1, self._runtime_init_retry_attempts + 1):
            try:
                return await asyncio.to_thread(operation)
            except Exception as exc:
                last_exc = exc
                if not self._is_runtime_init_timeout_error(exc) or attempt == self._runtime_init_retry_attempts:
                    raise
                await asyncio.sleep(self._runtime_init_retry_delay_seconds * attempt)
        if last_exc:
            raise last_exc
        raise RuntimeError("retry operation failed without exception")

    async def _call_with_runtime_init_retry_async(self, operation: Callable[[], Any]) -> Any:
        """
        Retry transient runtime initialization timeout errors for async operations.
        """
        last_exc: Exception | None = None
        for attempt in range(1, self._runtime_init_retry_attempts + 1):
            try:
                return await operation()
            except Exception as exc:
                last_exc = exc
                if not self._is_runtime_init_timeout_error(exc) or attempt == self._runtime_init_retry_attempts:
                    raise
                await asyncio.sleep(self._runtime_init_retry_delay_seconds * attempt)
        if last_exc:
            raise last_exc
        raise RuntimeError("retry async operation failed without exception")

    async def _call_with_a2a_card_retry(self, operation: Callable[[], Any]) -> Any:
        """
        Retry A2A card fetch for known transient runtime-side failures.
        """
        last_exc: Exception | None = None
        for attempt in range(1, self._a2a_card_retry_attempts + 1):
            try:
                return await asyncio.to_thread(operation)
            except Exception as exc:
                last_exc = exc
                if not self._is_retryable_a2a_card_error(exc) or attempt == self._a2a_card_retry_attempts:
                    raise
                await asyncio.sleep(self._a2a_card_retry_delay_seconds * attempt)
        if last_exc:
            raise last_exc
        raise RuntimeError("A2A card retry operation failed without exception")

    @staticmethod
    def _is_runtime_init_timeout_error(exc: Exception) -> bool:
        message = str(exc)
        return "Runtime initialization time exceeded" in message

    @staticmethod
    def _is_runtime_init_timeout_text(message: str) -> bool:
        return "Runtime initialization time exceeded" in message

    @staticmethod
    def _is_retryable_a2a_card_error(exc: Exception) -> bool:
        message = str(exc)
        if "Runtime initialization time exceeded" in message:
            return True
        if "GetAgentCard operation" in message and "(502)" in message:
            return True
        return "agent card endpoint" in message and "(502)" in message

    @staticmethod
    def _read_response_blob(blob: Any) -> bytes:
        if blob is None:
            return b""
        if isinstance(blob, (bytes, bytearray)):
            return bytes(blob)
        if hasattr(blob, "read"):
            return blob.read()
        return b""

    @staticmethod
    def _normalize_mcp_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for tool in tools or []:
            normalized.append(
                {
                    "name": tool.get("name"),
                    "description": tool.get("description", ""),
                    "inputSchema": tool.get("inputSchema", {"type": "object", "properties": {}}),
                }
            )
        return normalized

    @staticmethod
    def _normalize_mcp_resources(resources: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for resource in resources or []:
            normalized.append(
                {
                    "uri": resource.get("uri"),
                    "name": resource.get("name"),
                    "description": resource.get("description"),
                    "mimeType": resource.get("mimeType"),
                    "annotations": resource.get("annotations"),
                }
            )
        return normalized

    @staticmethod
    def _normalize_mcp_prompts(prompts: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for prompt in prompts or []:
            normalized.append(
                {
                    "name": prompt.get("name"),
                    "description": prompt.get("description"),
                    "arguments": prompt.get("arguments") or [],
                }
            )
        return normalized

    async def _build_runtime_http_auth(
        self,
        *,
        metadata: dict[str, Any],
        runtime_detail: dict[str, Any] | None = None,
    ) -> tuple[dict[str, str], httpx.Auth | None]:
        """
        Build authentication material for runtime data-plane requests.

        Modes:
        - IAM: SigV4 request signing
        - JWT: Bearer token header
        """
        mode = self.detect_runtime_auth_mode(metadata=metadata, runtime_detail=runtime_detail)
        if mode == "JWT":
            token = (
                getattr(REGISTRY_CONSTANTS, "AGENTCORE_RUNTIME_JWT", None)
                or os.getenv("AGENTCORE_RUNTIME_JWT")
                or os.getenv("AGENTCORE_RUNTIME_BEARER_TOKEN")
            )
            if not token:
                raise ValueError("Runtime auth mode JWT detected but no AGENTCORE_RUNTIME_JWT token was configured")
            return {"Authorization": f"Bearer {token}"}, None

        region = self.extract_region_from_arn(metadata.get("runtimeArn", ""), self.default_region)
        credentials_provider = await self.get_runtime_credentials_provider(region)
        if not credentials_provider:
            raise ValueError(f"Failed to initialize runtime credentials provider for region {region}")
        return {}, _SigV4HttpxAuth("bedrock-agentcore", region, credentials_provider)
