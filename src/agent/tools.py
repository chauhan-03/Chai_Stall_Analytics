"""Tool definitions (JSON schemas) for the agent and a dispatcher onto StallAnalytics."""
import json

DATE = {"type": "string", "description": "Date as YYYY-MM-DD"}

TOOLS = [
    {"name": "overview",
     "description": "Headline numbers for the whole statement: period covered, UPI sales, estimated total "
                    "revenue with cash added back, average daily revenue on class days.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "sales_mix",
     "description": "Estimated units and revenue per menu item over a period (default last 30 days). "
                    "Use for 'what sells most', 'kitne samose bike'.",
     "input_schema": {"type": "object", "properties": {
         "start": DATE, "end": DATE, "days": {"type": "integer", "description": "Window length if no start"},
         "top": {"type": "integer"}}}},
    {"name": "hourly_profile",
     "description": "Payments and revenue by hour of day; busiest and slowest hours. Optional academic phase "
                    "filter: classes, midsem, compre, fest, summer_break, winter_break.",
     "input_schema": {"type": "object", "properties": {
         "start": DATE, "end": DATE, "days": {"type": "integer"}, "phase": {"type": "string"}}}},
    {"name": "combos",
     "description": "Items customers buy together (association rules with lift and confidence), and how the "
                    "existing Chai Samosa Combo is doing. Use for combo offer questions.",
     "input_schema": {"type": "object", "properties": {"days": {"type": "integer"}, "top": {"type": "integer"}}}},
    {"name": "forecast_revenue",
     "description": "Daily revenue forecast with P10/P50/P90 range for the next N days (default 7), "
                    "including academic calendar effects.",
     "input_schema": {"type": "object", "properties": {
         "days": {"type": "integer"}, "start": DATE}}},
    {"name": "forecast_items",
     "description": "Units forecast per item per day with P10/P50/P90. Item names can be plain words like "
                    "'samosa', 'maggi', 'chai'.",
     "input_schema": {"type": "object", "properties": {
         "items": {"type": "array", "items": {"type": "string"}}, "days": {"type": "integer"},
         "start": DATE}}},
    {"name": "prep_plan",
     "description": "How many of each batch-made item (samosa, kachori, mirchi bada, bread pakoda, poha, "
                    "lassi) to prepare for a day, using the newsvendor rule. Use for 'kal kitne banau'.",
     "input_schema": {"type": "object", "properties": {"day": DATE}}},
    {"name": "menu_matrix",
     "description": "Menu engineering: classifies items as Star, Plowhorse, Puzzle or Dog by popularity "
                    "and margin, with an action for each.",
     "input_schema": {"type": "object", "properties": {"days": {"type": "integer"}}}},
    {"name": "estimate_elasticity",
     "description": "Estimated price elasticity for an item that had a price change in the menu history.",
     "input_schema": {"type": "object", "properties": {"item": {"type": "string"}}, "required": ["item"]}},
    {"name": "simulate_price",
     "description": "What-if: effect of changing an item's price on its daily units, revenue and profit.",
     "input_schema": {"type": "object", "properties": {
         "item": {"type": "string"}, "new_price": {"type": "number"}}, "required": ["item", "new_price"]}},
    {"name": "simulate_hours",
     "description": "What-if: rough extra revenue from opening one extra hour (0-23).",
     "input_schema": {"type": "object", "properties": {"extra_hour": {"type": "integer"}},
                      "required": ["extra_hour"]}},
    {"name": "compare_periods",
     "description": "Compare two date ranges: change in sales, payments per day, ticket size, sales by time "
                    "slot, customers, plus context (calendar, weather, closures). Use for 'why did sales drop'.",
     "input_schema": {"type": "object", "properties": {
         "a_start": DATE, "a_end": DATE, "b_start": DATE, "b_end": DATE},
         "required": ["a_start", "a_end", "b_start", "b_end"]}},
    {"name": "detect_shifts",
     "description": "Finds lasting changes in sales for a time slot (e.g. night sales fell after a date, "
                    "possibly a new competitor).",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "detect_outages",
     "description": "Days/hours where UPI payments stopped during normally busy times (likely UPI downtime).",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "customer_insights",
     "description": "Regular customers, top spenders, regulars who stopped coming, and new customers.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "daily_brief",
     "description": "Tomorrow's brief: revenue forecast, rush hours, prep list, top items and alerts.",
     "input_schema": {"type": "object", "properties": {"day": DATE}}},
]


def run_tool(analytics, name, args):
    if name not in analytics.tool_names():
        raise ValueError(f"unknown tool {name}")
    fn = getattr(analytics, name)
    out = fn(**(args or {}))
    return json.dumps(out, default=str, ensure_ascii=False)
