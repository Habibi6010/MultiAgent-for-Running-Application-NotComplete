import os
import json
from dotenv import load_dotenv
from langchain.tools import tool
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from typing import TypedDict, List, Dict, Any, Optional
from langgraph.graph import StateGraph, END, START

# Load environment variables from .env file
load_dotenv()

# Initialize LLM (prioritize Gemini for free tier)
if os.getenv("GOOGLE_API_KEY"):
    llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash-lite", temperature=0)
elif os.getenv("OPENAI_API_KEY"):
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
else:
    raise ValueError("No LLM API key found. Set GOOGLE_API_KEY or OPENAI_API_KEY in .env file")
# llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash-lite", temperature=0)

class ControllerState(TypedDict):
    # conversation
    messages: List[Dict[str, Any]]  # or BaseMessage objects if you prefer
    chat_history: List[Dict[str, str]]  # compact history (role/content)

    # extracted understanding
    domain: str                      # e.g., "each track_and_field"
    intent: str                      # e.g., "training_plan", "biomechanic", "paper_search"
    relevance: str                   # "relevant" | "irrelevant" | "unclear"
    missing_fields_required: List[str]        # what’s missing
    missing_fields_optional: List[str]        # what’s missing
    clarifying_questions: List[str]  # questions to ask user

    # structured task spec for downstream
    task_spec: Dict[str, Any]        # structured request (json)

    # packaging
    handoff_prompt: str              # final prompt for next agent
    ready: bool                      # gate to proceed


INTENT_SCHEMAS = {
  "training_plan": {
    "required": ["event", "level", "timeframe", "goal", "constraints"],
    "optional": ["weekly_days", "facility", "equipment", "injuries"]
  },
  "biomechanic": {
    "required": ["event", "phase", "question"],
    "optional": ["video_available", "metrics_available"]
  },
  "paper_search": {
    "required": ["topic", "keywords"],
    "optional": ["years", "venues", "multi_agent_required"]
  },
  "diet_plan": {
    "required": ["goal", "dietary_preferences", "timeframe"],
    "optional": ["restrictions", "allergies", "activity_level", "target_weight", "meals_per_day"]
  }
}


def classify_intent_node(state: ControllerState) -> ControllerState:
    """
    Classify user prompt into intent category from INTENT_SCHEMAS.
    Extracts initial task_spec fields based on the detected intent.
    """
    # Preserve existing context for multi-turn conversations
    previous_intent = state.get("intent", "")
    previous_domain = state.get("domain", "")
    previous_task_spec = state.get("task_spec", {}) if isinstance(state.get("task_spec", {}), dict) else {}
    previous_missing_required = state.get("missing_fields_required", [])

    # Get latest user message
    messages = state.get("messages", [])
    chat_history = state.get("chat_history", [])
    
    if messages:
        user_prompt = messages[-1].get("content") if isinstance(messages[-1], dict) else str(messages[-1])
    elif chat_history:
        user_prompt = chat_history[-1].get("content", "")
    else:
        user_prompt = ""
    
    if not user_prompt:
        state["intent"] = "unknown"
        state["domain"] = ""
        state["task_spec"] = {}
        # print("\n\n[classify_intent_node]", state)
        return state
    
    # Build schema description for LLM
    intent_descriptions = []
    for intent_name, schema in INTENT_SCHEMAS.items():
        required = ", ".join(schema["required"])
        optional = ", ".join(schema.get("optional", []))
        intent_descriptions.append(f'"{intent_name}": required fields: [{required}], optional: [{optional}]')
    
    schema_info = "\n".join(intent_descriptions)
    
    # Classification prompt for LLM
    classification_prompt = f"""
    Analyze the user's request and classify it into ONE of these intents.
    Extract ONLY the fields that match the exact canonical field names below.
    
    Available Intents and Fields:
    {schema_info}
    
    1. "training_plan" - User wants a workout/training program plan
       Example: "I need a 12-week training plan for 100m sprint as a beginner"
    
    2. "biomechanic" - User asks about technique, biomechanics, or movement analysis
       Example: "How do I improve my takeoff in high jump?"
    
    3. "paper_search" - User wants research papers or academic resources
       Example: "Find papers about VO2 max training"
    
    4. "diet_plan" - User wants a nutrition or meal plan for track & field performance
       Example: "Create a nutrition plan to improve my sprint performance"
    
    User Request: {user_prompt}
    
    Extract fields using EXACT canonical names from the schema above.
    Respond in JSON format:
    {{
        "intent": "training_plan" | "biomechanic" | "paper_search" | "diet_plan",
        "domain": (Based on intent, e.g. "track_and_field", "general"),
        "relevance": "relevant" | "irrelevant" | "unclear",
        "extracted_fields": {{
            "field_name": "value"
        }}
    }}

        If you cannot confidently classify the intent, respond with "unknown" and provide an empty extracted_fields.
        If you cann't determine intent but can extract some fields, still classify as "unknown" but include the extracted fields in the response.
        If the user request is not relevant to any of the intents, classify as "irrelevant" and provide an explanation in the extracted_fields, but if it's unclear whether it's relevant or not, classify as "unclear" and explain in the extracted_fields.
        But it the user request is relevant to one of the intents, but isn't on of the intents, put relevence as unclear and explain in the extracted_fields that you are not sure which intent it is, but it seems relevant to the closest intent, and extract any fields you can based on the known schemas.

    """
    
    # Use LLM to classify
    response = llm.invoke(classification_prompt)
    response_text = str(response.content)
