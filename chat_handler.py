"""
Gemini-powered chat handler for natural-language route editing.

Receives current routes + user message, asks Gemini to translate the
intent into structured tool calls, then applies them to the routes.
The recalculation of times/distances is delegated to
route_optimizer.recalculate_manually_adjusted_routes().
"""
import os
import json
from typing import List, Dict, Tuple, Optional

import google.generativeai as genai

DEFAULT_MODEL = os.environ.get('GEMINI_MODEL', 'gemini-2.5-flash')
ALLOWED_MODELS = {'gemini-2.5-flash', 'gemini-2.5-pro'}


SYSTEM_INSTRUCTION = """You are a school bus route editor assistant. The user
will describe changes they want in natural language; you translate those
changes into one or more tool calls.

Rules:
- ALWAYS respond in English, regardless of the language the user writes in.
  All summaries, clarifications, and free-text replies must be English only.
- Buses are referenced by their 1-indexed `bus_number` (1, 2, 3, ...).
- Students are referenced by `student_id` (preferred) or `name`. If a name is
  ambiguous (matches multiple students), call `ask_clarification` instead of
  guessing.
- A single user message may contain multiple independent operations. Emit one
  tool call per operation; they will all be applied atomically.
- Only emit tool calls for operations the user explicitly requested. Do not
  reorganize the fleet on your own initiative.
- When you have enough information to act, return tool calls. When the request
  is ambiguous or missing context, return `ask_clarification` with a precise
  question. Do not return both.
"""


# ---------------------------------------------------------------------------
# Tool declarations (Gemini function-calling schema)
# ---------------------------------------------------------------------------

TOOL_DECLARATIONS = [
    {
        "name": "move_students",
        "description": "Move one or more students from one bus to another. Use this when the user says things like 'move A, B, C from bus 5 to bus 6' or 'chuyển 3 bạn ở bus 2 sang bus 7'.",
        "parameters": {
            "type": "object",
            "properties": {
                "student_refs": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of student identifiers (student_id preferred, otherwise name)."
                },
                "from_bus": {"type": "integer", "description": "Source bus_number (1-indexed). Use 0 if the source is unknown — the resolver will find each student."},
                "to_bus": {"type": "integer", "description": "Destination bus_number (1-indexed)."}
            },
            "required": ["student_refs", "to_bus"]
        }
    },
    {
        "name": "swap_students",
        "description": "Swap two students between their respective buses. Each student goes to the other's bus.",
        "parameters": {
            "type": "object",
            "properties": {
                "student_a_ref": {"type": "string", "description": "First student (id or name)."},
                "student_b_ref": {"type": "string", "description": "Second student (id or name)."}
            },
            "required": ["student_a_ref", "student_b_ref"]
        }
    },
    {
        "name": "move_to_new_bus",
        "description": "Move students into a brand-new bus (created on the fly). Use this when the user wants to split a bus or extract students into their own route.",
        "parameters": {
            "type": "object",
            "properties": {
                "student_refs": {
                    "type": "array",
                    "items": {"type": "string"}
                }
            },
            "required": ["student_refs"]
        }
    },
    {
        "name": "merge_buses",
        "description": "Move every student from `from_bus` into `to_bus`, then remove the empty source bus.",
        "parameters": {
            "type": "object",
            "properties": {
                "from_bus": {"type": "integer"},
                "to_bus": {"type": "integer"}
            },
            "required": ["from_bus", "to_bus"]
        }
    },
    {
        "name": "reorder_pickup",
        "description": "Reorder the pickup sequence within a single bus.",
        "parameters": {
            "type": "object",
            "properties": {
                "bus_number": {"type": "integer"},
                "new_order": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Student ids/names in the desired pickup order. Must contain every student currently on the bus."
                }
            },
            "required": ["bus_number", "new_order"]
        }
    },
    {
        "name": "remove_students",
        "description": "Remove students from their bus (they become unassigned).",
        "parameters": {
            "type": "object",
            "properties": {
                "student_refs": {
                    "type": "array",
                    "items": {"type": "string"}
                }
            },
            "required": ["student_refs"]
        }
    },
    {
        "name": "ask_clarification",
        "description": "Ask the user a clarifying question when the request is ambiguous or refers to a student/bus that cannot be uniquely resolved.",
        "parameters": {
            "type": "object",
            "properties": {
                "question": {"type": "string"},
                "options": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of disambiguation choices to present to the user."
                }
            },
            "required": ["question"]
        }
    }
]


# ---------------------------------------------------------------------------
# Route helpers
# ---------------------------------------------------------------------------

