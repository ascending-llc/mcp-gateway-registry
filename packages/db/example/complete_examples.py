"""
Complete Runnable Examples for Weaviate ORM Framework

Demonstrates all features with actual executable code.
Designed to work with Bedrock provider by default.

Usage:
    cd packages
    source .venv/bin/activate
    
    # Ensure environment is set
    export EMBEDDINGS_PROVIDER=bedrock
    export AWS_REGION=us-east-1
    # Either set AWS credentials or use IAM Role
    
    python -m db.example.complete_examples
"""

import sys
import time
import os
from pathlib import Path
from datetime import datetime, timezone


# Add packages to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from db import (
    Model,
    TextField,
    IntField,
    FloatField,
    BooleanField,
    DateTimeField,
    TextArrayField,
    RangeValidator,
    Q,
    DoesNotExist,
    FieldValidationError,
    get_weaviate_client,
    init_weaviate, SearchType,
)
from weaviate.classes.config import DataType
import dotenv
from db.search import get_search_interface

dotenv_path = "../../.env"
dotenv.load_dotenv(dotenv_path)


# ============================================================================
# Example Models (Auto-use Bedrock vectorizer)
# ============================================================================

class Article(Model):
    """
    Example Article model.
    
    Vectorizer is not specified, so it automatically uses the provider's default:
    - bedrock -> text2vec-aws
    - openai -> text2vec-openai
    """
    title = TextField(required=True, max_length=200, min_length=5)
    content = TextField(required=True, min_length=50)
    category = TextField()
    tags = TextArrayField()
    views = IntField(min_value=0)
    rating = FloatField(validators=[RangeValidator(0.0, 5.0)])
    published = BooleanField()
    created_at = DateTimeField()

    class Meta:
        collection_name = "ExampleArticles"
        # No vectorizer specified - uses provider default


class Product(Model):
    """Example Product model."""
    name = TextField(required=True, max_length=100)
    description = TextField(required=True)
    price = IntField(required=True, min_value=0)
    in_stock = BooleanField()

    class Meta:
        collection_name = "ExampleProducts"
        # No vectorizer specified - uses provider default


# ============================================================================
# Helper Functions
# ============================================================================

def print_section(title: str):
    """Print section header."""
    print("\n" + "=" * 70)
    print(f"{title}")
    print("=" * 70)


def safe_delete_collection(model_class):
    """Safely delete collection if exists."""
    try:
        if model_class.collection_exists():
            model_class.delete_collection()
    except:
        pass


# ============================================================================
# Example 1: Client Configuration
# ============================================================================

def example_1_client_configuration():
    """Example 1: Client Configuration."""
    print_section("EXAMPLE 1: Client Configuration")

    try:
        # Get current client
        client = get_weaviate_client()

        print("\n1. Current client configuration:")
        print(f"   Host: {client.connection.host}")
        print(f"   Port: {client.connection.port}")
        print(f"   Provider: {client.provider.__class__.__name__}")
        print(f"   Vectorizer: {client.provider.get_vectorizer_name()}")
        print(f"   Model: {client.provider.get_model_name()}")

        # Check authentication method
        headers = client.provider.get_headers()
        if headers:
            print(f"   Auth: Explicit credentials")
        else:
            print(f"   Auth: IAM Role (instance profile)")

        print("\n2. Health checks:")
        print(f"   is_ready(): {client.is_ready()}")
        print(f"   ping(): {client.ping()}")

        print("\n✅ Client configuration working")

    except Exception as e:
        print(f"   ❌ Error: {e}")


# ============================================================================
# Example 2: Collection Management
# ============================================================================

def example_2_collection_management():
    """Example 2: Collection Management."""
    print_section("EXAMPLE 2: Collection Management")

    try:
        # Clean up first
        safe_delete_collection(Article)

        # Create collection
        print("\n1. Create collection:")
        Article.create_collection()
        print(f"   ✅ Collection 'ExampleArticles' created")

        # Check exists
        print("\n2. Check if collection exists:")
        exists = Article.collection_exists()
        print(f"   Exists: {exists}")

        # Get collection info
        print("\n3. Get collection info:")
        info = Article.get_collection_info()
        if info:
            print(f"   Name: {info['name']}")
            print(f"   Properties: {len(info['properties'])}")
            print(f"   Vectorizer: {info.get('vectorizer', 'N/A')}")

        print("\n✅ Collection management working")

    except Exception as e:
        print(f"   ❌ Error: {e}")


