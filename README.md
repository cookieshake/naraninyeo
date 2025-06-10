# Naraninyeo

A simple FastAPI application that processes messages.

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
