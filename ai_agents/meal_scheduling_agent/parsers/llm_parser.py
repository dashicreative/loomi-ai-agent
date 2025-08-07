"""
LLM Parser - Uses Claude/GPT to parse complex requests into structured data
"""

from typing import Tuple, Optional, List
from datetime import date, timedelta
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser

from services.llm_service import llm_service
from .parser_models import BatchScheduleAction, ScheduleTask
from ..prompts.templates import MealSchedulingPrompts


class LLMParser:
    """
    Uses LLM to parse complex scheduling requests
    """
    
    def __init__(self):
        self.prompt_template = MealSchedulingPrompts.get_enhanced_prompt()
        self.parser = JsonOutputParser()
    
    async def parse_complex_request(
        self, 
        user_request: str, 
        available_meals: List[str]
    ) -> Tuple[BatchScheduleAction, Optional[str]]:
        """
        Parse complex multi-task scheduling requests using LLM
        
        Args:
            user_request: The user's request
            available_meals: List of available meal names
            
        Returns:
            Tuple of (BatchScheduleAction, helpful_response_text)
            helpful_response_text is only set if LLM provides error guidance
        """
        try:
            # Build the chain
            chain = self.prompt_template | llm_service.claude | self.parser
            
            tomorrow = (date.today() + timedelta(days=1)).isoformat()
            
            result_dict = await chain.ainvoke({
                "user_request": user_request,
                "today": date.today().isoformat(),
                "tomorrow": tomorrow,
                "available_meals": ", ".join(available_meals),
                "format_instructions": "Return a JSON object with 'tasks' array and 'request_type' string"
            })
            
            # Convert dict result to BatchScheduleAction
            tasks = []
            for task_dict in result_dict.get('tasks', []):
                # Ensure is_random is True when meal_name is None
                if task_dict.get('meal_name') is None and not task_dict.get('is_random', False):
                    task_dict['is_random'] = True
                tasks.append(ScheduleTask(**task_dict))
            
            return BatchScheduleAction(
                tasks=tasks,
                request_type=result_dict.get('request_type', 'unknown')
            ), None
            
        except Exception as e:
            # We already have the LLM response from above, just check if it's helpful
            llm_response_text = None
            
            # Extract the helpful response text from the error
            error_str = str(e)
            if "Invalid json output:" in error_str:
                # Extract the actual LLM response from the error message
                response_text = error_str.split("Invalid json output:")[1].split("\n")[0].strip()
                
                # If LLM gives helpful text response about unavailable meals, capture it
                helpful_indicators = [
                    "don't have", "not available", "not in", "available meals", 
                    "how about", "instead", "try", "consider"
                ]
                
                if any(indicator in response_text.lower() for indicator in helpful_indicators):
                    llm_response_text = response_text
            
            print(f"LLM parsing failed: {e}")
            # Return the fallback with the helpful message if we have one
            return None, llm_response_text