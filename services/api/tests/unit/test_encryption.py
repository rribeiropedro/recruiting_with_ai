"""Unit tests for OAuth token encryption helpers (app/utils/encryption.py)."""
from unittest.mock import patch

from cryptography.fernet import Fernet


class TestEncryptOAuthToken:
    def test_roundtrip_returns_original_data(self):
        from app.utils.encryption import decrypt_oauth_token, encrypt_oauth_token

        data = {"access_token": "tok123", "refresh_token": "ref456"}
        assert decrypt_oauth_token(encrypt_oauth_token(data)) == data

    def test_complex_payload_roundtrip(self):
        from app.utils.encryption import decrypt_oauth_token, encrypt_oauth_token

        data = {
            "access_token": "ya29.very-long-access-token",
            "refresh_token": "1//0erefresh",
            "token_type": "Bearer",
            "expiry": "2025-01-01T00:00:00Z",
        }
        assert decrypt_oauth_token(encrypt_oauth_token(data)) == data

    def test_encrypted_value_is_string(self):
        from app.utils.encryption import encrypt_oauth_token

        result = encrypt_oauth_token({"access_token": "tok"})
        assert isinstance(result, str)

    def test_each_call_produces_unique_ciphertext(self):
        """Fernet uses a random IV, so two encryptions of the same data differ."""
        from app.utils.encryption import encrypt_oauth_token

        data = {"access_token": "tok"}
        assert encrypt_oauth_token(data) != encrypt_oauth_token(data)

    def test_encrypted_output_is_not_plaintext(self):
        from app.utils.encryption import encrypt_oauth_token

        data = {"access_token": "supersecret"}
        encrypted = encrypt_oauth_token(data)
        assert "supersecret" not in encrypted


class TestDecryptOAuthToken:
    def test_none_input_returns_none(self):
        from app.utils.encryption import decrypt_oauth_token

        assert decrypt_oauth_token(None) is None

    def test_empty_string_returns_none(self):
        from app.utils.encryption import decrypt_oauth_token

        assert decrypt_oauth_token("") is None

    def test_random_string_returns_none(self):
        from app.utils.encryption import decrypt_oauth_token

        assert decrypt_oauth_token("not-fernet-data-at-all") is None

    def test_tampered_ciphertext_returns_none(self):
        from app.utils.encryption import decrypt_oauth_token, encrypt_oauth_token

        encrypted = encrypt_oauth_token({"access_token": "tok"})
        tampered = encrypted[:-4] + "XXXX"
        assert decrypt_oauth_token(tampered) is None

    def test_wrong_key_returns_none(self):
        from app.utils.encryption import decrypt_oauth_token, encrypt_oauth_token

        data = {"access_token": "tok123"}
        encrypted = encrypt_oauth_token(data)

        wrong_key = Fernet.generate_key().decode()
        with patch("app.utils.encryption.settings") as mock_settings:
            mock_settings.ENCRYPTION_KEY = wrong_key
            result = decrypt_oauth_token(encrypted)

        assert result is None
