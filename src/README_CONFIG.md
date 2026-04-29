# Configuration Setup

## Initial Setup

1. **Copy the example config file:**
   ```bash
   cp config.example.json config.json
   ```

2. **Copy the example environment file:**
   ```bash
   cp .env.example .env
   ```

3. **Update `.env` with your actual API keys:**
   ```bash
   GOOGLE_API_KEY=your_actual_google_api_key
   SAMBANOVA_API_KEY=your_actual_sambanova_api_key
   SAMBANOVA_BASE_URL=https://ai.tejas.tacc.utexas.edu
   ```

4. **Update `config.json`** with your specific configuration needs (collections, paths, etc.)

## Security Notes

- **Never commit** `config.json` or `.env` files to git
- Both files are in `.gitignore` to prevent accidental commits
- API keys are read from `.env` file only
- `config.json` contains non-sensitive configuration only
- Use `config.example.json` as a template for new environments

## Configuration Priority

1. **API Keys**: Always from `.env` file
2. **System Settings**: From `config.json` 
3. **Runtime Overrides**: Environment variables take precedence over config file
