# Conversation Context Feature

## Overview

The DPWH agent now supports **persistent conversation context** using SQLite. This allows the agent to remember previous questions and provide contextual follow-up responses.

## How It Works

### Context Storage
- Conversations are stored in a SQLite database (`data/conversation_context.db`)
- Each user session is tracked with a unique session ID
- The agent extracts entities (cities, regions, contractors, years) from questions
- Context is automatically applied to follow-up questions

### Example Conversation

```
User: "How many projects are in Quezon City?"
Agent: [stores context: municipality=Quezon City]
      "There are 145 flood control projects in Quezon City."

User: "What's the total budget?"  
Agent: [applies stored context]
      "The total approved budget in Quezon City is ₱2,450,000,000.00"
      [Context: Quezon City]

User: "Show me the top 5 projects"
Agent: [still using Quezon City context]
      "Top 5 projects by approved budget in Quezon City:
       - Project A - ₱500M
       - Project B - ₱450M
       ..."
```

## Features

### 1. Automatic Context Extraction
The system automatically identifies and stores:
- **Locations**: municipalities, provinces, regions
- **Contractors**: company names
- **Time periods**: years, year ranges
- **Query types**: last action performed

### 2. Intelligent Context Application
- Only applies context when questions are ambiguous
- Preserves explicit filters in new questions
- Shows context summary when applied

### 3. Context Clearing
Context is automatically cleared when:
- User starts a new topic ("show me", "list", "find")
- User explicitly changes location
- Session ends

## Database Schema

### Tables

**sessions**
- `session_id` (TEXT): Unique session identifier
- `created_at` (TEXT): ISO timestamp
- `last_activity` (TEXT): Last interaction time
- `metadata` (TEXT): JSON metadata

**conversations**
- `id` (INTEGER): Auto-increment ID
- `session_id` (TEXT): Foreign key to sessions
- `timestamp` (TEXT): Message timestamp
- `user_message` (TEXT): User's question
- `agent_response` (TEXT): Agent's answer
- `context_extracted` (TEXT): JSON of extracted entities

**context_store**
- `session_id` (TEXT): Session ID
- `key` (TEXT): Context key (e.g., 'municipality')
- `value` (TEXT): Context value
- `updated_at` (TEXT): Last update time

## API Usage

### Python API

```python
from adk_app.dpwh_web_agent.tools import analytics_tools

# Set session for tracking
analytics_tools.set_session("my-session-123")

# Ask question - context is automatically managed
response = analytics_tools.answer_dpwh_question(
    "How many projects in Manila?", 
    session_id="my-session-123"
)

# Follow-up uses stored context
response = analytics_tools.answer_dpwh_question(
    "What's the total budget?",
    session_id="my-session-123"
)
# ^ This will automatically use Manila context
```

### Direct Database Access

```python
from adk_app.dpwh_web_agent.core.utils.context_db import (
    get_context,
    update_context,
    get_conversation_history,
    clear_context
)

# Get current context
context = get_context("my-session-123")
# {'municipality': 'Manila', 'last_action': 'count'}

# Update context
update_context("my-session-123", {'region': 'NCR'})

# Get conversation history
history = get_conversation_history("my-session-123", limit=10)

# Clear specific context keys
clear_context("my-session-123", keys=['municipality'])

# Clear all context
clear_context("my-session-123")
```

## Configuration

### Environment Variables

```bash
# Database location (default: ./data)
CONTEXT_DB_DIR=./data

# Flask session secret (auto-generated if not set)
FLASK_SECRET_KEY=your-secret-key-here
```

### Flask Integration

The Flask app automatically:
- Creates a unique session ID for each browser session
- Passes session ID to analytics_tools
- Maintains context across page reloads

## Implementation Files

- `core/utils/context_db.py` - SQLite database operations
- `core/utils/context_extractor.py` - Context extraction and application logic  
- `tools/analytics_tools.py` - Integration with agent (updated)
- `app.py` - Flask session management (updated)

## Benefits

✅ **Natural Conversation** - Users can ask follow-up questions without repeating filters  
✅ **Persistent Storage** - Context survives server restarts  
✅ **Session Management** - Multiple users maintain separate contexts  
✅ **Conversation History** - Full audit trail of questions and answers  
✅ **Flexible** - Context can be manually controlled if needed  

## Testing

```python
# Test context extraction
from adk_app.dpwh_web_agent.core.utils.context_extractor import extract_context_from_question

question = "How many projects in Quezon City?"
parsed = simple_parse(question, df)
context = extract_context_from_question(question, parsed, df)
# {'municipality': 'Quezon City', 'last_action': 'count'}
```

## Maintenance

The SQLite database is automatically created on first use at `data/conversation_context.db`.

To reset all conversations:
```bash
del data\conversation_context.db
```

To backup conversations:
```bash
copy data\conversation_context.db data\conversation_context_backup.db
```
