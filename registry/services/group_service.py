from typing import List
from packages.models._generated import IGroup  
from registry.utils.log import logger

class GroupService:
	async def search_groups(self, query: str) -> List[IGroup]:
		"""
		Search groups by name or email (case-insensitive substring match).
		Returns a list of IGroup instances representing matching groups (e.g., with id, name, email fields).
		"""
		try:
			search_query =  {
                "$or": [
					{"name": {"$regex": query, "$options": "i"}},
                    {"email": {"$regex": query, "$options": "i"}},
                ]
            }
			results = await IGroup.find(search_query).to_list()
			return results
		except Exception as e:
			logger.error(f"Error searching groups with query '{search_query}': {e}")
			return []


group_service = GroupService()
