from minecraft.types import varint


def from_stream(stream):
    length, stop = varint.from_stream(stream)
    return "".join(stream[stop: stop + length]), stop + length


def to_stream(value):
    return varint.to_stream(len(value)) + value
