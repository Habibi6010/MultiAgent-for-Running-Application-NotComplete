"""
Supabase Database Manager for Sport Agent
Handles conversation storage and retrieval
"""
import os
from datetime import datetime
from typing import Dict, List, Any, Optional
from dotenv import load_dotenv
from supabase import create_client, Client
import json

# Load environment variables from .env file
load_dotenv()


class SupabaseManager:
    """Manages Supabase database operations for conversation tracking"""
    
    def __init__(self):
        """Initialize Supabase client"""
        self.supabase_url = os.getenv("SUPABASE_URL", "")
        self.supabase_key = os.getenv("SUPABASE_KEY", "")
        self.client = None
        
        if not self.supabase_url or not self.supabase_key:
            print("Warning: SUPABASE_URL and SUPABASE_KEY not set. Database features disabled.")
        else:
            try:
                self.client = create_client(self.supabase_url, self.supabase_key)
                print("Connected to Supabase")
            except Exception as e:
                print(f"Failed to connect to Supabase: {e}")
                self.client = None
    
    def create_session(self, user_id=None):
        """
        Create a new conversation session
        
        Args:
            user_id: Optional user identifier
            
        Returns:
            session_id if successful, None otherwise
        """
        if not self.client:
            return None
        
        try:
            session_data = {
                "user_id": user_id or "anonymous",
                "created_at": datetime.utcnow().isoformat(),
                "status": "active"
            }
            
            response = self.client.table("sessions").insert(session_data).execute()
            session_id = None
            if response.data and len(response.data) > 0:
                session_id = response.data[0]['id']
            
            if session_id:
                print(f"Session created: {session_id}")
            
            return session_id
        except Exception as e:
            print(f"Failed to create session: {e}")
            return None
    
    def save_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Save a conversation message to database
        
        Args:
            session_id: Session identifier
            role: Message role (user/assistant/system)
            content: Message content
            metadata: Optional metadata (intent, task_spec, etc.)
            
        Returns:
            True if successful, False otherwise
        """
        if not self.client or not session_id:
            return False
        
        try:
            message_data = {
                "session_id": session_id,
                "role": role,
                "content": content,
                "metadata": json.dumps(metadata) if metadata else None,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            self.client.table("messages").insert(message_data).execute()
            return True
        except Exception as e:
            print(f"Failed to save message: {e}")
            return False
    
    def save_state(
        self,
        session_id: str,
        state: Dict[str, Any]
    ) -> bool:
        """
        Save controller state snapshot
        
        Args:
            session_id: Session identifier
            state: Complete controller state
            
        Returns:
            True if successful, False otherwise
        """
        if not self.client or not session_id:
            return False
        
        try:
            state_data = {
                "session_id": session_id,
                "intent": state.get("intent", ""),
                "domain": state.get("domain", ""),
                "relevance": state.get("relevance", ""),
                "task_spec": json.dumps(state.get("task_spec", {})),
                "ready": state.get("ready", False),
                "timestamp": datetime.utcnow().isoformat()
            }
            
            self.client.table("conversation_states").insert(state_data).execute()
            return True
        except Exception as e:
            print(f"Failed to save state: {e}")
            return False
    
    def update_session_status(
        self,
        session_id: str,
        status: str,
        final_state: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Update session status (active/completed/error)
        
        Args:
            session_id: Session identifier
            status: New status
            final_state: Optional final state when completing
            
        Returns:
            True if successful, False otherwise
        """
        if not self.client or not session_id:
            return False
        
        try:
            update_data = {
                "status": status,
                "updated_at": datetime.utcnow().isoformat()
            }
            
            if final_state:
                update_data["final_state"] = json.dumps(final_state)
            
            self.client.table("sessions").update(update_data).eq("id", session_id).execute()
            return True
        except Exception as e:
            print(f"Failed to update session: {e}")
            return False
    
    def get_session_history(self, session_id: str):
        """
        Retrieve conversation history for a session
        
        Args:
            session_id: Session identifier
            
        Returns:
            List of messages in chronological order
        """
        if not self.client or not session_id:
            return []
        
        try:
            response = self.client.table("messages")\
                .select("*")\
                .eq("session_id", session_id)\
                .order("timestamp")\
                .execute()
            if response.data and len(response.data) > 0:
                print(f"Retrieved {len(response.data)} messages for session {session_id}")
                return response.data
            else:
                print(f"No messages found for session {session_id}")
                return []
        except Exception as e:
            print(f"Failed to retrieve history: {e}")
            return []


def create_tables_sql():
    """
    SQL schema for Supabase tables (run this in Supabase SQL editor)
    """
    return """
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

    -- Create indexes for better query performance
    CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
    CREATE INDEX IF NOT EXISTS idx_states_session ON conversation_states(session_id);
    CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
    """


if __name__ == "__main__":
    print("Supabase Database Manager for Sport Agent")
#     print("\nTo set up the database:")
#     print("1. Create a Supabase project at https://supabase.com")
#     print("2. Go to SQL Editor and run the following schema:")
#     print("\n" + "="*60)
#     print(create_tables_sql())
#     print("="*60)
#     print("\n3. Set environment variables:")
#     print("   SUPABASE_URL=your_project_url")
#     print("   SUPABASE_KEY=your_anon_key")
        