# ============================================================================
# Example 3: CRUD Operations
# ============================================================================

def example_3_crud_operations():
    """Example 3: CRUD Operations."""
    print_section("EXAMPLE 3: CRUD Operations")

    try:
        # Ensure collection exists
        if not Article.collection_exists():
            Article.create_collection()

        # Create with proper datetime
        print("\n1. Create object:")
        article = Article.objects.create(
            title="Understanding Artificial Intelligence Today",
            content="AI is transforming the world in unprecedented ways. " * 10,
            category="tech",
            tags=["ai", "technology", "machine-learning"],
            views=0,
            rating=4.5,
            published=True,
            created_at=datetime.now(timezone.utc)  # Use UTC timezone
        )
        print(f"   ✅ Created: {article.id}")

        # Get by ID (fast)
        print("\n2. Get by ID (optimized):")
        fetched = Article.objects.get_by_id(article.id)
        print(f"   ✅ Retrieved: {fetched.title[:50]}...")

        # Update
        print("\n3. Update:")
        Article.objects.update(fetched, views=100)
        print(f"   ✅ Updated views to 100")

        # Delete
        print("\n4. Delete:")
        article.delete()
        print(f"   ✅ Deleted")

        # Verify deleted
        try:
            Article.objects.get_by_id(article.id)
            print(f"   ❌ Should have been deleted")
        except DoesNotExist:
            print(f"   ✅ Confirmed deleted")

        print("\n✅ CRUD operations working")

    except Exception as e:
        print(f"   ❌ Error: {e}")
        import traceback
        traceback.print_exc()


# ============================================================================
# Example 4: Batch Operations
# ============================================================================

def example_4_batch_operations():
    """Example 4: Batch Operations."""
    print_section("EXAMPLE 4: Batch Operations")

    try:
        if not Article.collection_exists():
            Article.create_collection()

        # Bulk create
        print("\n1. Bulk create (10 articles):")
        articles = [
            Article(
                title=f"Article {i}: Machine Learning Fundamentals Part {i}",
                content=f"This is article {i} about machine learning concepts. " * 15,
                category="tech",
                tags=["ml", "ai", "python"],
                views=i * 10,
                rating=4.0 + (i % 5) * 0.1,
                published=True,
                created_at=datetime.now(timezone.utc)
            )
            for i in range(10)
        ]

        result = Article.objects.bulk_create(articles, batch_size=5)
        print(f"   {result}")

        if result.has_errors:
            print(f"   ⚠️  Errors occurred:")
            for error in result.errors[:3]:
                print(f"      {error.get('message', error)}")

        # Get all for verification
        all_articles = Article.objects.all().limit(100).all()
        print(f"   ✅ Total articles in collection: {len(all_articles)}")

        # Delete where
        print("\n2. Delete where (views < 30):")
        count = Article.objects.delete_where(views__lt=30)
        print(f"   ✅ Deleted {count} articles")

        # Verify
        remaining = Article.objects.all().count()
        print(f"   Remaining: {remaining} articles")

        # Cleanup all
        print("\n3. Cleanup all test data:")
        if all_articles:
            ids = [a.id for a in all_articles if hasattr(a, 'id') and a.id]
            if ids:
                result = Article.objects.bulk_delete(ids)
                print(f"   ✅ Cleaned up {result.successful} articles")

        print("\n✅ Batch operations working")

    except Exception as e:
        print(f"   ❌ Error: {e}")


# ============================================================================
# Example 5: Search and Filter
# ============================================================================

