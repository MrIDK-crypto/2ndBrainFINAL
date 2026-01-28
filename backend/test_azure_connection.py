"""
Test Azure OpenAI connection to diagnose 401 errors
"""
import os
from openai import AzureOpenAI

def test_azure_connection():
    print("=== Azure OpenAI Connection Test ===\n")

    # Get environment variables
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    api_key = os.getenv("AZURE_OPENAI_API_KEY")
    api_version = os.getenv("AZURE_API_VERSION", "2024-12-01-preview")
    chat_deployment = os.getenv("AZURE_CHAT_DEPLOYMENT")
    embedding_deployment = os.getenv("AZURE_EMBEDDING_DEPLOYMENT")

    print(f"Endpoint: {endpoint}")
    print(f"API Version: {api_version}")
    print(f"Chat Deployment: {chat_deployment}")
    print(f"Embedding Deployment: {embedding_deployment}")
    print(f"API Key (first 10 chars): {api_key[:10]}..." if api_key else "API Key: NOT SET")
    print()

    # Create client
    try:
        client = AzureOpenAI(
            api_key=api_key,
            api_version=api_version,
            azure_endpoint=endpoint
        )
        print("✓ Client created successfully")
    except Exception as e:
        print(f"✗ Failed to create client: {e}")
        return

    # Test 1: Chat completion
    print("\n--- Test 1: Chat Completion ---")
    try:
        response = client.chat.completions.create(
            model=chat_deployment,
            messages=[{"role": "user", "content": "Say 'test successful' if you can read this."}],
            max_tokens=10
        )
        print(f"✓ Chat completion successful: {response.choices[0].message.content}")
    except Exception as e:
        print(f"✗ Chat completion failed: {e}")

    # Test 2: Embeddings
    print("\n--- Test 2: Embeddings ---")
    try:
        response = client.embeddings.create(
            model=embedding_deployment,
            input="test embedding",
            dimensions=1536
        )
        print(f"✓ Embedding successful: {len(response.data[0].embedding)} dimensions")
    except Exception as e:
        print(f"✗ Embedding failed: {e}")

    print("\n=== Test Complete ===")

if __name__ == "__main__":
    test_azure_connection()
