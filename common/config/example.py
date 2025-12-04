"""
Pydantic Settings Override Priority Explanation

Class Structure Overview:
"""

from pydantic_settings import BaseSettings, SettingsConfigDict

class SharedSettings(BaseSettings):
    """
    Parent class for shared configuration across multiple projects
    Uses .env.shared file for environment variables
    """
    model_config = SettingsConfigDict(env_file='.env.shared')
    A: str = "shared_default_value"

class Settings(SharedSettings):
    """
    Child class inheriting from SharedSettings
    Uses .env.settings file for project-specific environment variables
    """
    model_config = SettingsConfigDict(env_file='.env.settings')
    A: str = "settings_default_value"

# Priority Order (Highest to Lowest)
# When you instantiate Settings(), pydantic_settings resolves variable A using this exact priority order:
#
# 1. Constructor arguments - Settings(A="direct_value") [HIGHEST PRIORITY]
# 2. System environment variables - export A=system_value
# 3. Child class env file - .env.settings file: A=settings_env_value
# 4. Parent class env file - .env.shared file: A=shared_env_value
# 5. Child class default - A: str = "settings_default_value"
# 6. Parent class default - A: str = "shared_default_value" [LOWEST PRIORITY]

# Key Principle:
# Settings class configuration sources always take precedence over
# SharedSettings class configuration sources at the same level

# Override Examples:

# Scenario 1: Both env files have variable A
# .env.shared: A=shared_env_value
# .env.settings: A=settings_env_value
# Result: A = "settings_env_value" ✅

# Scenario 2: Only parent env file has variable A
# .env.shared: A=shared_env_value
# .env.settings: (no A variable)
# Result: A = "shared_env_value" ✅

# Scenario 3: No env files have variable A
# Result: A = "settings_default_value" ✅ (Settings class default wins)

# Important Notes:
# - It's NOT a two-step process where each class resolves internally first
# - It IS a single unified priority list where all configuration sources are ranked together
# - Settings class sources are always ranked higher than SharedSettings class sources of the same type
# - Environment variables always override class default values, regardless of inheritance

# Best Practice Summary:
# When Settings inherits from SharedSettings, the final value of variable A will be
# determined by the highest priority source available, with Settings class sources
# taking precedence over SharedSettings class sources at every level.
#
# Bottom line: If both .env.shared and .env.settings files contain variable A,
# the value from .env.settings will be used as the final result.

# Example usage:
if __name__ == "__main__":
    # This will follow the priority order explained above
    settings = Settings()
    print(f"Final value of A: {settings.A}")