def compact_routes_for_prompt(routes: List[Dict]) -> Dict:
    """Strip geometry/segments/etc. — keep only what the model needs to reason."""
    compact = []
    for idx, r in enumerate(routes, start=1):
        compact.append({
            "bus_number": idx,
            "vehicle_id": r.get('vehicle_id', ''),
            "vehicle_plate": r.get('vehicle_plate', ''),
            "capacity": r.get('vehicle_capacity', 40),
            "student_count": len(r.get('students', [])),
            "ride_time_minutes": r.get('time_minutes', 0),
            "students": [
                {
                    "student_id": str(s.get('student_id', s.get('id', ''))),
                    "name": s.get('name', ''),
                    "pickup_time": s.get('pickup_time', '')
                }
                for s in r.get('students', [])
            ]
        })
    return {"buses": compact}


def _find_student(routes: List[Dict], ref: str) -> List[Tuple[int, int, Dict]]:
    """Return all (bus_index, student_index, student) matching ref by id or name."""
    if ref is None:
        return []
    ref_str = str(ref).strip()
    ref_lower = ref_str.lower()
    matches = []
    for bi, route in enumerate(routes):
        for si, student in enumerate(route.get('students', [])):
            sid = str(student.get('student_id', student.get('id', ''))).strip()
            sname = str(student.get('name', '')).strip()
            if sid and sid == ref_str:
                matches.append((bi, si, student))
                continue
            if sname.lower() == ref_lower:
                matches.append((bi, si, student))
                continue
            # Looser substring fallback (only if no exact matches found yet)
            if ref_lower and ref_lower in sname.lower():
                matches.append((bi, si, student))
    # De-duplicate while preserving order
    seen = set()
    deduped = []
    for m in matches:
        key = (m[0], m[1])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(m)
    return deduped


def _resolve_refs(routes: List[Dict], refs: List[str]) -> Tuple[List[Tuple[int, int, Dict]], List[str]]:
    """Resolve a list of student refs. Returns (resolved, errors)."""
    resolved = []
    errors = []
    for ref in refs:
        matches = _find_student(routes, ref)
        if not matches:
            errors.append(f"Student '{ref}' not found")
        elif len(matches) > 1:
            names = ", ".join(f"{m[2].get('name','?')} (id {m[2].get('student_id','?')})" for m in matches[:5])
            errors.append(f"Ambiguous reference '{ref}' — matches: {names}")
        else:
            resolved.append(matches[0])
    return resolved, errors


def _bus_index(routes: List[Dict], bus_number: int) -> Optional[int]:
    """Convert 1-indexed bus_number to list index. None if out of range."""
    if bus_number is None:
        return None
    idx = int(bus_number) - 1
    if 0 <= idx < len(routes):
        return idx
    return None


# ---------------------------------------------------------------------------
# Tool execution
# ---------------------------------------------------------------------------

def _apply_move_students(routes, args):
    refs = args.get('student_refs', [])
    to_bus = args.get('to_bus')
    to_idx = _bus_index(routes, to_bus)
    if to_idx is None:
        return {"ok": False, "error": f"Destination bus {int(to_bus) if to_bus else '?'} does not exist"}
    resolved, errors = _resolve_refs(routes, refs)
    if errors:
        return {"ok": False, "error": "; ".join(errors)}
    moved = []
    # Remove from highest indices first so earlier indices stay valid.
    resolved.sort(key=lambda m: (m[0], -m[1]))
    for bi, si, student in resolved:
        if bi == to_idx:
            continue  # already on the destination bus
        routes[bi]['students'].pop(si)
        routes[to_idx]['students'].append(student)
        moved.append(student.get('name', student.get('student_id', '?')))
    return {"ok": True, "summary": f"Moved {len(moved)} student(s) to Bus {int(to_bus)}: {', '.join(moved)}"}


def _apply_swap_students(routes, args):
    a_ref = args.get('student_a_ref')
    b_ref = args.get('student_b_ref')
    a_matches = _find_student(routes, a_ref)
    b_matches = _find_student(routes, b_ref)
    if len(a_matches) != 1:
        return {"ok": False, "error": f"Cannot resolve student '{a_ref}' uniquely"}
    if len(b_matches) != 1:
        return {"ok": False, "error": f"Cannot resolve student '{b_ref}' uniquely"}
    abi, asi, a_student = a_matches[0]
    bbi, bsi, b_student = b_matches[0]
    if abi == bbi:
        return {"ok": False, "error": "Both students are on the same bus — use reorder_pickup instead"}
    routes[abi]['students'][asi] = b_student
    routes[bbi]['students'][bsi] = a_student
    return {"ok": True, "summary": f"Swapped {a_student.get('name','?')} (Bus {abi+1}) ↔ {b_student.get('name','?')} (Bus {bbi+1})"}


