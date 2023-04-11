import collections.abc, typing as t


def count(
    n: t.Union[collections.abc.Sized, int], singular: str, plural: t.Optional[str] = None
) -> str:
    if not isinstance(n, int):
        n = len(n)

    if plural is None:
        plural = singular + "s"

    return f"{n} {singular if n == 1 else plural}"