def example_5_search_operations():
    """Example 5: Search Operations."""
    print_section("EXAMPLE 5: Search and Filter")

    try:
        if not Article.collection_exists():
            Article.create_collection()

        # Create test data
        print("\n1. Creating test data (5 articles)...")
        test_articles = [
            Article(
                title="Python Programming Complete Guide",
                content="Complete guide to Python programming with examples and best practices. " * 15,
                category="tech",
                tags=["python", "programming"],
                views=1000,
                rating=4.5,
                published=True,
                created_at=datetime.now(timezone.utc)
            ),
            Article(
                title="Machine Learning with Python Tutorial",
                content="Introduction to machine learning algorithms and implementation in Python. " * 15,
                category="tech",
                tags=["ml", "ai", "python"],
                views=1500,
                rating=4.8,
                published=True,
                created_at=datetime.now(timezone.utc)
            ),
            Article(
                title="Data Science Fundamentals",
                content="Data science techniques using Python and popular libraries for analysis. " * 15,
                category="science",
                tags=["data-science", "python"],
                views=800,
                rating=4.2,
                published=False,
                created_at=datetime.now(timezone.utc)
            ),
        ]

        result = Article.objects.bulk_create(test_articles)
        print(f"   ✅ Created {result.successful} test articles")

        # Simple search
        print("\n2. Search for 'python':")
        results = Article.objects.search("python").limit(5).all()
        print(f"   Found {len(results)} results:")
        for r in results:
            print(f"     - {r.title[:60]}...")

        # Filter
        print("\n3. Filter by category:")
        results = Article.objects.filter(category="tech").all()
        print(f"   Found {len(results)} tech articles")

        # Q objects
        print("\n4. Complex filter with Q objects:")
        results = Article.objects.filter(
            Q(category="tech") | Q(category="science")
        ).filter(views__gt=500).all()
        print(f"   Found {len(results)} articles (tech OR science) with views > 500")

        # Cleanup
        count = Article.objects.delete_where(views__gte=0)
        print(f"\n5. Cleanup: Deleted {count} articles")

        print("\n✅ Search operations working")

    except Exception as e:
        print(f"   ❌ Error: {e}")
        import traceback
        traceback.print_exc()


# ============================================================================
# Example 6: Aggregation
# ============================================================================

def example_6_aggregation():
    """Example 6: Aggregation."""
    print_section("EXAMPLE 6: Aggregation")

    try:
        if not Article.collection_exists():
            Article.create_collection()

        # Create diverse test data
        print("\n1. Creating test data for aggregation...")
        data_list = []
        for i in range(20):
            data_list.append({
                "title": f"Article {i}: Topic {i % 4}",
                "content": f"Content for article {i}. " * 20,
                "category": ["tech", "science", "business", "health"][i % 4],
                "views": (i + 1) * 100,
                "rating": 3.0 + (i % 10) * 0.2,
                "published": i % 2 == 0,
                "created_at": datetime.now(timezone.utc).isoformat()
            })

        result = Article.objects.bulk_import(data_list, batch_size=10)
        print(f"   ✅ Created {result.successful} articles")

        # Aggregate by category
        print("\n2. Aggregate by category:")
        stats = Article.objects.aggregate() \
            .group_by("category") \
            .count() \
            .avg("views") \
            .execute()

        if stats:
            for stat in stats:
                print(f"   {stat.get('group', 'N/A')}: {stat.get('count', 0)} articles")
        else:
            print("   (No aggregation results - feature may require setup)")

        # Overall stats
        print("\n3. Overall statistics:")
        total_count = Article.objects.all().count()
        print(f"   Total articles: {total_count}")

        # Cleanup
        count = Article.objects.delete_where(views__gte=0)
        print(f"\n4. Cleanup: Deleted {count} articles")

        print("\n✅ Aggregation working")

    except Exception as e:
        print(f"   ❌ Error: {e}")


# ============================================================================
# Example 7: Field Validation
# ============================================================================

