"""Test data factories for packages tests."""

from datetime import UTC, datetime

import factory
from beanie import PydanticObjectId
from faker import Faker

fake = Faker()


class MCPServerFactory(factory.DictFactory):
    """Factory for creating MCP server test data."""

    serverName = factory.LazyFunction(lambda: fake.slug())
    config = factory.Dict({
        "title": factory.LazyFunction(lambda: fake.company()),
        "description": factory.LazyFunction(lambda: fake.text(max_nb_chars=200)),
        "type": "streamable-http",
        "url": factory.LazyFunction(lambda: f"http://{fake.slug()}:{fake.port_number()}"),
        "tools": factory.LazyFunction(lambda: ", ".join(fake.words(nb=3))),
        "capabilities": "{}",
        "requiresOAuth": False,
    })
    author = factory.LazyFunction(lambda: str(PydanticObjectId()))
    path = factory.LazyFunction(lambda: f"/mcp/{fake.slug()}")
    tags = factory.LazyFunction(lambda: fake.words(nb=3))
    scope = "private_user"
    status = "active"
    numTools = factory.LazyFunction(lambda: fake.random_int(min=0, max=20))
    numStars = factory.LazyFunction(lambda: fake.random_int(min=0, max=100))


class OAuthServerFactory(factory.DictFactory):
    """Factory for creating OAuth-enabled MCP server test data."""

    serverName = factory.LazyFunction(lambda: f"oauth-{fake.slug()}")
    config = factory.Dict({
        "title": factory.LazyFunction(lambda: f"OAuth {fake.company()}"),
        "description": factory.LazyFunction(lambda: fake.text(max_nb_chars=200)),
        "type": "streamable-http",
        "url": factory.LazyFunction(lambda: f"http://{fake.slug()}:{fake.port_number()}"),
        "requiresOAuth": True,
        "oauth": factory.Dict({
            "client_id": factory.LazyFunction(lambda: fake.uuid4()),
            "authorization_url": factory.LazyFunction(lambda: f"https://{fake.domain_name()}/authorize"),
            "token_url": factory.LazyFunction(lambda: f"https://{fake.domain_name()}/token"),
            "scopes": factory.List([factory.LazyFunction(lambda: fake.word()) for _ in range(2)]),
        }),
        "tools": factory.LazyFunction(lambda: ", ".join(fake.words(nb=2))),
        "capabilities": "{}",
    })
    author = factory.LazyFunction(lambda: str(PydanticObjectId()))
    path = factory.LazyFunction(lambda: f"/mcp/{fake.slug()}")
    tags = factory.LazyFunction(lambda: ["oauth"] + fake.words(nb=2))
    scope = "shared_app"
    status = "active"
    numTools = factory.LazyFunction(lambda: fake.random_int(min=1, max=10))
    numStars = factory.LazyFunction(lambda: fake.random_int(min=0, max=50))


class TokenFactory(factory.DictFactory):
    """Factory for creating token test data."""

    type = factory.LazyFunction(lambda: fake.random_element(elements=["oauth_access", "oauth_refresh", "api_key"]))
    identifier = factory.LazyFunction(lambda: fake.slug())
    user_id = factory.LazyFunction(lambda: str(PydanticObjectId()))
    encrypted_value = factory.LazyFunction(lambda: fake.sha256())
    expires_at = factory.LazyFunction(lambda: datetime.now(UTC))
    metadata = factory.Dict({
        "provider": factory.LazyFunction(lambda: fake.word()),
        "scopes": factory.List([factory.LazyFunction(lambda: fake.word()) for _ in range(2)]),
    })
