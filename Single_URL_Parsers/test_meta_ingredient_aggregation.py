#!/usr/bin/env python3
"""
Test quantity aggregation for meta_ingredients
"""

def test_quantity_aggregation():
    """Simulate meta ingredient quantity aggregation logic"""

    # Simulated ingredients_with_ids (what comes from step_ingredient_matcher)
    ingredients_with_ids = {
        "I001": {"name": "olive oil", "quantity": "1", "unit": "teaspoon"},
        "I002": {"name": "olive oil", "quantity": "1", "unit": "teaspoon"},
        "I003": {"name": "olive oil", "quantity": "1", "unit": "teaspoon"},
        "I004": {"name": "olive oil", "quantity": "1", "unit": "teaspoon"},
        "I005": {"name": "garlic", "quantity": "2", "unit": "clove"},
        "I006": {"name": "garlic", "quantity": "1", "unit": "clove"},
        "I007": {"name": "salt", "quantity": "1", "unit": "count"},  # Different unit
        "I008": {"name": "salt", "quantity": "1", "unit": "teaspoon"},  # Different unit - can't aggregate
    }

    # Simulated meta_ingredients (what comes from LLM deduplication)
    meta_ingredients = [
        {
            "id": "META_1",
            "name": "olive oil",
            "linked_raw_ids": ["I001", "I002", "I003", "I004"]
        },
        {
            "id": "META_2",
            "name": "garlic",
            "linked_raw_ids": ["I005", "I006"]
        },
        {
            "id": "META_3",
            "name": "salt",
            "linked_raw_ids": ["I007", "I008"]  # Mixed units - can't aggregate
        }
    ]

    print("\n🧪 Meta Ingredient Quantity Aggregation Test")
    print("="*60)

    # Apply aggregation logic (same as in vertical_video_processor.py)
    for meta in meta_ingredients:
        linked_ids = meta.get("linked_raw_ids", [])
        if not linked_ids:
            meta["quantity"] = ""
            meta["unit"] = ""
            continue

        # Collect all quantities and units from linked raw ingredients
        quantities = []
        units = []
        for raw_id in linked_ids:
            if raw_id in ingredients_with_ids:
                raw_ing = ingredients_with_ids[raw_id]
                qty = raw_ing.get("quantity", "")
                unit = raw_ing.get("unit", "")
                if qty and unit:
                    quantities.append(qty)
                    units.append(unit)

        # Aggregate quantities if all have the same unit
        if quantities and units:
            unique_units = set(units)
            if len(unique_units) == 1:
                # Same unit - sum the quantities
                try:
                    total = sum(float(q) for q in quantities)
                    # Return as int if whole number
                    meta["quantity"] = str(int(total)) if total.is_integer() else str(total)
                    meta["unit"] = units[0]
                except (ValueError, TypeError):
                    meta["quantity"] = ""
                    meta["unit"] = ""
            else:
                # Different units - can't aggregate
                meta["quantity"] = ""
                meta["unit"] = ""
        else:
            meta["quantity"] = ""
            meta["unit"] = ""

    # Display results
    print("\n✅ Aggregated Meta Ingredients:")
    print("-"*60)
    for meta in meta_ingredients:
        qty_display = f"{meta['quantity']} {meta['unit']}" if meta['quantity'] else "(no aggregation - mixed units)"
        linked_count = len(meta['linked_raw_ids'])
        print(f"{meta['id']:10} {meta['name']:15} → {qty_display:20} ({linked_count} raw ingredients)")

    print("\n📊 Expected Results:")
    print("-"*60)
    print("  META_1 (olive oil):  4 teaspoon   ✅ (1+1+1+1 = 4)")
    print("  META_2 (garlic):     3 clove      ✅ (2+1 = 3)")
    print("  META_3 (salt):       (empty)      ✅ (mixed units: count + teaspoon)")

    # Verify
    assert meta_ingredients[0]["quantity"] == "4" and meta_ingredients[0]["unit"] == "teaspoon"
    assert meta_ingredients[1]["quantity"] == "3" and meta_ingredients[1]["unit"] == "clove"
    assert meta_ingredients[2]["quantity"] == "" and meta_ingredients[2]["unit"] == ""

    print("\n✅ All tests passed!")
    print("="*60 + "\n")

if __name__ == "__main__":
    test_quantity_aggregation()
