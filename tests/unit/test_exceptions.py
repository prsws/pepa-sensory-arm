"""Unit tests for custom exceptions.

This module tests all custom exception classes to ensure they can be
properly raised, caught, and inherit from the correct base classes.
"""

import pytest

from custom_components.pepa_sensory_arm.exceptions import (
    AuthenticationError,
    ContextInjectionError,
    PepaSensoryArmError,
    PermissionDenied,
    RateLimitExceeded,
    TokenLimitExceeded,
    ToolExecutionError,
    ValidationError,
)


class TestPepaSensoryArmError:
    """Tests for PepaSensoryArmError base exception."""

    def test_raise_pepa_sensory_arm_error(self):
        """Test that PepaSensoryArmError can be raised."""
        with pytest.raises(PepaSensoryArmError):
            raise PepaSensoryArmError("Test error")

    def test_pepa_sensory_arm_error_message(self):
        """Test that PepaSensoryArmError preserves message."""
        message = "This is a test error message"
        with pytest.raises(PepaSensoryArmError) as exc_info:
            raise PepaSensoryArmError(message)

        assert str(exc_info.value) == message

    def test_pepa_sensory_arm_error_inherits_from_exception(self):
        """Test that PepaSensoryArmError inherits from Exception."""
        assert issubclass(PepaSensoryArmError, Exception)

    def test_catch_pepa_sensory_arm_error(self):
        """Test catching PepaSensoryArmError."""
        try:
            raise PepaSensoryArmError("Test")
        except PepaSensoryArmError as error:
            assert str(error) == "Test"
        else:
            pytest.fail("PepaSensoryArmError was not caught")

    def test_pepa_sensory_arm_error_no_message(self):
        """Test PepaSensoryArmError with no message."""
        with pytest.raises(PepaSensoryArmError):
            raise PepaSensoryArmError()


class TestContextInjectionError:
    """Tests for ContextInjectionError exception."""

    def test_raise_context_injection_error(self):
        """Test that ContextInjectionError can be raised."""
        with pytest.raises(ContextInjectionError):
            raise ContextInjectionError("Context injection failed")

    def test_context_injection_error_message(self):
        """Test that ContextInjectionError preserves message."""
        message = "Failed to inject context for entity light.living_room"
        with pytest.raises(ContextInjectionError) as exc_info:
            raise ContextInjectionError(message)

        assert str(exc_info.value) == message

    def test_context_injection_error_inherits_from_pepa_sensory_arm_error(self):
        """Test that ContextInjectionError inherits from PepaSensoryArmError."""
        assert issubclass(ContextInjectionError, PepaSensoryArmError)

    def test_catch_context_injection_error_as_pepa_sensory_arm_error(self):
        """Test catching ContextInjectionError as PepaSensoryArmError."""
        try:
            raise ContextInjectionError("Test")
        except PepaSensoryArmError:
            pass  # Should catch successfully
        else:
            pytest.fail("ContextInjectionError not caught as PepaSensoryArmError")

    def test_context_injection_error_formatted_message(self):
        """Test ContextInjectionError with formatted message."""
        entity_id = "sensor.temperature"
        error_msg = "Entity not found"
        message = f"Failed to inject context for {entity_id}: {error_msg}"

        with pytest.raises(ContextInjectionError) as exc_info:
            raise ContextInjectionError(message)

        assert entity_id in str(exc_info.value)
        assert error_msg in str(exc_info.value)


