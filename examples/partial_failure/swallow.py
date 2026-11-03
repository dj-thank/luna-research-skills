"""Rejected control: closes the resource but hides the terminal exception."""
def run(resource, source, consume, retained):
    try:
        with resource as handle:
            for item in source:
                consume(handle, item)
    except Exception:
        pass
