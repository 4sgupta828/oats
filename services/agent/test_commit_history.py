"""Test script for commit history functionality"""

from providers.code.github_provider import GitHubCodeProvider
from providers.base_provider import ProviderResult


def test_github_commits():
    """Test GitHub commit history retrieval"""

    # Initialize provider with test config
    # Note: This will be disabled if no valid token is provided
    config = {
        'token': 'ghp_test_token',  # Replace with real token to test
        'org': None,
        'repos': []
    }

    provider = GitHubCodeProvider(config)

    # Test 1: Verify method exists
    assert hasattr(provider, 'get_commits'), "Provider should have get_commits method"
    print("✓ Test 1: get_commits method exists")

    # Test 2: Check method signature
    import inspect
    sig = inspect.signature(provider.get_commits)
    params = list(sig.parameters.keys())
    expected_params = ['repo', 'branch', 'limit', 'since', 'author', 'path', 'include_diffs']
    assert all(p in params for p in expected_params), f"Missing parameters. Expected: {expected_params}, Got: {params}"
    print("✓ Test 2: get_commits has correct parameters")

    # Test 3: Try calling with no client (should return error result)
    if not provider.client:
        result = provider.get_commits(repo="test/repo")
        assert isinstance(result, ProviderResult), "Should return ProviderResult"
        assert not result.success, "Should fail when client not initialized"
        assert "not initialized" in result.error.lower(), f"Error should mention initialization: {result.error}"
        print("✓ Test 3: Handles missing client gracefully")
    else:
        print("⊘ Test 3: Skipped (client is initialized)")

    print("\n✓ All tests passed!")
    print("\nTo test with real GitHub data:")
    print("1. Set a valid GitHub token in the config")
    print("2. Call provider.get_commits(repo='owner/repo', since='24h')")
    print("\nExample usage:")
    print("  result = provider.get_commits(")
    print("      repo='torvalds/linux',")
    print("      branch='master',")
    print("      limit=5,")
    print("      since='24h',")
    print("      include_diffs=True")
    print("  )")


if __name__ == "__main__":
    test_github_commits()
