from db import initialize_database
import dotenv
from shared import McpTool
from weaviate.classes.query import Filter

dotenv.load_dotenv()

db = initialize_database()

try:
    mcp_tools = db.for_model(McpTool)
    filters = Filter.by_property("server_path").equal("/currenttime/")
    results = mcp_tools.filter(filters=filters)

    aa = mcp_tools.delete_by_filter(filters=filters)
    print(aa)

    print(f"Found {len(results)} tools:")
    for tool in results:
        print(f"  - {tool.tool_name} ({tool.server_path})")
finally:
    db.close()
    print("\n✅ Database connection closed")





