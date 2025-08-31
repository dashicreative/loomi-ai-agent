"""
Saved Meals Analyzer Tool

Analyzes saved meals for nutritional insights, comparisons, and recommendations.
"""

from typing import Dict, List, Optional
import json


async def analyze_saved_meals_tool(
    session_context: 'SessionContext',
    query: str,
    daily_goals: Optional[Dict] = None
) -> Dict:
    """
    Analyze saved meals based on user query.
    
    Args:
        session_context: Current session context with saved meals
        query: User's analysis request (e.g., "total calories", "protein needed")
        daily_goals: Optional daily nutritional goals
        
    Returns:
        Dictionary with analysis results
    """
    
    saved_meals = session_context.saved_meals
    
    if not saved_meals:
        return {
            "status": "no_saved_meals",
            "message": "You haven't saved any meals yet in this session.",
            "analysis": None
        }
    
    # Get nutrition totals
    totals = session_context.get_saved_nutrition_totals()
    
    # Parse query for analysis type
    query_lower = query.lower()
    
    # Goal-based queries (check FIRST before totals)
    if any(word in query_lower for word in ['need', 'left', 'remain', 'goal', 'target', 'more']):
        # Extract goal amount from query
        import re
        goal_match = re.search(r'(\d+)\s*g', query_lower)
        
        if 'protein' in query_lower and goal_match:
            goal = float(goal_match.group(1))
            remaining = max(0, goal - totals['protein'])
            percentage = (totals['protein'] / goal * 100) if goal > 0 else 0
            
            # Store the gap in session context for future reference
            if remaining > 0:
                session_context.current_nutrition_gaps['protein'] = remaining
            
            return {
                "status": "success",
                "analysis_type": "protein_remaining",
                "goal": goal,
                "current": totals['protein'],
                "remaining": remaining,
                "percentage_complete": percentage,
                "message": f"You've consumed {totals['protein']:.1f}g of your {goal:.0f}g protein goal ({percentage:.0f}% complete). You need {remaining:.1f}g more protein.",
                "meal_count": len(saved_meals)
            }
    
    # Basic totals query
    if any(word in query_lower for word in ['total', 'sum', 'all', 'how much', 'how many']):
        if 'calorie' in query_lower:
            return {
                "status": "success",
                "analysis_type": "total_calories",
                "value": totals['calories'],
                "message": f"Your {len(saved_meals)} saved meals contain {totals['calories']:.0f} total calories.",
                "meal_count": len(saved_meals)
            }
        elif 'protein' in query_lower:
            return {
                "status": "success",
                "analysis_type": "total_protein",
                "value": totals['protein'],
                "message": f"Your {len(saved_meals)} saved meals contain {totals['protein']:.1f}g total protein.",
                "meal_count": len(saved_meals)
            }
        elif 'fat' in query_lower:
            return {
                "status": "success",
                "analysis_type": "total_fat",
                "value": totals['fat'],
                "message": f"Your {len(saved_meals)} saved meals contain {totals['fat']:.1f}g total fat.",
                "meal_count": len(saved_meals)
            }
        elif 'carb' in query_lower:
            return {
                "status": "success",
                "analysis_type": "total_carbs",
                "value": totals['carbs'],
                "message": f"Your {len(saved_meals)} saved meals contain {totals['carbs']:.1f}g total carbs.",
                "meal_count": len(saved_meals)
            }
        else:
            # Return all totals
            return {
                "status": "success",
                "analysis_type": "all_totals",
                "values": totals,
                "message": f"Nutritional totals for your {len(saved_meals)} saved meals:",
                "breakdown": {
                    "calories": f"{totals['calories']:.0f} kcal",
                    "protein": f"{totals['protein']:.1f}g",
                    "fat": f"{totals['fat']:.1f}g",
                    "carbs": f"{totals['carbs']:.1f}g"
                },
                "meal_count": len(saved_meals)
            }
    
    
    # Meal comparison queries
    if any(word in query_lower for word in ['compare', 'which', 'highest', 'lowest', 'most', 'least']):
        if 'calorie' in query_lower:
            sorted_meals = sorted(saved_meals, 
                                key=lambda m: extract_nutrient_value(m, 'calorie'),
                                reverse=('highest' in query_lower or 'most' in query_lower))
            
            if sorted_meals:
                meal = sorted_meals[0]
                cal_value = extract_nutrient_value(meal, 'calorie')
                direction = "highest" if ('highest' in query_lower or 'most' in query_lower) else "lowest"
                
                return {
                    "status": "success",
                    "analysis_type": f"{direction}_calories",
                    "meal": {
                        "title": meal.get('title', 'Unknown'),
                        "calories": cal_value,
                        "saved_at": meal.get('saved_at')
                    },
                    "message": f"The meal with the {direction} calories is '{meal.get('title')}' with {cal_value:.0f} calories.",
                    "all_meals_ranked": [
                        {"title": m.get('title'), "calories": extract_nutrient_value(m, 'calorie')}
                        for m in sorted_meals
                    ]
                }
    
    # Average calculations
    if 'average' in query_lower or 'avg' in query_lower:
        meal_count = len(saved_meals) if saved_meals else 1
        averages = {
            'calories': totals['calories'] / meal_count,
            'protein': totals['protein'] / meal_count,
            'fat': totals['fat'] / meal_count,
            'carbs': totals['carbs'] / meal_count
        }
        
        return {
            "status": "success",
            "analysis_type": "averages",
            "values": averages,
            "message": f"Average nutrition per meal ({len(saved_meals)} meals saved):",
            "breakdown": {
                "calories": f"{averages['calories']:.0f} kcal",
                "protein": f"{averages['protein']:.1f}g",
                "fat": f"{averages['fat']:.1f}g",
                "carbs": f"{averages['carbs']:.1f}g"
            },
            "meal_count": len(saved_meals)
        }
    
    # Default response for unrecognized queries
    return {
        "status": "success",
        "analysis_type": "summary",
        "message": f"You have {len(saved_meals)} saved meals.",
        "totals": totals,
        "meals": [
            {
                "title": meal.get('title', 'Unknown'),
                "saved_at": meal.get('saved_at'),
                "calories": extract_nutrient_value(meal, 'calorie')
            }
            for meal in saved_meals
        ]
    }


def extract_nutrient_value(meal: Dict, nutrient_name: str) -> float:
    """
    Extract specific nutrient value from meal data.
    
    Args:
        meal: Recipe/meal dictionary
        nutrient_name: Name of nutrient to extract (e.g., 'calorie', 'protein')
        
    Returns:
        Numeric value of the nutrient, or 0.0 if not found
    """
    nutrition = meal.get('nutrition', [])
    
    for nutrient_info in nutrition:
        if isinstance(nutrient_info, dict):
            name = nutrient_info.get('name', '').lower()
            if nutrient_name.lower() in name:
                value_str = str(nutrient_info.get('value', '0'))
                try:
                    return float(''.join(c for c in value_str if c.isdigit() or c == '.'))
                except:
                    return 0.0
    
    return 0.0