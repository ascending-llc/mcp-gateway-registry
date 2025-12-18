from typing import Dict, Any, Optional
from cachetools import TTLCache
import time
import uuid
import logging

from .models import OAuthFlowStatus

logger = logging.getLogger(__name__)


class FlowStateManager:
    """
        FlowStateManager ->jarvis-api FlowStateManager
    """
    def __init__(self, namespace: str = 'oauth-flows', ttl: int = 600):
        self.namespace = namespace
        self.ttl = ttl
        self._cache: TTLCache = TTLCache(maxsize=1000, ttl=self.ttl)

    def generate_flow_id(self, user_id: str, server_name: str) -> str:
        """
            generate  flow id  -> jarvis-api generateFlowId
            :param user_id:
            :param server_name:

        """
        timestamp = int(time.time())
        unique_id = str(uuid.uuid4())[:8]
        return f"{user_id}:{server_name}:{timestamp}:{unique_id}"

    async def create_flow_state(self,
                                flow_id: str,
                                flow_type: str,
                                metadata: Dict[str, Any],
                                ttl: Optional[int] = None):
        """
        create flow state -> jarvis-api createFlowState
        Args:
            flow_id:
            flow_type:
            metadata:
            ttl:

        Returns:

        """
        try:
            current_time = time.time()
            effective_ttl = ttl or self.ttl

            flow_data = {
                "flow_id": flow_id,
                "flow_type": flow_type,
                "metadata": metadata,
                "status": OAuthFlowStatus.PENDING,
                "created_at": current_time,
                "expires_at": current_time + effective_ttl
            }

            cache_key = f"{self.namespace}:{flow_type}:{flow_id}"
            self._cache[cache_key] = flow_data

            logger.debug(f"Flow state created: {flow_id}, type: {flow_type}")

        except Exception as e:
            logger.error(f"Failed to create flow state {flow_id}: {str(e)}")
            raise

    async def get_flow_state(self,
                             flow_id: str,
                             flow_type: str,
                             ) -> Optional[Dict[str, Any]]:
        """
        get flow state -> jarvis-api getFlowState
        Args:
            flow_id:
            flow_type:

        Returns:

        """
        try:
            cache_key = f"{self.namespace}:{flow_type}:{flow_id}"
            flow_data = self._cache.get(cache_key)

            if flow_data is None:
                logger.debug(f"Flow state not found or expired: {flow_id}")
                return None

            return flow_data

        except Exception as e:
            logger.error(f"Failed to get flow state {flow_id}: {str(e)}")
            return None

    async def complete_flow(
            self,
            flow_id: str,
            flow_type: str,
            result: Any
    ) -> None:
        """
        complete flow -> jarvis-api completeFlow
        Args:
            flow_id:
            flow_type:
            result:

        Returns: None

        """
        try:
            cache_key = f"{self.namespace}:{flow_type}:{flow_id}"
            flow_data = self._cache.get(cache_key)

            if flow_data:
                flow_data["status"] = OAuthFlowStatus.COMPLETED
                flow_data["result"] = result
                flow_data["completed_at"] = time.time()
                self._cache[cache_key] = flow_data
                logger.info(f"Flow completed: {flow_id}")
            else:
                logger.warning(f"Cannot complete non-existent flow: {flow_id}")

        except Exception as e:
            logger.error(f"Failed to complete flow {flow_id}: {str(e)}")
            raise

    async def fail_flow(
            self,
            flow_id: str,
            flow_type: str,
            error: str
    ) -> None:
        """
        fail flow -> jarvis-api failFlow
        Args:
            flow_id:
            flow_type:
            error:

        Returns:

        """
        try:
            cache_key = f"{self.namespace}:{flow_type}:{flow_id}"
            flow_data = self._cache.get(cache_key)
            if flow_data:
                flow_data["status"] = OAuthFlowStatus.FAILED
                flow_data["error"] = error
                flow_data["failed_at"] = time.time()
                self._cache[cache_key] = flow_data
                logger.info(f"Flow failed: {flow_id}, error: {error}")
            else:
                logger.warning(f"Cannot fail non-existent flow: {flow_id}")

        except Exception as e:
            logger.error(f"Failed to fail flow {flow_id}: {str(e)}")
            raise

    async def delete_flow(
            self,
            flow_id: str,
            flow_type: str
    ) -> bool:
        """
        delete flow -> jarvis-api deleteFlow
        Args:
            flow_id:
            flow_type:

        Returns:

        """
        try:
            cache_key = f"{self.namespace}:{flow_type}:{flow_id}"
            if cache_key in self._cache:
                del self._cache[cache_key]
                logger.debug(f"Flow deleted: {flow_id}")
                return True
            return False

        except Exception as e:
            logger.error(f"Failed to delete flow {flow_id}: {str(e)}")
            return False

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
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
