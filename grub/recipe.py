"""Write a recipe with Claude, then have a second pass check it before it goes anywhere."""
import json
import re

import httpx

from . import env

API = "https://api.anthropic.com/v1/messages"

RECIPE_TOOL = {
    "name": "save_recipe",
    "description": "Save the finished recipe post.",
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Dish name, max 6 words."},
            "tagline": {"type": "string", "description": "One punchy line, max 12 words."},
            "servings": {"type": "string", "description": "e.g. 'Serves 4' or 'Serves 1 brave soul'"},
            "time": {"type": "string", "description": "e.g. '35 min'"},
            "ingredients": {
                "type": "array", "minItems": 4, "maxItems": 10,
                "items": {"type": "object",
                          "properties": {"qty": {"type": "string"}, "item": {"type": "string"}},
                          "required": ["qty", "item"]},
            },
            "steps": {"type": "array", "minItems": 3, "maxItems": 6,
                      "items": {"type": "string", "description": "One step, max 30 words."}},
            "allergens": {"type": "array", "items": {"type": "string"},
                          "description": "Edible only: main allergens (gluten, dairy, egg, nuts, ...). Empty for not-edible."},
            "image_prompt": {"type": "string", "description": "Describe ONLY the plated dish and its look, 40-70 words. No style words, no people."},
            "alt_text": {"type": "string", "description": "Plain description of the photo for screen readers, max 25 words."},
            "caption_hook": {"type": "string", "description": "Caption opening, 1-3 short lines, in the account's voice. Ends with a question to drive comments."},
            "hashtags": {"type": "array", "minItems": 4, "maxItems": 8, "items": {"type": "string"}},
        },
        "required": ["title", "tagline", "servings", "time", "ingredients", "steps", "allergens",
                     "image_prompt", "alt_text", "caption_hook", "hashtags"],
    },
}

CHECK_TOOL = {
    "name": "verdict",
    "description": "Record the safety review.",
    "input_schema": {
        "type": "object",
        "properties": {"pass": {"type": "boolean"}, "issues": {"type": "array", "items": {"type": "string"}}},
        "required": ["pass", "issues"],
    },
}

VOICE = ("You write for {brand}, an Instagram account that posts one AI-invented recipe a day. "
         "Voice: warm, witty, British-dry, never cringe. Short sentences. UK spelling, metric units.")

BRIEF = {
    "edible": (
        "Invent a real, cookable, delicious recipe with a fresh twist, achievable by a home cook in under 90 minutes "
        "using supermarket ingredients. It must actually work: sensible quantities, correct order, safe cooking "
        "(poultry and minced meat cooked through, no raw flour or raw egg eaten as-is). Steps must use every ingredient."
    ),
    "not_edible": (
        "Invent a gross-out JOKE recipe styled like a real cookbook entry, but built from things that are obviously "
        "not food (household objects, garden debris, stationery, old trainers, etc.). It must be absurd enough that "
        "nobody could mistake it for real food or be tempted to try it. Rules: no real chemicals, cleaning products, "
        "medicines, drugs, alcohol, plants or fungi that are actually toxic; no blood, bodily fluids, insects, animals, "
        "or anything gory; nothing small or plausible enough to become a dare or 'challenge'; no instructions that "
        "would be dangerous if copied (no heating batteries, aerosols or plastics, no mixing substances). "
        "Steps are comedic and impossible rather than practical. Never call it safe to eat."
    ),
}

CHECKER = {
    "edible": (
        "You are a food-safety editor. Fail the recipe if ANY of these apply: unsafe cooking of meat, poultry, fish or "
        "eggs; raw flour or raw egg eaten uncooked; dangerous techniques (deep-frying without guidance, pressure "
        "cooking hazards); quantities or timings that are clearly wrong; steps that skip or invent ingredients; "
        "allergens missing from the allergen list; anything not actually food. Minor style issues are not failures."
    ),
    "not_edible": (
        "You are a safety editor for a comedy 'not food' recipe account. Fail the post if ANY of these apply: it could "
        "be mistaken for real, edible food; it features real chemicals, cleaning products, medicines, drugs, alcohol, "
        "or genuinely toxic plants/fungi; it includes blood, bodily fluids, insects, animals or gore; it describes a "
        "method that would be hazardous if copied (heating batteries/aerosols/plastics, mixing substances, fire); "
        "it is small or plausible enough to become a dare; it targets or mocks a real person or group; "
        "anything implies it is safe to eat."
    ),
}