#     print(f"LLM Classification Response: {response.content}")
    # Parse JSON response
    try:
        # Extract JSON from response
        json_start = response_text.find('{')
        json_end = response_text.rfind('}') + 1
        if json_start != -1 and json_end > json_start:
            json_str = response_text[json_start:json_end]
            result = json.loads(json_str)
        else:
            result = {"intent": "unknown", "domain": ""}
    except json.JSONDecodeError:
        result = {"intent": "unknown", "domain": ""}
    
    # Update state
    intent = result.get("intent", "unknown")
    if intent not in INTENT_SCHEMAS:
        intent = "unknown"
    
    # If classifier is uncertain on follow-up turns, keep previously valid intent
    if intent == "unknown" and previous_intent in INTENT_SCHEMAS:
        intent = previous_intent

    state["intent"] = intent
    state["domain"] = result.get("domain", previous_domain or "general")
    extracted_fields = result.get("extracted_fields", {})
    if isinstance(extracted_fields, dict):
        merged_task_spec = dict(previous_task_spec)
        merged_task_spec.update(extracted_fields)
        state["task_spec"] = merged_task_spec
    else:
        state["task_spec"] = previous_task_spec
    
    # Mark if this is a follow-up to clarification (preserve missing fields for routing)
    if previous_missing_required:
        state["missing_fields_required"] = previous_missing_required

#     print("\n\n[classify_intent_node]", state)
    return state

def check_relevance_node(state: ControllerState) -> ControllerState:
    """
    Check if the user request is relevant to the domain.
    """
    intent = state.get("intent", "unknown")
    
    # If intent classification failed, mark as unclear
    if intent == "unknown":
        state["relevance"] = "unclear"
        state['ready'] = False  # Not ready if we don't understand the intent
        # print("\n\n[check_relevance_node]", state)
        return state
    
    # If we have a valid intent from our schemas, it's relevant
    if intent in INTENT_SCHEMAS:
        state["relevance"] = "relevant"
    else:
        state["relevance"] = "irrelevant"

#     print("\n\n[check_relevance_node]", state)
    return state

def check_completeness_node(state: ControllerState) -> ControllerState:
    """
    Check completeness of task_spec against INTENT_SCHEMAS.
    Validates both required and optional fields using canonical field names.
    """
    intent = state.get("intent", "unknown")
    schema = INTENT_SCHEMAS.get(intent)
    
    if not schema:
        state["missing_fields_required"] = ["intent_clarification"]
        state["missing_fields_optional"] = ["intent_clarification"]
        state["ready"] = False
        # print("\n\n[check_completeness_node]", state)
        return state

    task_spec = state.get("task_spec", {})

    unclear_markers = {
        "unknown", "unclear", "not sure", "not specified", "not provided",
        "n/a", "na", "none", "null", "tbd", "to be determined"
    }

    def is_missing_or_unclear(value: Any) -> bool:
        if value in [None, "", []]:
            return True
        if isinstance(value, str):
            normalized = value.strip().lower()
            if not normalized or normalized in unclear_markers:
                return True
        return False

    # Check required fields (these MUST be present and clear)
    required_fields = schema.get("required", [])
    missing_required = [
        f for f in required_fields 
        if f not in task_spec or is_missing_or_unclear(task_spec.get(f))
    ]
    
    # Check optional fields (nice to have, but not required)
    optional_fields = schema.get("optional", [])
    missing_optional = [
        f for f in optional_fields 
        if f not in task_spec or is_missing_or_unclear(task_spec.get(f))
    ]
    
    # Only required fields are missing - optional can be filled later
    state["missing_fields_required"] = missing_required
    state["missing_fields_optional"] = missing_optional
    # Ready only if all required fields are present and request is relevant
    state["ready"] = (len(missing_required) == 0 and state.get("relevance") == "relevant")

    # print("\n\n[check_completeness_node]", state)
    return state