class TestToolExecutionError:
    """Tests for ToolExecutionError exception."""

    def test_raise_tool_execution_error(self):
        """Test that ToolExecutionError can be raised."""
        with pytest.raises(ToolExecutionError):
            raise ToolExecutionError("Tool execution failed")

    def test_tool_execution_error_message(self):
        """Test that ToolExecutionError preserves message."""
        message = "Tool 'ha_control' failed: Entity not found"
        with pytest.raises(ToolExecutionError) as exc_info:
            raise ToolExecutionError(message)

        assert str(exc_info.value) == message

    def test_tool_execution_error_inherits_from_pepa_sensory_arm_error(self):
        """Test that ToolExecutionError inherits from PepaSensoryArmError."""
        assert issubclass(ToolExecutionError, PepaSensoryArmError)

    def test_catch_tool_execution_error_as_pepa_sensory_arm_error(self):
        """Test catching ToolExecutionError as PepaSensoryArmError."""
        try:
            raise ToolExecutionError("Test")
        except PepaSensoryArmError:
            pass  # Should catch successfully
        else:
            pytest.fail("ToolExecutionError not caught as PepaSensoryArmError")

    def test_tool_execution_error_with_tool_details(self):
        """Test ToolExecutionError with tool and entity details."""
        tool_name = "ha_control"
        entity_id = "light.bedroom"
        error = "Permission denied"
        message = (
            f"Tool '{tool_name}' failed: {error}. "
            f"Check entity_id '{entity_id}' exists and is accessible."
        )

        with pytest.raises(ToolExecutionError) as exc_info:
            raise ToolExecutionError(message)

        assert tool_name in str(exc_info.value)
        assert entity_id in str(exc_info.value)


class TestAuthenticationError:
    """Tests for AuthenticationError exception."""

    def test_raise_authentication_error(self):
        """Test that AuthenticationError can be raised."""
        with pytest.raises(AuthenticationError):
            raise AuthenticationError("Authentication failed")

    def test_authentication_error_message(self):
        """Test that AuthenticationError preserves message."""
        message = "Failed to authenticate with LLM: Invalid API key"
        with pytest.raises(AuthenticationError) as exc_info:
            raise AuthenticationError(message)

        assert str(exc_info.value) == message

    def test_authentication_error_inherits_from_pepa_sensory_arm_error(self):
        """Test that AuthenticationError inherits from PepaSensoryArmError."""
        assert issubclass(AuthenticationError, PepaSensoryArmError)

    def test_catch_authentication_error_as_pepa_sensory_arm_error(self):
        """Test catching AuthenticationError as PepaSensoryArmError."""
        try:
            raise AuthenticationError("Test")
        except PepaSensoryArmError:
            pass  # Should catch successfully
        else:
            pytest.fail("AuthenticationError not caught as PepaSensoryArmError")

    def test_authentication_error_with_url(self):
        """Test AuthenticationError with API URL details."""
        base_url = "https://api.openai.com/v1"
        message = f"Failed to authenticate with LLM at {base_url}: Invalid API key"

        with pytest.raises(AuthenticationError) as exc_info:
            raise AuthenticationError(message)

        assert base_url in str(exc_info.value)


class TestTokenLimitExceeded:
    """Tests for TokenLimitExceeded exception."""

    def test_raise_token_limit_exceeded(self):
        """Test that TokenLimitExceeded can be raised."""
        with pytest.raises(TokenLimitExceeded):
            raise TokenLimitExceeded("Token limit exceeded")

    def test_token_limit_exceeded_message(self):
        """Test that TokenLimitExceeded preserves message."""
        message = "Context size 10000 exceeds limit 8000"
        with pytest.raises(TokenLimitExceeded) as exc_info:
            raise TokenLimitExceeded(message)

        assert str(exc_info.value) == message

    def test_token_limit_exceeded_inherits_from_pepa_sensory_arm_error(self):
        """Test that TokenLimitExceeded inherits from PepaSensoryArmError."""
        assert issubclass(TokenLimitExceeded, PepaSensoryArmError)

    def test_catch_token_limit_exceeded_as_pepa_sensory_arm_error(self):
        """Test catching TokenLimitExceeded as PepaSensoryArmError."""
        try:
            raise TokenLimitExceeded("Test")
        except PepaSensoryArmError:
            pass  # Should catch successfully
        else:
            pytest.fail("TokenLimitExceeded not caught as PepaSensoryArmError")

    def test_token_limit_exceeded_with_counts(self):
        """Test TokenLimitExceeded with token count details."""
        token_count = 10000
        max_tokens = 8000
        message = (
            f"Context size {token_count} exceeds limit {max_tokens}. "
            "Consider reducing history or entity count."
        )

        with pytest.raises(TokenLimitExceeded) as exc_info:
            raise TokenLimitExceeded(message)

        assert str(token_count) in str(exc_info.value)
        assert str(max_tokens) in str(exc_info.value)


