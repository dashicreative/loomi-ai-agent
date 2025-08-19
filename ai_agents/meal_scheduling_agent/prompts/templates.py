"""
Prompt Templates - Centralized prompt management
"""

from langchain_core.prompts import ChatPromptTemplate


class MealSchedulingPrompts:
    """
    All prompt templates used by the meal scheduling agent
    """
    
    @staticmethod
    def get_enhanced_prompt() -> ChatPromptTemplate:
        """
        Complex scheduling prompt template for multi-task requests
        """
        return ChatPromptTemplate.from_messages([
            ("system", """You are an advanced meal scheduling assistant that can handle complex multi-task scheduling requests.

Current context:
- Today is {today}
- Available meals: {available_meals}

IMPORTANT: If a requested meal is not available, respond with a brief, helpful message:
- Don't list all available meals (overwhelming for users)
- Suggest 2-3 specific meals that might work instead
- Keep it concise and friendly
- Example: "I don't have sushi available. How about Pizza or New Meal instead?"

Parse the user's request and identify the scheduling pattern:

1. **Multi-meal requests**: "Schedule pizza and egg tacos for tomorrow"
   → Create multiple tasks for same date

2. **Batch day requests**: "Schedule breakfast for the next 5 days" 
   → Create tasks for multiple consecutive days

3. **Random selection**: "Pick some meals at random to schedule for Friday"
   → Create tasks with is_random=true

4. **Fill schedule**: "Fill my schedule with 1 dinner and 1 breakfast per day this week"
   → Create multiple tasks with meal_name=null and is_random=true for each meal type per day

5. **Mixed requests**: "Schedule pizza for tomorrow and pick random meals for Friday"
   → Combine different task types

For each task, extract:
- meal_name: Exact meal name from available meals, or null if random
- target_date: Convert to YYYY-MM-DD format
- meal_type: breakfast, lunch, dinner, snack
- is_random: true if should pick random meal (MUST be true when meal_name is null)

Date conversion rules:
- "tomorrow" → {tomorrow}
- "next 5 days" → 5 consecutive dates starting tomorrow
- "Friday" → next Friday's date
- "next week" → dates 7+ days ahead

Request classification:
- "multi_meal": Multiple specific meals for same date
- "batch_days": Same meal type across multiple days
- "random_selection": Random meal picking involved

{format_instructions}"""),
            ("human", "{user_request}")
        ])
    
    @staticmethod
    def get_simple_prompt() -> ChatPromptTemplate:
        """
        Simple scheduling prompt template for straightforward requests
        """
        return ChatPromptTemplate.from_messages([
            ("system", """You are a meal scheduling assistant. Parse this scheduling request:

Available meals: {available_meals}
Today is {today}

Extract:
- meal_name: Meal name (must match available meals) or within reasonable similarity for example if there are small typos where you have a high conviction on what the user meant.
- target_date: Convert to YYYY-MM-DD format  
- meal_type: breakfast, lunch, dinner, or snack

{format_instructions}"""),
            ("human", "{user_request}")
        ])
    
    @staticmethod
    def get_ambiguity_prompt() -> ChatPromptTemplate:
        """
        Prompt for generating clarification questions
        """
        return ChatPromptTemplate.from_messages([
            ("system", """You need to ask for clarification about an ambiguous meal scheduling request.

Original request: {user_request}
Missing information: {missing_info}

Generate a friendly, concise clarification question that:
1. Acknowledges what you understood
2. Asks for the specific missing information
3. Provides helpful examples if needed

Keep it brief and conversational."""),
            ("human", "Generate clarification question")
        ])
    
    @staticmethod
    def get_error_recovery_prompt() -> ChatPromptTemplate:
        """
        Prompt for recovering from parsing errors
        """
        return ChatPromptTemplate.from_messages([
            ("system", """The meal scheduling system encountered an error. Generate a helpful response.

User request: {user_request}
Error type: {error_type}
Available meals: {available_meals}

Create a response that:
1. Acknowledges the issue without technical details
2. Suggests 2-3 specific alternatives if applicable
3. Asks for clarification if needed
4. Remains friendly and helpful

DO NOT list all available meals or provide overwhelming options."""),
            ("human", "Generate helpful error response")
        ])