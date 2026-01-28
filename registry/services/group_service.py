from typing import List, Dict, Any
from packages.models._generated import IGroup  
from registry.utils.log import logger

class GroupService:
	async def search_groups(self, query: str) -> List[IGroup]:
		"""
		Search groups by name or email (case-insensitive substring match).
		Returns a list of dicts with keys: id, name, email
		"""
		try:
			query =  {
                "$or": [
					{"name": {"$regex": query, "$options": "i"}},
                    {"email": {"$regex": query, "$options": "i"}},
                ]
            }
			results = await IGroup.find(query).to_list()
			return results
		except Exception as e:
			logger.error(f"Error searching groups with query '{query}': {e}")
			return []


group_service = GroupService()
