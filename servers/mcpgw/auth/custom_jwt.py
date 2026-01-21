import logging
import jwt
from typing import Optional
from datetime import datetime
from fastmcp.server.auth import TokenVerifier, AccessToken
from config import settings

logger = logging.getLogger(__name__)


class CustomJWTVerifier(TokenVerifier):
    """
    JWT Token Verifier for HS256 (HMAC with SHA-256) signed tokens.
    
    This provider validates JWT tokens signed with a shared secret key,
    commonly used in microservices architectures where the token issuer
    and verifier share the same secret.
    """

    def __init__(
            self,
            secret_key: str,
            issuer: str,
            audience: str,
            base_url: Optional[str] = None,
            required_scopes: Optional[list[str]] = None,
            algorithms: Optional[list] = None,
            expected_kid: Optional[str] = None
    ):
        """
        Initialize JWT verifier.
        
        Args:
            secret_key: Shared secret key for verifying JWT signature
            issuer: Expected token issuer (iss claim)
            audience: Expected token audience (aud claim)
            base_url: Base URL of the server (optional)
            required_scopes: Required scopes for all requests (optional)
            algorithms: List of allowed signature algorithms, defaults to ["HS256"]
            expected_kid: Expected Key ID (kid), will be validated if provided
        """
        super().__init__(base_url=base_url, required_scopes=required_scopes)
        self.secret_key = secret_key
        self.issuer = issuer
        self.audience = audience
        self.algorithms = algorithms or ["HS256"]
        self.expected_kid = expected_kid

    async def verify_token(self, token: str) -> AccessToken | None:
        """
        Verify JWT token and return access information.
        
        This method is called by FastMCP framework's BearerAuthBackend to verify each request.
        The framework automatically extracts the Bearer token from the Authorization header.
        
        Args:
            token: JWT token string (without "Bearer " prefix)
            
        Returns:
            AccessToken object if verification succeeds, otherwise None
        """
        if not token:
            logger.warning("Empty token provided")
            return None

        # Verify JWT token
        try:
            # If expected_kid is specified, check the kid in token header first
            if self.expected_kid:
                try:
                    unverified_header = jwt.get_unverified_header(token)
                    token_kid = unverified_header.get("kid")

                    if token_kid != self.expected_kid:
                        logger.warning(
                            f"Token kid mismatch: expected={self.expected_kid}, got={token_kid}"
                        )
                        return None
                except jwt.DecodeError as e:
                    logger.error(f"Failed to decode token header: {e}")
                    return None

            # Decode and verify JWT token
            # For self-signed tokens (kid='mcp-self-signed'), skip audience validation
            # because the audience is now the resource URL (RFC 8707 Resource Indicators)
            is_self_signed = (token_kid == self.expected_kid)
            
            decode_options = {
                "verify_signature": True,
                "verify_exp": True,
                "verify_iss": True,
                "verify_aud": not is_self_signed,  # Skip aud check for self-signed tokens
                "require": ["exp", "iss", "aud", "sub"]
            }
            
            decode_kwargs = {
                "algorithms": self.algorithms,
                "issuer": self.issuer,
                "options": decode_options
            }
            
            # Only validate audience for provider tokens (not self-signed)
            if not is_self_signed:
                decode_kwargs["audience"] = self.audience
            else:
                logger.info("Skipping audience validation for self-signed token (RFC 8707 Resource Indicators)")
            
            claims = jwt.decode(
                token,
                self.secret_key,
                **decode_kwargs
            )

            # Extract user information
            subject = claims.get("sub")
            client_id = claims.get("client_id", "unknown")

            # Extract scopes (may be in "scope" or "scopes" claim)
            scopes = []
            if "scope" in claims:
                # OAuth2 standard format: space-separated string
                scope_str = claims["scope"]
                if isinstance(scope_str, str):
                    scopes = scope_str.split()
            elif "scopes" in claims:
                # Alternative format: array
                scopes_claim = claims["scopes"]
                if isinstance(scopes_claim, list):
                    scopes = scopes_claim

            # Get expiration time
            expires_at = claims.get("exp")

            # Log successful authentication
            exp_time = datetime.fromtimestamp(expires_at) if expires_at else None
            logger.info(
                f"JWT token validated successfully: "
                f"user={subject}, client_id={client_id}, scopes={scopes}, expires={exp_time}"
            )
            return AccessToken(
                token=token,  # JWT token string
                client_id=client_id,  # Client ID (required)
                scopes=scopes,  # Scope list (required, list type)
                expires_at=expires_at,  # Expiration timestamp (optional)
                claims=claims  # FastMCP extension field: complete JWT claims
            )

        except jwt.ExpiredSignatureError:
            logger.warning("JWT token has expired")
            return None
        except jwt.InvalidIssuerError:
            logger.warning(f"Invalid token issuer. Expected: {self.issuer}")
            return None
        except jwt.InvalidAudienceError:
            logger.warning(f"Invalid token audience. Expected: {self.audience}")
            return None
        except jwt.InvalidSignatureError:
            logger.warning("Invalid JWT signature")
            return None
        except jwt.DecodeError as e:
            logger.error(f"Failed to decode JWT token: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error during JWT validation: {e}", exc_info=True)
            return None


jwtVerifier = CustomJWTVerifier(
    secret_key=settings.JWT_SECRET_KEY,
    issuer=settings.JWT_ISSUER,
    audience=settings.JWT_AUDIENCE,
    expected_kid=settings.JWT_SELF_SIGNED_KID
)
