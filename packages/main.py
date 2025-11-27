from packages.db import DirectSearchManager, DirectDataManager, get_weaviate_client

client = get_weaviate_client()
search_mgr = DirectSearchManager(client)
data_mgr = DirectDataManager(client)

# Search any collection directly, no model definition needed
results = search_mgr.smart_search(
    collection_name="MCP_GATEWAY",
    query="ool: print_stock_data | Server: Financial Info Proxy (/fininfo)",
    limit=10,
    field_filters={"is_enabled": True},
    list_filters=None,
    alpha=0.5)

print(results)
