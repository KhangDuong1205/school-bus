"""
AI-powered post-optimisation refiner.

Takes the OR-Tools result and asks Gemini to spot improvements the solver
missed — primarily merging underused buses or relocating outlier students.
Each suggestion is independently verified by re-running a fast in-process
recalculator on a copy of the routes; only suggestions that pass
deterministic constraint checks AND strictly improve the fleet are
returned to the UI. The model's predicted impact numbers are discarded —
only the recalculated values are shown to the user.
"""
import os
import json
import copy
from typing import List, Dict, Optional, Tuple

import google.generativeai as genai


# Free-tier Gemini quotas: pro/2.0 models return quota=0; only the 2.5 flash
# family is reachable on a free key. Upgrade to billing if you want pro.
GEMINI_MODEL = os.environ.get('GEMINI_REFINER_MODEL', 'gemini-2.5-flash')


SYSTEM_PROMPT = """You are an expert school bus fleet auditor. The user has just
finished a CVRP optimisation and wants you to spot improvements the solver
missed — particularly opportunities to remove buses entirely.

PRIMARY GOAL (in priority order):
1. Reduce total bus count.
2. Keep every hard constraint satisfied.

HARD CONSTRAINTS — a suggestion that violates ANY of these will be rejected:
- A bus's student count must not exceed its capacity.
- No student's ride duration may exceed max_ride_time_minutes.
- Special-needs students have a 30-minute ride cap.
- Siblings (students sharing the same non-empty family_code) MUST stay on the
  same bus. Never split them.
- No empty buses (a merge that leaves source empty is fine — the empty bus
  is removed).

REASONING APPROACH (think through these before proposing):
1. Find underused buses (utilization < ~60%) — these are the merge candidates.
2. For each pair of underused buses, ask: do they serve geographically nearby
   students? Compare lat/lng — buses serving the same neighbourhood are the
   best merge candidates.
3. Estimate the merged bus's worst-case ride time. If it could plausibly
   exceed max_ride_time_minutes, do NOT propose the merge.
4. Check the combined student count against the LARGER bus's capacity.
5. For "move_student" suggestions: only propose moving a student who is
   geographically closer to a different bus's pickup cluster than to their
   current bus. Don't propose moves that just shuffle students around.
6. Respect family_code groupings — if you propose moving a student, you must
   move ALL students sharing that family_code together.

OUTPUT FORMAT:
Return ONLY valid JSON, nothing else (no markdown fences, no commentary):
{
  "analysis": "1-2 sentences summarising what you observed about the fleet.",
  "suggestions": [
    {
      "type": "merge_buses",
      "narrative": "1-2 conversational sentences explaining the trade. Sound like a human fleet manager talking, not a log file. Acknowledge any downside honestly. Do not list percentages or exact distances — the system fills those in separately.",
      "details": {
        "from_bus": 12,
        "to_bus": 15
      }
    },
    {
      "type": "move_student",
      "narrative": "1-2 conversational sentences.",
      "details": {
        "student_ref": "R4S7",
        "from_bus": 4,
        "to_bus": 8
      }
    }
  ]
}

INDEXING: All bus numbers and student refs are 1-indexed. `student_ref`
"R4S7" means bus_number=4, the 7th student in that bus's list. Always
match the ref's bus number to `from_bus`.

NARRATIVE STYLE RULES:
- Conversational, not bulleted. No "Reasoning:" or "Impact:" labels.
- Acknowledge tradeoffs naturally ("yes the ride gets a bit longer, but...").
- Use approximate language ("around 40 minutes", "a handful of kids"). The
  system shows exact verified numbers separately.
- Reference what a fleet operator cares about: spare capacity, freeing buses,
  drivers' workload, kids' total time on the road.
- 1-2 sentences MAX per suggestion. Brevity reads as confidence.

PROPOSAL DISCIPLINE:
- Quality over quantity. Aim for 3-6 strong suggestions.
- If you cannot find anything that respects the hard constraints, return
  "suggestions": []. Do NOT pad with weak proposals.

LANGUAGE: All output in English regardless of input language.
"""