def _apply_move_to_new_bus(routes, args):
    refs = args.get('student_refs', [])
    resolved, errors = _resolve_refs(routes, refs)
    if errors:
        return {"ok": False, "error": "; ".join(errors)}
    new_route = {
        'students': [],
        'distance_km': 0,
        'time_minutes': 0,
        'student_count': 0,
        'segments': [],
        'bus_number': f"Bus {len(routes) + 1}",
        'vehicle_plate': 'Pending',
        'vehicle_id': '',
        'vehicle_capacity': 40
    }
    resolved.sort(key=lambda m: (m[0], -m[1]))
    moved = []
    for bi, si, student in resolved:
        routes[bi]['students'].pop(si)
        new_route['students'].append(student)
        moved.append(student.get('name', '?'))
    new_route['student_count'] = len(new_route['students'])
    routes.append(new_route)
    return {"ok": True, "summary": f"Created new Bus {len(routes)} with {len(moved)} student(s): {', '.join(moved)}"}


def _apply_merge_buses(routes, args):
    from_bus = args.get('from_bus')
    to_bus = args.get('to_bus')
    fi = _bus_index(routes, from_bus)
    ti = _bus_index(routes, to_bus)
    if fi is None or ti is None:
        return {"ok": False, "error": f"Bus index out of range (from={from_bus}, to={to_bus})"}
    if fi == ti:
        return {"ok": False, "error": "Cannot merge a bus with itself"}
    moved_count = len(routes[fi]['students'])
    routes[ti]['students'].extend(routes[fi]['students'])
    routes.pop(fi)
    return {"ok": True, "summary": f"Merged Bus {int(from_bus)} into Bus {int(to_bus)} ({moved_count} student(s) transferred). Bus {int(from_bus)} removed."}


def _apply_reorder_pickup(routes, args):
    bus_number = args.get('bus_number')
    new_order = args.get('new_order', [])
    bi = _bus_index(routes, bus_number)
    if bi is None:
        return {"ok": False, "error": f"Bus {bus_number} does not exist"}
    current = routes[bi]['students']
    if len(new_order) != len(current):
        return {"ok": False, "error": f"Bus {bus_number} has {len(current)} students but new_order has {len(new_order)}"}
    reordered = []
    used = set()
    for ref in new_order:
        matches = [(si, s) for si, s in enumerate(current)
                   if str(s.get('student_id', s.get('id',''))).strip() == str(ref).strip()
                   or str(s.get('name','')).strip().lower() == str(ref).strip().lower()]
        matches = [m for m in matches if m[0] not in used]
        if not matches:
            return {"ok": False, "error": f"Student '{ref}' not on Bus {bus_number}"}
        used.add(matches[0][0])
        reordered.append(matches[0][1])
    routes[bi]['students'] = reordered
    return {"ok": True, "summary": f"Reordered {len(reordered)} pickups on Bus {int(bus_number)}"}


def _apply_remove_students(routes, args):
    refs = args.get('student_refs', [])
    resolved, errors = _resolve_refs(routes, refs)
    if errors:
        return {"ok": False, "error": "; ".join(errors)}
    resolved.sort(key=lambda m: (m[0], -m[1]))
    removed = []
    for bi, si, student in resolved:
        routes[bi]['students'].pop(si)
        removed.append(student.get('name', '?'))
    return {"ok": True, "summary": f"Removed {len(removed)} student(s): {', '.join(removed)}"}


TOOL_HANDLERS = {
    'move_students': _apply_move_students,
    'swap_students': _apply_swap_students,
    'move_to_new_bus': _apply_move_to_new_bus,
    'merge_buses': _apply_merge_buses,
    'reorder_pickup': _apply_reorder_pickup,
    'remove_students': _apply_remove_students,
}


# ---------------------------------------------------------------------------
# Validation after recalculation
# ---------------------------------------------------------------------------

def collect_warnings(routes: List[Dict], max_ride_time: int) -> List[str]:
    """Spot capacity overflows and time violations after edits."""
    warnings = []
    for idx, r in enumerate(routes, start=1):
        cap = r.get('vehicle_capacity', 40)
        count = len(r.get('students', []))
        if count > cap:
            warnings.append(f"Bus {idx} over capacity: {count}/{cap}")
        ride = r.get('time_minutes', 0)
        if ride and ride > max_ride_time:
            warnings.append(f"Bus {idx} ride time {ride} min exceeds limit ({max_ride_time} min)")
        if r.get('time_violations'):
            for v in r['time_violations']:
                warnings.append(f"Bus {idx}: {v.get('student','?')} ride {v.get('ride_minutes','?')} min exceeds limit")
    return warnings


