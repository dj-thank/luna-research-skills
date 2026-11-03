"""Use the explicit with statement recommended by upstream PR123."""
def run(resource, source, consume, retained):
    with resource as handle:
        for item in source:
            consume(handle, item)