# ---------------------------------------------------------------------------
# Compact payload for the LLM
# ---------------------------------------------------------------------------

def _compact_state(routes: List[Dict],
                   max_ride_time: int,
                   default_capacity: int = 40) -> Dict:
    """Build the JSON payload sent to the LLM.

    Each student is given a `ref` of the form `R{bus_number}S{position}`
    using 1-indexed values so it matches the `bus_number` field shown
    elsewhere in the payload — keeps the LLM from confusing 0/1-indexing.
    Parsed back via _resolve_student_ref().
    """
    buses = []
    underused = 0

    for bi, route in enumerate(routes):
        students = route.get('students', [])
        capacity = (
            route.get('vehicle_capacity')
            or route.get('capacity')
            or default_capacity
        )
        count = len(students)
        utilization = round(count / capacity, 2) if capacity else 0
        if utilization < 0.6:
            underused += 1

        student_views = []
        max_ride = 0
        for si, s in enumerate(students):
            ride = float(s.get('ride_duration_minutes', 0) or 0)
            if ride > max_ride:
                max_ride = ride
            view = {
                "ref": f"R{bi+1}S{si+1}",
                "name": s.get('name', '') or '',
                "lat": round(float(s.get('latitude', 0) or 0), 5),
                "lng": round(float(s.get('longitude', 0) or 0), 5),
                "ride_min": round(ride, 1),
            }
            family = s.get('family_code')
            if family and str(family).strip():
                view['family_code'] = str(family).strip()
            if s.get('special_needs'):
                view['special_needs'] = True
            student_views.append(view)

        buses.append({
            "bus_number": bi + 1,
            "capacity": int(capacity),
            "student_count": count,
            "utilization": utilization,
            "time_minutes": round(float(route.get('time_minutes', 0) or 0), 1),
            "distance_km": round(float(route.get('distance_km', 0) or 0), 2),
            "max_student_ride_min": round(max_ride, 1),
            "students": student_views,
        })

    return {
        "objective": "minimize bus count while respecting all hard constraints",
        "constraints": {
            "max_ride_time_minutes": max_ride_time,
            "special_needs_cap_minutes": 30,
        },
        "fleet_summary": {
            "total_buses": len(routes),
            "total_students": sum(b['student_count'] for b in buses),
            "underused_buses_below_60pct": underused,
        },
        "buses": buses,
    }


# ---------------------------------------------------------------------------
# LLM provider calls
# ---------------------------------------------------------------------------

def _call_gemini(payload_json: str) -> str:
    """Call Gemini, return raw text response."""
    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured")

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(
        model_name=GEMINI_MODEL,
        system_instruction=SYSTEM_PROMPT,
        generation_config={
            "response_mime_type": "application/json",
            "temperature": 0.3,
        },
    )
    prompt = (
        f"Current fleet state:\n```json\n{payload_json}\n```\n\n"
        f"Audit the fleet and return suggestions."
    )
    response = model.generate_content(prompt)
    text = (response.text or '').strip()
    if not text:
        raise RuntimeError("Gemini returned empty response")
    return text


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _parse_response(raw: str) -> Dict:
    """Tolerate fenced/dirty JSON. Returns {analysis, suggestions}."""
    s = raw.strip()
    # Strip common code-fence wrappers if the model ignored response_format.
    if s.startswith('```'):
        first_nl = s.find('\n')
        if first_nl != -1:
            s = s[first_nl + 1:]
        if s.endswith('```'):
            s = s[:-3]
        s = s.strip()
    try:
        parsed = json.loads(s)
    except json.JSONDecodeError as e:
        # Try to find the outermost { ... } block.
        start = s.find('{')
        end = s.rfind('}')
        if start != -1 and end > start:
            try:
                parsed = json.loads(s[start:end + 1])
            except json.JSONDecodeError:
                raise RuntimeError(f"AI response is not valid JSON: {e}")
        else:
            raise RuntimeError(f"AI response is not valid JSON: {e}")

    suggestions = parsed.get('suggestions') or []
    if not isinstance(suggestions, list):
        raise RuntimeError("AI 'suggestions' field is not a list")
    return {
        "analysis": str(parsed.get('analysis', '')).strip(),
        "suggestions": suggestions,
    }