def ask_clarifications_node(state: ControllerState) -> ControllerState:
    """
    Use LLM to generate natural clarifying questions for missing required fields
    and mention optional fields that could enhance the response.
    """
    missing_required = state.get("missing_fields_required", [])
    missing_optional = state.get("missing_fields_optional", [])
    intent = state.get("intent", "unknown")
    schema = INTENT_SCHEMAS.get(intent, {})
    current_spec = state.get("task_spec", {})
    
    if not missing_required:
        state["clarifying_questions"] = []
        # print("\n\n[ask_clarifications_node]", state)
        return state
    
    # Build context for LLM
    optional_str = ""
    if missing_optional:
        optional_str = f"""
Additionally, we have these optional fields that can enhance the response if you know them:
{', '.join(missing_optional)}

If you have information about any of these, feel free to share!"""
    
    # Use LLM to generate natural clarifying questions
    clarification_prompt = f"""
    Generate a natural, conversational message to ask the user for missing required information.
    
    Intent: {intent}
    Missing Required Fields: {', '.join(missing_required)}
    Current Information: {current_spec}
    {optional_str}
    schema_info = {list(INTENT_SCHEMAS.keys())}
    requiered_fields_info = {schema.get("required", [])}
    optional_fields_info = {schema.get("optional", [])}

    Create a friendly, helpful message that:
    1. Asks for the missing required fields in a natural way (not just a list)
    2. Explains why these fields are needed
    3. If there are optional fields, mention them politely at the end
    4. If the intent is unknown or generic which is not in the known schemas, ask clarifying questions to understand what they want and suggest possible intents based on the available schemas.
    5. Avoid asking for information we already have or that is not relevant to the intent.
    6. If the intent is known but there are no missing required fields, do not generate clarifying questions.
    7. if required fields are missing, but required_fields_info is not empty. Ask all required and optional fields in the same message.
    8. If the intent is unknown, ask open-ended questions to understand the user's needs and suggest possible intents based on the available schemas.
    9. Just ask a quesions you need, don't talk too much, keep it short and concise, without Hello or greetings.
    10. Use the exact canonical field names when asking for information to ensure we can extract the answers correctly in the next step.
    Keep the tone conversational and encouraging.
    """
    
    try:
        response = llm.invoke(clarification_prompt)
        clarifying_text = str(response.content)
        state["clarifying_questions"] = [clarifying_text]
    except Exception as e:
        print(f"Error generating clarifications: {e}")
        # Fallback to simple format if LLM fails
        questions = [f"Please provide: {f}" for f in missing_required[:-1]]
        if missing_optional:
            questions.append(f"Optional fields you can provide: {', '.join(missing_optional)}")
        state["clarifying_questions"] = questions

#     print("\n\n[ask_clarifications_node]", state)
    return state