class TestRateLimitExceeded:
    """Tests for RateLimitExceeded exception."""

    def test_raise_rate_limit_exceeded(self):
        """Test that RateLimitExceeded can be raised."""
        with pytest.raises(RateLimitExceeded):
            raise RateLimitExceeded("Rate limit exceeded")

    def test_rate_limit_exceeded_message(self):
        """Test that RateLimitExceeded preserves message."""
        message = "Rate limit exceeded for OpenAI. Retry after 60 seconds."
        with pytest.raises(RateLimitExceeded) as exc_info:
            raise RateLimitExceeded(message)

        assert str(exc_info.value) == message

    def test_rate_limit_exceeded_inherits_from_pepa_sensory_arm_error(self):
        """Test that RateLimitExceeded inherits from PepaSensoryArmError."""
        assert issubclass(RateLimitExceeded, PepaSensoryArmError)

    def test_catch_rate_limit_exceeded_as_pepa_sensory_arm_error(self):
        """Test catching RateLimitExceeded as PepaSensoryArmError."""
        try:
            raise RateLimitExceeded("Test")
        except PepaSensoryArmError:
            pass  # Should catch successfully
        else:
            pytest.fail("RateLimitExceeded not caught as PepaSensoryArmError")

    def test_rate_limit_exceeded_with_retry_info(self):
        """Test RateLimitExceeded with retry information."""
        provider = "OpenAI"
        retry_after = 60
        message = f"Rate limit exceeded for {provider}. " f"Retry after {retry_after} seconds."

        with pytest.raises(RateLimitExceeded) as exc_info:
            raise RateLimitExceeded(message)

        assert provider in str(exc_info.value)
        assert str(retry_after) in str(exc_info.value)


class TestPermissionDenied:
    """Tests for PermissionDenied exception."""

    def test_raise_permission_denied(self):
        """Test that PermissionDenied can be raised."""
        with pytest.raises(PermissionDenied):
            raise PermissionDenied("Permission denied")

    def test_permission_denied_message(self):
        """Test that PermissionDenied preserves message."""
        message = "Entity light.bedroom is not accessible"
        with pytest.raises(PermissionDenied) as exc_info:
            raise PermissionDenied(message)

        assert str(exc_info.value) == message

    def test_permission_denied_inherits_from_pepa_sensory_arm_error(self):
        """Test that PermissionDenied inherits from PepaSensoryArmError."""
        assert issubclass(PermissionDenied, PepaSensoryArmError)

    def test_catch_permission_denied_as_pepa_sensory_arm_error(self):
        """Test catching PermissionDenied as PepaSensoryArmError."""
        try:
            raise PermissionDenied("Test")
        except PepaSensoryArmError:
            pass  # Should catch successfully
        else:
            pytest.fail("PermissionDenied not caught as PepaSensoryArmError")

    def test_permission_denied_with_entity_info(self):
        """Test PermissionDenied with entity details."""
        entity_id = "switch.garage_door"
        message = (
            f"Entity {entity_id} is not accessible. "
            "Ensure it is exposed in the integration configuration."
        )

        with pytest.raises(PermissionDenied) as exc_info:
            raise PermissionDenied(message)

        assert entity_id in str(exc_info.value)


