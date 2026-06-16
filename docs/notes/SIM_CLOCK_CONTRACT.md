# SimClock — an engine-agnostic sim-time contract for physics-stepped controllers

**Status:** DESIGN (2026-06-16). The sim-floor patch (cont.120, commit c7701b3e) stops the
composition bleeding; this is the proper core fix Anton called for: *"löses i kärnan, en lösning
så bra att den kan exporteras"* + *"kompatibelt med andra fysikmotorer, eller iaf ett mönster
som kan anpassas."*

## The problem (and why it GROWS with scene complexity)

Controllers that time themselves by **wall-clock** (`time.monotonic()`) break when the
per-physics-tick wall-clock duration varies. In a multi-cell composition the sibling cells'
concurrent cuRobo `plan_pose` calls stall the **single-threaded** Kit physics tick, so wall-clock
**races ahead of sim-time** → trajectory playback + grip gates fire while the arm is still
physically mid-descent → premature grip-close → grasp at the cube's top edge → drop. (Measured:
the 3-cell drop, cont.120 — inst2 CP-13 bottomed z=0.967, dwelled 0.2s sim, lifted without
gripping.)

This is not a one-off. It **scales with the scene**: more cells / objects / planners → more
per-tick wall-clock variance → the wall-clock/sim-time skew widens. Every wall-clock-timed
decision becomes less reliable as scenes grow.

**Scope in this controller:** `pick_place.py` has **22** `time.monotonic()` sites —
trajectory playback (`seg_start_t`/`elapsed`), pre-grip settle, post-grip dwell, the move-token
hold + stale-steal timeouts, the plan-token 5s stale-steal, belt resume timing. The sim-floor
patch protects only the 2 grip gates; the architecture needs the wall-clock dependency **removed**.

## The principle (well-trodden, not exotic)

**Control time ≠ wall time.** Control logic must advance with the **integrator** (simulation
time), never the host wall-clock. This is exactly the standard robotics pattern: ROS
`use_sim_time` + the `/clock` topic — the simulator publishes time; nodes read *sim*-time, not
system time. We are applying that battle-tested pattern to this controller.

## The contract (the exportable seam)

One method. The controller depends on **nothing else** for timing:

```
SimClock:
    now() -> float        # monotonic SIMULATION seconds; advances iff the integrator steps
    dt()  -> float        # (optional) last integrator step, for accumulators
```

`clock.now()` replaces every `time.monotonic()`. The clock is the **only** engine-specific piece.

## Implementations — the "adaptable to other engines" part

Each engine satisfies `now()` its own way; the controller is untouched across engines:

| Engine            | `now()` implementation                                              |
|-------------------|--------------------------------------------------------------------|
| **Isaac/Kit/PhysX** | `omni.timeline.get_timeline_interface().get_current_time()` or `SimulationContext.current_time` — read the engine's **native** authoritative clock (no accumulation needed). |
| **MuJoCo**        | `data.time`                                                        |
| **PyBullet**      | accumulate `stepSimulation` dt (`fixedTimeStep`)                   |
| **Newton / Warp** | accumulate the substep dt                                          |
| **Custom engine** | accumulate the integrator dt (the engine-agnostic fallback)       |

**`AccumulatorSimClock`** is the universal fallback: one authoritative subscription to the
engine's per-step hook does `t += dt`; all controllers **read** it (they never advance it
themselves — avoids N-fold over-counting with N controllers per tick). Any engine that exposes a
per-step dt is supported. Where the engine has a native clock query (Kit, MuJoCo) we prefer it —
zero accumulation, zero owner-bookkeeping.

## Why this is genuinely exportable / hot-swap-aligned

Porting the controller to a new physics backend = implement **one method**. That is the whole
point of the hot-swap doctrine (engine behind clean contracts; Anton's "build my own physics
engine someday" goal): **SimClock is part of the engine-runtime contract**, sitting alongside the
twin-contract from sibling-project The control logic becomes engine-agnostic and **deterministic**
(reproducible regardless of machine speed or scene load) — a property worth having on its own.

## The external half: ONE clock for ROS too (closes the loop)

ROS2 is a first-class surface of this project (Carter/Jetbot/Franka/G1/Go2 ROS2 OmniGraphs,
`setup_ros2_bridge`, `ros2_connect`, the PLC/`ros2_cmd` backend). So the sim-clock must not be a
private controller detail — it must be the **same** time the project already publishes to ROS via
the **`/clock`** topic. The canonical Isaac+ROS2 pattern *is* this design:

```
Isaac physics integrator
   └─ SimulationContext.current_time         ← THE single authoritative sim-time
        ├─ (internal) SimClock.now()         → every controller reads this
        └─ (external) ROS2 "Publish Clock" OmniGraph node → /clock topic
                                                → nav2 / MoveIt / PLC bridges run
                                                  use_sim_time:=true, read /clock
```

`SimClock.now()`'s Kit implementation (`SimulationContext.current_time`) is **byte-for-byte the
value the ROS2 `/clock` publisher emits**. So the internal controllers and the entire external ROS
ecosystem consume **one** clock — zero skew between the arm controller, the nav stack, MoveIt, and
the PLC/fieldbus bridges. That is exactly what ROS `use_sim_time` was designed to guarantee, and
it falls out for free once the controller stops reading wall-clock.

Caveat (already in the repo's deprecations): the ROS2 bridge needs `AMENT_PREFIX_PATH` in Kit's
process env — Isaac must be launched from a shell that sourced `/opt/ros/<distro>/setup.bash`. The
SimClock work doesn't change that; it just makes the internal side honor the same clock.

## Migration plan (this controller — deliberate, gated, measured)

1. **`_sim_now()` helper**: Kit-native (`SimulationContext.current_time` / timeline) with the
   dt-accumulator as fallback. Installed once (idempotent, `builtins`-guarded); owner re-assign on
   stage reset. **Probe first**: verify the native clock is queryable in the controller's
   `exec_sync`/RPC context (cf. the `SimulationContext._physics_context` caveat at pick_place.py:870)
   — fall back to the accumulator if not.
2. **Replace the 22 sites** with `_sim_now()`, by category: playback → settle/dwell → token
   timeouts → belt timing.
3. **Simplify the band-aids**: once playback is sim-time, the cont.120 sim-floor AND the
   move-token "fling-fix" (re-anchoring `seg_start_t` during holds) become **redundant** —
   sim-time playback cannot race. Remove them in the same pass.
4. **Roll out gated**: `_use_sim_clock` (default OFF first) → no-regression sweep on a
   representative sample of the stable 37+8 single-robot library + the composition golds → flip
   default ON. This touches the most-tested code; it is measured, not slammed in. Risk note: in
   headless fast-sim `wall-clock ≠ sim-time`, so single-robot motion *timing* changes (the
   trajectory `motion_time` is in sim-seconds — sim-time is the *correct* reference); verify the
   stable templates still deliver before flipping the default.

## Sequencing

sim-floor patch committed (composition unblocked). Full SimClock migration = next deliberate
refactor, after banking the current composition-verification wins (4-cell+ golds). Tracked as a
task. The pattern, once proven here, is documented for reuse in sibling-project / sibling-project /
any future custom-engine work.