def example_7_field_validation():
    """Example 7: Field Validation."""
    print_section("EXAMPLE 7: Field Validation")

    try:
        if not Article.collection_exists():
            Article.create_collection()

        # Valid article
        print("\n1. Create valid article:")
        article = Article(
            title="Valid Article Title Here",
            content="This is a sufficiently long content that meets the minimum length requirement. " * 5,
            views=100,
            rating=4.5,
            created_at=datetime.now(timezone.utc)
        )
        article.save()
        print(f"   ✅ Saved: {article.id}")
        article.delete()

        # Invalid: title too short
        print("\n2. Test validation: title too short")
        try:
            article = Article(
                title="Hi",  # Too short (min_length=5)
                content="Long enough content here. " * 10,
                created_at=datetime.now(timezone.utc)
            )
            article.save()
            print(f"   ❌ Should have failed validation")
        except FieldValidationError as e:
            print(f"   ✅ Caught validation error:")
            print(f"      Field: {e.field_name}")
            print(f"      Reason: {e.reason}")

        # Invalid: rating out of range
        print("\n3. Test validation: rating out of range")
        try:
            article = Article(
                title="Valid Title Here",
                content="Valid content here. " * 15,
                rating=6.0,  # Max is 5.0
                created_at=datetime.now(timezone.utc)
            )
            article.save()
            print(f"   ❌ Should have failed validation")
        except FieldValidationError as e:
            print(f"   ✅ Caught validation error:")
            print(f"      Field: {e.field_name}")
            print(f"      Reason: {e.reason}")

        print("\n✅ Field validation working")

    except Exception as e:
        print(f"   ❌ Error: {e}")


# ============================================================================
# Example 8: Batch Import with Progress
# ============================================================================

def example_8_large_batch_import():
    """Example 8: Large Batch Import."""
    print_section("EXAMPLE 8: Large Batch Import with Progress")

    try:
        if not Article.collection_exists():
            Article.create_collection()

        # Generate test data
        print("\n1. Generating 50 articles...")
        data_list = []
        now = datetime.now(timezone.utc).isoformat()

        for i in range(50):
            data_list.append({
                "title": f"Article {i}: Technology Trends in {2024 + i % 5}",
                "content": f"This is article {i} discussing technology trends and innovations. " * 20,
                "category": ["tech", "science", "business"][i % 3],
                "tags": ["tech", "innovation", "trends"],
                "views": i * 20,
                "rating": 3.5 + (i % 15) * 0.1,
                "published": i % 2 == 0,
                "created_at": now
            })

        print(f"   ✅ Generated {len(data_list)} articles")

        # Import with progress
        print("\n2. Importing with progress tracking:")

        progress_updates = []

        def show_progress(current, total):
            progress_updates.append((current, total))
            pct = (current / total) * 100
            bar_length = 30
            filled = int(bar_length * current / total)
            bar = '█' * filled + '░' * (bar_length - filled)
            print(f"\r   [{bar}] {current}/{total} ({pct:.1f}%)", end="")

        result = Article.objects.bulk_import(
            data_list,
            batch_size=20,
            on_progress=show_progress
        )

        print(f"\n   ✅ {result}")
        print(f"   Progress updates: {len(progress_updates)}")

        # Verify
        count = Article.objects.all().count()
        print(f"   Total in collection: {count}")

        # Cleanup
        deleted = Article.objects.delete_where(views__gte=0)
        print(f"\n3. Cleanup: Deleted {deleted} articles")

        print("\n✅ Large batch import working")

    except Exception as e:
        print(f"   ❌ Error: {e}")


# ============================================================================
# Example 9: Performance Demo
# ============================================================================

