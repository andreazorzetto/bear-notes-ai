# Setting Up OpenAI API Access

To use the ChatGPT integration with Bear Notes AI, follow these steps to set up your OpenAI account and obtain an API key:

## 1. Create an OpenAI Account

If you don't already have an account, sign up at [OpenAI](https://platform.openai.com/signup).

## 2. Purchase API Credits

1. Go to [Billing Overview](https://platform.openai.com/settings/organization/billing/overview)
2. Click "Add payment method" and enter your payment details
3. Purchase credits (minimum $5 recommended to start)

![Billing Overview](https://i.imgur.com/example1.png)

## 3. Generate an API Key

1. Navigate to [API Keys](https://platform.openai.com/settings/organization/api-keys)
2. Click "Create new secret key"
3. Give your key a name (e.g., "Bear Notes AI")
4. Copy your API key immediately (it won't be shown again!)

![API Keys Page](https://i.imgur.com/example2.png)

## 4. Using Your API Key

There are two ways to use your API key with Bear Notes AI:

### Option 1: Pass as Command Line Argument

```bash
./bear_notes_ai.py --chatgpt --api-key "your-openai-api-key" -k "keyword" -q "Your question"
```

### Option 2: Set as Environment Variable

```bash
export OPENAI_API_KEY="your-openai-api-key"
./bear_notes_ai.py --chatgpt -k "keyword" -q "Your question"
```

## 5. API Usage and Costs

- The script uses the GPT-4o model, which has higher costs but better capabilities
- Typical costs are approximately:
  - $0.01 - $0.10 per note depending on note length
  - More when processing multiple notes together
- Monitor your usage at [Usage Dashboard](https://platform.openai.com/usage)

## Troubleshooting

If you encounter issues:

1. **Authentication Error**: Verify your API key is correct and has not expired
2. **Insufficient Credits**: Check your balance in the billing dashboard
3. **Rate Limits**: If you hit rate limits, space out your requests

## Security Note

Keep your API key secure:
- Don't share it publicly
- Don't commit it to public repositories
- Consider using environment variables instead of command line arguments when possible