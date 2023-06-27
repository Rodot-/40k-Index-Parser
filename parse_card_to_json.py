import json
import re

from pprint import pprint

from py_pdf_parser.loaders import load_file
from py_pdf_parser.visualise import visualise
from py_pdf_parser.filtering import ElementList

FONT_MAPPING = {
    "VDSYER+ConduitITCStd-ExtraBold,14.0": "title",
    "TUOTXV+ConduitITCStd-Bold,9.0": "section",  # Stuff on the right bar
    "TUOTXV+ConduitITCStd-Bold,7.5": "list_ability",
    "TUOTXV+ConduitITCStd-Regular,7.5": "static_ability",
}


def until(iterable, condition):

    for item in iterable:
        if condition(item):
            yield item
        else:
            break


def parse_card(page):

    output = {}
    output["NAME"] = page.elements[0].text()

    ability_section = page.elements.filter_by_text_equal(
        "ABILITIES"
    ).extract_single_element()
    ability_elements = page.elements.below(
        ability_section, inclusive=True
    ).filter_by_font("section")
    right_bar_elements = ability_elements
    for element in right_bar_elements:
        name = element.text()
        if name == "INVULNERABLE SAVE":
            output[name] = page.elements.to_the_right_of(element)[0].text()
            continue
        else:
            output[name] = {}
        condition = lambda x: x not in right_bar_elements
        elements = list(until(page.elements.below(element), condition))
        elements = ElementList(page.document, {e._index for e in elements})
        enumerated_elements = elements.filter_by_text_contains(":")
        list_abilities = enumerated_elements.filter_by_font("list_ability")
        static_abilities = enumerated_elements.filter_by_font("static_ability")
        section_description = (
            elements.filter_by_font("static_ability") - static_abilities
        )
        for ability in list_abilities:
            key, value = [t.strip() for t in ability.text().split(":", 1)]
            output[name][key] = [t.strip() for t in value.split(", ")]
        for ability in static_abilities:
            key, value = [t.strip() for t in ability.text().split(":", 1)]
            output[name][key] = value.strip()
        if section_description:
            output[name] = section_description[0].text()

    faction_keywords = page.elements.filter_by_text_contains(
        "FACTION KEYWORDS:"
    )[0]
    key, value = faction_keywords.text().split(":", 1)
    output[key.strip()] = [v.strip() for v in value.split(", ")]
    keywords_element = page.elements.filter_by_text_contains(
        "KEYWORDS:"
    )  # need to change this for multi-model keywords
    keywords = page.elements.between(
        keywords_element[0], faction_keywords, inclusive=True
    )[:-1]
    keywords = ", ".join([keyword.text() for keyword in keywords])
    if (
        len(keywords.split(":", 1)) == 2
    ):  # TODO: Handle different models with different keys
        key, values = keywords.split(":", 1)
        output[key.strip()] = [v.strip() for v in values.split(", ")]

    weapon_start = page.elements.filter_by_text_contains("WEAPONS\n")[0]
    weapons = page.elements.below(weapon_start, inclusive=True).above(
        keywords_element[0]
    )
    section = None
    output["RANGED WEAPONS"] = {}
    output["MELEE WEAPONS"] = {}
    for weapon in weapons:
        if "Italic" in weapon.font_name or weapon.text().startswith(
            "One Shot:"
        ):
            # Then this is just a note on the weapon
            continue  # TODO: Deal with it later
        text = weapon.text()
        if "–" in text:  # This weapon has multiple profiles!
            # TODO: Generally handle this
            text = text.split("\n", 1)[0]  # For now we'll just take the first
        if text.startswith("RANGED WEAPONS"):
            section = "RANGED WEAPONS"
            text = text[14:].strip()
        elif text.startswith("MELEE WEAPONS"):
            section = "MELEE WEAPONS"
            text = text.split("\n", 1)[1].strip()
        if "[" in text:
            name, abilities = text.split("[")
        else:
            name = text
            abilities = []
        name = name.strip()
        if abilities:
            abilities = abilities.strip().strip("]").strip("[").split(",")
            abilities = [a.strip() for a in abilities]
        
        output[section][name] = {}
        output[section][name]["ABILITIES"] = abilities

        statline = page.elements.to_the_right_of(
            weapon
        ) 
        if len(statline.filter_by_text_contains("RANGE")) < 1:
            if len(statline) == 1:  # this is a weapon ability
                output[section][name]["ABILITIES"].append(statline[0].text())
                continue
            if len(statline.filter_by_regex('\d{1,3}"|Melee')) == 0:
                if name == "Deathstrike missile":
                    return output
                import pdb

                pdb.set_trace()
            statline_start = statline.filter_by_regex('\d{1,3}"|Melee')[0]
            statline = statline.after(statline_start, inclusive=True)
            statline = dict(
                (
                    map(str.strip, (s, e.text()))
                    for e, s in zip(
                        statline,
                        (
                            "RANGE",
                            "A",
                            "WS" if "Melee" in statline_start.text() else "BS",
                            "S",
                            "AP",
                            "D",
                        ),
                    )
                )
            )
        else:
            statline = statline.after(
                statline.filter_by_text_contains("RANGE")[0], inclusive=True
            )[:6]

            statline = dict(
                ((map(str.strip, e.text().split("\n", 1)) for e in statline))
            )
        output[section][name].update(statline)

    return output


if __name__ == "__main__":

    document = load_file(
        "AstraMilitarum.pdf",
        font_mapping=FONT_MAPPING,
        font_mapping_is_regex=True,
        regex_flags=re.MULTILINE,
    )
    with open("test.json", "w") as f:
        for page_num in list(range(7, 125, 2)):
            page = document.get_page(page_num)
            try:
                output = parse_card(page)
                f.write(json.dumps(output, indent=4, sort_keys=True))
            except Exception as e:
                print(f"Ran Into Exception on Page {page_num}:")
                print(e)
