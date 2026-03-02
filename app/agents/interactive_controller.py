"""
Interactive Input Controller for Sport Agent
Entry point for user conversations with database persistence
"""
import os
from typing import Dict, Any, List, Optional
from input_controler import build_controller_graph, ControllerState, INTENT_SCHEMAS
from db_manager import SupabaseManager


class InteractiveController:
    """
    Manages interactive user sessions with the input controller
    Handles conversation flow, database persistence, and supervisor handoff
    """
    
    def __init__(self, user_id= None):
        """
        Initialize interactive controller
        
        Args:
            user_id: Optional user identifier for session tracking
        """
        self.controller_graph = build_controller_graph()
        self.db = SupabaseManager()
        self.user_id = user_id or "anonymous"
        self.session_id = self.db.create_session(self.user_id)
        
        
        # Session state
        self.conversation_active = False
        self.current_state: Optional[Dict[str, Any]] = None
    
    def start_session(self):
        """Start an interactive conversation session"""
        self.conversation_active = True
        
        print("\n" + "="*70)
        print("🏃 Welcome to Sport Agent - Track & Field Training Assistant")
        print("="*70)
        print("\nI can help you with:")
        print("  • 📅 Training Plans - Get customized workout programs")
        print("  • 🎯 Biomechanics - Improve your technique and form")
        print("  • 📚 Research Papers - Find scientific literature")
        print("  • 🍎 Eating Plans - Create nutrition strategies for performance")
        print("\nType 'quit' or 'exit' to end the conversation")
        print("-"*70 + "\n")
        
        # Main conversation loop
        while self.conversation_active:
            try:
                user_input = input("You: ").strip()
                
                if not user_input:
                    continue
                
                # Check for exit commands
                if user_input.lower() in ['quit', 'exit', 'bye', 'goodbye']:
                    self._end_session()
                    break
                
                # Process user input through controller
                self._process_user_input(user_input)
                
            except KeyboardInterrupt:
                print("\n\nSession interrupted by user")
                self._end_session()
                break
            except Exception as e:
                print(f"\nError: {e}")
                print("Let's try again...\n")
    
    def _process_user_input(self, user_input: str):
        """
        Process user input through the controller graph
        
        Args:
            user_input: User's message
        """
        # Save user message to database
        self.db.save_message(
            session_id=self.session_id,
            role="user",
            content=user_input
        )
        
        # Initialize or update state
        if self.current_state is None:
            # First message - initialize state
            self.current_state = {
                "messages": [{"role": "user", "content": user_input}],
                "chat_history": [{"role": "user", "content": user_input}],
                "domain": "",
                "intent": "",
                "relevance": "",
                "missing_fields_required": [],
                "missing_fields_optional": [],
                "clarifying_questions": [],
                "task_spec": {},
                "handoff_prompt": "",
                "ready": False
            }
        else:
            # Continuing conversation - append message
            self.current_state["messages"].append({"role": "user", "content": user_input})
            self.current_state["chat_history"].append({"role": "user", "content": user_input})
        
        # Invoke controller graph
        try:
            result_state = self.controller_graph.invoke(
                self.current_state
            )
            self.current_state = result_state
            
            # Save state snapshot
            self.db.save_state(self.session_id, result_state)
            
            # Handle different outcomes
            self._handle_controller_result(result_state)
            
        except Exception as e:
            print(f"\nController error: {e}")
            assistant_msg = "I encountered an error processing your request. Could you please rephrase?"
            print(f"\nAssistant: {assistant_msg}\n")
            self.db.save_message(self.session_id, "assistant", assistant_msg, {"error": str(e)})
    
    def _handle_controller_result(self, state: Dict[str, Any]):
        """
        Handle the controller result and respond to user
        
        Args:
            state: Final controller state after processing
        """
        relevance = state.get("relevance", "")
        ready = state.get("ready", False)
        intent = state.get("intent", "")
        clarifying_questions = state.get("clarifying_questions", [])
        
        # Case 1: Irrelevant request
        if relevance == "irrelevant":
            assistant_msg = self._handle_irrelevant_request(state)
            print(f"\nAssistant: {assistant_msg}\n")
            self.db.save_message(self.session_id, "assistant", assistant_msg, {"relevance": "irrelevant"})
            if self.current_state is not None:
                self.current_state["chat_history"].append({"role": "assistant", "content": assistant_msg})
            
            # Reset state for new question
            self.current_state = None
        
        # Case 2: Request is ready - handoff to supervisor
        elif ready:
            assistant_msg = self._handle_ready_state(state)
            print(f"\nAssistant: {assistant_msg}\n")
            self.db.save_message(self.session_id, "assistant", assistant_msg, {
                "intent": intent,
                "task_spec": state.get("task_spec", {}),
                "ready": True
            })
            if self.current_state is not None:
                self.current_state["chat_history"].append({"role": "assistant", "content": assistant_msg})
            
            # Hand off to supervisor agent
            self._handoff_to_supervisor(state)
        
        # Case 3: Need clarifications
        elif clarifying_questions:
            assistant_msg = "\n".join(clarifying_questions)
            print(f"\nAssistant: {assistant_msg}\n")
            self.db.save_message(self.session_id, "assistant", assistant_msg, {
                "intent": intent,
                "missing_required": state.get("missing_fields_required", []),
                "missing_optional": state.get("missing_fields_optional", [])
            })
            if self.current_state is not None:
                self.current_state["chat_history"].append({"role": "assistant", "content": assistant_msg})
        
        # Case 4: Processing state (should not reach here normally)
        else:
            assistant_msg = "I'm processing your request..."
            print(f"\nAssistant: {assistant_msg}\n")
            self.db.save_message(self.session_id, "assistant", assistant_msg)
            if self.current_state is not None:
                self.current_state["chat_history"].append({"role": "assistant", "content": assistant_msg})
    
    def _handle_irrelevant_request(self, state: Dict[str, Any]) -> str:
        """
        Generate response for irrelevant requests
        
        Args:
            state: Controller state
            
        Returns:
            Response message
        """
        intent = state.get("intent", "unknown")
        
        message = f"""I apologize, but your request about '{intent}' doesn't match what I can help with.

I specialize in Track & Field athletics and can assist you with:

1. **Training Plans** - Create customized workout programs
   Example: "I need a 12-week training plan for 100m sprint"

2. **Biomechanics Analysis** - Improve technique and form
   Example: "How can I improve my high jump takeoff?"

3. **Research Papers** - Find scientific literature
   Example: "Find papers about sprint start techniques"

4. **Eating Plans** - Create nutrition strategies for performance
   Example: "Create a nutrition plan to improve my sprint performance"

Please ask a question related to track and field training, biomechanics, research, or nutrition."""
        
        return message
    
    def _handle_ready_state(self, state: Dict[str, Any]) -> str:
        """
        Generate response when request is complete and ready
        
        Args:
            state: Controller state
            
        Returns:
            Response message
        """
        intent = state.get("intent", "")
        task_spec = state.get("task_spec", {})
        
        # Intent-specific acknowledgment
        if intent == "training_plan":
            message = f"Perfect! I have all the details for your training plan. Let me connect you with our training specialist..."
        elif intent == "biomechanic":
            message = f"Great! I understand your biomechanics question. Routing you to our technique analysis expert..."
        elif intent == "paper_search":
            message = f"Excellent! I'll search our research database for papers on your topic..."
        elif intent == "diet_plan":
            message = f"Perfect! I have all your nutrition requirements. Let me connect you with our nutrition specialist..."
        else:
            message = "I have all the information needed. Processing your request..."
        
        return message
    
    def _handoff_to_supervisor(self, state: Dict[str, Any]):
        """
        Hand off to supervisor agent when request is ready
        
        Args:
            state: Complete controller state
        """
        intent = state.get("intent", "")
        handoff_prompt = state.get("handoff_prompt", "")
        task_spec = state.get("task_spec", {})
        
        print("\n" + "="*70)
        print(f"🚀 HANDOFF TO SUPERVISOR AGENT")
        print("="*70)
        print(f"Intent: {intent}")
        print(f"Task Spec: {task_spec}")
        print("\nHandoff Prompt:")
        print("-"*70)
        print(handoff_prompt)
        print("="*70 + "\n")
        
        # Save final state to database
        self.db.update_session_status(
            self.session_id,
            status="completed",
            final_state=state
        )
        
        # TODO: Actually invoke supervisor agent here
        # For now, just simulate the handoff
        print("⚙️  [Supervisor agent would be invoked here to route to specialist]\n")
        
        # End or continue session
        continue_input = input("Would you like to start a new request? (yes/no): ").strip().lower()
        if continue_input in ['yes', 'y']:
            # Reset for new request
            self.current_state = None
            # Create new session
            self.session_id = self.db.create_session(self.user_id)
            print("\n" + "-"*70)
            print("Starting new request...\n")
        else:
            self._end_session()
            self.conversation_active = False
    
    def _end_session(self):
        """End the conversation session"""
        if self.session_id:
            self.db.update_session_status(
                self.session_id,
                status="ended",
                final_state=self.current_state
            )
        
        print("\n" + "="*70)
        print("👋 Thank you for using Sport Agent!")
        print("   Your conversation has been saved.")
        print("="*70 + "\n")


def main():
    """Entry point for interactive controller"""
    # Optional: Get user ID from environment or input
    user_id = os.getenv("USER_ID")
    
    if not user_id:
        user_input = input("Enter your user ID (or press Enter for anonymous): ").strip()
        user_id = user_input if user_input else None
    
    # Start interactive session
    controller = InteractiveController(user_id=user_id)
    controller.start_session()


if __name__ == "__main__":
    main()
