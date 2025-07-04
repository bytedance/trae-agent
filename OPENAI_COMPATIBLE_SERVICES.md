# OpenAI-Compatible Services Support

Trae Agent now supports multiple OpenAI-compatible services, allowing you to use various LLM providers with the same interface. This document provides configuration examples and usage instructions for supported services.

## 🎁 Free Tier Highlights

### Alibaba Cloud DashScope - 1 Million Free Tokens! 🚀
Alibaba Cloud offers an exceptional free tier for developers:

- **1,000,000 tokens** total across 4 Qwen models
- **No time limit** - use at your own pace
- **4 powerful models** included:
  - `qwen-turbo` - Fast and efficient for most tasks
  - `qwen-plus` - Balanced performance and capability
  - `qwen-max` - Most capable model for complex tasks
  - `qwen-max-longcontext` - Extended context for long documents

**Perfect for:**
- Learning and experimentation
- Prototyping applications
- Development and testing
- Small to medium projects

**How to get started:**
1. Sign up at [Alibaba Cloud Model Studio](https://www.alibabacloud.com/help/en/model-studio/new-free-quota)
2. Get your API key from the console
3. Configure Trae Agent with the DashScope endpoint
4. Start using 1M tokens for free!

### Other Free Options
- **OpenRouter**: Various free models available
- **Groq**: 30 requests/minute free tier
- **Together AI**: 600 requests/minute free tier
- **Ollama**: Completely free (local usage)

## API Types Supported

### OpenAI-Compatible Services
These services use the standard OpenAI API format and require both `api_key` and `base_url`:
- **OpenRouter**: Multi-model access
- **Together AI**: Open-source models
- **Groq**: Ultra-fast inference  
- **DeepSeek**: Advanced reasoning

### Native API Services
These services use their own API format:
- **Ollama**: Uses native Ollama API (`/api/chat` endpoint)
  - No API key required
  - Different request/response format
  - Local deployment only

### Using Ollama with OpenAI-Compatible API
If you want to use Ollama with OpenAI-compatible format, you can:
1. Use **LiteLLM** as a proxy:
   ```bash
   pip install litellm
   litellm --model ollama/llama3.2 --port 8000
   ```
2. Then configure as `openai_compatible`:
   ```json
   {
     "openai_compatible": {
       "api_key": "any-key",
       "base_url": "http://localhost:8000/v1",
       "model": "ollama/llama3.2"
     }
   }
   ```

## Configuration Requirements

### Essential Parameters

All OpenAI-compatible services require these two essential parameters:

1. **`api_key`**: Your authentication key for the service
2. **`base_url`**: The API endpoint URL for the service

**Important**: The `base_url` parameter is mandatory for all OpenAI-compatible services. Without it, the client cannot determine which service to connect to.

### Common Endpoints

| Service | Base URL | Notes |
|---------|----------|-------|
| OpenRouter | `https://openrouter.ai/api/v1` | Standard OpenAI-compatible endpoint |
| Together AI | `https://api.together.xyz/v1` | Fast open-source models |
| Groq | `https://api.groq.com/openai/v1` | Ultra-fast inference |
| DeepSeek | `https://api.deepseek.com/v1` | Advanced reasoning models |
| Alibaba Cloud | `https://dashscope-intl.aliyuncs.com/compatible-mode/v1` | 1M free tokens, Qwen models |
| Novita AI | `https://api.novita.ai/v3/openai` | Competitive pricing, multiple models |
| Ollama | `http://localhost:11434` | Local deployment (native API, no /v1) |

### Custom Endpoints

Some services may have custom endpoints:
- **Enterprise deployments**: Custom domain URLs
- **Regional endpoints**: Different URLs for different regions
- **Development/staging**: Alternative URLs for testing

Example with custom endpoint:
```json
{
  "custom_service": {
    "api_key": "your-api-key",
    "base_url": "https://your-custom-endpoint.com/v1",
    "model": "your-model-name"
  }
}
```

## Supported Services

### 1. OpenRouter
**Description**: Access to multiple models through a single API
**Website**: https://openrouter.ai/
**Required**: API key and base_url

```json
{
  "default_provider": "openrouter",
  "model_providers": {
    "openrouter": {
      "api_key": "sk-or-v1-your-api-key",
      "base_url": "https://openrouter.ai/api/v1",
      "model": "anthropic/claude-3.5-sonnet",
      "max_tokens": 4096,
      "temperature": 0.5,
      "top_p": 1,
      "parallel_tool_calls": true,
      "max_retries": 10
    }
  }
}
```

**Popular Models**:
- `anthropic/claude-3.5-sonnet`
- `openai/gpt-4o`
- `meta-llama/llama-3.1-70b-instruct`
- `google/gemma-2-9b-it:free` (Free tier)

### 2. Together AI
**Description**: Fast inference for open-source models
**Website**: https://together.ai/
**Required**: API key and base_url

```json
{
  "default_provider": "together",
  "model_providers": {
    "together": {
      "api_key": "your-together-api-key",
      "base_url": "https://api.together.xyz/v1",
      "model": "meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo",
      "max_tokens": 4096,
      "temperature": 0.5,
      "top_p": 1,
      "parallel_tool_calls": true,
      "max_retries": 10
    }
  }
}
```

**Popular Models**:
- `meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo`
- `mistralai/Mixtral-8x7B-Instruct-v0.1`
- `NousResearch/Nous-Hermes-2-Mixtral-8x7B-DPO`

### 3. Groq
**Description**: Ultra-fast inference with specialized hardware
**Website**: https://groq.com/
**Required**: API key and base_url

```json
{
  "default_provider": "groq",
  "model_providers": {
    "groq": {
      "api_key": "gsk_your-groq-api-key",
      "base_url": "https://api.groq.com/openai/v1",
      "model": "llama-3.1-70b-versatile",
      "max_tokens": 4096,
      "temperature": 0.5,
      "top_p": 1,
      "parallel_tool_calls": true,
      "max_retries": 10
    }
  }
}
```

**Popular Models**:
- `llama-3.1-70b-versatile`
- `llama-3.1-8b-instant`
- `mixtral-8x7b-32768`
- `gemma2-9b-it`

### 4. DeepSeek
**Description**: Advanced reasoning models
**Website**: https://deepseek.com/
**Required**: API key and base_url

```json
{
  "default_provider": "deepseek",
  "model_providers": {
    "deepseek": {
      "api_key": "sk-your-deepseek-api-key",
      "base_url": "https://api.deepseek.com/v1",
      "model": "deepseek-chat",
      "max_tokens": 4096,
      "temperature": 0.5,
      "top_p": 1,
      "parallel_tool_calls": true,
      "max_retries": 10
    }
  }
}
```

**Popular Models**:
- `deepseek-chat`
- `deepseek-coder`

### 5. Alibaba Cloud (DashScope)
**Description**: Alibaba's AI model service with generous free tier
**Website**: https://www.alibabacloud.com/help/en/model-studio/
**Required**: API key and base_url
**Free Tier**: 1 million tokens across 4 Qwen models

```json
{
  "default_provider": "alibaba",
  "model_providers": {
    "alibaba": {
      "api_key": "your-alibaba-api-key",
      "base_url": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
      "model": "qwen-turbo",
      "max_tokens": 4096,
      "temperature": 0.5,
      "top_p": 1,
      "parallel_tool_calls": true,
      "max_retries": 10
    }
  }
}
```

**Popular Models**:
- `qwen-turbo` (Fast and efficient)
- `qwen-plus` (Balanced performance)
- `qwen-max` (Most capable)
- `qwen-max-longcontext` (Extended context)

**Free Tier Details**:
- 1,000,000 tokens total across all 4 models
- No time limit on usage
- Perfect for development and testing
- More info: https://www.alibabacloud.com/help/en/model-studio/new-free-quota

### 6. Novita AI
**Description**: AI inference platform with competitive pricing
**Website**: https://novita.ai/
**Required**: API key and base_url

```json
{
  "default_provider": "novita",
  "model_providers": {
    "novita": {
      "api_key": "your-novita-api-key",
      "base_url": "https://api.novita.ai/v3/openai",
      "model": "meta-llama/llama-3.1-8b-instruct",
      "max_tokens": 4096,
      "temperature": 0.5,
      "top_p": 1,
      "parallel_tool_calls": true,
      "max_retries": 10
    }
  }
}
```

**Popular Models**:
- `meta-llama/llama-3.1-8b-instruct`
- `meta-llama/llama-3.1-70b-instruct`
- `mistralai/mixtral-8x7b-instruct-v0.1`
- `microsoft/wizardlm-2-8x22b`

### 7. Ollama (Local - Native API)
**Description**: Run models locally using Ollama's native API
**Website**: https://ollama.ai/
**Required**: Only base_url (no API key needed)
**Note**: Uses Ollama's native API, not OpenAI-compatible

```json
{
  "default_provider": "ollama",
  "model_providers": {
    "ollama": {
      "api_key": "",
      "base_url": "http://localhost:11434",
      "model": "llama3.2:latest",
      "max_tokens": 4096,
      "temperature": 0.5,
      "top_p": 1,
      "parallel_tool_calls": false,
      "max_retries": 3
    }
  }
}
```

**Setup Requirements**:
1. Install Ollama: `curl -fsSL https://ollama.ai/install.sh | sh`
2. Pull a model: `ollama pull llama3.2`
3. Start Ollama service: `ollama serve`

**Popular Models**:
- `llama3.2:latest`
- `codellama:latest`
- `mistral:latest`
- `qwen2.5:latest`

## Usage Examples

### Command Line Usage

```bash
# Use OpenRouter with Claude
trae-cli run "Create a Python script" --provider openrouter --model "anthropic/claude-3.5-sonnet"

# Use Groq for fast inference
trae-cli run "Debug this code" --provider groq --model "llama-3.1-70b-versatile"

# Use Alibaba Cloud with free tier
trae-cli run "Write unit tests" --provider alibaba --model "qwen-turbo"

# Use Novita AI
trae-cli run "Explain this function" --provider novita --model "meta-llama/llama-3.1-8b-instruct"

# Use local Ollama
trae-cli run "Code review" --provider ollama --model "llama3.2:latest"

# Use Together AI
trae-cli run "Generate documentation" --provider together --model "meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo"
```

### Environment Variables

Set API keys using environment variables:

```bash
export OPENROUTER_API_KEY="sk-or-v1-your-key"
export TOGETHER_API_KEY="your-together-key"
export GROQ_API_KEY="gsk_your-groq-key"
export DEEPSEEK_API_KEY="sk-your-deepseek-key"
export ALIBABA_API_KEY="your-alibaba-api-key"
export NOVITA_API_KEY="your-novita-api-key"
```

### Interactive Mode

```bash
# Start interactive session with specific provider
trae-cli interactive --provider openrouter --model "anthropic/claude-3.5-sonnet"
```

## Tool Calling Support

Most OpenAI-compatible services support tool calling (function calling). The client automatically detects and enables this feature when available.

**Services with Tool Calling**:
- ✅ OpenRouter (model-dependent)
- ✅ Together AI (select models)
- ✅ Groq (select models)
- ✅ DeepSeek
- ❌ Ollama (limited support)

## Configuration Tips

### 1. Model Selection
- **For coding tasks**: Use `deepseek-coder`, `qwen-turbo`, `codellama`, or Claude models
- **For fast responses**: Use Groq with Llama models or `qwen-turbo`
- **For cost efficiency**: Use Alibaba Cloud free tier, OpenRouter free models, or Novita AI
- **For privacy**: Use local Ollama models
- **For multilingual**: Use Qwen models (excellent Chinese support)

### 2. Performance Tuning
- **Parallel Tool Calls**: Enable for faster multi-tool execution
- **Max Retries**: Adjust based on service reliability
- **Temperature**: Lower (0.1-0.3) for coding, higher (0.7-0.9) for creative tasks

### 3. Rate Limiting
Different services have different rate limits:
- **OpenRouter**: Varies by model and tier
- **Together AI**: 600 requests/minute (free tier)
- **Groq**: 30 requests/minute (free tier)
- **DeepSeek**: 60 requests/minute (free tier)
- **Alibaba Cloud**: 1M tokens total (free tier), then pay-per-use
- **Novita AI**: Varies by plan and model
- **Ollama**: No limits (local)

## Troubleshooting

### Common Issues

1. **API Key Not Working**
   ```bash
   # Check if key is set
   echo $OPENROUTER_API_KEY
   
   # Verify in config
   trae-cli show-config
   ```

2. **Model Not Found**
   - Check service documentation for available models
   - Some models require specific API access levels

3. **Connection Errors**
   ```
   Error: base_url is required for OpenAI-compatible services
   ```
   **Solution**: Ensure `base_url` is specified in your configuration:
   ```json
   {
     "provider_name": {
       "api_key": "your-key",
       "base_url": "https://api.service.com/v1",  // Required!
       "model": "model-name"
     }
   }
   ```

4. **Wrong Endpoint URL**
   ```
   Error: Connection failed to https://wrong-url.com
   ```
   **Solution**: Verify the correct endpoint URL from the service documentation

5. **Tool Calling Not Working**
   - Verify model supports function calling
   - Check if `parallel_tool_calls` is properly configured

6. **Ollama Connection Issues**
   ```bash
   # Check if Ollama is running (native API)
   curl http://localhost:11434/api/tags
   
   # Start Ollama service
   ollama serve
   
   # List available models
   ollama list
   
   # Pull a model if needed
   ollama pull llama3.2
   ```

7. **Ollama vs OpenAI-Compatible**
   ```
   Error: Ollama model not responding correctly
   ```
   **Solution**: Ensure you're using the correct provider:
   - Use `"provider": "ollama"` for native Ollama API
   - Use `"provider": "openai_compatible"` with LiteLLM proxy for OpenAI format

8. **Custom Port Configuration**
   If Ollama runs on a different port:
   ```json
   {
     "ollama": {
       "base_url": "http://localhost:8080",  // Custom port
       "api_key": ""  // No API key needed
     }
   }
   ```

### Debug Mode

Enable detailed logging for troubleshooting:

```bash
# Run with trajectory recording
trae-cli run "your task" --trajectory-file debug.json

# Check the trajectory file for detailed API interactions
```

## Best Practices

### 1. **Always specify base_url for OpenAI-compatible services**
   ```json
   // ❌ Wrong - Missing base_url
   {
     "openrouter": {
       "api_key": "sk-or-v1-your-key",
       "model": "anthropic/claude-3.5-sonnet"
     }
   }
   
   // ✅ Correct - With base_url
   {
     "openrouter": {
       "api_key": "sk-or-v1-your-key",
       "base_url": "https://openrouter.ai/api/v1",
       "model": "anthropic/claude-3.5-sonnet"
     }
   }
   ```

2. **Use appropriate models for tasks**:
   - Code generation: DeepSeek Coder, CodeLlama
   - General chat: Claude, GPT-4, Llama
   - Fast responses: Groq models

3. **Configure retries appropriately**:
   - Higher retries for unreliable networks
   - Lower retries for local services

4. **Monitor usage and costs**:
   - Most services provide usage dashboards
   - Set up billing alerts where available

5. **Test locally first**:
   - Use Ollama for development and testing
   - Switch to cloud services for production

6. **Validate endpoints before deployment**:
   ```bash
   # Test endpoint connectivity
   curl -H "Authorization: Bearer your-api-key" \
        https://api.service.com/v1/models
   ```

## Contributing

To add support for a new OpenAI-compatible service:

1. Add the service to the `LLMProvider` enum
2. Update the configuration examples
3. Test tool calling compatibility
4. Update this documentation

For service-specific issues, please check the respective service documentation and support channels.
