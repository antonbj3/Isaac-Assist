"""semantic_usd_diff — compare two USD stages by RESOLVED content [P2-01].

The toolify-migration verifier: byte-diffing USD text fails (the 200 hand-
rolled baselines differ in API ordering / attribute style / unicode escaping
— proven on P0-08), so migration safety needs SEMANTIC equivalence: same
prim graph, same types, same authored attribute VALUES (float tolerance),
regardless of authoring order or source formatting.

Verdicts: ``equivalent`` (migration is regression-safe by construction — no
gate run needed) vs ``divergent`` (a real content change → the function gate
must re-verify). This is the cheap static leg that makes mass-migration
auditable: byte-identical ⊂ semantically-equivalent ⊂ needs-physics.

Uses pxr (usd-core, available outside Kit). No Kit dependency.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from pxr import Usd  # usd-core; no Kit required

_FLOAT_TOL = 1e-6
# Generated/session attrs that are authoring noise, not scene content.
_SKIP_ATTRS = {"xformOpOrder"}  # order list compared via the ops themselves
# PhysX/controller WRITEBACK — authored by the engine during sim, never by
# scene authoring (CP-52 self-diff: these varied build-to-build). xformOps
# are NOT here: positions are load-bearing scene semantics.
_SKIP_ATTR_PREFIXES = ("state:", "physics:velocity", "physics:angularVelocity",
                       "ctrl:")


def _plain(value: Any) -> Any:
    """Normalize pxr value types to plain python for comparison."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    # Quats are NOT iterable — decompose to floats or they stringify and
    # the float tolerance never applies (live wave-1 finding: settled-cube
    # orientations diffed on 1e-7 noise as strings).
    if hasattr(value, "GetReal") and hasattr(value, "GetImaginary"):
        imag = value.GetImaginary()
        return [float(value.GetReal())] + [float(v) for v in imag]
    # Gf vectors/matrices + Vt arrays are iterable
    try:
        return [_plain(v) for v in value]
    except TypeError:
        return str(value)


def stage_signature(path: str) -> Dict[str, Dict[str, Any]]:
    """Open *path* and return {prim_path: {type, attrs{name: value},
    rels{name: [targets]}}} for every prim on the composed stage,
    capturing AUTHORED properties at the default timecode."""
    stage = Usd.Stage.Open(path)
    if stage is None:
        raise ValueError(f"cannot open USD stage: {path}")
    sig: Dict[str, Dict[str, Any]] = {}
    # TraverseInstanceProxies: default Traverse skips instanceable subtrees —
    # 330 of CP-17's 417 prims (robot link geometry, Looks, collision meshes)
    # were INVISIBLE to the diff (QA-audit agent 1, self-verified). A
    # candidate could swap a hand-geometry reference unseen without this.
    for prim in stage.Traverse(Usd.TraverseInstanceProxies()):
        # Kit session state, not authored scene: /Render holds viewport/
        # RTX settings that Kit lazily writes between builds (live CP-01
        # pilot: omni:rtx:* appeared in build B only); /Environment is
        # new_stage() default-light furniture that comes and goes between
        # session stages (wave-1 finding). Never scene-semantic.
        p = str(prim.GetPath())
        # path-BOUNDARY match: plain prefix would blind the diff to
        # legitimate prims like /RenderBox or /EnvironmentWall (QA-audit)
        if (p == "/Render" or p.startswith("/Render/")
                or p == "/Environment" or p.startswith("/Environment/")):
            continue
        attrs: Dict[str, Any] = {}
        rels: Dict[str, List[str]] = {}
        for prop in prim.GetAuthoredProperties():
            name = prop.GetName()
            if name in _SKIP_ATTRS or name.startswith(_SKIP_ATTR_PREFIXES):
                continue
            if isinstance(prop, Usd.Attribute):
                if prop.HasAuthoredValue():
                    attrs[name] = _plain(prop.Get())
            else:  # relationship
                rels[name] = sorted(str(t) for t in prop.GetTargets())
        sig[str(prim.GetPath())] = {
            "type": prim.GetTypeName(),
            "attrs": attrs,
            "rels": rels,
        }
    return sig


def _values_equal(a: Any, b: Any, tol: float) -> bool:
    # equality FIRST: inf - inf is nan (never <= tol), so identical
    # infinities read as a diff without this (live CP-01 pilot finding —
    # Franka link maxLinearVelocity=inf flagged on both sides)
    if isinstance(a, float) and isinstance(b, float):
        return a == b or abs(a - b) <= tol
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) \
            and not isinstance(a, bool) and not isinstance(b, bool):
        return a == b or abs(float(a) - float(b)) <= tol
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_values_equal(x, y, tol) for x, y in zip(a, b))
    return a == b


def diff_signatures(sig_a: Dict, sig_b: Dict,
                    float_tol: float = _FLOAT_TOL) -> Dict[str, Any]:
    """Compare two signatures. Returns {equivalent, missing_in_b, extra_in_b,
    type_diffs, attr_diffs} — every divergence names its prim/attr so the
    migration review is actionable."""
    missing = sorted(set(sig_a) - set(sig_b))
    extra = sorted(set(sig_b) - set(sig_a))
    type_diffs: List[Dict[str, str]] = []
    attr_diffs: List[Dict[str, Any]] = []

    for path in sorted(set(sig_a) & set(sig_b)):
        a, b = sig_a[path], sig_b[path]
        if a["type"] != b["type"]:
            type_diffs.append({"prim": path, "a": str(a["type"]), "b": str(b["type"])})
        for name in sorted(set(a["attrs"]) | set(b["attrs"])):
            if name not in a["attrs"]:
                attr_diffs.append({"prim": path, "attr": name, "a": None, "b": b["attrs"][name]})
            elif name not in b["attrs"]:
                attr_diffs.append({"prim": path, "attr": name, "a": a["attrs"][name], "b": None})
            elif not _values_equal(a["attrs"][name], b["attrs"][name], float_tol):
                attr_diffs.append({"prim": path, "attr": name,
                                   "a": a["attrs"][name], "b": b["attrs"][name]})
        if a["rels"] != b["rels"]:
            attr_diffs.append({"prim": path, "attr": "<relationships>",
                               "a": a["rels"], "b": b["rels"]})

    return {
        "equivalent": not (missing or extra or type_diffs or attr_diffs),
        "missing_in_b": missing,
        "extra_in_b": extra,
        "type_diffs": type_diffs,
        "attr_diffs": attr_diffs,
    }


def diff_stages(path_a: str, path_b: str, float_tol: float = _FLOAT_TOL) -> Dict[str, Any]:
    """Semantic diff of two USD files. ``equivalent=True`` ⇒ the migration
    that produced B from A is regression-safe by construction."""
    return diff_signatures(stage_signature(path_a), stage_signature(path_b),
                           float_tol=float_tol)