# ---------------------------------------------------------------------------
# Suggestion application + verification
# ---------------------------------------------------------------------------

def _resolve_student_ref(ref: str) -> Optional[Tuple[int, int]]:
    """Parse 'R<bus_number>S<position>' (both 1-indexed) into 0-indexed
    (bus_index, student_index). Returns None on bad format."""
    if not isinstance(ref, str) or not ref.startswith('R'):
        return None
    try:
        rest = ref[1:]
        bi_str, si_str = rest.split('S', 1)
        bi = int(bi_str) - 1
        si = int(si_str) - 1
        if bi < 0 or si < 0:
            return None
        return bi, si
    except (ValueError, IndexError):
        return None


def _apply_to_routes(routes: List[Dict], suggestion: Dict) -> Optional[List[Dict]]:
    """Apply a single suggestion to a deep copy of routes. Return None if
    the suggestion is structurally invalid (out of range, bad refs)."""
    new_routes = copy.deepcopy(routes)
    stype = suggestion.get('type')
    details = suggestion.get('details') or {}

    if stype == 'merge_buses':
        from_bus = details.get('from_bus')
        to_bus = details.get('to_bus')
        try:
            fi = int(from_bus) - 1
            ti = int(to_bus) - 1
        except (TypeError, ValueError):
            return None
        if fi == ti or not (0 <= fi < len(new_routes)) or not (0 <= ti < len(new_routes)):
            return None
        new_routes[ti].setdefault('students', []).extend(
            new_routes[fi].get('students', [])
        )
        new_routes.pop(fi)
        return new_routes

    if stype == 'move_student':
        ref = details.get('student_ref')
        target = details.get('to_bus')
        parsed = _resolve_student_ref(ref)
        if not parsed:
            return None
        bi, si = parsed
        try:
            ti = int(target) - 1
        except (TypeError, ValueError):
            return None
        if not (0 <= bi < len(new_routes)) or not (0 <= ti < len(new_routes)):
            return None
        if bi == ti:
            return None
        students = new_routes[bi].setdefault('students', [])
        if not (0 <= si < len(students)):
            return None
        student = students.pop(si)

        # Family glue: if the student belongs to a family, drag the rest of
        # the family with them. Move from highest index down so popping
        # doesn't shift the indices we still need.
        family_code = student.get('family_code')
        family_movers = [student]
        if family_code and str(family_code).strip():
            fc = str(family_code).strip()
            same_family_idx = [
                idx for idx, s in enumerate(students)
                if str(s.get('family_code', '')).strip() == fc
            ]
            for idx in sorted(same_family_idx, reverse=True):
                family_movers.append(students.pop(idx))

        if not students:
            # Source bus emptied — drop it. Adjust ti if it was after bi.
            new_routes.pop(bi)
            if ti > bi:
                ti -= 1

        new_routes[ti].setdefault('students', []).extend(family_movers)
        return new_routes

    return None


def _check_hard_constraints(routes: List[Dict],
                            max_ride_time: int,
                            default_capacity: int = 40) -> List[str]:
    """Return list of hard-constraint violations after recalc. Empty = pass."""
    issues = []
    for bi, r in enumerate(routes, start=1):
        students = r.get('students', [])
        if not students:
            issues.append(f"Bus {bi} is empty after change")
            continue
        cap = r.get('vehicle_capacity') or r.get('capacity') or default_capacity
        if len(students) > cap:
            issues.append(f"Bus {bi} over capacity ({len(students)}/{cap})")
        # Per-student ride checks
        for s in students:
            ride = float(s.get('ride_duration_minutes', 0) or 0)
            limit = 30 if s.get('special_needs') else max_ride_time
            if ride > limit + 0.05:  # tiny tolerance for rounding
                issues.append(
                    f"Bus {bi}: {s.get('name','student')} ride "
                    f"{ride:.1f} min exceeds {limit} min cap"
                )
        # Sibling integrity check — every family_code must be entirely on
        # this bus or entirely elsewhere
    # Cross-bus sibling check
    family_buses = {}
    for bi, r in enumerate(routes, start=1):
        for s in r.get('students', []):
            fc = s.get('family_code')
            if fc and str(fc).strip():
                family_buses.setdefault(str(fc).strip(), set()).add(bi)
    for fc, bus_set in family_buses.items():
        if len(bus_set) > 1:
            issues.append(f"Family '{fc}' split across buses {sorted(bus_set)}")
    return issues


