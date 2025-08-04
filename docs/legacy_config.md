# Legacy JSON Configuration Guide

> **⚠️ DEPRECATED:** This JSON configuration format is deprecated and maintained for legacy compatibility only. For new installations, please use the [YAML configuration format](../README.md#configuration) instead.

## JSON Configuration Setup

**Configuration Setup:**

1. **Copy the example configuration file:**

   ```bash
   cp trae_config.json.example trae_config.json
   ```

2. **Edit `trae_config.json` and replace the placeholder values with your actual credentials:**
   - Replace `"your_openai_api_key"` with your actual OpenAI API key
   - Replace `"your_anthropic_api_key"` with your actual Anthropic API key
   - Replace `"your_google_api_key"` with your actual Google API key
   - Replace `"your_azure_base_url"` with your actual Azure base URL
   - Replace other placeholder URLs and API keys as needed

**Note:** The `trae_config.json` file is ignored by git to prevent accidentally committing your API keys.

## JSON Configuration Structure

Trae Agent uses a JSON configuration file for settings. Please refer to the `trae_config.json.example` file in the root directory for the detailed configuration structure.

**Configuration Priority:**

1. Command-line arguments (highest)
2. Configuration file values
3. Environment variables
4. Default values (lowest)

## Example JSON Configuration

The JSON configuration file contains provider-specific settings for various LLM services:

```json
{
  "default_provider": "anthropic",
  "max_steps": 20,
  "enable_lakeview": true,
  "model_providers": {
    "openai": {
      "api_key": "your_openai_api_key",
      "base_url": "https://api.openai.com/v1",
      "model": "gpt-4o",
      "max_tokens": 128000,
      "temperature": 0.5,
      "top_p": 1,
      "max_retries": 10
    },
    "anthropic": {
      "api_key": "your_anthropic_api_key",
      "base_url": "https://api.anthropic.com",
      "model": "claude-sonnet-4-20250514",
      "max_tokens": 4096,
      "temperature": 0.5,
      "top_p": 1,
      "top_k": 0,
      "max_retries": 10
    }
  }
}
```

## Migration to YAML

To migrate from JSON to YAML configuration:

1. **Create a new YAML configuration file:**
   ```bash
   cp trae_config.yaml.example trae_config.yaml
   ```

2. **Transfer your settings** from `trae_config.json` to `trae_config.yaml` following the new structure

3. **Remove the old JSON file** (optional but recommended):
   ```bash
   rm trae_config.json
   ```

For detailed YAML configuration instructions, please refer to the main [README.md](../README.md#configuration).
