"""Parse a natural-language prompt into business category and location."""


def parse_prompt(prompt: str) -> tuple[str, str]:
    """Extract business_category and location from a natural-language prompt.

    Handles prompts like:
        - "coffee shops in America" -> ("coffee shops", "America")
        - "dentist in New York" -> ("dentist", "New York")
        - "burger shop near me" -> ("burger shop", "")
        - "restaurants" -> ("restaurants", "")

    If "in" is not found, the entire string is treated as the category.
    """
    trimmed = prompt.strip()
    if not trimmed:
        return ("", "")

    # Remove common question prefixes
    prefixes = [
        "where is the ",
        "where are the ",
        "find me ",
        "show me ",
        "i need ",
        "i'm looking for ",
        "looking for ",
        "search for ",
        "search ",
        "find ",
    ]
    cleaned = trimmed
    for prefix in prefixes:
        if cleaned.lower().startswith(prefix):
            cleaned = cleaned[len(prefix):]
            break

    # Remove trailing "near me" / "close to me" etc.
    suffixes = [" near me", " close to me", " nearby", " around me", " in my area"]
    for suffix in suffixes:
        if cleaned.lower().endswith(suffix):
            cleaned = cleaned[: -len(suffix)]
            break

    # Split on "in" — the primary delimiter
    parts = cleaned.split(" in ", 1)
    if len(parts) == 2:
        category = parts[0].strip()
        location = parts[1].strip()
        if category and location:
            return (category, location)

    # Split on "near" as secondary
    parts = cleaned.split(" near ", 1)
    if len(parts) == 2:
        category = parts[0].strip()
        location = parts[1].strip()
        if category and location:
            return (category, location)

    # No split found — entire string is category
    return (cleaned.strip(), "")


if __name__ == "__main__":
    # Quick self-test
    tests = [
        ("coffee shops in America", ("coffee shops", "America")),
        ("dentist in New York", ("dentist", "New York")),
        ("burger shop near me", ("burger shop", "")),
        ("restaurants", ("restaurants", "")),
        ("Where is the nearest pizza place in Chicago", ("nearest pizza place", "Chicago")),
        ("Find me bakeries in London", ("bakeries", "London")),
    ]
    for prompt, expected in tests:
        result = parse_prompt(prompt)
        status = "PASS" if result == expected else "FAIL"
        print(f"{status}: '{prompt}' -> {result}")