def build_handoff_prompt_node(state: ControllerState) -> ControllerState:
    """
    Build a comprehensive handoff prompt using LLM.
    Generates context-aware, well-structured instructions for downstream agents.
    """
    domain = state.get("domain", "unknown")
    intent = state.get("intent", "unknown")
    task_spec = state.get("task_spec", {})
    chat_history = state.get("chat_history", [])
    
    if intent == "unknown":
        # Fallback to simple format if intent is unknown
        state["handoff_prompt"] = (
            "Unable to generate handoff prompt: Intent classification failed.\n"
            "Please clarify what you need help with."
        )
        # print("\n\n[build_handoff_prompt_node]", state)
        return state
    
    # Build context information
    schema = INTENT_SCHEMAS.get(intent, {})
    required_fields = schema.get("required", [])
    optional_fields = schema.get("optional", [])
    
    # Format chat history for context
    history_str = ""
    if chat_history:
        history_str = "Chat History:\n"
        for msg in chat_history[:]:  # Use full history for better context
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            history_str += f"  {role}: {content}\n"
    
    # Format task spec
    task_spec_str = json.dumps(task_spec, indent=2)
    
    # Handoff prompt generation
    handoff_generation_prompt = f"""
    Generate a comprehensive, professional handoff prompt for a downstream specialist agent.
    
    Context:
    - Domain: {domain}
    - Intent/Task Type: {intent}
    - Required Fields: {', '.join(required_fields)}
    - Optional Fields: {', '.join(optional_fields)}
    
    Task Specification:
    {task_spec_str}
    
    {history_str}
    
    Create a detailed handoff prompt that:
    
    1. ROLE DEFINITION: Clearly define the specialist agent's role based on the intent
       - For "training_plan": Training program designer specializing in track & field
       - For "biomechanic": Biomechanics expert specializing in track & field movements
       - For "paper_search": Research specialist in track & field sports science
       - For "diet_plan": Nutrition specialist for track & field athletes
    
    2. TASK CLARITY: Explicitly state what the agent must do with the provided data
    
    3. CONTEXT: Explain the user's goals and constraints based on task_spec
    
    4. DELIVERABLES: Specify what the agent should produce/output
    
    5. QUALITY STANDARDS: Set expectations for accuracy, detail, and completeness
    
    6. LIMITATIONS: Mention what the agent should NOT do or assume
    
    Format the prompt professionally and make it actionable for the specialist agent.
    """
    
    try:
        response = llm.invoke(handoff_generation_prompt)
        handoff_prompt = str(response.content)
        state["handoff_prompt"] = handoff_prompt
    except Exception as e:
        print(f"Error generating handoff prompt: {e}")
        # Fallback to structured format
        state["handoff_prompt"] = (
            f"You are a {intent.replace('_', ' ').title()} Specialist Agent.\n\n"
            f"DOMAIN: {domain}\n"
            f"INTENT: {intent}\n\n"
            f"TASK SPECIFICATION:\n{task_spec_str}\n\n"
            f"Required Fields: {', '.join(required_fields)}\n"
            f"Optional Fields: {', '.join(optional_fields)}\n\n"
            f"Use the above information to provide a comprehensive and detailed response.\n"
            f"Ensure all required fields are addressed in your output."
        )

#     print("\n\n[build_handoff_prompt_node]", state)
    return state

def route_after_relevance(state: ControllerState) -> str:
    rel = state.get("relevance")
    if rel == "irrelevant":
        return "irrelevant_end"

    return "check_completeness"

def route_after_completeness(state: ControllerState) -> str:
    if state.get("ready"):
        return "build_handoff"
    return "ask_clarifications"

def build_controller_graph():
    """
    Build and compile the controller graph.
    Returns the compiled graph application.
    """
    graph = StateGraph(ControllerState)

    graph.add_node("classify_intent", classify_intent_node)
    graph.add_node("check_relevance", check_relevance_node)
    graph.add_node("check_completeness", check_completeness_node)
    graph.add_node("ask_clarifications", ask_clarifications_node)
    graph.add_node("build_handoff", build_handoff_prompt_node)

    graph.set_entry_point("classify_intent")
    graph.add_edge("classify_intent", "check_relevance")

    graph.add_conditional_edges("check_relevance", route_after_relevance, {
        "check_completeness": "check_completeness",
        "irrelevant_end": END,
    })

    graph.add_conditional_edges("check_completeness", route_after_completeness, {
        "ask_clarifications": "ask_clarifications",
        "build_handoff": "build_handoff",
    })
    # Stop after asking clarification so the app can wait for the user's next turn
    graph.add_edge("ask_clarifications", END)

    graph.add_edge("build_handoff", END)

    return graph.compile()


# Initialize controller app when imported or run
controller_app = build_controller_graph()


if __name__ == "__main__":
    user_input = input("Enter your request: ").strip()
    current_state = {
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
#     # Invoke the controller graph
    result = controller_app.invoke(current_state)
    
#     print("\n" + "="*60)
#     print("Controller Result:")
#     print("="*60)
#     print(f"Intent: {result.get('intent')}")
#     print(f"Domain: {result.get('domain')}")
#     print(f"Ready: {result.get('ready')}")
#     print(f"Task Spec: {result.get('task_spec')}")
#     print(f"Missing Required Fields: {result.get('missing_fields_required')}")
#     print(f"Clarifying Questions: {result.get('clarifying_questions')}") 