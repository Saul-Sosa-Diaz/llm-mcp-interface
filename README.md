# LLM Assistant with Model Context Protocol Integration

An advanced AI assistant application built with Chainlit, OpenAI LLM, and Model Context Protocol (MCP) for seamless integration with external tools and services.

## Table of Contents

- [Features](#features)
- [Technology Stack](#technology-stack)
- [Prerequisites](#prerequisites)
- [Installation & Setup](#installation--setup)
- [Project Structure](#project-structure)
- [Configuration](#configuration)
- [Usage](#usage)
- [Development](#development)
- [Deployment](#deployment)
- [Troubleshooting](#troubleshooting)
- [Security](#security)
- [License](#license)
- [Support & Contact](#support--contact)


## Technology Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Web Framework** | [Chainlit](https://chainlit.io) | Interactive chat UI |
| **LLM** | OpenAI API (or compatible like Vllm or LM Studio) | Language model backend |
| **Protocol** | Model Context Protocol (MCP) | Tool integration protocol |
| **Database** | SQLite with aiosqlite | Async conversation storage |
| **Containerization** | Docker & Docker Compose | Production deployment |
| **Language** | Python 3.11+ | Application runtime |

## Prerequisites

### Local Development
- Python 3.11+
- Docker & Docker Compose (for containerized deployment)
- OpenAI API key or compatible LLM endpoint
- Git

## Installation & Setup

### Docker Deployment 

#### 1. Clone and navigate to project
```bash
git clone <repository-url>
cd llm-mcp-interface
```

#### 2. Configure environment variables
```bash
# Copy example configuration
cp .env.example .env

# Edit .env with your credentials
nano .env  # or use your preferred editor
```

Required environment variables:
```bash
API_KEY=your_api_key_here
BASE_URL=https://api.openai.com/v1
MODEL=Qwen/Qwen3-32B
DATABASE_PATH=chat_history.db
```

#### 3. Configure MCP servers
Edit `mcp_config.json` to configure Model Context Protocol servers:
```json
{
  "mcpServers": {
    "fetch": {
      "command": "uvx",
      "args": ["mcp-server-fetch"]
    }
  }
}
```

#### 4. Start services
```bash
docker-compose up -d
```

This starts the **Chainlit Application** backend service.

#### 5. Access the application

Access at `http://localhost:8006/chat`

#### 6. View logs and manage services
```bash
# View logs
docker-compose logs -f chainlit

# Check health status
docker-compose ps

# Stop services
docker-compose down

# Rebuild after code changes
docker-compose up -d --build

# Execute command in container
docker-compose exec chainlit bash

# Clean up (remove volumes and data)
docker-compose down -v
```

## Project Structure

```
.
├── source/                      # Application source code
│   ├── app.py                  # Main Chainlit application
│   ├── database.py             # Chat history persistence layer
│   └── mcp_manager.py          # MCP server management
├── Dockerfile                  # Container image definition
├── docker-compose.yml          # Multi-container orchestration
├── mcp_config.json             # MCP server configuration
├── requirements.txt            # Python dependencies
├── .env.example               # Environment template
├── chainlit.md                # Chainlit welcome message
├── clean_history.py           # Git history sanitizer
└── README.md                  # This file
```

## Configuration

### Environment Variables

```bash
# LLM API Configuration
API_KEY=your_api_key_here
BASE_URL=https://api.openai.com/v1
MODEL=Qwen/Qwen3-32B

# Database
DATABASE_PATH=chat_history.db
```

### MCP Configuration (`mcp_config.json`)

```json
{
  "mcpServers": {
    "server_name": {
      "command": "executable_or_package",
      "args": ["arg1", "arg2"],
      "env": {
        "ENV_VAR": "value"
      }
    }
  }
}
```

## Usage

### Basic Chat
1. Open the web interface
2. Type your message
3. The assistant processes your request and responds
4. If tools are available, they execute automatically when helpful

### Tool Execution
The LLM automatically decides when to use available tools:
- Tool calls are shown in the chat interface
- Results are processed and incorporated into responses
- All interactions are logged to the database


### Adding New Features

**Adding a New MCP Server:**
1. Update `mcp_config.json` with server details
2. Restart the application
3. Tools are automatically discovered

**Modifying LLM Behavior:**
Edit `SYSTEM_PROMPT` in `source/app.py` to adjust assistant personality and instructions.


## License

MIT License - See [LICENSE](./LICENSE) file for details.

Copyright (c) 2026