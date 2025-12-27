from typing import Dict, Any, Optional, TypeVar, Generic, Callable
from dataclasses import dataclass, field, asdict
from cachetools import TTLCache
import time
import asyncio
import logging

from .models import OAuthFlowStatus

logger = logging.getLogger(__name__)

T = TypeVar('T')


@dataclass
class FlowState(Generic[T]):
    """
    Flow state representation.
    Equivalent to jarvis-api FlowState<T> interface.
    """
    type: str
    status: OAuthFlowStatus
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    result: Optional[T] = None
    error: Optional[str] = None
    completed_at: Optional[float] = None
    failed_at: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage"""
        data = asdict(self)
        # Convert enum to string
        data['status'] = self.status.value if isinstance(self.status, OAuthFlowStatus) else self.status
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'FlowState':
        """Create FlowState from dictionary"""
        # Convert string status to enum
        if 'status' in data and isinstance(data['status'], str):
            data['status'] = OAuthFlowStatus(data['status'])
        return cls(**data)

    def is_pending(self) -> bool:
        """Check if flow is pending"""
        return self.status == OAuthFlowStatus.PENDING

    def is_completed(self) -> bool:
        """Check if flow is completed"""
        return self.status == OAuthFlowStatus.COMPLETED

    def is_failed(self) -> bool:
        """Check if flow is failed"""
        return self.status == OAuthFlowStatus.FAILED

    def get_age(self) -> float:
        """Get flow age in seconds"""
        if self.completed_at:
            return time.time() - self.completed_at
        return time.time() - self.created_at


class FlowStateManager(Generic[T]):
    """
    Flow state manager for handling OAuth and other async flows.
    """

    def __init__(self, namespace: str = 'oauth-flows', ttl: int = 600):
        self.namespace = namespace
        self.ttl = ttl  # TTL in seconds
        self._cache: TTLCache = TTLCache(maxsize=1000, ttl=self.ttl)
        self._intervals: set = set()  # Track monitoring tasks

    def _get_flow_key(self, flow_id: str, flow_type: str) -> str:
        """Get cache key for flow"""
        return f"{self.namespace}:{flow_type}:{flow_id}"

    def _normalize_expiration_timestamp(self, timestamp: float) -> float:
        """
        Normalize expiration timestamp to milliseconds.
        Detects whether input is in seconds or milliseconds.
        Timestamps below 10 billion are assumed to be in seconds (valid until ~2286).
        """
        SECONDS_THRESHOLD = 1e10
        if timestamp < SECONDS_THRESHOLD:
            return timestamp * 1000
        return timestamp

    def _is_token_expired(self, flow_state: Optional[FlowState[T]]) -> bool:
        """
        Check if flow's token has expired based on expires_at field.
        
        Args:
            flow_state: Flow state to check
            
        Returns:
            True if token expired, False otherwise
        """
        if not flow_state or not flow_state.result:
            return False

        if not isinstance(flow_state.result, dict):
            return False

        expires_at = flow_state.result.get('expires_at')
        if not expires_at or not isinstance(expires_at, (int, float)):
            return False

        normalized_expires_at = self._normalize_expiration_timestamp(expires_at)
        return normalized_expires_at < time.time() * 1000

    async def create_flow_state(
            self,
            flow_id: str,
            flow_type: str,
            metadata: Dict[str, Any],
            ttl: Optional[int] = None
    ) -> FlowState[T]:
        """
        Create new flow state.
        Equivalent to jarvis-api createFlow initial state creation.
        
        Args:
            flow_id: Flow identifier
            flow_type: Type of flow ('mcp_oauth', 'mcp_get_tokens', etc.)
            metadata: Flow metadata
            ttl: Time to live in seconds (optional)
            
        Returns:
            Created FlowState instance
        """
        try:
            flow_state = FlowState[T](
                type=flow_type,
                status=OAuthFlowStatus.PENDING,
                metadata=metadata,
                created_at=time.time()
            )

            cache_key = self._get_flow_key(flow_id, flow_type)
            effective_ttl = ttl or self.ttl

            # Store as dict for cache
            self._cache[cache_key] = flow_state.to_dict()

            logger.debug(f"Flow state created: {flow_id}, type: {flow_type}")
            return flow_state

        except Exception as e:
            logger.error(f"Failed to create flow state {flow_id}: {str(e)}")
            raise

    async def get_flow_state(
            self,
            flow_id: str,
            flow_type: str
    ) -> Optional[FlowState[T]]:
        """
        Get current flow state.
        Equivalent to jarvis-api getFlowState.
        
        Args:
            flow_id: Flow identifier
            flow_type: Type of flow
            
        Returns:
            FlowState instance or None if not found
        """
        try:
            cache_key = self._get_flow_key(flow_id, flow_type)
            flow_data = self._cache.get(cache_key)

            if flow_data is None:
                logger.debug(f"Flow state not found or expired: {flow_id}")
                return None

            # Convert dict back to FlowState
            if isinstance(flow_data, dict):
                return FlowState.from_dict(flow_data)

            return flow_data

        except Exception as e:
            logger.error(f"Failed to get flow state {flow_id}: {str(e)}")
            return None

    async def complete_flow(
            self,
            flow_id: str,
            flow_type: str,
            result: T
    ) -> bool:
        """
        Complete flow successfully.
        Equivalent to jarvis-api completeFlow.
        
        Args:
            flow_id: Flow identifier
            flow_type: Type of flow
            result: Flow result
            
        Returns:
            True if completed, False if flow not found
        """
        try:
            cache_key = self._get_flow_key(flow_id, flow_type)
            flow_state = await self.get_flow_state(flow_id, flow_type)

            if not flow_state:
                logger.warning(f"Cannot complete non-existent flow: {flow_id}")
                return False

            # Prevent duplicate completion
            if flow_state.is_completed():
                logger.debug(f"Flow already completed, skipping: {flow_id}")
                return True

            # Update flow state
            flow_state.status = OAuthFlowStatus.COMPLETED
            flow_state.result = result
            flow_state.completed_at = time.time()

            # Store updated state
            self._cache[cache_key] = flow_state.to_dict()

            logger.info(f"Flow completed: {flow_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to complete flow {flow_id}: {str(e)}")
            raise

    async def fail_flow(
            self,
            flow_id: str,
            flow_type: str,
            error: str
    ) -> bool:
        """
        Mark flow as failed.
        Equivalent to jarvis-api failFlow.
        
        Args:
            flow_id: Flow identifier
            flow_type: Type of flow
            error: Error message
            
        Returns:
            True if marked failed, False if flow not found
        """
        try:
            cache_key = self._get_flow_key(flow_id, flow_type)
            flow_state = await self.get_flow_state(flow_id, flow_type)

            if not flow_state:
                logger.warning(f"Cannot fail non-existent flow: {flow_id}")
                return False

            # Update flow state
            flow_state.status = OAuthFlowStatus.FAILED
            flow_state.error = error
            flow_state.failed_at = time.time()

            # Store updated state
            self._cache[cache_key] = flow_state.to_dict()

            logger.info(f"Flow failed: {flow_id}, error: {error}")
            return True

        except Exception as e:
            logger.error(f"Failed to fail flow {flow_id}: {str(e)}")
            raise

    async def delete_flow(
            self,
            flow_id: str,
            flow_type: str
    ) -> bool:
        """
        Delete flow state.
        Equivalent to jarvis-api deleteFlow.
        
        Args:
            flow_id: Flow identifier
            flow_type: Type of flow
            
        Returns:
            True if deleted, False if not found
        """
        try:
            cache_key = self._get_flow_key(flow_id, flow_type)
            if cache_key in self._cache:
                del self._cache[cache_key]
                logger.debug(f"Flow deleted: {flow_id}")
                return True
            return False

        except Exception as e:
            logger.error(f"Failed to delete flow {flow_id}: {str(e)}")
            return False

    async def create_flow(
            self,
            flow_id: str,
            flow_type: str,
            metadata: Dict[str, Any] = None,
            signal: Optional[Any] = None
    ) -> T:
        """
        Create new flow and wait for completion.
        Equivalent to jarvis-api createFlow.
        
        Args:
            flow_id: Flow identifier
            flow_type: Type of flow
            metadata: Flow metadata
            signal: Abort signal (optional)
            
        Returns:
            Flow result when completed
        """
        flow_key = self._get_flow_key(flow_id, flow_type)

        # Check if flow already exists
        existing_state = await self.get_flow_state(flow_id, flow_type)
        if existing_state:
            logger.debug(f"[{flow_key}] Flow already exists")
            return await self._monitor_flow(flow_key, flow_type, signal)

        # Double-check after small delay
        await asyncio.sleep(0.25)
        existing_state = await self.get_flow_state(flow_id, flow_type)
        if existing_state:
            logger.debug(f"[{flow_key}] Flow exists on 2nd check")
            return await self._monitor_flow(flow_key, flow_type, signal)

        # Create initial state
        initial_state = FlowState[T](
            type=flow_type,
            status=OAuthFlowStatus.PENDING,
            metadata=metadata or {},
            created_at=time.time()
        )

        logger.debug(f"[{flow_key}] Creating initial flow state")
        self._cache[flow_key] = initial_state.to_dict()

        return await self._monitor_flow(flow_key, flow_type, signal)

    async def _monitor_flow(
            self,
            flow_key: str,
            flow_type: str,
            signal: Optional[Any] = None
    ) -> T:
        """
        Monitor flow until completion or failure.
        Equivalent to jarvis-api monitorFlow.
        
        Args:
            flow_key: Cache key for flow
            flow_type: Type of flow
            signal: Abort signal (optional)
            
        Returns:
            Flow result when completed
            
        Raises:
            Exception: If flow fails, times out, or is aborted
        """
        check_interval = 2.0  # seconds
        elapsed_time = 0
        ttl_ms = self.ttl * 1000

        while True:
            try:
                # Get flow state from cache
                flow_data = self._cache.get(flow_key)

                if not flow_data:
                    logger.error(f"[{flow_key}] Flow state not found")
                    raise Exception(f"{flow_type} flow state not found")

                flow_state = FlowState.from_dict(flow_data)

                # Check abort signal
                if signal and hasattr(signal, 'aborted') and signal.aborted:
                    logger.warn(f"[{flow_key}] Flow aborted")
                    del self._cache[flow_key]
                    raise Exception(f"{flow_type} flow aborted")

                # Check if flow completed
                if not flow_state.is_pending():
                    logger.debug(f"[{flow_key}] Flow completed with status: {flow_state.status}")

                    if flow_state.is_completed() and flow_state.result is not None:
                        return flow_state.result
                    elif flow_state.is_failed():
                        del self._cache[flow_key]
                        raise Exception(flow_state.error or f"{flow_type} flow failed")

                    return None

                # Check timeout
                elapsed_time += check_interval * 1000
                if elapsed_time >= ttl_ms:
                    logger.error(
                        f"[{flow_key}] Flow timed out | Elapsed: {elapsed_time}ms | TTL: {ttl_ms}ms"
                    )
                    del self._cache[flow_key]
                    raise Exception(f"{flow_type} flow timed out")

                logger.debug(f"[{flow_key}] Flow pending, elapsed: {elapsed_time}ms, checking again...")

                # Wait before next check
                await asyncio.sleep(check_interval)

            except Exception as e:
                if "not found" in str(e) or "aborted" in str(e) or "timed out" in str(e) or "failed" in str(e):
                    raise
                logger.error(f"[{flow_key}] Error checking flow state: {e}")
                raise

    async def create_flow_with_handler(
            self,
            flow_id: str,
            flow_type: str,
            handler: Callable[[], T],
            signal: Optional[Any] = None
    ) -> T:
        """
        Create flow and execute handler if no existing flow found.
        Equivalent to jarvis-api createFlowWithHandler.
        
        Args:
            flow_id: Flow identifier
            flow_type: Type of flow
            handler: Async function to execute
            signal: Abort signal (optional)
            
        Returns:
            Handler result or existing flow result
        """
        flow_key = self._get_flow_key(flow_id, flow_type)

        # Check if flow exists with valid token
        existing_state = await self.get_flow_state(flow_id, flow_type)
        if existing_state and not self._is_token_expired(existing_state):
            logger.debug(f"[{flow_key}] Flow already exists with valid token")
            return await self._monitor_flow(flow_key, flow_type, signal)

        # Double-check after delay
        await asyncio.sleep(0.25)
        existing_state = await self.get_flow_state(flow_id, flow_type)
        if existing_state and not self._is_token_expired(existing_state):
            logger.debug(f"[{flow_key}] Flow exists on 2nd check with valid token")
            return await self._monitor_flow(flow_key, flow_type, signal)

        # Create initial state
        initial_state = FlowState[T](
            type=flow_type,
            status=OAuthFlowStatus.PENDING,
            metadata={},
            created_at=time.time()
        )

        logger.debug(f"[{flow_key}] Creating initial flow state")
        self._cache[flow_key] = initial_state.to_dict()

        try:
            # Execute handler
            result = await handler()
            await self.complete_flow(flow_id, flow_type, result)
            return result
        except Exception as error:
            await self.fail_flow(flow_id, flow_type, str(error))
            raise

    async def is_flow_stale(
            self,
            flow_id: str,
            flow_type: str,
            stale_threshold_ms: int = 2 * 60 * 1000
    ) -> Dict[str, Any]:
        """
        Check if flow is stale based on age and status.
        Equivalent to jarvis-api isFlowStale.
        
        Args:
            flow_id: Flow identifier
            flow_type: Type of flow
            stale_threshold_ms: Age threshold in milliseconds (default: 2 minutes)
            
        Returns:
            Dict with isStale, age, and status
        """
        flow_state = await self.get_flow_state(flow_id, flow_type)

        if not flow_state:
            return {'isStale': False, 'age': 0}

        # PENDING flows are never stale
        if flow_state.is_pending():
            return {'isStale': False, 'age': 0, 'status': flow_state.status.value}

        # Calculate age
        flow_age_seconds = flow_state.get_age()
        flow_age_ms = flow_age_seconds * 1000

        return {
            'isStale': flow_age_ms > stale_threshold_ms,
            'age': flow_age_ms,
            'status': flow_state.status.value
        }

    def get_stats(self) -> Dict[str, Any]:
        """Get flow manager statistics"""
        return {
            'active_flows': len(self._cache),
            'max_size': self._cache.maxsize,
            'ttl': self.ttl,
            'namespace': self.namespace
        }


_flow_manager_instance: Optional[FlowStateManager] = None


def get_flow_manager() -> FlowStateManager:
    global _flow_manager_instance
    if _flow_manager_instance is None:
        _flow_manager_instance = FlowStateManager()
    return _flow_manager_instance
