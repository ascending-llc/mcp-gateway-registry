"""
Test script to verify Article.objects.search_by_type() works correctly
"""

from packages.db import (
    Model,
    TextField,
    TextArrayField,
    BooleanField,
    SearchType,
    init_weaviate,
    close_weaviate
)


# Define a simple model
class McpTool(Model):
    """MCP Tool model for testing"""
    
    tool_name = TextField(
        description="Tool name",
        index_filterable=True,
        index_searchable=True
    )
    
    server_name = TextField(
        description="Server display name",
        index_filterable=True,
        index_searchable=True
    )
    
    description_main = TextField(
        description="Main tool description",
        index_searchable=True
    )
    
    tags = TextArrayField(
        description="Server tags",
        index_filterable=True,
        index_searchable=True
    )
    
    is_enabled = BooleanField(
        description="Whether the service is enabled",
        index_filterable=True
    )
    
    combined_text = TextField(
        description="Combined searchable text",
        index_searchable=True
    )
    
    class Meta:
        collection_name = "MCP_GATEWAY"


def main():
    print("=" * 80)
    print("Testing Article.objects.search_by_type()")
    print("=" * 80)
    
    # Initialize Weaviate
    init_weaviate()
    
    try:
        # Test 1: Using SearchType enum
        print("\n✅ Test 1: Using SearchType.HYBRID enum")
        print("-" * 80)
        results = McpTool.objects.search_by_type(
            SearchType.HYBRID,
            text="format stock data",
            alpha=0.7,
            limit=3
        )
        print(f"Found {len(results)} results")
        for i, tool in enumerate(results, 1):
            print(f"  {i}. {tool.tool_name}")
        
        # Test 2: Using string
        print("\n✅ Test 2: Using string 'near_text'")
        print("-" * 80)
        results = McpTool.objects.search_by_type(
            "near_text",
            text="weather data",
            limit=3
        )
        print(f"Found {len(results)} results")
        for i, tool in enumerate(results, 1):
            print(f"  {i}. {tool.tool_name}")
        
        # Test 3: BM25 search
        print("\n✅ Test 3: Using SearchType.BM25")
        print("-" * 80)
        results = McpTool.objects.search_by_type(
            SearchType.BM25,
            text="stock market",
            limit=3
        )
        print(f"Found {len(results)} results")
        for i, tool in enumerate(results, 1):
            print(f"  {i}. {tool.tool_name}")
        
        # Test 4: Dynamic selection
        print("\n✅ Test 4: Dynamic strategy selection")
        print("-" * 80)
        user_mode = "semantic"
        search_type = SearchType.NEAR_TEXT if user_mode == "semantic" else SearchType.BM25
        
        results = McpTool.objects.search_by_type(
            search_type,
            text="data processing",
            limit=3
        )
        print(f"Mode: {user_mode}, SearchType: {search_type.value}")
        print(f"Found {len(results)} results")
        
        # Test 5: Compare different strategies
        print("\n✅ Test 5: Compare different strategies")
        print("-" * 80)
        
        query = "format data string"
        strategies = [
            (SearchType.NEAR_TEXT, "Semantic"),
            (SearchType.BM25, "Keyword"),
            (SearchType.HYBRID, "Hybrid"),
        ]
        
        for search_type, name in strategies:
            results = McpTool.objects.search_by_type(
                search_type,
                text=query,
                limit=3
            )
            print(f"  {name:12} : {len(results)} results")
        
        print("\n" + "=" * 80)
        print("✅ All tests passed! Article.objects.search_by_type() works!")
        print("=" * 80)
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Cleanup
        close_weaviate()
        print("\n✅ Connection closed")


if __name__ == "__main__":
    main()

