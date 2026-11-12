"""Human-readable download progress: size, speed and time left, with no GTK."""


def size_text(size):
    """Human size such as 1,8 GB or 640 KB."""
    for unit, divisor in (("GB", 1024**3), ("MB", 1024**2), ("KB", 1024)):
        if size >= divisor:
            return f"{size / divisor:.1f} {unit}".replace(".", ",")
    return f"{int(size)} B"


def duration_text(seconds):
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds} s"
    minutes, seconds = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes} min {seconds:02d} s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours} h {minutes:02d} min"


def describe(received, total, elapsed, *, resumed_from=0):
    """'12,4 MB de 40,2 MB · 3,1 MB/s · 9 s restantes'. Speed counts only bytes fetched in this run,
    and the time left is shown only when it can be computed."""
    parts = [f"{size_text(received)} de {size_text(total)}" if total else size_text(received)]
    fetched = received - resumed_from
    if elapsed >= 1 and fetched > 0:
        speed = fetched / elapsed
        parts.append(f"{size_text(speed)}/s")
        if total and total > received:
            parts.append(f"{duration_text((total - received) / speed)} restantes")
    return " · ".join(parts)
