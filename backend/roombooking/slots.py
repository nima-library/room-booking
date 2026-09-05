from collections import defaultdict

from .firebase_config import db

# --- HELPERS FOR SYSTEM CLOSURES ---

ALL_TIMES = [
    "08:00 AM - 09:00 AM", "09:00 AM - 10:00 AM", "10:00 AM - 11:00 AM",
    "11:00 AM - 12:00 PM", "12:00 PM - 01:00 PM", "01:00 PM - 02:00 PM",
    "02:00 PM - 03:00 PM", "03:00 PM - 04:00 PM", "04:00 PM - 05:00 PM",
    "05:00 PM - 06:00 PM", "06:00 PM - 07:45 PM"
]


def get_slots_in_range(range_str):
    if " - " not in range_str:
        return []
    parts = range_str.split(" - ")
    if len(parts) != 2:
        return []
    range_start, range_end = parts[0].strip(), parts[1].strip()

    start_idx = -1
    end_idx = -1
    for i, slot in enumerate(ALL_TIMES):
        s_parts = slot.split(" - ")
        if s_parts[0].strip() == range_start:
            start_idx = i
        if s_parts[1].strip() == range_end:
            end_idx = i

    if start_idx != -1 and end_idx != -1 and start_idx <= end_idx:
        return ALL_TIMES[start_idx:end_idx + 1]
    return []


def merge_slots(slots_map):
    reason_to_slots = defaultdict(list)
    for slot, reason in slots_map.items():
        reason_to_slots[reason].append(slot)

    merged_results = []
    for reason, slots in reason_to_slots.items():
        indices = sorted([ALL_TIMES.index(s) for s in slots if s in ALL_TIMES])
        if not indices:
            continue

        runs = []
        current_run = [indices[0]]
        for idx in indices[1:]:
            if idx == current_run[-1] + 1:
                current_run.append(idx)
            else:
                runs.append(current_run)
                current_run = [idx]
        runs.append(current_run)

        for run in runs:
            start_slot = ALL_TIMES[run[0]]
            end_slot = ALL_TIMES[run[-1]]
            start_time = start_slot.split(" - ")[0]
            end_time = end_slot.split(" - ")[1]
            merged_results.append({
                "time_slot": f"{start_time} - {end_time}",
                "reason": reason
            })

    return merged_results


def is_slot_blocked(date, time_slot):
    block_doc = db.collection("blocked_days").document(date).get()
    if block_doc.exists:
        doc_data = block_doc.to_dict()
        if doc_data.get("type", "full") == "full":
            return True, doc_data.get("reason", "Library Closed")
        elif doc_data.get("type") == "hours":
            slots_data = doc_data.get("slots", {})
            if isinstance(slots_data, list):
                if time_slot in slots_data:
                    return True, doc_data.get("reason", "Library Closed")
            elif isinstance(slots_data, dict):
                if time_slot in slots_data:
                    return True, slots_data[time_slot]
    return False, None
