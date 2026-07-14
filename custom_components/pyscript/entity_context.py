# entity_context.py
# CSV entity context for the Pepa sensory arm (Home Agent LLM).
# Filters to HA-exposed entities only (replaces the old llm_conversation_context label).
# volatile flag derived from an HA label named "volatile".
#
# Deploy  : <config>/pyscript/entity_context.py
# Trigger : pyscript.entity_context   (Developer Tools -> Actions, "Return response" on)
#
# Returns:
#   csv     - CSV string ready for system-prompt injection
#   count   - number of exposed entities

from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import area_registry as ar
from homeassistant.components.homeassistant.exposed_entities import async_should_expose


def _csv_field(val):
    s = str(val)
    if "," in s:
        return '"' + s + '"'
    return s


@service(supports_response="optional")
def entity_context():
    entity_reg = er.async_get(hass)
    device_reg = dr.async_get(hass)
    area_reg = ar.async_get(hass)

    rows = []
    count = 0

    for st in hass.states.async_all():
        entity_id = st.entity_id

        # Only entities exposed to the HA conversation assistant
        if not async_should_expose(hass, "conversation", entity_id):
            continue

        area_name = "Unassigned"
        aliases = ""
        volatile = "false"

        entity_entry = entity_reg.async_get(entity_id)
        if entity_entry:

            # Area: entity -> device -> area
            device_id = getattr(entity_entry, "device_id", None)
            if device_id:
                device_entry = device_reg.async_get(device_id)
                area_id = getattr(device_entry, "area_id", None) if device_entry else None
                if area_id:
                    area_entry = area_reg.async_get_area(area_id)
                    if area_entry:
                        area_name = getattr(area_entry, "name", "Unassigned")

            # Aliases: strip ComputedNameType internal entries
            raw_aliases = getattr(entity_entry, "aliases", None)
            if raw_aliases:
                alias_str = ""
                for alias in raw_aliases:
                    alias_s = str(alias)
                    if "ComputedNameType" not in alias_s:
                        if alias_str == "":
                            alias_str = alias_s
                        else:
                            alias_str = alias_str + "|" + alias_s
                aliases = alias_str

            # Volatile: direct label_id comparison.
            # No registry lookup, no dotted calls. HA slugifies the label
            # name "volatile" to the id "volatile", so we match the id.
            raw_labels = getattr(entity_entry, "labels", None)
            if raw_labels:
                for label_id in raw_labels:
                    if str(label_id) == "volatile":
                        volatile = "true"

        name = st.attributes.get("friendly_name", entity_id)
        row = (
            _csv_field(entity_id)
            + ","
            + _csv_field(name)
            + ","
            + _csv_field(area_name)
            + ","
            + _csv_field(aliases)
            + ","
            + volatile
        )
        rows.append(row)
        count = count + 1

    rows.sort()

    csv_lines = ["entity_id,name,area,aliases,volatile"]
    for row in rows:
        csv_lines.append(row)

    csv_str = ""
    for line in csv_lines:
        if csv_str == "":
            csv_str = line
        else:
            csv_str = csv_str + "\n" + line

    log.info("entity_context: {} exposed entities".format(count))

    return {
        "csv": csv_str,
        "count": count,
    }
