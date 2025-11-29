"""
Tests for embeddings providers.
"""

import pytest
from unittest.mock import patch
from db.core.providers import (
    EmbeddingsProvider,
    BedrockProvider,
    OpenAIProvider,
    ProviderFactory
)
from db.core.exceptions import InvalidProvider, MissingCredentials


class TestBedrockProvider:
    """Test BedrockProvider."""
    
    def test_initialization(self):
        """Test provider initialization."""
        provider = BedrockProvider(
            access_key="test-key",
            secret_key="test-secret",
            region="us-west-2"
        )
        
        assert provider.access_key == "test-key"
        assert provider.secret_key == "test-secret"
        assert provider.region == "us-west-2"
        assert provider.session_token is None
    
    def test_get_headers(self):
        """Test get_headers method."""
        provider = BedrockProvider(
            access_key="key123",
            secret_key="secret456"
        )
        
        headers = provider.get_headers()
        
        assert 'X-AWS-Access-Key' in headers
        assert headers['X-AWS-Access-Key'] == "key123"
        assert 'X-AWS-Secret-Key' in headers
        assert headers['X-AWS-Secret-Key'] == "secret456"
    
    def test_get_headers_with_session_token(self):
        """Test headers with session token."""
        provider = BedrockProvider(
            access_key="key",
            secret_key="secret",
            session_token="token123"
        )
        
        headers = provider.get_headers()
        
        assert 'X-AWS-Session-Token' in headers
        assert headers['X-AWS-Session-Token'] == "token123"
    
    def test_get_vectorizer_name(self):
        """Test get_vectorizer_name method."""
        provider = BedrockProvider("key", "secret")
        
        assert provider.get_vectorizer_name() == "text2vec-aws"
    
    def test_get_model_name(self):
        """Test get_model_name method."""
        provider = BedrockProvider("key", "secret")
        
        assert "titan" in provider.get_model_name().lower()
    
    def test_from_env_success(self, monkeypatch):
        """Test creating provider from environment."""
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "env-key")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "env-secret")
        monkeypatch.setenv("AWS_REGION", "eu-west-1")
        
        provider = BedrockProvider.from_env()
        
        assert provider.access_key == "env-key"
        assert provider.secret_key == "env-secret"
        assert provider.region == "eu-west-1"
    
    def test_from_env_with_iam_role(self, monkeypatch):
        """Test creating provider without explicit credentials (IAM Role)."""
        # Clear any existing env vars to simulate IAM Role scenario
        monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
        monkeypatch.delenv("AWS_SECRET_ACCESS_KEY", raising=False)
        monkeypatch.setenv("AWS_REGION", "us-west-2")
        
        # Should not raise error - allows IAM Role authentication
        provider = BedrockProvider.from_env()
        
        assert provider.access_key == ""
        assert provider.secret_key == ""
        assert provider.region == "us-west-2"
        
        # Headers should be empty (IAM Role will be used)
        headers = provider.get_headers()
        assert headers == {}


class TestOpenAIProvider:
    """Test OpenAIProvider."""
    
    def test_initialization(self):
        """Test provider initialization."""
        provider = OpenAIProvider(api_key="sk-test123")
        
        assert provider.api_key == "sk-test123"
    
    def test_get_headers(self):
        """Test get_headers method."""
        provider = OpenAIProvider(api_key="sk-abc")
        
        headers = provider.get_headers()
        
        assert 'X-OpenAI-Api-Key' in headers
        assert headers['X-OpenAI-Api-Key'] == "sk-abc"
    
    def test_get_vectorizer_name(self):
        """Test get_vectorizer_name method."""
        provider = OpenAIProvider("key")
        
        assert provider.get_vectorizer_name() == "text2vec-openai"
    
    def test_from_env_success(self, monkeypatch):
        """Test creating provider from environment."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-env-key")
        
        provider = OpenAIProvider.from_env()
        
        assert provider.api_key == "sk-env-key"
    
    def test_from_env_missing_key(self, monkeypatch):
        """Test error when API key missing."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        
        with pytest.raises(MissingCredentials) as exc_info:
            OpenAIProvider.from_env()
        
        assert "openai" in str(exc_info.value).lower()


class TestProviderFactory:
    """Test ProviderFactory."""
    
    def test_list_providers(self):
        """Test listing registered providers."""
        providers = ProviderFactory.list_providers()
        
        assert 'bedrock' in providers
        assert 'openai' in providers
    
    def test_create_bedrock(self):
        """Test creating Bedrock provider."""
        provider = ProviderFactory.create(
            'bedrock',
            access_key="key",
            secret_key="secret"
        )
        
        assert isinstance(provider, BedrockProvider)
        assert provider.access_key == "key"
    
    def test_create_openai(self):
        """Test creating OpenAI provider."""
        provider = ProviderFactory.create(
            'openai',
            api_key="sk-test"
        )
        
        assert isinstance(provider, OpenAIProvider)
        assert provider.api_key == "sk-test"
    
    def test_create_invalid_provider(self):
        """Test error when creating invalid provider."""
        with pytest.raises(InvalidProvider) as exc_info:
            ProviderFactory.create('invalid_provider')
        
        assert exc_info.value.provider == 'invalid_provider'
        assert 'bedrock' in exc_info.value.available
        assert 'openai' in exc_info.value.available
    
    def test_from_env_bedrock(self, monkeypatch):
        """Test creating provider from env (Bedrock)."""
        monkeypatch.setenv("EMBEDDINGS_PROVIDER", "bedrock")
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "key")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "secret")
        
        provider = ProviderFactory.from_env()
        
        assert isinstance(provider, BedrockProvider)
    
    def test_from_env_openai(self, monkeypatch):
        """Test creating provider from env (OpenAI)."""
        monkeypatch.setenv("EMBEDDINGS_PROVIDER", "openai")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        
        provider = ProviderFactory.from_env()
        
        assert isinstance(provider, OpenAIProvider)
    
    def test_register_custom_provider(self):
        """Test registering custom provider."""
        class CustomProvider(EmbeddingsProvider):
            def get_headers(self):
                return {}
            def get_vectorizer_name(self):
                return "custom-vectorizer"
            def get_model_name(self):
                return "custom-model"
            @classmethod
            def from_env(cls):
                return cls()
        
        ProviderFactory.register('custom', CustomProvider)
        
        assert 'custom' in ProviderFactory.list_providers()
        
        provider = ProviderFactory.create('custom')
        assert isinstance(provider, CustomProvider)

