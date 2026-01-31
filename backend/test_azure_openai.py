#!/usr/bin/env python3
"""
Test Azure OpenAI connection and embedding generation
"""

import os

# Azure OpenAI Configuration from environment variables
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "https://secondbrain-resource.cognitiveservices.azure.com")
AZURE_API_VERSION = os.getenv("AZURE_API_VERSION", "2024-12-01-preview")
AZURE_EMBEDDING_DEPLOYMENT = os.getenv("AZURE_EMBEDDING_DEPLOYMENT", "text-embedding-3-large")

if not AZURE_OPENAI_API_KEY:
    print("❌ ERROR: AZURE_OPENAI_API_KEY environment variable not set")
    print("\nSet it with:")
    print("  export AZURE_OPENAI_API_KEY='your-key-here'")
    exit(1)

print("=" * 60)
print("AZURE OPENAI CONNECTION TEST")
print("=" * 60)

print(f"\n📋 Configuration:")
print(f"  Endpoint: {AZURE_OPENAI_ENDPOINT}")
print(f"  API Version: {AZURE_API_VERSION}")
print(f"  Embedding Deployment: {AZURE_EMBEDDING_DEPLOYMENT}")
print(f"  API Key: {AZURE_OPENAI_API_KEY[:20]}...{AZURE_OPENAI_API_KEY[-10:]}")

try:
    from openai import AzureOpenAI

    print(f"\n✓ OpenAI library imported")

    # Initialize Azure OpenAI client
    print(f"\n🔗 Connecting to Azure OpenAI...")
    client = AzureOpenAI(
        api_key=AZURE_OPENAI_API_KEY,
        api_version=AZURE_API_VERSION,
        azure_endpoint=AZURE_OPENAI_ENDPOINT
    )

    print(f"✓ Client initialized")

    # Test embedding generation
    print(f"\n🧪 Testing embedding generation...")
    test_text = "This is a test document for embedding generation."

    response = client.embeddings.create(
        model=AZURE_EMBEDDING_DEPLOYMENT,
        input=test_text,
        dimensions=1536  # Match your existing Pinecone index
    )

    embedding = response.data[0].embedding

    print(f"✓ Embedding generated successfully!")
    print(f"  Length: {len(embedding)} dimensions")
    print(f"  Sample values: [{embedding[0]:.4f}, {embedding[1]:.4f}, {embedding[2]:.4f}, ...]")
    print(f"  Token usage: {response.usage.total_tokens}")

    print("\n✅ CONNECTION SUCCESSFUL")
    print("=" * 60)
    print("\n✓ Your Azure OpenAI credentials are working correctly!")
    print("✓ The issue must be elsewhere...")

except Exception as e:
    print(f"\n❌ ERROR: {e}")
    print(f"\n  Error type: {type(e).__name__}")

    error_str = str(e)

    if "401" in error_str or "Unauthorized" in error_str:
        print("\n🔴 401 UNAUTHORIZED ERROR")
        print("\n  Possible causes:")
        print("  1. API key is wrong or expired")
        print("  2. API key doesn't have access to this resource")
        print("  3. Endpoint URL is incorrect")
        print("\n  Solutions:")
        print("  1. Go to Azure Portal: https://portal.azure.com")
        print("  2. Navigate to your Azure OpenAI resource: 'secondbrain-resource'")
        print("  3. Click 'Keys and Endpoint' in the left menu")
        print("  4. Copy KEY 1 or KEY 2")
        print("  5. Verify the endpoint matches")
        print("  6. Update AZURE_OPENAI_API_KEY on Render")

    elif "404" in error_str or "NotFound" in error_str:
        print("\n🔴 404 NOT FOUND ERROR")
        print("\n  Possible causes:")
        print("  1. Deployment name is wrong")
        print("  2. Deployment doesn't exist")
        print("\n  Solutions:")
        print("  1. Go to Azure OpenAI Studio: https://oai.azure.com")
        print("  2. Select your resource: 'secondbrain-resource'")
        print("  3. Go to 'Deployments' page")
        print("  4. Check the exact name of your embedding deployment")
        print(f"  5. Current value: '{AZURE_EMBEDDING_DEPLOYMENT}'")
        print("  6. Update AZURE_EMBEDDING_DEPLOYMENT on Render if needed")

    else:
        print("\n📝 Debug information:")
        import traceback
        traceback.print_exc()

print("\n" + "=" * 60)
