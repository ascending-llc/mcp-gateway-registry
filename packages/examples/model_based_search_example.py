"""
Model-based Search with search_by_type() Example

Demonstrates how to use search_by_type() with Model classes (Article.objects.search_by_type).
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
from weaviate.classes.query import Filter


# Define your model
class McpTool(Model):
    """MCP Tool model for demonstration"""
    
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
    print("  Model-based Search with search_by_type()")
    print("=" * 80)
    
    # Initialize
    init_weaviate()
    
    try:
        # ============================================================
        # Feature 1: Universal Search with SearchType
        # ============================================================
        print("\n📍 Feature 1: Universal Search with SearchType Enum")
        print("-" * 80)
        
        # Semantic search
        print("\n1️⃣  Semantic Search (NEAR_TEXT)")
        results = McpTool.objects.search_by_type(
            SearchType.NEAR_TEXT,
            text="format stock market data",
            limit=3
        )
        print(f"Found {len(results)} results")
        for i, tool in enumerate(results, 1):
            print(f"  {i}. {tool.tool_name}")
            print(f"     Server: {tool.server_name}")
        
        # BM25 keyword search
        print("\n2️⃣  Keyword Search (BM25)")
        results = McpTool.objects.search_by_type(
            SearchType.BM25,
            text="stock data",
            limit=3
        )
        print(f"Found {len(results)} results")
        for i, tool in enumerate(results, 1):
            print(f"  {i}. {tool.tool_name}")
        
        # Hybrid search
        print("\n3️⃣  Hybrid Search (BM25 + Semantic)")
        results = McpTool.objects.search_by_type(
            SearchType.HYBRID,
            text="format string data",
            alpha=0.7,  # 70% semantic, 30% keyword
            limit=3
        )
        print(f"Found {len(results)} results")
        for i, tool in enumerate(results, 1):
            print(f"  {i}. {tool.tool_name}")
            if hasattr(tool, '_score'):
                print(f"     Score: {tool._score:.4f}")
        
        # Fuzzy search
        print("\n4️⃣  Fuzzy Search (Typo-tolerant)")
        results = McpTool.objects.search_by_type(
            SearchType.FUZZY,
            text="formt dat",  # Intentional typos
            limit=3,
            alpha=0.3
        )
        print(f"Found {len(results)} results")
        for i, tool in enumerate(results, 1):
            print(f"  {i}. {tool.tool_name}")
        
        # ============================================================
        # Feature 2: Using String Instead of Enum
        # ============================================================
        print("\n\n📍 Feature 2: Using String Instead of Enum")
        print("-" * 80)
        
        results = McpTool.objects.search_by_type(
            "near_text",  # String instead of SearchType.NEAR_TEXT
            text="weather forecast",
            limit=3
        )
        print(f"Found {len(results)} results using string 'near_text'")
        print("✅ String-based search type works with models too!")
        
        # ============================================================
        # Feature 3: Dynamic Strategy Selection
        # ============================================================
        print("\n\n📍 Feature 3: Dynamic Strategy Selection")
        print("-" * 80)
        
        # Simulate user preference
        user_preferences = ["semantic", "precise", "balanced"]
        
        for preference in user_preferences:
            if preference == "semantic":
                search_type = SearchType.NEAR_TEXT
            elif preference == "precise":
                search_type = SearchType.BM25
            else:
                search_type = SearchType.HYBRID
            
            results = McpTool.objects.search_by_type(
                search_type,
                text="data processing",
                limit=3
            )
            print(f"\n{preference.capitalize()} mode ({search_type.value}): {len(results)} results")
        
        # ============================================================
        # Feature 4: Compare Search Strategies
        # ============================================================
        print("\n\n📍 Feature 4: Compare Search Strategies")
        print("-" * 80)
        
        query = "stock market information"
        strategies = [
            (SearchType.NEAR_TEXT, "Semantic"),
            (SearchType.BM25, "Keyword"),
            (SearchType.HYBRID, "Hybrid"),
        ]
        
        print(f"\nComparing strategies for query: '{query}'")
        for search_type, name in strategies:
            results = McpTool.objects.search_by_type(
                search_type,
                text=query,
                limit=5
            )
            print(f"  {name:12} : {len(results)} results")
            if results:
                print(f"               Top: {results[0].tool_name}")
        
        # ============================================================
        # Feature 5: With Filters
        # ============================================================
        print("\n\n📍 Feature 5: Search with Filters")
        print("-" * 80)
        
        # Using Weaviate Filter object
        enabled_filter = Filter.by_property("is_enabled").equal(True)
        
        results = McpTool.objects.search_by_type(
            SearchType.HYBRID,
            text="data",
            filters=enabled_filter,
            limit=5
        )
        print(f"Found {len(results)} enabled tools")
        for i, tool in enumerate(results[:3], 1):
            print(f"  {i}. {tool.tool_name} (enabled: {tool.is_enabled})")
        
        # ============================================================
        # Feature 6: Type Safety Benefits
        # ============================================================
        print("\n\n📍 Feature 6: Type Safety with Models")
        print("-" * 80)
        
        results = McpTool.objects.search_by_type(
            SearchType.NEAR_TEXT,
            text="format data",
            limit=3
        )
        
        print("✅ Model-based search provides type-safe access:")
        for tool in results[:2]:
            # Type-safe property access
            print(f"\n  Tool: {tool.tool_name}")
            print(f"  Server: {tool.server_name}")
            print(f"  Description: {tool.description_main[:50]}...")
            print(f"  Tags: {tool.tags}")
        
        # ============================================================
        # Summary
        # ============================================================
        print("\n" + "=" * 80)
        print("  Summary")
        print("=" * 80)
        
        print("\n✅ Features Demonstrated:")
        print("  1. Universal search with SearchType enum")
        print("  2. String-based search type")
        print("  3. Dynamic strategy selection")
        print("  4. Easy comparison of strategies")
        print("  5. Search with filters")
        print("  6. Type-safe property access")
        
        print("\n💡 Key Advantages of Model-based Search:")
        print("  - Type safety and IDE autocomplete")
        print("  - Clean, readable code")
        print("  - Same SearchType API as direct search")
        print("  - Easy to switch between strategies")
        print("  - Integrated with model validation")
        
        print("\n📚 Available Search Types:")
        for st in SearchType:
            print(f"  - SearchType.{st.name}: {st.value}")
        
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

