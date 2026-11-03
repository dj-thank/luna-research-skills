"""Historical documented context() call site; retain the iterator until readback."""
import more_itertools

def run(resource, source, consume, retained):
    managed = more_itertools.context(resource)
    retained.append(managed)
    for handle in managed:
        for item in source:
            consume(handle, item)
