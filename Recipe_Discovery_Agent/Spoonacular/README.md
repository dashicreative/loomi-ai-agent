# Spoonacular Ingredient Search Test

## Setup

1. Get a Spoonacular API key from: https://spoonacular.com/food-api/console
2. Set your API key as an environment variable:
   ```bash
   export SPOONACULAR_API_KEY='your_key_here'
   ```

## Usage

Run the interactive test:
```bash
python ingredient_search_test.py
```

Enter ingredient names when prompted, and the tool will return the Spoonacular URL for that ingredient.

## Example

```
Enter ingredient name: apple
Searching for: apple
Found ingredient: apple
Ingredient ID: 9003
Ingredient URL: https://spoonacular.com/ingredients/9003-apple
```

Press Ctrl+C to exit the interactive mode.