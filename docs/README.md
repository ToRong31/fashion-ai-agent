# Fashion AI Agent - Technical Documentation

> Multi-agent AI system for Vietnamese fashion e-commerce (ToRoMe Store)

## Overview

The Fashion AI Agent is a **multi-agent system** built with FastAPI, LangGraph, and Google A2A SDK that provides intelligent shopping assistance for the ToRoMe fashion store. It consists of 4 specialized agents working together to handle product search, outfit recommendations, and order processing.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      Frontend (Port 3000)                        │
│                    React + Vite + TailwindCSS                   │
└────────────────────────────┬────────────────────────────────────┘
                             │ POST /api/ai/chat
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Orchestrator (Port 8000)                      │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Routing Agent - Intent classification & agent routing  │   │
│  │  • Keyword-based fallback                               │   │
│  │  • LLM tool-calling (OpenAI)                          │   │
│  └─────────────────────────────────────────────────────────┘   │
└────┬──────────────┬──────────────┬─────────────────────────────┘
     │              │              │
     ▼              ▼              ▼
┌──────────┐  ┌──────────┐  ┌──────────┐
│  Search  │  │  Stylist │  │  Order   │
│  Agent   │  │  Agent   │  │  Agent   │
│ (8001)   │  │ (8002)   │  │ (8003)   │
└────┬─────┘  └────┬─────┘  └────┬─────┘
     │              │              │
     └──────────────┴──────────────┘
                    │
                    ▼
     ┌─────────────────────────────┐
     │    Backend (Port 9000)       │
     │  Spring Boot Microservices   │
     │  PostgreSQL + Elasticsearch  │
     └─────────────────────────────┘
```

## Agents

| Agent | Port | Purpose | Skills |
|-------|------|---------|--------|
| **Orchestrator** | 8000 | Intent routing, LLM-based delegation | Routing, Agent discovery |
| **Search Agent** | 8001 | Product catalog search | Product Search |
| **Stylist Agent** | 8002 | Outfit recommendations | Outfit Recommendation |
| **Order Agent** | 8003 | Cart & checkout | Order Processing |

## Communication Protocol

- **A2A (Agent-to-Agent)**: Google A2A SDK for inter-agent communication
- **REST**: External clients (Frontend) communicate via HTTP
- **Tool Calling**: OpenAI function calling for LLM-based routing

## Quick Start

```bash
cd fashion-ai-agent

# Configure environment
cp .env.example .env
# Edit .env with OPENAI_API_KEY

# Run with Docker
docker compose up --build
```

## Documentation Index

- [Orchestrator Agent](./orchestrator.md) - Intent routing and agent delegation
- [Search Agent](./search-agent.md) - Semantic product search
- [Stylist Agent](./stylist-agent.md) - AI fashion styling
- [Order Agent](./order-agent.md) - Shopping cart & checkout
- [API Reference](./api-reference.md) - Full API documentation
