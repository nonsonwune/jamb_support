#!/bin/bash

# Set up environment variables for gRPC
export GRPC_PYTHON_BUILD_SYSTEM_OPENSSL=1
export GRPC_PYTHON_BUILD_SYSTEM_ZLIB=1

# Load API keys from .env file
set -a
source .env
set +a

# Verify that at least one API key is set
api_key_count=0
for i in {1..10}; do
    key_var="GEMINI_API_KEY_$i"
    if [ -n "${!key_var}" ]; then
        ((api_key_count++))
    fi
done

if [ $api_key_count -eq 0 ]; then
    echo "Error: No Gemini API keys found in .env file"
    exit 1
else
    echo "Loaded $api_key_count Gemini API key(s)"
fi

echo "Environment variables set up successfully."