# Belt and braces: a hard filter that runs regardless of what the checker says.
BLOCKLIST = re.compile(
    r"\b(bleach|ammonia|chlorine|detergent|tide ?pod|laundry pod|drain cleaner|lye|antifreeze|bleach|"
    r"battery acid|lithium|mercury|lead paint|paracetamol|ibuprofen|pills?|vape|nicotine|cannabis|"
    r"vodka|whisky|gin|rum|alcohol|blood|urine|faeces|feces|vomit|semen|cockroach|maggot|rat|"
    r"lighter fluid|petrol|gasoline|aerosol|deadly nightshade|foxglove|death cap|hemlock|oleander)\b",
    re.I,
)


def _call(model: str, system: str, user: str, tool: dict, max_tokens: int = 2000) -> dict:
    resp = httpx.post(
        API,
        headers={"x-api-key": env("ANTHROPIC_API_KEY"), "anthropic-version": "2023-06-01",
                 "content-type": "application/json"},
        json={"model": model, "max_tokens": max_tokens, "system": system,
              "tools": [tool], "tool_choice": {"type": "tool", "name": tool["name"]},
              "messages": [{"role": "user", "content": user}]},
        timeout=120,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"Anthropic API {resp.status_code}: {resp.text[:500]}")
    for block in resp.json()["content"]:
        if block["type"] == "tool_use":
            return block["input"]
    raise RuntimeError("Anthropic response had no tool output")


def blocklist_hits(recipe: dict) -> list[str]:
    text = json.dumps(recipe, ensure_ascii=False)
    return sorted({m.group(0).lower() for m in BLOCKLIST.finditer(text)})


def write_recipe(kind: str, past_titles: list[str], cfg: dict, log=print) -> dict:
    llm = cfg["llm"]
    avoid = "\n".join(f"- {t}" for t in past_titles[-llm["history_window"]:]) or "- (none yet)"
    feedback = ""
    for attempt in range(1, llm["max_attempts"] + 1):
        user = (f"{BRIEF[kind]}\n\nDo not repeat or closely echo any of these recent posts:\n{avoid}\n"
                f"{feedback}\nSave it with the save_recipe tool.")
        recipe = _call(llm["writer_model"], VOICE.format(brand=cfg["brand"]["name"]), user, RECIPE_TOOL)
        # Only the joke recipes need the word filter ("blood orange" and "a splash of rum" are fine for real food).
        hits = blocklist_hits(recipe) if kind == "not_edible" else []
        if hits:
            issues = [f"Blocked words used: {', '.join(hits)}"]
        else:
            review = _call(llm["checker_model"], CHECKER[kind],
                           "Review this post:\n" + json.dumps(recipe, indent=2, ensure_ascii=False),
                           CHECK_TOOL, max_tokens=800)
            if review["pass"]:
                log(f"  recipe ok on attempt {attempt}: {recipe['title']}")
                return recipe
            issues = review["issues"] or ["failed review"]
        log(f"  attempt {attempt} rejected: {'; '.join(issues)}")
        feedback = "\nA previous draft was rejected for: " + "; ".join(issues) + ". Write a different recipe that avoids these problems.\n"
    raise RuntimeError(f"No safe recipe after {llm['max_attempts']} attempts")


def build_caption(recipe: dict, kind: str, cfg: dict) -> str:
    c = cfg["caption"]
    lines = [recipe["caption_hook"].strip(), ""]
    if kind == "edible":
        lines.append(f"{recipe['servings']} · {recipe['time']}")
        if recipe.get("allergens"):
            lines.append("Contains: " + ", ".join(recipe["allergens"]))
        lines += ["Full recipe in the slides 👉", "", c["edible_footer"]]
    else:
        lines += ["Swipe for the 'method' 👉", "", c["not_edible_footer"]]
    tags = []
    for t in list(recipe["hashtags"]) + c["base_hashtags"]:
        t = "#" + re.sub(r"[^\w]", "", t.lstrip("#"))
        if t.lower() not in {x.lower() for x in tags} and len(t) > 1:
            tags.append(t)
    lines += ["", " ".join(tags[:15])]
    return "\n".join(lines)[:2200]
