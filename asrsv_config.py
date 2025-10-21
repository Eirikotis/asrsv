# asrsv_config.py
# Configuration using environment variables for security
import os

# API Keys from environment variables
BIRDEYE_API_KEY = os.getenv("BIRDEYE_API_KEY", "7a6cd7e4f6504a6e927b1d0a0a3a9d2d")
HELIUS_API_KEY = os.getenv("HELIUS_API_KEY", "03260779-c896-4ebf-8a72-390245121ad8")

# Asset configuration
ASSET_MINT = "assetSHnT4AzwSGDx6wqv7CWacqjg1LEXnbir3FnSSa"
RESERVE_WALLETS = [
    "BtzoeQZAPUr6MLmE947Bxu7PpuJRehaTVadgK2yPVKC6",
    "GyfVNzAvC8FAHRxPtZjm5xhi6mM8PNy2xCe7nNCWnMnk",
]
