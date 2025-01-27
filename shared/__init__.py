from dataclasses import dataclass, field
from typing import Any, Dict, Optional, List, Tuple

from hassil import parse_sentence
from hassil.intents import SlotList, TextSlotList, is_template
from hassil.recognize import RecognizeResult
from hassil.sample import sample_expression
from jinja2 import BaseLoader, Environment, StrictUndefined


@dataclass
class State:
    """Minimal HA-like state object for responses."""

    entity_id: str
    name: str
    state: str
    attributes: Dict[str, Any] = field(default_factory=dict)
    area_id: Optional[str] = None
    _domain: Optional[str] = None

    @property
    def domain(self) -> str:
        if self._domain is None:
            self._domain = self.entity_id.split(".", maxsplit=1)[0]

        return self._domain

    @property
    def state_with_unit(self) -> str:
        unit = self.attributes.get("unit_of_measurement")
        if unit:
            return f"{self.state} {unit}"

        return self.state


@dataclass
class AreaEntry:
    """Minimal HA-like area object for responses."""

    id: str
    name: str


def get_matched_states(
    states: List[State], areas: List[AreaEntry], result: RecognizeResult
) -> Tuple[List[State], List[State]]:
    """Split states into matched/unmatched."""
    if result.intent.name != "HassGetState":
        return states, []

    # Implement some matching logic for HassGetState
    entity_name: Optional[str] = None
    name_entity = result.entities.get("name")
    if name_entity is not None:
        entity_name = _normalize_name(name_entity.value)

    area_name: Optional[str] = None
    area_entity = result.entities.get("area")
    if area_entity is not None:
        area_name = _normalize_name(area_entity.value)

    domain_name: Optional[str] = None
    domain_entity = result.entities.get("domain")
    if domain_entity is not None:
        domain_name = _normalize_name(domain_entity.value)

    device_class: Optional[str] = None
    device_class_entity = result.entities.get("device_class")
    if device_class_entity is not None:
        device_class = device_class_entity.value

    state_name: Optional[str] = None
    state_entity = result.entities.get("state")
    if state_entity is not None:
        state_name = state_entity.value

    area_ids = {_normalize_name(area.name): area.id for area in areas}
    matched: List[State] = []
    unmatched: List[State] = []

    for state in states:
        if (entity_name is not None) and (_normalize_name(state.name) != entity_name):
            # Filter by entity name
            continue

        if (area_name is not None) and (state.area_id != area_ids.get(area_name)):
            # Filter by area
            continue
        if (domain_name is not None) and (domain_name != state.domain):
            # Filter by domain
            continue

        if (device_class is not None) and (
            device_class != state.attributes.get("device_class")
        ):
            # Filter by entity name
            continue

        if state_name is not None:
            # Match state
            if state.state == state_name:
                matched.append(state)
            else:
                unmatched.append(state)
        else:
            # Everything "matches" with no state constraint
            matched.append(state)

    # print(matched, area_name, state_name, entity_name, domain_name)

    return matched, unmatched


def _normalize_name(name: str) -> str:
    return name.strip().casefold()


def get_jinja2_environment() -> Environment:
    """Create default Jinja2 environment."""
    return Environment(loader=BaseLoader(), undefined=StrictUndefined)


def render_response(
    response_template: str,
    result: RecognizeResult,
    matched: List[State],
    unmatched: Optional[List[State]] = None,
    env: Optional[Environment] = None,
) -> str:
    """Renders a response template using Jinja2."""
    assert response_template, "Empty response template"
    if unmatched is None:
        unmatched = []

    # First matched or unmatched state
    state1: Optional[State] = None
    if matched:
        state1 = matched[0]
    elif unmatched:
        state1 = unmatched[0]

    if env is None:
        env = get_jinja2_environment()

    return env.from_string(response_template).render(
        {
            "slots": {
                entity.name: entity.text or entity.value
                for entity in result.entities_list
            },
            "state": state1,
            "query": {"matched": matched, "unmatched": unmatched},
        }
    )


def get_slot_lists(fixtures: dict[str, Any]) -> dict[str, SlotList]:
    # Load test areas and entities for language
    slot_lists: dict[str, SlotList] = {}

    # Generate names from templates
    area_names: List[str] = []
    for area in fixtures["areas"]:
        area_name = area["name"]
        if is_template(area_name):
            area_names.extend(sample_expression(parse_sentence(area_name)))
        else:
            area_names.append(area_name)

    slot_lists["area"] = TextSlotList.from_strings(area_names)

    entity_tuples: List[Tuple[str, str, Dict[str, Any]]] = []
    for entity in fixtures["entities"]:
        context = _entity_context(entity)
        entity_name = entity["name"]
        if is_template(entity_name):
            entity_names = list(sample_expression(parse_sentence(entity_name)))
        else:
            entity_names = [entity_name]

        entity_tuples.extend((name, name, context) for name in entity_names)

    slot_lists["name"] = TextSlotList.from_tuples(entity_tuples)

    return slot_lists


def _entity_context(entity: dict[str, Any]) -> dict[str, Any]:
    """Extract matching context from test fixture entity."""
    entity_id = entity["id"]
    domain = entity_id.split(".", maxsplit=1)[0]
    return {"domain": domain}


def get_states(fixtures: dict[str, Any]) -> List[State]:
    states: List[State] = []
    for entity in fixtures.get("entities", []):
        states.append(
            State(
                entity_id=entity["id"],
                name=entity["name"],
                state=entity.get("state", "off"),
                area_id=entity.get("area"),
                attributes=entity.get("attributes", {}),
            )
        )
    return states


def get_areas(fixtures: dict[str, Any]) -> List[AreaEntry]:
    areas: List[AreaEntry] = []
    for area in fixtures.get("areas", []):
        areas.append(
            AreaEntry(
                id=area["id"],
                name=area["name"],
            )
        )
    return areas
