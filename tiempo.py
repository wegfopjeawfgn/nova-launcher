"""Playtime per instance, kept in library.json under "playtime" (seconds)."""


def add(library, instance_id, seconds):
    seconds = int(seconds)
    if seconds < 1:
        return
    times = library.setdefault("playtime", {})
    times[instance_id] = int(times.get(instance_id, 0)) + seconds


def of(library, instance_id):
    return int(library.get("playtime", {}).get(instance_id, 0))


def total(library):
    return sum(int(value) for value in library.get("playtime", {}).values())


def short(seconds):
    minutes = int(seconds) // 60
    if minutes < 1:
        return "Sin jugar" if not seconds else "Menos de 1 min"
    hours, minutes = divmod(minutes, 60)
    return f"{hours} h {minutes:02d} min" if hours else f"{minutes} min"
