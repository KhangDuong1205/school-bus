"""Read sg_osm/singapore_drive.graphml and report the distribution of
`maxspeed` per `highway` tag, so we know the real speed-limit data in
the graph (vs. the hand-picked SCHOOL_BUS_SPEED_KMH table)."""
import os
from collections import Counter, defaultdict
import osmnx as ox

GRAPHML_PATH = os.path.join(os.path.dirname(__file__), 'sg_osm', 'singapore_drive.graphml')


def _first(v):
    if isinstance(v, list):
        return v[0] if v else None
    return v


def _parse_maxspeed(v):
    """Return (km/h as float) or None. Handles 'NN', 'NN km/h', 'NN mph',
    lists, and 'signals'/'walk' strings."""
    v = _first(v)
    if v is None:
        return None
    s = str(v).strip().lower()
    if not s or s in ('none', 'signals', 'walk', 'variable'):
        return None
    is_mph = 'mph' in s
    digits = ''
    for ch in s:
        if ch.isdigit() or ch == '.':
            digits += ch
        elif digits:
            break
    if not digits:
        return None
    try:
        n = float(digits)
    except ValueError:
        return None
    return n * 1.60934 if is_mph else n


def main():
    print(f"Loading {GRAPHML_PATH} ...")
    g = ox.load_graphml(GRAPHML_PATH)
    print(f"{len(g.nodes)} nodes, {len(g.edges)} edges\n")

    by_class = defaultdict(list)
    missing = Counter()
    total = 0
    with_speed = 0

    for _u, _v, d in g.edges(data=True):
        total += 1
        hw = _first(d.get('highway')) or 'UNKNOWN'
        ms = _parse_maxspeed(d.get('maxspeed'))
        if ms is None:
            missing[hw] += 1
        else:
            with_speed += 1
            by_class[hw].append(ms)

    print(f"Edges with maxspeed: {with_speed}/{total} "
          f"({100*with_speed/total:.1f}%)\n")

    print(f"{'highway':<22}{'count':>8}{'min':>8}{'p25':>8}"
          f"{'median':>8}{'p75':>8}{'max':>8}{'mode':>10}")
    print('-' * 80)
    for hw in sorted(by_class.keys()):
        vals = sorted(by_class[hw])
        n = len(vals)
        mn = vals[0]
        mx = vals[-1]
        med = vals[n // 2]
        p25 = vals[n // 4]
        p75 = vals[(3 * n) // 4]
        mode = Counter(vals).most_common(1)[0]
        print(f"{hw:<22}{n:>8}{mn:>8.0f}{p25:>8.0f}"
              f"{med:>8.0f}{p75:>8.0f}{mx:>8.0f}"
              f"   {mode[0]:.0f} ({mode[1]})")

    print("\nEdges WITHOUT maxspeed, by highway class:")
    for hw, n in missing.most_common():
        print(f"  {hw:<22}{n:>8}")


if __name__ == '__main__':
    main()
