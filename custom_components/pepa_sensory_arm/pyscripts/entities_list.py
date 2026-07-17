# entities_list.py
# Inject-ready entity context for the Pepa sensory arm.
#
# Builds the STATIC entity columns and PUBLISHES them to a sensor attribute so the
# agent's Jinja2 system prompt can read them with:
#     {{ state_attr('sensor.pepa_entity_context', 'csv') }}
#
# Columns (all static -- change only on HA config changes, hence cacheable):
#     entity_id, name, area, aliases, domain, services, volatile
# The LIVE columns (state, current_value) are intentionally NOT cached here --
# they stay rendered live in the system prompt so status reads are never stale.
#
# Supersedes entity_context.py functionally. entity_context.py is kept as-is for
# reference; all names here are distinct so the two files coexist in pyscripts/.
#
# Deploy  : <config>/pyscripts/entities_list.py
# Service : pyscripts.entities_list   (manual call; "Return response" -> {csv, count})
# Sensor  : sensor.pepa_entity_context
#             state           = entity count
#             attribute 'csv'  = static CSV string (header included)
# Refresh : on HA start, on entity_registry change, and a 10-min backstop
#           (expose-toggle changes don't always emit a registry event)

from homeassistant.components.homeassistant.exposed_entities import async_should_expose
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

SENSOR = "sensor.pepa_entity_context"


def _el_csv_field(val):
    s = str(val)
    if "," in s:
        return '"' + s + '"'
    return s


def _el_domain(entity_id):
    # Domain = chars before the first dot. Char loop avoids a dotted .split()
    # call, staying within this file's no-dotted-method-on-locals discipline.
    domain = ""
    for ch in entity_id:
        if ch == ".":
            break
        domain = domain + ch
    return domain


def _el_services(domain):
    # Static per-domain service map, pipe-delimited (commas would break the CSV
    # column; pipe matches the alias convention). Ported from the prompt's
    # Jinja2 if/elif so this static column leaves per-utterance rendering.
    if domain == "light":
        return "turn_on|turn_off|toggle|turn_on[brightness_pct]|turn_on[rgb_color]"
    if domain == "fan":
        return "turn_on|turn_off|toggle|set_percentage"
    if domain == "climate":
        return "set_temperature|set_hvac_mode|turn_on|turn_off"
    if domain == "cover":
        return "open_cover|close_cover|set_cover_position|toggle"
    if domain == "media_player":
        return "turn_on|turn_off|play_media|media_pause|media_stop|volume_set"
    if domain == "switch" or domain == "input_boolean":
        return "turn_on|turn_off|toggle"
    if domain == "lock":
        return "lock|unlock"
    if domain == "binary_sensor" or domain == "sensor" or domain == "weather":
        return "read_only"
    return "turn_on|turn_off"


def _el_build():
    """Build the static-column CSV. Returns (csv_str, count)."""
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

            # Volatile: direct label_id comparison (HA slugifies "volatile" -> id "volatile")
            raw_labels = getattr(entity_entry, "labels", None)
            if raw_labels:
                for label_id in raw_labels:
                    if str(label_id) == "volatile":
                        volatile = "true"

        name = st.attributes.get("friendly_name", entity_id)
        domain = _el_domain(entity_id)
        services = _el_services(domain)

        row = (
            _el_csv_field(entity_id)
            + ","
            + _el_csv_field(name)
            + ","
            + _el_csv_field(area_name)
            + ","
            + _el_csv_field(aliases)
            + ","
            + _el_csv_field(domain)
            + ","
            + _el_csv_field(services)
            + ","
            + volatile
        )
        rows.append(row)
        count = count + 1

    rows.sort()

    csv_lines = ["entity_id,name,area,aliases,domain,services,volatile"]
    for row in rows:
        csv_lines.append(row)

    csv_str = ""
    for line in csv_lines:
        if csv_str == "":
            csv_str = line
        else:
            csv_str = csv_str + "\n" + line

    return csv_str, count


def _el_publish():
    """Build and publish the static CSV to the sensor attribute for prompt injection."""
    csv_str, count = _el_build()
    state.set(SENSOR, count, csv=csv_str, count=count, friendly_name="Pepa Entity Context")
    log.info("entities_list: published {} exposed entities to {}".format(count, SENSOR))
    return csv_str, count


@service(supports_response="optional")
def entities_list():
    """Manual trigger: rebuild, publish, and return {csv, count}."""
    csv_str, count = _el_publish()
    return {"csv": csv_str, "count": count}


@time_trigger("startup")
def _el_startup():
    _el_publish()


@event_trigger("entity_registry_updated")
def _el_on_registry(**kwargs):
    _el_publish()


# Backstop for expose-toggle changes, which don't always emit a registry event.
# period() syntax can vary by pyscripts version; adjust the interval if needed.
@time_trigger("period(00:00, 10min)")
def _el_periodic():
    _el_publish()