def example_9_search_by_type_with_model():
    """Example 9: search_by_type with Model."""
    print_section("EXAMPLE 9: search_by_type with Model")
    
    try:
        if not Article.collection_exists():
            Article.create_collection()
        
        # Create test data
        print("\n1. Creating test data...")
        test_data = [
            {
                "title": "Python Programming Guide for Beginners",
                "content": "Complete Python programming tutorial with examples. " * 15,
                "category": "tech",
                "tags": ["python", "programming", "tutorial"],
                "views": 1000,
                "published": True,
                "created_at": datetime.now(timezone.utc).isoformat()
            },
            {
                "title": "Machine Learning with Python",
                "content": "Learn machine learning algorithms using Python. " * 15,
                "category": "tech",
                "tags": ["ml", "python", "ai"],
                "views": 1500,
                "published": True,
                "created_at": datetime.now(timezone.utc).isoformat()
            }
        ]
        result = Article.objects.bulk_import(test_data)
        print(f"   ✅ Created {result.successful} articles")
        
        # Compare different search types
        print("\n2. Compare search types for 'python machine learning':")
        search_types = [
            (SearchType.BM25, "BM25 (keyword)"),
            (SearchType.NEAR_TEXT, "Semantic"),
            (SearchType.HYBRID, "Hybrid"),
            (SearchType.FUZZY, "Fuzzy"),
        ]
        
        for search_type, name in search_types:
            results = Article.objects.search_by_type(
                search_type,
                query="python machine learning"
            ).limit(5).all()
            print(f"   {name:20s}: {len(results)} results")
        
        # Dynamic selection based on user preference
        print("\n3. Dynamic search type selection:")
        
        def search_with_preference(query, preference):
            """Select search type based on user preference."""
            type_map = {
                'exact': SearchType.BM25,
                'smart': SearchType.HYBRID,
                'semantic': SearchType.NEAR_TEXT,
                'tolerant': SearchType.FUZZY
            }
            search_type = type_map.get(preference, SearchType.HYBRID)
            return Article.objects.search_by_type(search_type, query=query).all()
        
        for pref in ['exact', 'smart', 'semantic']:
            results = search_with_preference("python", pref)
            print(f"   Preference '{pref}': {len(results)} results")
        
        # Cleanup
        count = Article.objects.delete_where(views__gte=0)
        print(f"\n4. Cleanup: Deleted {count} articles")
        
        print("\n✅ search_by_type with Model working")
        
    except Exception as e:
        print(f"   ❌ Error: {e}")


def example_10_search_by_type_without_model():
    """Example 10: search_by_type without Model (Collection-based)."""
    print_section("EXAMPLE 10: search_by_type without Model (Collection)")
    
    try:

        
        if not Article.collection_exists():
            Article.create_collection()
        
        # Create test data
        print("\n1. Creating test data...")
        data = [
            {
                "title": "Data Science Tutorial",
                "content": "Learn data science with Python and R. " * 15,
                "category": "science",
                "tags": ["data", "python"],
                "views": 800,
                "published": True,
                "created_at": datetime.now(timezone.utc).isoformat()
            }
        ]
        result = Article.objects.bulk_import(data)
        print(f"   ✅ Created {result.successful} articles")
        
        # Collection-based search with search_by_type
        print("\n2. Collection-based search (no Model definition needed):")
        
        search = get_search_interface()
        
        # Different search types on collection
        print("\n   Testing different search types on 'ExampleArticles' collection:")
        
        # BM25
        results = search.collection("ExampleArticles").search_by_type(
            SearchType.BM25,
            query="data science"
        ).limit(5).all()
        print(f"   BM25: {len(results)} results")
        
        # Semantic
        results = search.collection("ExampleArticles").search_by_type(
            SearchType.NEAR_TEXT,
            query="data analysis and visualization"
        ).limit(5).all()
        print(f"   Semantic: {len(results)} results")
        
        # Hybrid (recommended)
        results = search.collection("ExampleArticles").search_by_type(
            SearchType.HYBRID,
            query="python data science"
        ).limit(5).all()
        print(f"   Hybrid: {len(results)} results")
        
        # With filters
        print("\n3. Collection-based search with filters:")
        results = search.collection("ExampleArticles")\
            .filter(published=True, views__gt=500)\
            .search_by_type(SearchType.HYBRID, query="data")\
            .limit(10)\
            .all()
        print(f"   Found {len(results)} published articles with views > 500")
        
        # Cleanup
        count = Article.objects.delete_where(views__gte=0)
        print(f"\n4. Cleanup: Deleted {count} articles")
        
        print("\n✅ search_by_type without Model working")
        
    except Exception as e:
        print(f"   ❌ Error: {e}")
        import traceback
        traceback.print_exc()


