#!/usr/bin/env python3
"""
Generate production .env file with secure passwords and keys.
"""
import secrets
import string
import os
from pathlib import Path


def generate_password(length=32, include_special=False):
    """Generate a secure random password (alphanumeric only by default)."""
    alphabet = string.ascii_letters + string.digits
    
    # Ensure at least one of each type
    password = [
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.digits),
    ]
    
    # Fill the rest randomly
    password.extend(secrets.choice(alphabet) for _ in range(length - len(password)))
    
    # Shuffle
    secrets.SystemRandom().shuffle(password)
    
    return ''.join(password)


def generate_secret_key(length=64):
    """Generate a secret key for Flask/Django-like applications."""
    return secrets.token_urlsafe(length)


def escape_for_env(value):
    """Escape special characters for .env file."""
    # If value contains spaces or special chars, wrap in quotes
    if any(c in value for c in [' ', '$', '"', "'", '\\']):
        return f'"{value.replace('"', '\\"')}"'
    return value


def main():
    """Generate production .env file."""
    script_dir = Path(__file__).parent
    env_file = script_dir / ".env"
    env_example = script_dir / ".env.example"
    
    print("Generating production passwords and secrets...")
    
    # Generate secure passwords and keys (alphanumeric only)
    postgres_password = generate_password(32, include_special=False)
    redis_password = generate_password(24, include_special=False)
    minio_access_key = generate_password(20, include_special=False)
    minio_secret_key = generate_password(40, include_special=False)
    secret_key = generate_secret_key(64)
    
    # Read template from .env.example if exists
    template_lines = []
    if env_example.exists():
        with open(env_example, 'r') as f:
            template_lines = f.readlines()
    else:
        # Create default template
        template_lines = [
            "# OpenAI Configuration\n",
            "OPENAI_API_KEY=your_openai_api_key_here\n",
            "\n",
            "# Database Configuration\n",
            "POSTGRES_HOST=postgres\n",
            "POSTGRES_PORT=5432\n",
            "POSTGRES_DB=court_registry\n",
            "POSTGRES_USER=court_user\n",
            "POSTGRES_PASSWORD=your_postgres_password_here\n",
            "\n",
            "# Redis Configuration\n",
            "REDIS_HOST=redis\n",
            "REDIS_PORT=6379\n",
            "REDIS_PASSWORD=your_redis_password_here\n",
            "REDIS_DB=0\n",
            "\n",
            "# MCP Server Configuration\n",
            "MCP_SERVER_PORT=8000\n",
            "MCP_SERVER_HOST=0.0.0.0\n",
            "\n",
            "# Court Registry Source\n",
            "COURT_REGISTRY_BASE_URL=https://reyestr.court.gov.ua\n",
            "COURT_REGISTRY_SEARCH_ENDPOINT=/Search\n",
            "COURT_REGISTRY_RSS_ENDPOINT=/RSS\n",
            "\n",
            "# Fetcher Configuration\n",
            "FETCHER_WORKERS=10\n",
            "FETCHER_MAX_RETRIES=3\n",
            "FETCHER_TIMEOUT=30\n",
            "\n",
            "# Parser Configuration\n",
            "PARSER_VERSION=1.0.0\n",
            "PARSER_CONFIDENCE_THRESHOLD=0.7\n",
            "\n",
            "# Embedding Configuration\n",
            "EMBEDDING_MODEL=text-embedding-3-small\n",
            "EMBEDDING_BATCH_SIZE=100\n",
            "EMBEDDING_CHUNK_SIZE=512\n",
            "\n",
            "# Storage Configuration (MinIO)\n",
            "STORAGE_TYPE=minio\n",
            "STORAGE_PATH=/app/storage\n",
            "MINIO_ENDPOINT=localhost:9000\n",
            "MINIO_ACCESS_KEY=your_minio_access_key_here\n",
            "MINIO_SECRET_KEY=your_minio_secret_key_here\n",
            "MINIO_BUCKET_NAME=court-registry\n",
            "MINIO_USE_SSL=false\n",
            "MINIO_REGION=us-east-1\n",
            "\n",
            "# Monitoring Configuration\n",
            "DISCOVERY_INTERVAL_MINUTES=10\n",
            "RECONCILIATION_INTERVAL_HOURS=24\n",
            "\n",
            "# Logging\n",
            "LOG_LEVEL=INFO\n",
            "LOG_FORMAT=json\n",
            "\n",
            "# Security\n",
            "SECRET_KEY=your_secret_key_here_change_in_production\n",
            "ALLOWED_ORIGINS=http://localhost:3000,http://localhost:8000\n",
        ]
    
    # Process template and replace passwords
    output_lines = []
    for line in template_lines:
        stripped = line.strip()
        
        # Replace passwords and secrets
        if stripped.startswith("POSTGRES_PASSWORD="):
            output_lines.append(f"POSTGRES_PASSWORD={escape_for_env(postgres_password)}\n")
        elif stripped.startswith("REDIS_PASSWORD="):
            output_lines.append(f"REDIS_PASSWORD={escape_for_env(redis_password)}\n")
        elif stripped.startswith("MINIO_ACCESS_KEY="):
            output_lines.append(f"MINIO_ACCESS_KEY={escape_for_env(minio_access_key)}\n")
        elif stripped.startswith("MINIO_SECRET_KEY="):
            output_lines.append(f"MINIO_SECRET_KEY={escape_for_env(minio_secret_key)}\n")
        elif stripped.startswith("SECRET_KEY="):
            output_lines.append(f"SECRET_KEY={escape_for_env(secret_key)}\n")
        elif stripped.startswith("POSTGRES_HOST=") and "localhost" in stripped:
            # Use postgres for Docker Compose
            output_lines.append("POSTGRES_HOST=postgres\n")
        elif stripped.startswith("REDIS_HOST=") and "localhost" in stripped:
            # Use redis for Docker Compose
            output_lines.append("REDIS_HOST=redis\n")
        elif stripped.startswith("MINIO_ENDPOINT=") and "localhost" in stripped:
            # Keep localhost for Docker Compose (MinIO runs in same container)
            output_lines.append("MINIO_ENDPOINT=localhost:9000\n")
        elif stripped.startswith("ALLOWED_ORIGINS=") and "localhost" in stripped:
            # Keep localhost for development, but add production note
            output_lines.append("# ALLOWED_ORIGINS=http://localhost:3000,http://localhost:8000\n")
            output_lines.append("# TODO: Update ALLOWED_ORIGINS with your production domains\n")
            output_lines.append("ALLOWED_ORIGINS=http://localhost:3000,http://localhost:8000\n")
        elif stripped.startswith("OPENAI_API_KEY=") and "your_" in stripped:
            output_lines.append("# TODO: Set your OpenAI API key\n")
            output_lines.append("OPENAI_API_KEY=your_openai_api_key_here\n")
        elif stripped.startswith("STORAGE_TYPE=") and "local" in stripped:
            # Set to minio by default
            output_lines.append("STORAGE_TYPE=minio\n")
        else:
            output_lines.append(line)
    
    # Write .env file
    with open(env_file, 'w') as f:
        f.writelines(output_lines)
    
    # Set secure permissions (readable only by owner)
    os.chmod(env_file, 0o600)
    
    print(f"Generated .env file at {env_file}")
    print(f"File permissions set to 600 (readable only by owner)")
    print("\nGenerated credentials:")
    print(f"   POSTGRES_PASSWORD: {postgres_password[:8]}... (32 chars)")
    print(f"   REDIS_PASSWORD: {redis_password[:8]}... (24 chars)")
    print(f"   MINIO_ACCESS_KEY: {minio_access_key[:8]}... (20 chars)")
    print(f"   MINIO_SECRET_KEY: {minio_secret_key[:8]}... (40 chars)")
    print(f"   SECRET_KEY: {secret_key[:16]}... (64 chars)")
    print("\nIMPORTANT:")
    print("   1. Set your OPENAI_API_KEY in .env file")
    print("   2. Update ALLOWED_ORIGINS with your production domains")
    print("   3. Keep .env file secure and never commit it to git")
    print("   4. Backup these passwords in a secure password manager")


if __name__ == "__main__":
    main()
