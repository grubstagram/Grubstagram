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
        "(poultry and minced meat cooked through, no raw flour or raw egg eaten as-is). Steps must use every ingredient, "
        "and every ingredient a step uses must be in the list (salt, pepper, water and cooking oil count: list them too)."
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
        "allergens missing from the allergen list; anything not actually food. Minor style issues are not failures. "
        "Pantry staples (salt, pepper, water, a little cooking oil) may appear in the steps without being listed: "
        "that is never a failure."
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


def _extract(content: list, tool: dict) -> dict | None:
    """Prefer the tool call; fall back to a JSON object in plain text."""
    for block in content:
        if block.get("type") == "tool_use" and block.get("name") == tool["name"]:
            return block["input"]
    text = "".join(b.get("text", "") for b in content if b.get("type") == "text")
    m = re.search(r"\{.*\}", text, re.S)
    if m:
        try:
            data = json.loads(m.group(0))
            if all(k in data for k in tool["input_schema"].get("required", [])):
                return data
        except json.JSONDecodeError:
            pass
    return None


def _call(model: str, system: str, user: str, tool: dict, max_tokens: int = 4000, tries: int = 3) -> dict:
    # Newer Claude models reject a forced tool_choice, so we ask firmly and let the model pick the tool.
    system = (f"{system}\n\nAnswer ONLY by calling the `{tool['name']}` tool, straight away and exactly once. "
              "Do not write any analysis or plain text before or after it; put your reasons inside the tool call.")
    last = ""
    for _ in range(tries):
        resp = httpx.post(
            API,
            headers={"x-api-key": env("ANTHROPIC_API_KEY"), "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={"model": model, "max_tokens": max_tokens, "system": system,
                  "tools": [tool], "tool_choice": {"type": "auto"},
                  "messages": [{"role": "user", "content": user}]},
            timeout=180,
        )
        if resp.status_code in (429, 500, 502, 503, 529):
            last = f"Anthropic API {resp.status_code}: {resp.text[:300]}"
            continue
        if resp.status_code >= 400:
            raise RuntimeError(f"Anthropic API {resp.status_code}: {resp.text[:500]}")
        body = resp.json()
        out = _extract(body.get("content", []), tool)
        if out is not None:
            return out
        text = "".join(b.get("text", "") for b in body.get("content", []) if b.get("type") == "text")
        last = f"model replied without using the tool (stop: {body.get('stop_reason')}; said: {text[:160]!r})"
    raise RuntimeError(f"Anthropic call failed after {tries} tries: {last}")


def blocklist_hits(recipe: dict, extra: list[str] | None = None) -> list[str]:
    text = json.dumps(recipe, ensure_ascii=False)
    hits = {m.group(0).lower() for m in BLOCKLIST.finditer(text)}
    if extra:
        rx = re.compile(r"\b(" + "|".join(re.escape(w) for w in extra) + r")s?\b", re.I)
        hits |= {m.group(0).lower() for m in rx.finditer(text)}
    return sorted(hits)


COPYRIGHT_WRITER = (
    "Use today's inspiration for mood, ideas and tone only. Invent your own dish names and words. "
    "Never name, describe or depict copyrighted characters, and never quote or use the titles, catchphrases or "
    "invented words of books, films or TV still in copyright (no Wonka, BFG, Twits, snozzcumbers, Hogwarts and so on). "
    "Public-domain tales (Grimm, Andersen, English fairy tales, Alice in Wonderland, The Wind in the Willows, Peter Pan, "
    "Dracula, Frankenstein, Macbeth) may be named. An author may be name-checked in the caption as homage "
    "(e.g. 'a potion Roald Dahl would be proud of') but never in the image prompt, and no real people appear in the image."
)
COPYRIGHT_CHECK = (" Also fail it if it names or depicts a copyrighted character, quotes a copyrighted book or film, "
                   "or uses a copyrighted title, catchphrase or invented word (public-domain tales and a passing author "
                   "name-check in the caption are fine), or if the image prompt names an author, film or real person.")


def write_recipe(kind: str, past_titles: list[str], cfg: dict, log=print, theme: dict | None = None,
                 inspiration: str | None = None, owner_note: str | None = None) -> dict:
    llm = cfg["llm"]
    theme = theme or {}
    brief = theme.get(f"{kind}_brief") or BRIEF[kind]
    checker = (theme.get(f"{kind}_checker") or CHECKER[kind]) + COPYRIGHT_CHECK + (" " + theme["extra_check"] if theme.get("extra_check") else "")
    brand = cfg["brand"]["name"]
    checker += (f" The account's own name ({brand}) and hashtags made from it (e.g. #{brand.replace(' ', '')}) "
                "are ours to use and are never a copyright problem.")
    if inspiration:
        brief = f"{brief}\n\nToday's inspiration: {inspiration}.\n{COPYRIGHT_WRITER}"
    if owner_note is not None:
        note = owner_note.strip()[:500]
        brief += ("\n\nThe account owner rejected an earlier draft for today, so write something clearly different"
                  + (f'. Their note about what they want: "{note}". Follow it unless it conflicts with the rules above.' if note else "."))
    extra_block = theme.get("block", []) if kind == "not_edible" else []
    avoid = "\n".join(f"- {t}" for t in past_titles[-llm["history_window"]:]) or "- (none yet)"
    feedback = ""
    for attempt in range(1, llm["max_attempts"] + 1):
        user = (f"{brief}\n\nDo not repeat or closely echo any of these recent posts:\n{avoid}\n"
                f"{feedback}\nSave it with the save_recipe tool.")
        recipe = _call(llm["writer_model"], VOICE.format(brand=cfg["brand"]["name"]), user, RECIPE_TOOL)
        # Only the joke recipes need the word filter ("blood orange" and "a splash of rum" are fine for real food).
        hits = blocklist_hits(recipe, extra_block) if kind == "not_edible" else []
        if hits:
            issues = [f"Blocked words used: {', '.join(hits)}"]
        else:
            post = "Review this post:\n" + json.dumps(recipe, indent=2, ensure_ascii=False)
            try:
                review = _call(llm["checker_model"], checker, post, CHECK_TOOL, max_tokens=2000)
            except RuntimeError as e:   # the small model misbehaved: let the writer model do the check
                log(f"  checker fell back to {llm['writer_model']}: {e}")
                review = _call(llm["writer_model"], checker, post, CHECK_TOOL, max_tokens=2000)
            if review["pass"]:
                log(f"  recipe ok on attempt {attempt}: {recipe['title']}")
                return recipe
            issues = review["issues"] or ["failed review"]
        log(f"  attempt {attempt} rejected: {'; '.join(issues)}")
        feedback = "\nA previous draft was rejected for: " + "; ".join(issues) + ". Write a different recipe that avoids these problems.\n"
    raise RuntimeError(f"No safe recipe after {llm['max_attempts']} attempts")


def build_caption(recipe: dict, kind: str, cfg: dict, theme: dict | None = None) -> str:
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
    for t in list((theme or {}).get("hashtags", [])) + list(recipe["hashtags"]) + c["base_hashtags"]:
        t = "#" + re.sub(r"[^\w]", "", t.lstrip("#"))
        if t.lower() not in {x.lower() for x in tags} and len(t) > 1:
            tags.append(t)
    lines += ["", " ".join(tags[:15])]
    return "\n".join(lines)[:2200]