# ---------------------------------------------------------------------------
# Gemini interaction
# ---------------------------------------------------------------------------

def _build_genai_tools():
    """Convert TOOL_DECLARATIONS into google.generativeai Tool objects."""
    return [{"function_declarations": TOOL_DECLARATIONS}]


def _history_to_genai(history: List[Dict]) -> List[Dict]:
    """Convert client-side history (role + text) into Gemini contents format."""
    contents = []
    for turn in history or []:
        role = turn.get('role', 'user')
        text = turn.get('text', '')
        if not text:
            continue
        gemini_role = 'user' if role == 'user' else 'model'
        contents.append({"role": gemini_role, "parts": [{"text": text}]})
    return contents


def run_chat(message: str, routes: List[Dict], history: List[Dict],
             model_name: str = DEFAULT_MODEL) -> Dict:
    """
    Main entry point. Returns:
      {
        'tool_calls': [{name, args, result}, ...],
        'updated_routes': [...],
        'ai_message': '...',
        'clarification': '...' or None,
        'error': '...' or None
      }
    """
    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        return {"error": "GEMINI_API_KEY is not configured"}

    if model_name not in ALLOWED_MODELS:
        model_name = DEFAULT_MODEL

    genai.configure(api_key=api_key)

    compact_state = compact_routes_for_prompt(routes)
    state_json = json.dumps(compact_state, ensure_ascii=False)

    user_turn = (
        f"Current route state:\n```json\n{state_json}\n```\n\n"
        f"User request: {message}"
    )

    contents = _history_to_genai(history)
    contents.append({"role": "user", "parts": [{"text": user_turn}]})

    try:
        model = genai.GenerativeModel(
            model_name=model_name,
            system_instruction=SYSTEM_INSTRUCTION,
            tools=_build_genai_tools(),
        )
        response = model.generate_content(contents)
    except Exception as e:
        return {"error": f"Gemini call failed: {e}"}

    # Walk the response for function calls and text.
    tool_calls_made = []
    clarification = None
    free_text_parts = []

    try:
        for cand in response.candidates or []:
            parts = getattr(cand.content, 'parts', []) or []
            for part in parts:
                fc = getattr(part, 'function_call', None)
                if fc and getattr(fc, 'name', None):
                    args = dict(fc.args) if fc.args else {}
                    tool_calls_made.append({"name": fc.name, "args": args})
                text = getattr(part, 'text', None)
                if text:
                    free_text_parts.append(text)
    except Exception as e:
        return {"error": f"Failed to parse Gemini response: {e}"}

    # Handle clarification requests
    for tc in tool_calls_made:
        if tc['name'] == 'ask_clarification':
            clarification = tc['args'].get('question', 'Could you clarify?')
            options = tc['args'].get('options')
            return {
                "tool_calls": [],
                "updated_routes": routes,
                "ai_message": clarification + (
                    "\n\nOptions: " + ", ".join(options) if options else ""
                ),
                "clarification": clarification,
                "needs_recalc": False,
            }

    # Apply mutations
    actionable = [tc for tc in tool_calls_made if tc['name'] in TOOL_HANDLERS]
    apply_results = []
    for tc in actionable:
        handler = TOOL_HANDLERS[tc['name']]
        result = handler(routes, tc['args'])
        apply_results.append({"name": tc['name'], "args": tc['args'], "result": result})

    if not actionable and not free_text_parts:
        return {
            "tool_calls": [],
            "updated_routes": routes,
            "ai_message": "I didn't understand that request. Could you rephrase?",
            "clarification": None,
            "needs_recalc": False,
        }

    # Build a default summary if model didn't produce free text
    if free_text_parts:
        ai_message = "\n".join(free_text_parts).strip()
    else:
        successes = [r['result']['summary'] for r in apply_results if r['result'].get('ok')]
        failures = [r['result']['error'] for r in apply_results if not r['result'].get('ok')]
        bits = []
        if successes:
            bits.append("Done: " + " | ".join(successes))
        if failures:
            bits.append("Issues: " + " | ".join(failures))
        ai_message = "\n".join(bits) if bits else "No changes applied."

    return {
        "tool_calls": apply_results,
        "updated_routes": routes,
        "ai_message": ai_message,
        "clarification": None,
        "needs_recalc": any(r['result'].get('ok') for r in apply_results),
    }
