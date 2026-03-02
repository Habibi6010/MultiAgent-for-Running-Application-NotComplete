# 🏃 Sport Agent - Track & Field Training Assistant

An intelligent conversational agent for track and field athletes, coaches, and researchers. Sport Agent helps with training plans, biomechanics analysis, and research paper discovery.

## 🎯 Features

- **Interactive Conversations**: Natural dialogue-based interface
- **Intent Classification**: Automatically understands user requests
- **Smart Clarifications**: Asks relevant questions to gather complete information
- **Database Persistence**: Saves all conversations to Supabase
- **Multi-Agent Routing**: Routes requests to specialized agents

### What Sport Agent Can Help With

1. **Training Plans** 📅
   - Custom workout programs
   - Event-specific training schedules
   - Periodization planning

2. **Biomechanics Analysis** 🎯
   - Technique improvement
   - Movement analysis
   - Form optimization

3. **Research Papers** 📚
   - Scientific literature search
   - Training methodology research
   - Performance studies

## 🚀 Quick Start

### Prerequisites

- Python 3.8+
- Google Gemini API key OR OpenAI API key
- (Optional) Supabase account for conversation storage

### Installation

1. **Clone the repository**
   ```bash
   cd "Sport Agent"
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up environment variables**
   ```bash
   # Copy the example file
   cp .env.example .env
   
   # Edit .env and add your API keys
   ```

4. **(Optional) Set up Supabase database**
   
   If you want conversation storage:
   - Create a Supabase project at https://supabase.com
   - Run the SQL schema from `app/agents/db_manager.py`
   - Add SUPABASE_URL and SUPABASE_KEY to your .env file

### Running Sport Agent

```bash
python app/main.py
```

## 📖 Usage Examples

### Example 1: Training Plan Request
```
You: I need a 12-week training plan for 400m dash, intermediate level
Assistant: Great! I'd like to gather some more details...
[Agent asks clarifying questions about goals, constraints, etc.]
```

### Example 2: Biomechanics Question
```
You: How can I improve my block start in the 100m sprint?
Assistant: I can help with that! Do you have video available for analysis?
[Agent routes to biomechanics specialist]
```

### Example 3: Research Search
```
You: Find papers about VO2 max training for middle distance runners
Assistant: Perfect! I'll search for recent research on that topic...
[Agent routes to research database]
```

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      User Input                             │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   v
┌─────────────────────────────────────────────────────────────┐
│              Interactive Controller                          │
│  • Manages conversation flow                                │
│  • Saves to Supabase                                        │
│  • Handles irrelevant queries                               │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   v
┌─────────────────────────────────────────────────────────────┐
│              Input Controller Graph                          │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 1. Classify Intent                                   │   │
│  │ 2. Check Relevance    → If irrelevant: prompt retry │   │
│  │ 3. Check Completeness                                │   │
│  │ 4. Ask Clarifications ← Loop until complete         │   │
│  │ 5. Build Handoff Prompt                              │   │
│  └─────────────────────────────────────────────────────┘   │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   v
┌─────────────────────────────────────────────────────────────┐
│              Supervisor Agent (TODO)                         │
│  Routes to:                                                  │
│  • Training Agent                                            │
│  • Biomechanics Agent                                        │
│  • Research Agent                                            │
└─────────────────────────────────────────────────────────────┘
```

## 📁 Project Structure

```
Sport Agent/
├── app/
│   ├── main.py                          # Main entry point
│   └── agents/
│       ├── input_controler.py           # Core controller logic
│       ├── interactive_controller.py    # Session management
│       ├── db_manager.py                # Supabase integration
│       └── show_graph.py                # Graph visualization
├── data/                                # Training data
├── .env.example                         # Environment template
├── .gitignore                           # Git ignore rules
├── requirements.txt                     # Python dependencies
└── README.md                            # This file
```

## 🔧 Configuration

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GOOGLE_API_KEY` | Yes* | Google Gemini API key |
| `OPENAI_API_KEY` | Yes* | OpenAI API key |
| `SUPABASE_URL` | No | Supabase project URL |
| `SUPABASE_KEY` | No | Supabase anon key |
| `USER_ID` | No | User identifier |

*At least one LLM API key is required

### Supabase Schema

Run this SQL in your Supabase SQL Editor:

```sql
-- Sessions table
CREATE TABLE IF NOT EXISTS sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    status TEXT NOT NULL,
    final_state JSONB
);

-- Messages table
CREATE TABLE IF NOT EXISTS messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id UUID REFERENCES sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    metadata JSONB,
    timestamp TIMESTAMPTZ NOT NULL
);

-- Conversation states table
CREATE TABLE IF NOT EXISTS conversation_states (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id UUID REFERENCES sessions(id) ON DELETE CASCADE,
    intent TEXT,
    domain TEXT,
    relevance TEXT,
    task_spec JSONB,
    ready BOOLEAN,
    timestamp TIMESTAMPTZ NOT NULL
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
CREATE INDEX IF NOT EXISTS idx_states_session ON conversation_states(session_id);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
```

## 🎨 Visualizing the Graph

You can visualize the controller graph:

```python
from app.agents.show_graph import plot_graph
from app.agents.input_controler import controller_app

# Generate HTML visualization
plot_graph(controller_app, "graph.html", open_browser=True)
```

Or from command line:
```bash
python app/agents/show_graph.py app/agents/input_controler.py:controller_app --html graph.html --open
```

## 🛠️ Development

### Testing the Controller

```python
from app.agents.input_controler import build_controller_graph

# Build the graph
graph = build_controller_graph()

# Test with a message
state = {
    "messages": [{"role": "user", "content": "I need a training plan for 100m"}],
    "chat_history": [],
    "domain": "track_and_field",
    "intent": "",
    "relevance": "",
    "missing_fields_required": [],
    "missing_fields_optional": [],
    "clarifying_questions": [],
    "task_spec": {},
    "handoff_prompt": "",
    "ready": False
}

result = graph.invoke(state, {"recursion_limit": 10})
print(result)
```

## 🤝 Contributing

Contributions are welcome! Areas for improvement:

- [ ] Implement supervisor agent routing
- [ ] Add specialist agents (training, biomechanics, research)
- [ ] Enhanced error handling
- [ ] Multi-language support
- [ ] Voice interface
- [ ] Web UI

## 📝 License

MIT License

## 🙏 Acknowledgments

- Built with [LangGraph](https://github.com/langchain-ai/langgraph)
- LLM powered by Google Gemini and OpenAI
- Database by Supabase

## 📞 Support

For issues or questions, please open a GitHub issue.

---

**Note**: This is the entry point agent for the Sport Agent system. Downstream specialist agents are in development.
