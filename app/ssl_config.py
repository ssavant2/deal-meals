"""
SSL/TLS Configuration Manager.

Handles certificate storage, validation, and uvicorn SSL setup.
Certificates are stored in /certs/ volume (mounted from host).

Usage:
    from ssl_config import ssl_manager

    # Check if SSL is configured and valid
    if ssl_manager.is_ssl_ready():
        ssl_args = ssl_manager.get_uvicorn_ssl_args()
"""

import os
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Dict, Tuple
from loguru import logger

# Try to import cryptography for cert validation
try:
    from cryptography import x509
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.backends import default_backend
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False
    logger.warning("cryptography not installed - cert validation limited")


class SSLConfigManager:
    """Manages SSL/TLS certificates and configuration."""

    # Default paths
    CERTS_DIR = Path("/certs")
    CERT_FILE = "cert.pem"
    KEY_FILE = "key.pem"
    CONFIG_FILE = "ssl_config.json"

    def __init__(self):
        self.certs_dir = self.CERTS_DIR
        self._ensure_certs_dir()

    def _ensure_certs_dir(self):
        """Create certs directory if it doesn't exist."""
        try:
            self.certs_dir.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            logger.warning(f"Cannot create {self.certs_dir} - running without SSL support")

    @property
    def cert_path(self) -> Path:
        return self.certs_dir / self.CERT_FILE

    @property
    def key_path(self) -> Path:
        return self.certs_dir / self.KEY_FILE

    @property
    def config_path(self) -> Path:
        return self.certs_dir / self.CONFIG_FILE

    def _load_config(self) -> Dict:
        """Load SSL config from JSON file."""
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load SSL config: {e}")
        return {"enabled": False}

    def _save_config(self, config: Dict):
        """Save SSL config to JSON file."""
        try:
            with open(self.config_path, 'w') as f:
                json.dump(config, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save SSL config: {e}")
            raise

    def is_ssl_enabled(self) -> bool:
        """Check if SSL is enabled in config."""
        # Check for FORCE_HTTP override first
        if os.environ.get("FORCE_HTTP", "").lower() in ("true", "1", "yes"):
            return False
        return self._load_config().get("enabled", False)

    def has_certificates(self) -> bool:
        """Check if both cert and key files exist."""
        return self.cert_path.exists() and self.key_path.exists()

    def is_ssl_ready(self) -> bool:
        """Check if SSL is enabled AND certificates are present."""
        return self.is_ssl_enabled() and self.has_certificates()

    def get_uvicorn_ssl_args(self) -> Dict:
        """Get SSL arguments for uvicorn.run() if SSL is ready."""
        if self.is_ssl_ready():
            return {
                "ssl_keyfile": str(self.key_path),
                "ssl_certfile": str(self.cert_path)
            }
        return {}

    def validate_cert_key_pair(self, cert_data: bytes, key_data: bytes) -> Tuple[bool, str]:
        """
        Validate that certificate and private key match.

        Returns:
            (success, message) tuple
        """
        if not CRYPTO_AVAILABLE:
            # Basic check: just verify they look like PEM files
            cert_str = cert_data.decode('utf-8', errors='ignore')
            key_str = key_data.decode('utf-8', errors='ignore')

            if "-----BEGIN CERTIFICATE-----" not in cert_str:
                return False, "ssl.cert_invalid_format"
            if "-----BEGIN" not in key_str or "PRIVATE KEY" not in key_str:
                return False, "ssl.key_invalid_format"

            return True, "ssl.cert_key_ok"

        try:
            # Parse certificate
            cert = x509.load_pem_x509_certificate(cert_data, default_backend())

            # Parse private key
            private_key = serialization.load_pem_private_key(
                key_data, password=None, backend=default_backend()
            )

            # Get public keys from both
            cert_public_key = cert.public_key()
            key_public_key = private_key.public_key()

            # Compare public key bytes
            cert_pub_bytes = cert_public_key.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            )
            key_pub_bytes = key_public_key.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            )

            if cert_pub_bytes != key_pub_bytes:
                return False, "ssl.cert_key_mismatch"

            return True, "ssl.cert_key_valid"

        except Exception as e:
            return False, f"Validation error: {str(e)}"

    def get_cert_info(self) -> Optional[Dict]:
        """
        Get information about the current certificate.

        Returns:
            Dict with cert info, or None if no cert exists
        """
        if not self.cert_path.exists():
            return None

        try:
            with open(self.cert_path, 'rb') as f:
                cert_data = f.read()

            if not CRYPTO_AVAILABLE:
                return {
                    "exists": True,
                    "details_available": False,
                    "message": "Install cryptography package for certificate details"
                }

            cert = x509.load_pem_x509_certificate(cert_data, default_backend())

            # Extract subject info
            subject_parts = []
            for attr in cert.subject:
                subject_parts.append(f"{attr.oid._name}={attr.value}")

            # Check if expired
            # cryptography >= 42 uses not_valid_after_utc (timezone-aware)
            # older versions use not_valid_after (timezone-naive, assumed UTC)
            try:
                not_valid_after = cert.not_valid_after_utc
                not_valid_before = cert.not_valid_before_utc
            except AttributeError:
                not_valid_after = cert.not_valid_after.replace(tzinfo=timezone.utc)
                not_valid_before = cert.not_valid_before.replace(tzinfo=timezone.utc)

            now = datetime.now(timezone.utc)
            is_expired = not_valid_after < now
            days_until_expiry = (not_valid_after - now).days

            return {
                "exists": True,
                "details_available": True,
                "subject": ", ".join(subject_parts),
                "issuer": ", ".join([f"{attr.oid._name}={attr.value}" for attr in cert.issuer]),
                "not_valid_before": not_valid_before.isoformat(),
                "not_valid_after": not_valid_after.isoformat(),
                "is_expired": is_expired,
                "days_until_expiry": days_until_expiry,
                "serial_number": str(cert.serial_number)
            }

        except Exception as e:
            logger.error(f"Failed to read certificate info: {e}")
            return {
                "exists": True,
                "details_available": False,
                "error": str(e)
            }

    def save_certificates(self, cert_data: bytes, key_data: bytes) -> Tuple[bool, str]:
        """
        Save certificate and key after validation.

        Returns:
            (success, message) tuple
        """
        # Validate first
        valid, message = self.validate_cert_key_pair(cert_data, key_data)
        if not valid:
            return False, message

        try:
            # Write certificate
            with open(self.cert_path, 'wb') as f:
                f.write(cert_data)

            # Write key with restricted permissions
            with open(self.key_path, 'wb') as f:
                f.write(key_data)

            # Set restrictive permissions on key file
            os.chmod(self.key_path, 0o600)

            logger.info("SSL certificates saved successfully")
            return True, "ssl.cert_saved"

        except Exception as e:
            logger.error(f"Failed to save certificates: {e}")
            return False, f"Failed to save certificates: {str(e)}"

    def delete_certificates(self) -> Tuple[bool, str]:
        """
        Delete existing certificates and disable SSL.

        Returns:
            (success, message) tuple
        """
        try:
            if self.cert_path.exists():
                self.cert_path.unlink()
            if self.key_path.exists():
                self.key_path.unlink()

            # Disable SSL in config
            config = self._load_config()
            config["enabled"] = False
            self._save_config(config)

            logger.info("SSL certificates deleted")
            return True, "ssl.cert_deleted"

        except Exception as e:
            logger.error(f"Failed to delete certificates: {e}")
            return False, f"Failed to delete certificates: {str(e)}"

    def set_ssl_enabled(self, enabled: bool) -> Tuple[bool, str]:
        """
        Enable or disable SSL.

        Returns:
            (success, message) tuple
        """
        if enabled and not self.has_certificates():
            return False, "ssl.no_cert"

        try:
            config = self._load_config()
            config["enabled"] = enabled
            self._save_config(config)

            status = "enabled" if enabled else "disabled"
            logger.info(f"SSL {status}")
            return True, "ssl.enabled" if enabled else "ssl.disabled"

        except Exception as e:
            return False, f"Failed to update SSL config: {str(e)}"

    def get_status(self) -> Dict:
        """
        Get complete SSL status for API/GUI.

        Returns:
            Dict with all SSL status information
        """
        config = self._load_config()
        cert_info = self.get_cert_info()
        force_http = os.environ.get("FORCE_HTTP", "").lower() in ("true", "1", "yes")

        return {
            "ssl_enabled": config.get("enabled", False),
            "force_http_override": force_http,
            "effective_ssl": self.is_ssl_ready() and not force_http,
            "has_certificates": self.has_certificates(),
            "certificate": cert_info,
            "certs_dir": str(self.certs_dir),
            "crypto_available": CRYPTO_AVAILABLE
        }


# Global instance
ssl_manager = SSLConfigManager()