def example_11_performance():
    """Example 11: Performance Comparison."""
    print_section("EXAMPLE 11: Performance: get_by_id vs filter")

    try:
        if not Article.collection_exists():
            Article.create_collection()

        # Create test article
        print("\n1. Creating test article...")
        article = Article.objects.create(
            title="Performance Test Article Title",
            content="This is a test article for performance comparison. " * 20,
            category="tech",
            created_at=datetime.now(timezone.utc)
        )
        print(f"   ✅ Created: {article.id}")

        # Performance comparison
        print("\n2. Performance comparison (100 queries each):")
        
        # get_by_id (fast - direct UUID lookup)
        start = time.time()
        for _ in range(100):
            Article.objects.get_by_id(article.id)
        duration_by_id = time.time() - start
        print(f"   get_by_id: {duration_by_id:.3f}s")
        
        # filter by title (slower - needs to scan)
        start = time.time()
        for _ in range(100):
            Article.objects.filter(title=article.title).first()
        duration_filter = time.time() - start
        print(f"   filter:    {duration_filter:.3f}s")
        
        if duration_by_id > 0:
            speedup = duration_filter / duration_by_id
            print(f"   ⚡ get_by_id is {speedup:.1f}x faster than filter")

        # Model.objects access performance
        print("\n3. Model.objects access (10,000 times):")
        start = time.time()
        for _ in range(10000):
            _ = Article.objects
        duration = time.time() - start
        print(f"   Duration: {duration:.3f}s")
        print(f"   Per access: {duration / 10000 * 1000:.4f}ms")
        print(f"   ✅ Descriptor pattern - very fast!")

        # Cleanup
        article.delete()
        print(f"\n4. Cleanup complete")

        print("\n✅ Performance demo complete")

    except Exception as e:
        print(f"   ❌ Error: {e}")


# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    """Run all examples."""
    print("\n" + "=" * 70)
    print(" " * 10 + "Weaviate ORM Framework - Complete Examples")
    print(" " * 25 + "Version 2.0.0")
    print("=" * 70)

    # Check and initialize
    print("\n🔍 Initializing...")
    try:
        init_weaviate()
        client = get_weaviate_client()

        print(f"✅ Connected to: {client.connection.host}:{client.connection.port}")
        print(f"✅ Provider: {client.provider.__class__.__name__}")
        print(f"✅ Vectorizer: {client.provider.get_vectorizer_name()}")

        # Check health
        if not client.is_ready() or not client.ping():
            print("\n⚠️  Weaviate is not fully ready")
            print("   Some examples may fail")

    except Exception as e:
        print(f"\n❌ Failed to initialize: {e}")
        print("\nPlease ensure:")
        print("  1. Weaviate is running")
        print("  2. Environment variables are set:")
        print("     - WEAVIATE_HOST, WEAVIATE_PORT")
        print("     - EMBEDDINGS_PROVIDER=bedrock")
        print("     - AWS_REGION (required)")
        print("     - AWS credentials or IAM Role")
        return

    # Run examples
    examples = [
        # ("Client Configuration", example_1_client_configuration),
        # ("Collection Management", example_2_collection_management),
        # ("CRUD Operations", example_3_crud_operations),
        # ("Batch Operations", example_4_batch_operations),
        # ("Search and Filter", example_5_search_operations),
        # ("Aggregation", example_6_aggregation),
        # ("Field Validation", example_7_field_validation),
        # ("Large Batch Import", example_8_large_batch_import),
        ("search_by_type with Model", example_9_search_by_type_with_model),
        ("search_by_type without Model", example_10_search_by_type_without_model),
        # ("Performance Demo", example_11_performance),
    ]

    print("\n" + "=" * 70)
    print("Running Examples...")
    print("=" * 70)

    success_count = 0
    for name, example_func in examples:
        try:
            example_func()
            success_count += 1
            time.sleep(0.3)  # Small delay
        except Exception as e:
            print(f"\n❌ Example '{name}' failed: {e}")

    # Print summary
    print("\n" + "=" * 70)
    print("Examples Summary")
    print("=" * 70)
    print(f"\n✅ Completed {success_count}/{len(examples)} examples")

    print("\n📚 Documentation:")
    print("   - README.md - Complete usage guide")
    print("   - db/example/check_config.py - Check configuration")
    print("   - tests/ - Test examples")

    print("\n🎯 Key Features:")
    print("   ✅ Clean configuration (3 objects)")
    print("   ✅ IAM Role support (no explicit credentials needed)")
    print("   ✅ Batch operations with error reporting")
    print("   ✅ Progress tracking for large imports")
    print("   ✅ Fast ID lookups (get_by_id)")
    print("   ✅ Field validation and conversion")
    print("   ✅ Advanced search and aggregation")



if __name__ == "__main__":
    main()