def _summarise_routes(routes: List[Dict]) -> Dict:
    """Snapshot used for delta computation."""
    total_km = 0.0
    max_ride = 0.0
    for r in routes:
        total_km += float(r.get('distance_km', 0) or 0)
        for s in r.get('students', []):
            ride = float(s.get('ride_duration_minutes', 0) or 0)
            if ride > max_ride:
                max_ride = ride
    return {
        "bus_count": len(routes),
        "total_km": round(total_km, 2),
        "max_ride_min": round(max_ride, 1),
    }


def _verify_one(suggestion: Dict,
                base_routes: List[Dict],
                school: Dict,
                api_key: str,
                school_arrival_seconds: int,
                max_ride_time: int,
                service_time: int,
                base_summary: Dict) -> Optional[Dict]:
    """Apply, recalc, check. Returns enriched suggestion or None if rejected.

    Uses the fast verification recalc that skips per-segment polyline
    fetching — verification only needs total times/distances and per-student
    ride times, which come straight from the cached igraph matrices. The full
    polyline-fetching recalc (~30-90s for 41 buses) only runs in
    apply_suggestion when the user actually accepts a change."""
    from route_optimizer import recalculate_routes_for_verification

    candidate = _apply_to_routes(base_routes, suggestion)
    if candidate is None:
        return None

    # Drop empty buses defensively
    candidate = [r for r in candidate if r.get('students')]
    if not candidate:
        return None

    try:
        recalculated = recalculate_routes_for_verification(
            candidate, school,
            school_arrival_seconds, max_ride_time,
            service_time=service_time
        )
    except Exception as e:
        return {
            "_rejected": True,
            "_reject_reason": f"Recalculation crashed: {e}",
            **suggestion,
        }

    issues = _check_hard_constraints(recalculated, max_ride_time)
    if issues:
        return {
            "_rejected": True,
            "_reject_reason": "; ".join(issues[:3]),
            **suggestion,
        }

    new_summary = _summarise_routes(recalculated)
    deltas = {
        "bus_count": new_summary['bus_count'] - base_summary['bus_count'],
        "total_km": round(new_summary['total_km'] - base_summary['total_km'], 2),
        "max_ride_min": round(new_summary['max_ride_min'] - base_summary['max_ride_min'], 1),
    }

    return {
        "type": suggestion.get('type'),
        "narrative": str(suggestion.get('narrative', '')).strip(),
        "details": suggestion.get('details') or {},
        "verified": {
            "before": base_summary,
            "after": new_summary,
            "delta": deltas,
        },
        "_routes_after": recalculated,
    }


# ---------------------------------------------------------------------------
# Top-level entry point
# ---------------------------------------------------------------------------

