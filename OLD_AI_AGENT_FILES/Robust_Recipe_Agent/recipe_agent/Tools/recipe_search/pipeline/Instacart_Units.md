# Instacart API Accepted Units of Measurement

## Measured Items (Liquids & Volume)

| Primary Unit | Accepted Variants | Example Items |
|--------------|-------------------|---------------|
| cup | cup, cups, c | walnuts, heavy cream, rolled oats |
| fl oz can | fl oz can | tomato soup, sweet corn |
| fl oz container | fl oz container | olive oil, rice vinegar |
| fl oz jar | fl oz jar | organic coconut oil, bone broth, marinated artichoke |
| fl oz pouch | fl oz pouch | cold-pressed baby food |
| fl oz ounce | fl oz ounce | whole milk, bottled water, vegetable oil |
| gallon | gallon, gallons, gal, gals | whole milk, distilled water |
| milliliter | milliliter, millilitre, milliliters, millilitres, ml, mls | milk, apple juice |
| liter | liter, litre, liters, litres, l | alkaline water, passion fruit juice |
| pint | pint, pints, pt, pts | ice cream |
| pt container | pt container | blueberries |
| quart | quart, quarts, qt, qts | ice cream |
| tablespoon | tablespoon, tablespoons, tb, tbs | olive oil, salt, sugar |
| teaspoon | teaspoon, teaspoons, ts, tsp, tspn | pepper, curry, cinnamon |

## Weighed Items

| Primary Unit | Accepted Variants | Example Items |
|--------------|-------------------|---------------|
| gram | gram, grams, g, gs | rice noodles |
| kilogram | kilogram, kilograms, kg, kgs | chicken, beef, pork |
| lb bag | lb bag, lb | potatoes, grapefruit, grapes |
| lb can | lb can, lb | shredded chicken |
| lb container | lb container, lb | strawberries, blackberries |
| per lb | per lb | pears, tangelos, apples |
| ounce | ounce, ounces, oz | cereal, butter, oats |
| ounces bag | ounces bag, oz bag | dog treats, cat treats, pineapple chunks |
| ounces can | ounces can, oz can | canned black beans, canned tuna |
| ounces container | ounces container, oz container | turkey quick meal, greek salad meal |
| pound | pound, pounds, lb, lbs | beef, flour, pork |

## Countable Items

| Primary Unit | Accepted Variants | Example Items |
|--------------|-------------------|---------------|
| bunch | bunch, bunches | carrots, red beets, radish |
| can | can, cans | sweet corn, butternut squash |
| each | each | tomatoes, oranges, onions |
| ears | ears | corn |
| head | head, heads | lettuce |
| large | large, lrg, lge, lg | eggs, oranges, avocados |
| medium | medium, med, md | eggs, oranges, avocados |
| package | package, packages | beef rump roast |
| packet | packet | scone, croissants |
| small | small, sm | eggs, oranges, avocados |
| small ears | small ears | corn |
| small head | small head, small heads | lettuce |

## Important Notes for AI Parsing

1. **For countable items**: Always use "each" rather than weight units (e.g., "3 each" tomatoes, not "1 lb" tomatoes)
2. **Multiple measurements allowed**: You can provide arrays of different unit measurements for better matching
3. **Case sensitivity**: Units appear to be case-insensitive in the API
4. **Container combinations**: Some units combine with container types (e.g., "fl oz jar", "oz can", "lb bag")
5. **Default unit**: If no unit specified, defaults to "each"

## Recommended Parsing Strategy

1. When possible, choose the simplest variant (e.g., "cup" over "cups", "oz" over "ounces")
2. For liquids, prefer "fl oz" for small amounts, "cup" for medium, "quart" or "gallon" for large
3. For weights, prefer "oz" for small amounts (under 1 lb), "lb" for larger amounts
4. Always include container type if known (can, jar, bag, container)