class TestValidationError:
    """Tests for ValidationError exception."""

    def test_raise_validation_error(self):
        """Test that ValidationError can be raised."""
        with pytest.raises(ValidationError):
            raise ValidationError("Validation failed")

    def test_validation_error_message(self):
        """Test that ValidationError preserves message."""
        message = "Invalid entity_id format: invalid_entity"
        with pytest.raises(ValidationError) as exc_info:
            raise ValidationError(message)

        assert str(exc_info.value) == message

    def test_validation_error_inherits_from_pepa_sensory_arm_error(self):
        """Test that ValidationError inherits from PepaSensoryArmError."""
        assert issubclass(ValidationError, PepaSensoryArmError)

    def test_catch_validation_error_as_pepa_sensory_arm_error(self):
        """Test catching ValidationError as PepaSensoryArmError."""
        try:
            raise ValidationError("Test")
        except PepaSensoryArmError:
            pass  # Should catch successfully
        else:
            pytest.fail("ValidationError not caught as PepaSensoryArmError")

    def test_validation_error_with_format_details(self):
        """Test ValidationError with format details."""
        entity_id = "invalid_entity"
        message = f"Invalid entity_id format: {entity_id}. " "Expected format: domain.entity_name"

        with pytest.raises(ValidationError) as exc_info:
            raise ValidationError(message)

        assert entity_id in str(exc_info.value)
        assert "domain.entity_name" in str(exc_info.value)


class TestExceptionHierarchy:
    """Tests for exception hierarchy and catching behavior."""

    def test_catch_all_exceptions_with_pepa_sensory_arm_error(self):
        """Test that all custom exceptions can be caught as PepaSensoryArmError."""
        exceptions = [
            ContextInjectionError("test"),
            ToolExecutionError("test"),
            AuthenticationError("test"),
            TokenLimitExceeded("test"),
            RateLimitExceeded("test"),
            PermissionDenied("test"),
            ValidationError("test"),
        ]

        for exc in exceptions:
            try:
                raise exc
            except PepaSensoryArmError:
                pass  # Should catch successfully
            else:
                pytest.fail(f"{exc.__class__.__name__} not caught as PepaSensoryArmError")

    def test_exception_type_specificity(self):
        """Test that specific exception types can be caught separately."""
        # Raise ValidationError and catch it specifically
        try:
            raise ValidationError("test")
        except ValidationError as error:
            assert isinstance(error, ValidationError)
            assert isinstance(error, PepaSensoryArmError)
        except PepaSensoryArmError:
            pytest.fail("ValidationError should be caught before PepaSensoryArmError")

    def test_multiple_exception_handlers(self):
        """Test multiple exception handlers in order."""
        caught_exception_type = None

        try:
            raise ToolExecutionError("test")
        except ValidationError:
            caught_exception_type = "ValidationError"
        except ToolExecutionError:
            caught_exception_type = "ToolExecutionError"
        except PepaSensoryArmError:
            caught_exception_type = "PepaSensoryArmError"

        assert caught_exception_type == "ToolExecutionError"

    def test_reraise_exception(self):
        """Test re-raising exceptions."""
        with pytest.raises(ContextInjectionError):
            try:
                raise ContextInjectionError("original error")
            except ContextInjectionError:
                raise  # Re-raise the same exception

    def test_exception_chaining(self):
        """Test exception chaining with 'from' clause."""
        with pytest.raises(ToolExecutionError) as exc_info:
            try:
                raise ValueError("original error")
            except ValueError as error:
                raise ToolExecutionError("wrapped error") from error

        # Check that the exception chain is preserved
        assert exc_info.value.__cause__ is not None
        assert isinstance(exc_info.value.__cause__, ValueError)


class TestExceptionWithAttributes:
    """Tests for exceptions with additional attributes."""

    def test_exception_with_custom_attributes(self):
        """Test adding custom attributes to exceptions."""
        error = ToolExecutionError("Tool failed")
        error.tool_name = "ha_control"
        error.entity_id = "light.living_room"

        try:
            raise error
        except ToolExecutionError as exc:
            assert hasattr(exc, "tool_name")
            assert hasattr(exc, "entity_id")
            assert exc.tool_name == "ha_control"
            assert exc.entity_id == "light.living_room"

    def test_exception_string_representation(self):
        """Test string representation of exceptions."""
        message = "This is the error message"
        error = PepaSensoryArmError(message)

        assert str(error) == message
        assert message in repr(error)
