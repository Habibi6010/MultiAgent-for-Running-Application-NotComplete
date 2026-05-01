"""
Sport Agent - Main Entry Point
Interactive track & field training assistant
"""
import os
import sys
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Add agents directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'agents'))

from agents.interactive_controller import InteractiveController


def main():
    """
    Main entry point for Sport Agent
    Starts an interactive conversation session
    """
    print("\n" + "="*70)
    print("🏃 SPORT AGENT - Track & Field Training Assistant")
    print("="*70)
    print("\n📋 Checking environment setup...\n")
    
    # Check required environment variables
    required_vars = {
        # "GOOGLE_API_KEY": "Google Gemini API key for LLM",
        "OPENAI_API_KEY": "OpenAI API key for LLM (alternative)",
    }
    
    optional_vars = {
        "SUPABASE_URL": "Supabase project URL for conversation storage",
        "SUPABASE_KEY": "Supabase anon key for database access",
        "USER_ID": "User identifier for session tracking"
    }
    
    # Check required variables
    missing_required = []
    for var, description in required_vars.items():
        if not os.getenv(var):
            missing_required.append(f"  ❌ {var}: {description}")
        else:
            print(f"  ✅ {var} is set")
    
    # Check optional variables
    for var, description in optional_vars.items():
        if os.getenv(var):
            print(f"  ✅ {var} is set")
        else:
            print(f"  ⚠️  {var} not set ({description})")
    
    if missing_required:
        print("\n❌ Missing required environment variables:")
        for msg in missing_required:
            print(msg)
        print("\nPlease set these variables and try again.")
        print("You can create a .env file or export them in your terminal.")
        return
    
    print("\n✅ Environment setup complete!\n")
    
    # Get user ID if provided
    user_id = os.getenv("USER_ID")
    if not user_id:
        user_input = input("Enter your user ID (or press Enter for anonymous): ").strip()
        user_id = user_input if user_input else None
    
    # Start interactive controller
    try:
        controller = InteractiveController(user_id=user_id)
        controller.start_session()
    except KeyboardInterrupt:
        print("\n\n👋 Goodbye!")
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()