````markdown
# Naraninyeo

A simple FastAPI application that processes messages with AI-powered conversation capabilities.

## Project Structure

```
naraninyeo/
├── core/           # Core configuration and database connections
├── models/         # Pydantic data models (pure data structures)
├── repository/     # Data access layer (CRUD operations)
├── services/       # Business logic layer
├── llm/           # LLM-related modules
│   ├── agent.py   # Core LLM agent logic
│   ├── prompts.py # System prompts
│   └── schemas.py # LLM-specific data models
└── tools/         # Utility tools
```

## Architecture

This project follows a clean architecture pattern:

- **Models**: Pure data structures without business logic
- **Repository**: Data persistence and retrieval (MongoDB, Qdrant)
- **Services**: Business logic and orchestration
- **LLM**: AI conversation capabilities (separated for cohesion)

## Installation

```bash
pip install -e .
```

## Running the Application

```bash
python main.py
```

The server will start at `http://localhost:8000`

## API Endpoints

### POST /new_message

Send a message to the API.

Request body:
```json
{
    "message": "Your message here"
}
```

Response:
```json
{
    "do_reply": true,
    "message": "Your message here"
}
```

## API Documentation

Once the server is running, you can access the interactive API documentation at:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Features

- **AI-powered conversations**: Uses Google Gemini models for intelligent responses
- **Message clustering**: Groups similar conversations for context
- **Search integration**: Supports multiple search types (news, blog, web, etc.)
- **Clean architecture**: Proper separation of concerns with Models, Repository, Services, and LLM layers

````