def refine_routes(routes: List[Dict],
                  school: Dict,
                  api_key: str,
                  school_arrival_seconds: int,
                  max_ride_time: int,
                  service_time: int) -> Dict:
    """
    Returns:
      {
        "analysis": "...",
        "suggestions": [verified suggestion, ...],
        "rejected_count": N,
        "model": "<model name>",
      }
    """
    import time as _t
    payload = _compact_state(routes, max_ride_time)
    payload_json = json.dumps(payload, ensure_ascii=False)
    print(f"[refine] payload size: {len(payload_json)/1024:.1f} KB", flush=True)

    _llm_start = _t.time()
    raw = _call_gemini(payload_json)
    model_used = GEMINI_MODEL
    print(f"[refine] LLM ({model_used}) responded in {_t.time()-_llm_start:.1f}s, "
          f"raw response: {len(raw)/1024:.1f} KB", flush=True)

    parsed = _parse_response(raw)

    base_summary = _summarise_routes(routes)
    verified = []
    rejected = 0

    # Cap: even if the model returns 10 ideas, we only verify a bounded
    # number. Each verification builds matrices and computes 2-opt across
    # all buses — wallclock is ~2-5s per suggestion, so 8 is a comfortable
    # ceiling that keeps total verification under ~40s.
    MAX_VERIFY = 8
    suggestions_to_check = parsed['suggestions'][:MAX_VERIFY]
    skipped_for_cap = max(0, len(parsed['suggestions']) - MAX_VERIFY)

    # Time budget: stop verifying once we've spent this long, return what
    # we have. The user has been waiting on the LLM already.
    import time
    VERIFY_BUDGET_S = 60
    start = time.time()

    print(f"[refine] LLM returned {len(parsed['suggestions'])} suggestions, "
          f"verifying up to {len(suggestions_to_check)} (budget {VERIFY_BUDGET_S}s)",
          flush=True)

    for idx, sug in enumerate(suggestions_to_check):
        elapsed = time.time() - start
        if elapsed > VERIFY_BUDGET_S:
            print(f"[refine] verification budget exceeded at suggestion {idx+1}, "
                  f"stopping. Verified={len(verified)} rejected={rejected}",
                  flush=True)
            break
        t0 = time.time()
        print(f"[refine] verifying {idx+1}/{len(suggestions_to_check)} "
              f"(type={sug.get('type')})...", flush=True)
        result = _verify_one(
            sug, routes, school, api_key,
            school_arrival_seconds, max_ride_time, service_time,
            base_summary
        )
        dt = time.time() - t0
        if result is None:
            rejected += 1
            print(f"[refine]   skipped (invalid structure) in {dt:.1f}s", flush=True)
            continue
        if result.get('_rejected'):
            rejected += 1
            print(f"[refine]   rejected: {result.get('_reject_reason')} ({dt:.1f}s)", flush=True)
            continue
        delta = result['verified']['delta']
        if delta['bus_count'] > 0:
            rejected += 1
            print(f"[refine]   rejected: increases bus count ({dt:.1f}s)", flush=True)
            continue
        if delta['bus_count'] == 0 and delta['total_km'] >= 0 and delta['max_ride_min'] >= 0:
            rejected += 1
            print(f"[refine]   rejected: no improvement on any axis ({dt:.1f}s)", flush=True)
            continue
        verified.append(result)
        print(f"[refine]   ACCEPTED Δbus={delta['bus_count']} Δkm={delta['total_km']} "
              f"Δride={delta['max_ride_min']} ({dt:.1f}s)", flush=True)

    print(f"[refine] done. verified={len(verified)} rejected={rejected} "
          f"skipped_for_cap={skipped_for_cap} elapsed={time.time()-start:.1f}s",
          flush=True)

    return {
        "analysis": parsed['analysis'],
        "suggestions": verified,
        "rejected_count": rejected + skipped_for_cap,
        "model": model_used,
    }


def apply_suggestion(routes: List[Dict],
                     suggestion: Dict,
                     school: Dict,
                     api_key: str,
                     school_arrival_seconds: int,
                     max_ride_time: int,
                     service_time: int) -> Dict:
    """
    Apply a single suggestion (already-verified) to routes and return the
    fully-recalculated route list. Re-verifies before applying because the
    routes may have changed since the suggestion was generated.
    """
    from route_optimizer import recalculate_manually_adjusted_routes

    candidate = _apply_to_routes(routes, suggestion)
    if candidate is None:
        return {"error": "Suggestion is no longer valid (route state changed)"}

    candidate = [r for r in candidate if r.get('students')]
    if not candidate:
        return {"error": "Applying this suggestion would leave no routes"}

    try:
        recalculated = recalculate_manually_adjusted_routes(
            candidate, school, api_key,
            school_arrival_seconds, max_ride_time,
            service_time=service_time
        )
    except Exception as e:
        return {"error": f"Recalculation failed: {e}"}

    issues = _check_hard_constraints(recalculated, max_ride_time)
    if issues:
        return {
            "error": f"Suggestion no longer feasible: {'; '.join(issues[:2])}"
        }

    return {"routes": recalculated}
